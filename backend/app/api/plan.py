"""E2  POST /api/plan
E3  POST /api/plans/{plan_id}/reoptimize
"""

from __future__ import annotations


from fastapi import APIRouter

from app.core.cache import get_cache
from app.core.errors import AppError
from app.pipeline import run_plan
from app.schemas import FarmProfile, PlanResult

router = APIRouter()


@router.post("/plan", response_model=PlanResult)
async def create_plan(profile: FarmProfile) -> PlanResult:
    """E2 — Plan from a complete profile, no agent. Target: warm response under 5 s.

    explanation.provider = 'template' (no LLM calls).
    """
    result = await run_plan(profile)
    # Store for E3 (reoptimize by plan_id) and E4 (restore by thread_id)
    cache = await get_cache()
    plan_data = result.model_dump(mode="json")
    await cache.set_plan(result.plan_id, plan_data)
    if result.thread_id:
        await cache.set_memory(result.thread_id, "profile", profile.model_dump(mode="json"))
        await cache.set_memory(result.thread_id, "plan", plan_data)
        await cache.set_memory(result.thread_id, "messages", [])
    return result


@router.post("/plans/{plan_id}/reoptimize", response_model=PlanResult)
async def reoptimize(plan_id: str, body: dict) -> PlanResult:
    """E3 — Re-solve with new risk/budget/scenario using the stored plan inputs.
    No external API calls. Target: under 1.5 s.
    Writes changed field back to agent checkpointer so chat follow-ups stay consistent.
    """
    cache = await get_cache()
    stored = await cache.get_plan(plan_id)
    if stored is None:
        raise AppError("PLAN_NOT_FOUND", {"plan_id": plan_id}).to_http_exception()

    # Patch the stored profile with any changed fields
    stored_profile = stored.get("profile", {})
    for field in ("risk_appetite", "budget_rs", "land_acres"):
        if field in body:
            stored_profile[field] = body[field]
    if "safety_scenario" in body:
        stored_profile["safety_scenario"] = body["safety_scenario"]

    profile = FarmProfile(**stored_profile)
    new_plan = await run_plan(
        profile,
        thread_id=stored.get("thread_id"),
        plan_id=plan_id,
    )
    # Bump version
    new_plan = new_plan.model_copy(update={
        "version": stored.get("version", 1) + 1,
        "previous_version": stored.get("version", 1),
    })

    # Write back to cache and agent memory
    await cache.set_plan(plan_id, new_plan.model_dump(mode="json"))
    if new_plan.thread_id:
        await cache.set_memory(new_plan.thread_id, "profile", stored_profile)

    # Write patched fields back to the LangGraph checkpointer so the next
    # chat turn (E1) reads the updated profile. This is the only place outside
    # the graph that writes to the checkpointer (per memory.py contract).
    if new_plan.thread_id:
        patch = {k: body[k] for k in ("risk_appetite", "budget_rs", "land_acres") if k in body}
        if patch:
            try:
                from app.agent.memory import update_profile_fields
                await update_profile_fields(new_plan.thread_id, patch)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "E3 checkpointer write-back failed (non-fatal): %s", exc
                )

    return new_plan
