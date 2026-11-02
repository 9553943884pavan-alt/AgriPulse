"""E1  POST /api/agent/chat  (Server-Sent Events)

SSE event order for a full plan:
  thread → profile → trace… → plan → message → done

The LangGraph graph lives in app/agent/graph.py.
This router is the thin HTTP adapter: it converts the request body into the
initial graph state, streams LangGraph events as SSE, and maps node outputs
to the SSE schema defined in backend/SPECS.md §5.2 E1.

Single-path rule: the graph nodes call app/services/ and app/ml/ functions —
the exact same functions used by /api/plan (E2). E1 and E2 always produce
identical plans for the same profile.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import logging
import re
import time
import uuid

from fastapi import APIRouter, Request
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.agent.memory import cap_messages
from app.agent.nodes import SEED_BASIS, compute_missing
from app.core.errors import AppError
from app.schemas import FarmProfile, PlanResult

logger = logging.getLogger(__name__)
router = APIRouter()


THREAD_ID_RE = re.compile(r"^th_[0-9a-f]{32}$")
MAX_MESSAGE_CHARS = 2000
RECURSION_LIMIT = 40          # LangGraph step cap: a bug can never loop forever
_LANGUAGES = ("mr", "hi", "en")
# Keys a client may send in profile_patch / profile: FarmProfile fields the farmer controls.
_PROFILE_KEYS = frozenset(FarmProfile.model_fields) - {"missing", "defaults_used"}
_VALIDATION_BASE = {"location_text": "x", "land_acres": 1.0, "budget_rs": 1.0}
_PLACEHOLDER_LOCATIONS = {"", "unknown", "none", "null", "undefined", "n/a", "na", "-"}


def _invalid(*fields: str) -> AppError:
    return AppError("VALIDATION_ERROR", {"fields": sorted(set(fields))})


def _validate_chat_body(body: dict) -> dict:
    """Check the request and return the clean values. Raises AppError (HTTP 422)."""
    bad: list[str] = []

    thread_id = body.get("thread_id")
    if thread_id in (None, ""):
        thread_id = None
    elif not isinstance(thread_id, str) or not THREAD_ID_RE.match(thread_id):
        bad.append("thread_id")

    language = body.get("language")
    language = language if isinstance(language, str) and language in _LANGUAGES else "en"

    patch_raw = body.get("profile_patch")
    patch: dict | None = None
    if patch_raw:
        if not isinstance(patch_raw, dict) or set(patch_raw) - _PROFILE_KEYS:
            bad.append("profile_patch")
        else:
            try:
                checked = FarmProfile.model_validate({**_VALIDATION_BASE, **patch_raw})
                patch = {key: getattr(checked, key) for key in patch_raw}
            except ValidationError:
                bad.append("profile_patch")

    message = body.get("message")
    if message is None:
        message = ""
    if not isinstance(message, str):
        bad.append("message")
        message = ""
    else:
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            bad.append("message")
        elif not message and patch is None:
            bad.append("message")

    if bad:
        raise _invalid(*bad)
    return {
        "thread_id": thread_id,
        "language": language,
        "message": message,
        "profile_patch": patch,
        "seed_profile": seed_profile_from_body(body.get("profile"), language),
    }


def seed_profile_from_body(raw, language: str = "en") -> FarmProfile | None:
    """A client-supplied saved Farm Profile, used only as a starting point.

    Unusable values (placeholder / empty location, land or budget <= 0, bad types) are
    dropped and stay "missing", so the agent asks for them. Returns None when nothing
    required (location, land, budget) is usable. Seeded fields are recorded in
    defaults_used so the UI can say where they came from."""
    if not isinstance(raw, dict):
        return None
    good: dict = {}
    for key, value in raw.items():
        if key not in _PROFILE_KEYS or value is None:
            continue
        if key == "location_text":
            if not isinstance(value, str) or value.strip().lower() in _PLACEHOLDER_LOCATIONS:
                continue
            value = value.strip()
        elif key in ("land_acres", "budget_rs"):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if not number > 0 or number == float("inf"):
                continue
            value = number
        try:
            FarmProfile.model_validate({**_VALIDATION_BASE, key: value})
        except ValidationError:
            continue
        good[key] = value
    if not any(k in good for k in ("location_text", "land_acres", "budget_rs")):
        return None
    data = {"location_text": "unknown", "land_acres": 0.0, "budget_rs": 0.0, **good}
    data.setdefault("language", language)
    data["missing"] = compute_missing(data)
    data["defaults_used"] = [
        {"field": k, "value": v if isinstance(v, (str, int, float)) and not isinstance(v, bool) else str(v),
         "basis": SEED_BASIS}
        for k, v in good.items() if k != "language"
    ]
    try:
        from app.services.water import normalise_borewell

        return normalise_borewell(FarmProfile.model_validate(data))
    except ValidationError:
        return None


def _is_complete_profile(profile) -> bool:
    return profile is not None and not compute_missing(profile.model_dump())


async def restore_thread_state(cache, thread_id: str) -> tuple[list, dict]:
    """Stored memory of ONE thread -> (chat messages, graph state keys).

    The graph checkpointer is in-process only, so after a restart the stored profile and
    plan (same CropOption/Strategy types) rebuild everything plan Q&A needs. Only this
    thread's rows are read; nothing is shared between threads."""
    prior = await cache.get_memory(thread_id, "messages")
    messages = cap_messages(prior) if isinstance(prior, list) else []
    state: dict = {}
    cached_profile = await cache.get_memory(thread_id, "profile")
    if isinstance(cached_profile, dict):
        try:
            state["profile"] = FarmProfile.model_validate(cached_profile)
        except ValidationError:
            logger.warning("Stored profile for thread %s is invalid; ignoring it", thread_id)
    cached_plan = await cache.get_memory(thread_id, "plan")
    if isinstance(cached_plan, dict):
        try:
            plan = PlanResult.model_validate(cached_plan)
        except ValidationError:
            logger.warning("Stored plan for thread %s is invalid; ignoring it", thread_id)
        else:
            state.update(
                plan_result=plan, strategies=plan.strategies, crops=plan.crops,
                excluded=plan.excluded_crops, water=plan.water, scenarios=plan.scenarios,
                location=plan.location, season=plan.season, impact=plan.impact,
            )
    return messages, state


