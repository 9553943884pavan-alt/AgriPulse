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
import time
import uuid

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.core.errors import AppError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/agent/chat")
async def agent_chat(request: Request, body: dict):
    """E1 — One conversation turn, streamed as SSE.

    Request body:
      thread_id?      omit on first turn; response creates one
      message         farmer's text or transcription
      language?       mr | hi | en  (default: mr)
      profile_patch?  partial FarmProfile override (card edit, no message needed)
      district?       pre-fill district if known
    """
    # Thread IDs are bearer-style secrets until user authentication is added.
    # Do not truncate UUID entropy: a 32-bit ID can be enumerated in a public API.
    thread_id = body.get("thread_id") or f"th_{uuid.uuid4().hex}"
    language = body.get("language", "mr")
    if language not in ("mr", "hi", "en"):
        language = "mr"
    profile_patch = body.get("profile_patch") or None

    # Get compiled graph from app state (initialised in lifespan)
    graph = getattr(request.app.state, "agent_graph", None)

    initial_state: dict = {
        "thread_id": thread_id,
        "message": body.get("message", ""),
        "language": language,
        "profile_patch": profile_patch,
        "missing": [],
        "scenarios": [],
        "water": [],
        "candidates": [],
        "excluded": [],
        "scenario_yields": {},
        "long_duration_crops": set(),
        "strategies": [],
        "relaxations": [],
        "relaxation_count": 0,
        "explanation_text": "",
        "explanation_grounded": False,
        "explanation_provider": "template",
        "grounding_retry_count": 0,
        "water_saved_pct": 0.0,
        "trace": [],
        "messages": [],
        "route": "new_plan",   # overwritten by route_node
        "no_data": False,
    }

    config = {"configurable": {"thread_id": thread_id}}

    async def _persist(event: dict, cache, messages: list) -> None:
        """Save profile / plan / chat messages so GET /api/threads/{id} and
        POST /api/plans/{id}/reoptimize work for agent-created plans."""
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
                await cache.set_memory(thread_id, "messages", messages)
        except Exception:
            logger.warning("Could not persist agent event %s", event.get("event"), exc_info=True)

    async def _stream():
        started = time.perf_counter()
        try:
            from app.core.cache import get_cache

            try:
                cache = await get_cache()
                prior = await cache.get_memory(thread_id, "messages")
                # The graph checkpointer is intentionally in-process. Restore
                # durable profile/plan state from the application cache so a
                # backend restart does not make a continuing conversation lose
                # its farm memory.
                if not body.get("profile_patch"):
                    from app.schemas import FarmProfile, PlanResult

                    cached_profile = await cache.get_memory(thread_id, "profile")
                    cached_plan = await cache.get_memory(thread_id, "plan")
                    if isinstance(cached_profile, dict):
                        initial_state["profile"] = FarmProfile.model_validate(cached_profile)
                    if isinstance(cached_plan, dict):
                        restored_plan = PlanResult.model_validate(cached_plan)
                        initial_state["plan_result"] = restored_plan
                        initial_state["strategies"] = restored_plan.strategies
            except Exception:
                logger.warning(
                    "Agent cache unavailable, continuing without persistence (thread=%s)",
                    thread_id, exc_info=True,
                )
                cache, prior = None, None
            messages: list = list(prior) if isinstance(prior, list) else []
            if body.get("message"):
                messages.append({
                    "role": "farmer",
                    "text": body["message"],
                    "language": language,
                    "at": datetime.now(tz=timezone.utc).isoformat(),
                })
            async for ev in _stream_events():
                if cache is not None:
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
                # Fallback: graph not initialised (startup failed or test mode)
                async for item in _stub_stream(initial_state, language):
                    yield item
            else:
                async for event in graph.astream_events(
                    initial_state,
                    config=config,
                    version="v1",   # LangGraph 0.2 default — NOT "v2"
                ):
                    sse_events = _lg_event_to_sse(event)
                    if isinstance(sse_events, list):
                        for sse in sse_events:
                            yield sse
                    elif sse_events:
                        yield sse_events

        except Exception as exc:
            logger.exception("Agent stream error (thread=%s)", thread_id)
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

def _lg_event_to_sse(event: dict) -> dict | list[dict] | None:
    """Map a LangGraph astream_events dict to an SSE payload.

    LangGraph v1 event structure:
      {"event": "on_chain_end", "name": "<node_name>", "data": {"output": <state_patch>}}

    SSE events the frontend expects (SPECS §5.2 E1):
      profile   — after extract_profile or merge_patch
      trace     — after each data-gathering node, predict_yield, optimize, explain
      plan      — after respond_node builds a PlanResult
      message   — after explain_node completes
      question  — after ask_missing_node fires
    """
    kind = event.get("event", "")
    name = event.get("name", "")
    output = event.get("data", {}).get("output", {}) or {}

    if kind != "on_chain_end":
        return None

    # profile event — after extract_profile or merge_patch
    if name in ("extract_profile", "merge_patch"):
        profile = output.get("profile")
        if profile:
            data = profile.model_dump_json() if hasattr(profile, "model_dump_json") else json.dumps(profile)
            return {"event": "profile", "data": data}

    # question event — after ask_missing
    if name == "ask_missing":
        question = output.get("question")
        if question:
            return {"event": "question", "data": json.dumps(question)}

    # trace events — after nodes that emit trace steps
    if name in ("gather_data", "recommend_crops", "predict_yield", "optimize",
                "check_feasibility", "relax_constraint", "explain", "grounding_check"):
        trace_list = output.get("trace", [])
        if trace_list:
            last = trace_list[-1]
            data = last.model_dump_json() if hasattr(last, "model_dump_json") else json.dumps(last)
            return {"event": "trace", "data": data}

    # plan + message events — after respond
    if name == "respond":
        plan_result = output.get("plan_result")
        if plan_result:
            plan_json = plan_result.model_dump_json() if hasattr(plan_result, "model_dump_json") else json.dumps(plan_result)
            if hasattr(plan_result, "model_dump"):
                plan_data = plan_result.model_dump(mode="json")
            else:
                plan_data = plan_result
            explanation = plan_data.get("explanation", {})
            message = {
                "text": explanation.get("text", ""),
                "language": explanation.get("language", "mr"),
                "provider": explanation.get("provider", "template"),
            }
            return [
                {"event": "plan", "data": plan_json},
                {"event": "message", "data": json.dumps(message)},
            ]

    return None


# ── Fallback stub stream (when graph is not initialised) ──────────────────────

async def _stub_stream(state: dict, language: str):
    """Used only when the LangGraph agent failed to start. Never invents a farm profile."""
    texts = {
        "mr": "सहाय्यक सध्या उपलब्ध नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
        "hi": "सहायक अभी उपलब्ध नहीं है। कृपया कुछ देर बाद पुनः प्रयास करें।",
        "en": "The assistant is not available right now. Please try again shortly.",
    }
    yield {"event": "message", "data": json.dumps({
        "text": texts.get(language, texts["en"]),
        "language": language,
        "provider": "template",
    })}
