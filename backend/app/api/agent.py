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
import logging
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
    thread_id = body.get("thread_id") or f"th_{uuid.uuid4().hex[:8]}"
    language = body.get("language", "mr")
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

    async def _stream():
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}

        try:
            if graph is None:
                # Fallback: graph not initialised (startup failed or test mode)
                async for item in _stub_stream(initial_state, language):
                    yield item
                return

            async for event in graph.astream_events(
                initial_state,
                config=config,
                version="v1",   # LangGraph 0.2 default — NOT "v2"
            ):
                sse_item = _lg_event_to_sse(event)
                if sse_item:
                    if isinstance(sse_item, list):
                        for sse in sse_item:
                            yield sse
                    else:
                        yield sse_item

        except AppError as e:
            yield {"event": "error", "data": json.dumps(e.to_response().model_dump())}
        except Exception as exc:
            logger.exception("Agent stream error (thread=%s)", thread_id)
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": {
                        "code": "INTERNAL",
                        "message": str(exc),
                        "user_message": {
                            "mr": "त्रुटी झाली. कृपया पुन्हा प्रयत्न करा.",
                            "hi": "त्रुटि हुई। कृपया पुनः प्रयास करें।",
                            "en": "An error occurred. Please try again.",
                        },
                        "retryable": True,
                        "details": {},
                    }
                }),
            }

        yield {"event": "done", "data": json.dumps({"ms": 0})}

    return EventSourceResponse(_stream(), ping=10)


# ── LangGraph event → SSE mapper ─────────────────────────────────────────────

def _lg_event_to_sse(event: dict) -> dict | None:
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
    if name in ("router", "merge_patch"):
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
            events = [{"event": "plan", "data": plan_json}]
            if hasattr(plan_result, "explanation") and plan_result.explanation:
                msg_payload = {
                    "text": plan_result.explanation.text,
                    "language": plan_result.explanation.language,
                }
                events.append({"event": "message", "data": json.dumps(msg_payload)})
            return events

    return None


# ── Fallback stub stream (when graph is not initialised) ──────────────────────

async def _stub_stream(state: dict, language: str):
    """Minimal SSE stream used when the LangGraph graph failed to start."""
    from app.pipeline import run_plan
    from app.schemas import FarmProfile

    profile_data = {
        "location_text": state.get("message", "")[:50] or "Maharashtra",
        "land_acres": 5.0,
        "budget_rs": 50000.0,
        "language": language,
    }
    try:
        profile = FarmProfile(**profile_data)
        plan = await run_plan(profile, thread_id=state["thread_id"])
        yield {"event": "plan", "data": plan.model_dump_json()}
        yield {"event": "message", "data": json.dumps({
            "text": plan.explanation.text,
            "language": language,
            "provider": plan.explanation.provider,
        })}
    except Exception as exc:
        logger.warning("stub stream failed: %s", exc)