def fresh_turn_state(thread_id: str, message: str, language: str, profile_patch: dict | None) -> dict:
    """Every per-turn key starts clean, so nothing from the previous turn leaks into this one.
    (profile, asked_fields and pending_field are deliberately NOT here: they carry over.)"""
    return {
        "thread_id": thread_id,
        "message": message,
        "language": language,
        "profile_patch": profile_patch,
        "route": "new_plan",   # overwritten by route_node
        "plan_only": False,
        "missing": [],
        "optional_ask": None,
        "question": None,
        "location": None,
        "season": None,
        "weather": {},
        "soil": {},
        "prices": {},
        "costs": {},
        "scenarios": [],
        "water": [],
        "candidates": [],
        "crops": [],
        "excluded": [],
        "scenario_yields": {},
        "long_duration_crops": set(),
        "impact": None,
        "opt_warnings": [],
        "strategies": [],
        "feasibility": None,
        "relaxations": [],
        "relaxation_count": 0,
        "explanation_text": "",
        "explanation_grounded": False,
        "explanation_provider": "template",
        "grounding_retry_count": 0,
        "water_saved_pct": 0.0,
        "shap_factors": [],
        "long_crop_facts": [],
        "plan_result": None,
        "reply": None,
        "trace": [],
        "messages": [],
        "no_data": False,
    }


