"""E2  POST /api/plan
E3  POST /api/plans/{plan_id}/reoptimize
"""

from __future__ import annotations


from fastapi import APIRouter
from pydantic import ValidationError

from app.api.profile import PROFILE_META_KEY, load_meta, meta_for_profile_write, meta_with_plan
from app.core.cache import get_cache
from app.core.errors import AppError, ensure_positive
from app.pipeline import run_plan
from app.schemas import FarmProfile, PlanResult
from app.services.data_status import count_data_status
from app.services.water import normalise_borewell

router = APIRouter()


@router.post("/plan", response_model=PlanResult)
async def create_plan(profile: FarmProfile) -> PlanResult:
    """E2 — Plan from a complete profile, no agent. Target: warm response under 5 s.

    explanation.provider = 'template' (no LLM calls).
    """
    ensure_positive({"land_acres": profile.land_acres, "budget_rs": profile.budget_rs})
    profile = normalise_borewell(profile)
    result = await run_plan(profile)
    result = result.model_copy(update={"data_status": count_data_status(result)})
    # Store for E3 (reoptimize by plan_id) and E4 (restore by thread_id)
    cache = await get_cache()
    plan_data = result.model_dump(mode="json")
    await cache.set_plan(result.plan_id, plan_data)
    if result.thread_id:
        profile_data = profile.model_dump(mode="json")
        prev_profile = await cache.get_memory(result.thread_id, "profile")
        prev_meta = await load_meta(cache, result.thread_id)
        # The plan was built from this profile: record the version it belongs to.
        meta = meta_with_plan(meta_for_profile_write(prev_meta, prev_profile, profile_data))
        await cache.set_memory(result.thread_id, "profile", profile_data)
        await cache.set_memory(result.thread_id, "plan", plan_data)
        await cache.set_memory(result.thread_id, "messages", [])
        await cache.set_memory(result.thread_id, PROFILE_META_KEY, meta)
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
        raise AppError("PLAN_NOT_FOUND", {"plan_id": plan_id})

    # Patch the stored profile with any changed fields
    stored_profile = stored.get("profile", {})
    for field in ("risk_appetite", "budget_rs", "land_acres"):
        if field in body:
            stored_profile[field] = body[field]
    if "safety_scenario" in body:
        stored_profile["safety_scenario"] = body["safety_scenario"]

    ensure_positive({k: stored_profile.get(k) for k in ("land_acres", "budget_rs")})
    try:
        profile = normalise_borewell(FarmProfile(**stored_profile))
    except ValidationError as exc:
        raise AppError("VALIDATION_ERROR", {"errors": [e["loc"][-1] for e in exc.errors()]}) from exc
    new_plan = await run_plan(
        profile,
        thread_id=stored.get("thread_id"),
        plan_id=plan_id,
    )
    # Bump version
    new_plan = new_plan.model_copy(update={
        "data_status": count_data_status(new_plan),
        "version": stored.get("version", 1) + 1,
        "previous_version": stored.get("version", 1),
    })

    # Write back to cache and agent memory
    new_plan_data = new_plan.model_dump(mode="json")
    await cache.set_plan(plan_id, new_plan_data)
    if new_plan.thread_id:
        prev_profile = await cache.get_memory(new_plan.thread_id, "profile")
        prev_meta = await load_meta(cache, new_plan.thread_id)
        meta = meta_with_plan(meta_for_profile_write(prev_meta, prev_profile, stored_profile))
        await cache.set_memory(new_plan.thread_id, "profile", stored_profile)
        # The thread restore (E4) and the next chat turn must see the NEW plan, not the old one.
        await cache.set_memory(new_plan.thread_id, "plan", new_plan_data)
        await cache.set_memory(new_plan.thread_id, PROFILE_META_KEY, meta)

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
