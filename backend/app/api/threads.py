"""E4  GET /api/threads/{thread_id}"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.memory import cap_messages
from app.core.cache import get_cache
from app.api.profile import PROFILE_META_KEY, effective_version, plan_is_stale
from app.core.errors import AppError
from app.schemas import FarmProfile, PlanResult

router = APIRouter()


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> dict:
    """E4 — Restore profile + last plan + messages for page reload (F14)."""
    cache = await get_cache()
    memory = await cache.get_all_memory(thread_id)
    if not memory:
        raise AppError("PLAN_NOT_FOUND", {"thread_id": thread_id})

    profile_data = memory.get("profile")
    plan_data = memory.get("plan")
    messages_data = cap_messages(memory.get("messages") or [])

    meta = memory.get(PROFILE_META_KEY)
    meta = meta if isinstance(meta, dict) else None
    has_profile = bool(profile_data)

    return {
        "thread_id": thread_id,
        "profile": FarmProfile(**profile_data) if profile_data else None,
        "plan": PlanResult(**plan_data) if plan_data else None,
        "messages": messages_data,
        # Phase 2 (additive): which saved-profile version this is, and whether the plan predates it.
        "profile_version": effective_version(meta, has_profile),
        "profile_saved_at": (meta or {}).get("saved_at") if has_profile else None,
        "plan_stale": plan_is_stale(meta, has_profile, bool(plan_data)),
    }