@router.post("/agent/chat")
async def agent_chat(request: Request, body: dict):
    """E1 — One conversation turn, streamed as SSE.

    Request body:
      thread_id?      omit on first turn; response creates one (th_ + 32 hex)
      message         farmer's text or transcription (1-2000 chars)
      language?       mr | hi | en  (default: en)
      profile_patch?  partial FarmProfile override (card edit, no message needed)
      profile?        saved Farm Profile; seeds a thread that has no stored profile
    """
    req = _validate_chat_body(body)
    # Thread IDs are bearer-style secrets until user authentication is added.
    # Do not truncate UUID entropy: a 32-bit ID can be enumerated in a public API.
    thread_id = req["thread_id"] or f"th_{uuid.uuid4().hex}"
    language = req["language"]
    message = req["message"]
    seed_profile = req["seed_profile"]

    # Get compiled graph from app state (initialised in lifespan)
    graph = getattr(request.app.state, "agent_graph", None)

    initial_state: dict = fresh_turn_state(thread_id, message, language, req["profile_patch"])
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    ctx = TraceContext()

    async def _persist(event: dict, cache, messages: list) -> bool:
        """Save profile / plan / chat messages so GET /api/threads/{id} and
        POST /api/plans/{id}/reoptimize work for agent-created plans.
        Returns False when the event could not be stored."""
        try:
            name = event.get("event")
            if name == "profile":
                profile_data = json.loads(event["data"])
                # Do not replace a durable, complete profile with the temporary
                # placeholder emitted while the agent is asking for a missing
                # field after a restart.
                if (
                    not profile_data.get("missing")
                    and profile_data.get("location_text") not in (None, "", "unknown")
                    and float(profile_data.get("land_acres") or 0) > 0
                    and float(profile_data.get("budget_rs") or 0) > 0
                ):
                    await cache.set_memory(thread_id, "profile", profile_data)
            elif name == "plan":
                plan_data = json.loads(event["data"])
                await cache.set_plan(plan_data["plan_id"], plan_data)
                await cache.set_memory(thread_id, "plan", plan_data)
            elif name in ("message", "question"):
                payload = json.loads(event["data"])
                messages.append({
                    "role": "agent",
                    "text": payload.get("text", ""),
                    "language": payload.get("language", language),
                    "at": datetime.now(tz=timezone.utc).isoformat(),
                })
                messages[:] = cap_messages(messages)
                await cache.set_memory(thread_id, "messages", messages)
            return True
        except Exception:
            logger.warning("Could not persist agent event %s", event.get("event"), exc_info=True)
            return False

    async def _stream():
        started = time.perf_counter()
        try:
            from app.core.cache import get_cache

            cache, messages = None, []
            try:
                cache = await get_cache()
                # The graph checkpointer is intentionally in-process. Restore
                # durable profile/plan state from the application cache so a
                # backend restart does not make a continuing conversation lose
                # its farm memory.
                messages, restored = await restore_thread_state(cache, thread_id)
                initial_state.update(restored)
            except Exception:
                logger.warning(
                    "Agent cache unavailable, continuing without persistence (thread=%s)",
                    thread_id, exc_info=True,
                )
                cache, messages = None, []
            if "profile" not in initial_state and seed_profile is not None:
                # The server's stored profile always wins; a client profile only seeds a
                # thread that has none. A complete one is saved so a refresh keeps it.
                initial_state["profile"] = seed_profile
                if cache is not None and _is_complete_profile(seed_profile):
                    try:
                        await cache.set_memory(thread_id, "profile", seed_profile.model_dump(mode="json"))
                    except Exception:
                        logger.warning("Could not store seeded profile (thread=%s)", thread_id, exc_info=True)
            if message:
                messages.append({
                    "role": "farmer",
                    "text": message,
                    "language": language,
                    "at": datetime.now(tz=timezone.utc).isoformat(),
                })
                messages[:] = cap_messages(messages)
            async for ev in _stream_events():
                if ev.get("event") == "plan":
                    t_save = datetime.now(tz=timezone.utc)
                    saved = cache is not None and await _persist(ev, cache, messages)
                    yield ctx.api_trace(
                        "persist", "saved" if saved else "failed", "ok" if saved else "failed",
                        "Plan saved to this conversation" if saved
                        else "Plan could not be saved; it may not survive a refresh",
                        started=t_save,
                    )
                elif cache is not None:
                    await _persist(ev, cache, messages)
                yield ev
        except Exception as exc:  # last line of defence: never a bare 5xx
            logger.exception("Agent chat failed outside the graph (thread=%s)", thread_id)
            yield _error_event(exc, language)
        yield {"event": "done", "data": json.dumps({"ms": int((time.perf_counter() - started) * 1000)})}

    async def _stream_events():
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}

        try:
            if graph is None:
                # Graph not initialised (startup failed or test mode): a real error event.
                async for item in _stub_stream(initial_state, language):
                    yield item
            else:
                async for event in graph.astream_events(
                    initial_state,
                    config=config,
                    version="v1",   # LangGraph 0.2 default — NOT "v2"
                ):
                    sse_events = _lg_event_to_sse(event, ctx)
                    if isinstance(sse_events, list):
                        for sse in sse_events:
                            yield sse
                    elif sse_events:
                        yield sse_events

        except Exception as exc:
            logger.exception("Agent stream error (thread=%s)", thread_id)
            if ctx.tools_started:
                yield ctx.api_trace("plan", "failed", "failed", "Planning stopped before it finished")
            yield _error_event(exc, language)

    return EventSourceResponse(_stream(), ping=10)


def _error_event(exc: Exception, language: str) -> dict:
    """Turn any exception into a structured SSE 'error' event (ApiError shape)."""
    if not isinstance(exc, AppError):
        # Exception text can contain provider URLs, request data, or credentials.
        # It is logged by the caller; clients receive only the stable public error.
        exc = AppError("INTERNAL", {"exception": type(exc).__name__}, message="Internal server error")
    return {"event": "error", "data": json.dumps(exc.to_response().model_dump())}


# ── LangGraph event → SSE mapper ─────────────────────────────────────────────

