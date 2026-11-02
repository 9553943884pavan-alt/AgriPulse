"""E4  GET /api/threads/{thread_id}"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.memory import cap_messages
from app.core.cache import get_cache
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

    return {
        "thread_id": thread_id,
        "profile": FarmProfile(**profile_data) if profile_data else None,
        "plan": PlanResult(**plan_data) if plan_data else None,
        "messages": messages_data,
    }
