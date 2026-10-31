"""E1  POST /api/agent/chat  (Server-Sent Events)

SSE event order for a full plan:
  thread → profile → trace… → plan → message → done

The agent LangGraph graph (backend/app/agent/) is implemented by the ML lead.
This router provides the SSE scaffolding; until the graph exists it streams
a direct run_plan() result so the frontend SSE parser can be developed.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.cache import get_cache
from app.core.errors import AppError
from app.pipeline import run_plan
from app.schemas import FarmProfile

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/agent/chat")
async def agent_chat(body: dict):
    """E1 — One conversation turn, streamed as SSE.

    Request body:
      thread_id?  (omit for first turn; response creates one)
      message     farmer's text or transcription
      language?   mr | hi | en
      profile_patch?  partial FarmProfile override
    """
    thread_id = body.get("thread_id") or f"th_{uuid.uuid4().hex[:8]}"
    language = body.get("language", "mr")
    profile_patch = body.get("profile_patch") or {}

    cache = await get_cache()

    async def _stream():
        # ── Event: thread ──────────────────────────────────────────────────
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}

        try:
            # Load or build profile from memory
            existing = await cache.get_memory(thread_id, "profile") or {}
            existing.update(profile_patch)

            # Parse message for profile fields (placeholder — agent does this)
            message_text = body.get("message", "")
            profile_data = _parse_message_to_profile(message_text, existing, language)
            profile = FarmProfile(**profile_data)

            # ── Event: profile ─────────────────────────────────────────────
            yield {"event": "profile", "data": profile.model_dump_json()}

            # Check required fields
            missing = []
            if not profile.location_text:
                missing.append("location_text")
            if not profile.land_acres:
                missing.append("land_acres")
            if not profile.budget_rs:
                missing.append("budget_rs")

            if missing:
                profile.missing = missing  # type: ignore[assignment]
                question = _ask_missing(missing[0], language)
                yield {"event": "question", "data": json.dumps(question)}
                yield {"event": "done", "data": json.dumps({"ms": 0})}
                return

            # ── Event: trace (simulated) ───────────────────────────────────
            for step_name in ("locate", "weather", "soil", "prices", "optimize"):
                yield {
                    "event": "trace",
                    "data": json.dumps({
                        "id": f"ev_{uuid.uuid4().hex[:4]}",
                        "node": "gather_data",
                        "step": step_name,
                        "status": "running",
                        "started_at": datetime.now(tz=timezone.utc).isoformat(),
                        "duration_ms": 0,
                        "summary": f"Starting {step_name}...",
                        "source": None,
                        "fallback_used": None,
                    }),
                }

            # ── Run plan ───────────────────────────────────────────────────
            plan = await run_plan(profile, thread_id=thread_id)

            # Complete trace events
            yield {
                "event": "trace",
                "data": json.dumps({
                    "id": f"ev_{uuid.uuid4().hex[:4]}",
                    "node": "gather_data", "step": "complete",
                    "status": "ok",
                    "started_at": datetime.now(tz=timezone.utc).isoformat(),
                    "duration_ms": 100, "summary": "Data gathered",
                    "source": None, "fallback_used": None,
                }),
            }

            # ── Event: plan ────────────────────────────────────────────────
            yield {"event": "plan", "data": plan.model_dump_json()}

            # ── Event: message ─────────────────────────────────────────────
            yield {
                "event": "message",
                "data": json.dumps({
                    "text": plan.explanation.text,
                    "language": language,
                    "provider": plan.explanation.provider,
                }),
            }

            # Save to memory
            await cache.set_memory(thread_id, "profile", profile.model_dump(mode="json"))
            await cache.set_memory(thread_id, "plan", plan.model_dump(mode="json"))

        except AppError as e:
            yield {"event": "error", "data": json.dumps(e.to_response().model_dump())}
        except Exception as e:
            logger.exception("Unexpected error in agent chat")
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": {
                        "code": "INTERNAL",
                        "message": str(e),
                        "user_message": {"mr": "त्रुटी झाली.", "hi": "त्रुटि हुई।", "en": "An error occurred."},
                        "retryable": True, "details": {},
                    }
                }),
            }

        # ── Event: done (always last) ──────────────────────────────────────
        yield {"event": "done", "data": json.dumps({"ms": 0})}

    return EventSourceResponse(_stream(), ping=10)  # heartbeat every 10 s


def _parse_message_to_profile(message: str, existing: dict, language: str) -> dict:
    """Minimal rule-based profile extraction (placeholder for the LangGraph agent).
    The real extraction is done by the agent's extract_profile node (AG.3).
    """
    import re
    profile = {
        "location_text": existing.get("location_text", ""),
        "land_acres": existing.get("land_acres", 0),
        "budget_rs": existing.get("budget_rs", 0),
        "water_source": existing.get("water_source"),
        "language": language,
        "missing": [],
        "defaults_used": [],
    }
    # Very simple extraction — enough to test the SSE flow
    if not profile["location_text"]:
        for word in message.split():
            if len(word) > 3 and word[0].isupper():
                profile["location_text"] = word
                break
    acres_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:एकर|acre|acres)", message, re.IGNORECASE)
    if acres_match:
        profile["land_acres"] = float(acres_match.group(1))
    budget_match = re.search(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:रुपये|₹|rs|rupees)", message, re.IGNORECASE)
    if budget_match:
        profile["budget_rs"] = float(budget_match.group(1).replace(",", ""))
    if "बोअरवेल" in message or "borewell" in message.lower():
        profile["water_source"] = "borewell"
        profile["borewell_count"] = existing.get("borewell_count", 1)
    return profile


def _ask_missing(field: str, language: str) -> dict:
    questions = {
        "location_text": {"mr": "तुमचे गाव किंवा जिल्हा कोणता आहे?", "hi": "आपका गांव या जिला कौन सा है?", "en": "Which village or district is your farm in?"},
        "land_acres": {"mr": "तुमच्याकडे किती एकर जमीन आहे?", "hi": "आपके पास कितने एकड़ जमीन है?", "en": "How many acres of land do you have?"},
        "budget_rs": {"mr": "शेतीसाठी तुमच्याकडे किती पैसे आहेत?", "hi": "खेती के लिए आपके पास कितना बजट है?", "en": "What is your farming budget in rupees?"},
    }
    q = questions.get(field, {"mr": "?", "hi": "?", "en": "?"})
    return {"text": q.get(language, q["en"]), "field": field, "language": language}
