"""Phase 2  PUT /api/profile  +  profile/plan version tracking.

The farmer saves the Farm Profile on the server first, then asks for an optimised plan
against that saved profile. Every successful save bumps a per-thread version; every
persisted plan records the profile version it was built from, so a stale plan is
detectable (plan_stale) and a stale optimize request is refused (PROFILE_STALE).

Thread memory keys used here (agent_memory):
  profile       the saved FarmProfile (dict)
  profile_meta  {"version": int, "saved_at": ISO, "plan_profile_version": int | None}
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas import FarmProfile
from app.services import location as loc_svc

logger = logging.getLogger(__name__)
router = APIRouter()

PROFILE_META_KEY = "profile_meta"
THREAD_ID_RE = re.compile(r"^th_[0-9a-f]{32}$")
# Fields the server computes; a client echoing them back is harmless, so they are ignored.
_SERVER_FIELDS = frozenset({"missing", "defaults_used"})
PROFILE_KEYS = frozenset(FarmProfile.model_fields) - _SERVER_FIELDS
# Fields that make two profiles "the same" when deciding whether a save changed anything.
_CORE_IGNORED = _SERVER_FIELDS | {"language"}
_PLACEHOLDER_LOCATIONS = {"", "unknown", "none", "null", "undefined", "n/a", "na", "-"}
MAX_LAND_ACRES = 10000.0
MAX_LOCATION_CHARS = 200
LOCATION_TIMEOUT_S = 10.0


# ── version bookkeeping (shared with the agent and /api/plan) ────────────────

def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def profile_core(data: dict | None) -> dict:
    """The farmer-controlled part of a stored profile, for change detection."""
    return {k: v for k, v in (data or {}).items() if k in PROFILE_KEYS and k not in _CORE_IGNORED}


def effective_version(meta: dict | None, has_profile: bool) -> int | None:
    """Current profile version. A legacy profile with no meta counts as version 1."""
    version = (meta or {}).get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version >= 1:
        return version
    return 1 if has_profile else None


def plan_is_stale(meta: dict | None, has_profile: bool, has_plan: bool) -> bool:
    """A stored plan exists and was built from a different profile version."""
    if not (has_profile and has_plan):
        return False
    built_from = (meta or {}).get("plan_profile_version")
    if not isinstance(built_from, int) or isinstance(built_from, bool):
        built_from = 1          # legacy plan: built before versions existed
    return built_from != effective_version(meta, True)


def bumped_meta(prev_meta: dict | None, had_profile: bool) -> dict:
    """Meta after one more successful profile save (first save is version 1)."""
    prev = effective_version(prev_meta, had_profile) or 0
    return {
        "version": prev + 1,
        "saved_at": now_iso(),
        "plan_profile_version": (prev_meta or {}).get("plan_profile_version"),
    }


def meta_for_profile_write(prev_meta: dict | None, prev_profile: dict | None, new_profile: dict) -> dict:
    """Meta to store with `new_profile`: bumped when the profile is new or changed,
    otherwise the previous meta (created as version 1 for a legacy profile)."""
    changed = prev_profile is None or profile_core(prev_profile) != profile_core(new_profile)
    if changed:
        return bumped_meta(prev_meta, prev_profile is not None)
    if prev_meta and isinstance(prev_meta.get("version"), int):
        return dict(prev_meta)
    return {"version": 1, "saved_at": now_iso(), "plan_profile_version": None}


def meta_with_plan(meta: dict | None, has_profile: bool = True) -> dict:
    """Meta after a plan was persisted: the plan was built from the current profile version."""
    out = dict(meta) if meta else {"version": effective_version(None, has_profile) or 1, "saved_at": now_iso()}
    out["version"] = effective_version(out, has_profile) or 1
    out["plan_profile_version"] = out["version"]
    return out


async def load_meta(cache, thread_id: str) -> dict | None:
    meta = await cache.get_memory(thread_id, PROFILE_META_KEY)
    return meta if isinstance(meta, dict) else None


# ── validation ────────────────────────────────────────────────────────────────

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validation_error(fields: dict[str, str]) -> AppError:
    return AppError("VALIDATION_ERROR", {"fields": fields}, message="; ".join(fields.values()))


def validate_profile_body(body) -> tuple[str | None, FarmProfile]:
    """Strict check of the PUT body. Returns (thread_id or None, clean FarmProfile).
    Raises AppError VALIDATION_ERROR (422) with details.fields {field: message}."""
    if not isinstance(body, dict):
        raise _validation_error({"body": "Request body must be a JSON object."})
    errors: dict[str, str] = {}

    for key in body:
        if key not in ("thread_id", "profile"):
            errors[str(key)] = "Unknown field."

    thread_id = body.get("thread_id")
    if thread_id in (None, ""):
        thread_id = None
    elif not isinstance(thread_id, str) or not THREAD_ID_RE.match(thread_id):
        errors["thread_id"] = "thread_id must look like th_ followed by 32 hex characters."

    raw = body.get("profile")
    if not isinstance(raw, dict):
        errors["profile"] = "profile must be an object."
        raise _validation_error(errors)

    data: dict = {}
    for key, value in raw.items():
        if key in _SERVER_FIELDS:
            continue
        if key not in PROFILE_KEYS:
            errors[key] = "Unknown field."
        elif value is not None:
            data[key] = value

    loc = data.get("location_text")
    if loc is None:
        errors.setdefault("location_text", "Location is required.")
    elif not isinstance(loc, str) or loc.strip().lower() in _PLACEHOLDER_LOCATIONS:
        errors["location_text"] = "Location is required."
    elif len(loc.strip()) > MAX_LOCATION_CHARS:
        errors["location_text"] = f"Location must be at most {MAX_LOCATION_CHARS} characters."
    else:
        data["location_text"] = loc.strip()

    land = data.get("land_acres")
    if land is None:
        errors.setdefault("land_acres", "Land area is required.")
    elif not _is_number(land) or not 0 < land <= MAX_LAND_ACRES:
        errors["land_acres"] = f"Land area must be a number greater than 0 and at most {MAX_LAND_ACRES:g} acres."

    budget = data.get("budget_rs")
    if budget is None:
        errors.setdefault("budget_rs", "Budget is required.")
    elif not _is_number(budget) or not budget > 0:
        errors["budget_rs"] = "Budget must be a number greater than 0."

    # Borewell fields are optional, but a value that is given must be real.
    for key, label in (("borewell_count", "Number of borewells"),
                       ("borewell_yield_lph", "Borewell yield"),
                       ("pump_hours_per_day", "Pump hours per day")):
        if key not in data:
            continue
        value = data[key]
        if key == "borewell_count" and (isinstance(value, bool) or not isinstance(value, int)):
            errors[key] = f"{label} must be a whole number greater than 0."
        elif not _is_number(value) or not value > 0:
            errors[key] = f"{label} must be greater than 0."
        elif key == "pump_hours_per_day" and value > 24:
            errors[key] = "Pump hours per day cannot be more than 24."

    if "canal_access" in data and not isinstance(data["canal_access"], bool):
        errors["canal_access"] = "canal_access must be true or false."

    if errors:
        raise _validation_error(errors)

    try:
        profile = FarmProfile.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            field = str(err["loc"][0]) if err.get("loc") else "profile"
            errors.setdefault(field, "Invalid value.")
        raise _validation_error(errors) from exc
    return thread_id, profile


async def resolve_location(location_text: str) -> list[dict]:
    """Check the place exists. A place that is definitely not found is a 422 on
    location_text; any other failure (network, timeout) only produces a warning."""
    try:
        await asyncio.wait_for(loc_svc.locate(location_text), timeout=LOCATION_TIMEOUT_S)
    except AppError as exc:
        if exc.code in ("LOCATION_NOT_FOUND", "DISTRICT_NOT_AGRICULTURAL"):
            # Keep the specific code (422); details.fields names the field for the form.
            raise AppError(
                exc.code,
                {**exc.details, "location_text": location_text, "fields": {"location_text": exc.message}},
                message=exc.message,
                user_message=exc.user_message,
            ) from exc
        logger.warning("Location check failed for PUT /profile (%s); saving anyway", exc.code)
        return [_unverified_warning()]
    except Exception:
        logger.warning("Location check failed for PUT /profile; saving anyway", exc_info=True)
        return [_unverified_warning()]
    return []


def _unverified_warning() -> dict:
    return {
        "code": "LOCATION_UNVERIFIED",
        "params": {"field": "location_text"},
        "message": "The place could not be checked right now; your profile was saved anyway.",
    }


# ── endpoint ──────────────────────────────────────────────────────────────────

@router.put("/profile")
async def save_profile(body: dict) -> dict:
    """Save the Farm Profile on the server (no planning). Every successful save is a new version.

    Body: {"thread_id"?: "th_<32 hex>", "profile": {FarmProfile fields}}
    200:  {thread_id, profile, profile_version, saved_at, plan_stale, warnings}
    """
    from app.core.cache import get_cache
    from app.services.water import normalise_borewell

    thread_id, profile = validate_profile_body(body)
    warnings = await resolve_location(profile.location_text)
    profile = normalise_borewell(profile)

    thread_id = thread_id or f"th_{uuid.uuid4().hex}"
    cache = await get_cache()
    prev_profile = await cache.get_memory(thread_id, "profile")
    prev_meta = await load_meta(cache, thread_id)
    meta = bumped_meta(prev_meta, isinstance(prev_profile, dict))
    profile_data = profile.model_dump(mode="json")
    await cache.set_memory(thread_id, "profile", profile_data)
    await cache.set_memory(thread_id, PROFILE_META_KEY, meta)

    has_plan = isinstance(await cache.get_memory(thread_id, "plan"), dict)
    return {
        "thread_id": thread_id,
        "profile": profile_data,
        "profile_version": meta["version"],
        "saved_at": meta["saved_at"],
        "plan_stale": plan_is_stale(meta, True, has_plan),
        "warnings": warnings,
    }