# Graph nodes whose state patch can carry new trace items.
_TRACE_NODES = frozenset({
    "extract_profile", "merge_patch", "ask_missing", "gather_data", "recommend_crops",
    "predict_yield", "optimize", "check_feasibility", "relax_constraint", "explain",
    "grounding_check", "answer_from_memory", "smalltalk", "respond",
})


class TraceContext:
    """Per-request trace bookkeeping: one run_id, a running sequence number, and the
    ids already streamed (a node's patch carries the whole trace list so far)."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.sequence = 0
        self.seen: set[str] = set()
        self.tools_started = False

    def _stamp(self, item) -> dict:
        from app.schemas import TraceEvent

        if not isinstance(item, TraceEvent):
            item = TraceEvent.model_validate(item)
        self.sequence += 1
        if item.node == "plan" and item.step == "started":
            self.tools_started = True
        item = item.model_copy(update={"run_id": self.run_id, "sequence": self.sequence})
        return {"event": "trace", "data": item.model_dump_json()}

    def new_traces(self, trace_list) -> list[dict]:
        """SSE trace events for items not streamed yet, in the order the nodes made them."""
        out: list[dict] = []
        for item in trace_list or []:
            item_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            if item_id in self.seen:
                continue
            self.seen.add(item_id)
            out.append(self._stamp(item))
        return out

    def api_trace(self, node: str, step: str, status: str, summary: str, started=None) -> dict:
        """A trace item for something the API layer itself did (saving the plan)."""
        from app.agent.nodes import _trace

        item = _trace(node, step, status, summary, started=started)
        self.seen.add(item.id)
        return self._stamp(item)


def _lg_event_to_sse(event: dict, ctx: TraceContext | None = None) -> dict | list[dict] | None:
    """Map a LangGraph astream_events dict to an SSE payload.

    LangGraph v1 event structure:
      {"event": "on_chain_end", "name": "<node_name>", "data": {"output": <state_patch>}}

    SSE events the frontend expects (SPECS §5.2 E1):
      profile   — after extract_profile or merge_patch
      trace     — every new trace item a node produced, in order
      question  — after ask_missing_node fires
      plan      — after respond_node builds a PlanResult
      message   — the agent's text: with the plan, or alone for a question / small talk
    """
    kind = event.get("event", "")
    name = event.get("name", "")
    output = event.get("data", {}).get("output", {}) or {}

    if kind != "on_chain_end" or not isinstance(output, dict):
        return None
    ctx = ctx or TraceContext()
    events: list[dict] = []

    # profile event — after extract_profile or merge_patch
    if name in ("extract_profile", "merge_patch"):
        profile = output.get("profile")
        if profile:
            data = profile.model_dump_json() if hasattr(profile, "model_dump_json") else json.dumps(profile)
            events.append({"event": "profile", "data": data})

    # trace events: everything new that this node recorded
    if name in _TRACE_NODES:
        events.extend(ctx.new_traces(output.get("trace")))

    # question event — after ask_missing
    if name == "ask_missing":
        question = output.get("question")
        if question:
            events.append({"event": "question", "data": json.dumps(question)})

    # plan + message events — after respond
    if name == "respond":
        plan_result = output.get("plan_result")
        reply = output.get("reply")
        if plan_result:
            plan_json = plan_result.model_dump_json() if hasattr(plan_result, "model_dump_json") else json.dumps(plan_result)
            if hasattr(plan_result, "model_dump"):
                plan_data = plan_result.model_dump(mode="json")
            else:
                plan_data = plan_result
            explanation = plan_data.get("explanation", {})
            message = {
                "text": explanation.get("text", ""),
                "language": explanation.get("language", "en"),
                "provider": explanation.get("provider", "template"),
            }
            events.append({"event": "plan", "data": plan_json})
            events.append({"event": "message", "data": json.dumps(message)})
        elif isinstance(reply, dict) and reply.get("text"):
            # A question or small talk: the answer only, never a new plan version.
            events.append({"event": "message", "data": json.dumps(reply)})

    if not events:
        return None
    return events[0] if len(events) == 1 else events


# ── Fallback stub stream (when graph is not initialised) ──────────────────────

async def _stub_stream(state: dict, language: str):
    """Used only when the LangGraph agent failed to start. A real error event (never a
    normal-looking message), and it never invents a farm profile."""
    yield _error_event(
        AppError(
            "UPSTREAM_UNAVAILABLE",
            {"component": "agent"},
            message="The assistant is not available right now.",
            user_message={
                "mr": "सहाय्यक सध्या उपलब्ध नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
                "hi": "सहायक अभी उपलब्ध नहीं है। कृपया कुछ देर बाद पुनः प्रयास करें।",
                "en": "The assistant is not available right now. Please try again shortly.",
            },
        ),
        language,
    )
