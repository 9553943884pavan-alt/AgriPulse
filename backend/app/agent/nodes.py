"""AG.3/4/5/6/8/9/10 — LangGraph node functions.

Each node receives AgentState and returns a partial state dict.
LangGraph merges the partial dict into the full state.

LLM budget: at most 3 calls per plan turn.
  Call 1: extract_profile  (structured JSON extraction)
  Call 2: explain          (natural-language plan summary)
  Retry : explain again if grounding fails once (that's call 3, the max)

route, ask_missing, merge_patch, check_feasibility, relax_constraint,
grounding_check, respond, answer_from_memory, save_memory — NO LLM calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.schemas import (
    DefaultUsed,
    Explanation,
    FarmProfile,
    KeyPoint,
    Location,
    PlanResult,
    Season,
    TraceEvent,
    Warning,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _trace(node: str, step: str, status: str, summary: str, duration_ms: int = 0) -> TraceEvent:
    return TraceEvent(
        id=f"ev_{uuid.uuid4().hex}",
        node=node,
        step=step,
        status=status,  # type: ignore[arg-type]
        started_at=_now(),
        duration_ms=duration_ms,
        summary=summary,
        source=None,
        fallback_used=None,
    )


def _devanagari_to_ascii(text: str) -> str:
    """Convert Devanagari digits to ASCII (०→0 … ९→9)."""
    return text.translate(str.maketrans("०१२३४५६७८९", "0123456789"))


def _parse_number_words(text: str) -> str:
    """Expand Indian number words before parsing floats."""
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:crore|करोड़?)",
        lambda m: str(float(m.group(1)) * 1e7), text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:lakh|लाख)",
        lambda m: str(float(m.group(1)) * 1e5), text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:hazar|हज़ार|हजार)",
        lambda m: str(float(m.group(1)) * 1e3), text, flags=re.IGNORECASE
    )
    return text


def _extract_float(text: str) -> float | None:
    """Best-effort float extraction from a normalised string."""
    text = _devanagari_to_ascii(text)
    text = _parse_number_words(text)
    # strip Indian digit grouping
    text = re.sub(r"(\d),(\d{2,3})", r"\1\2", text)
    text = re.sub(r"(\d),(\d{2,3})", r"\1\2", text)
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# AG.5 route — rule-based, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def route_node(state: dict) -> dict:
    """Decide the path: new_plan / follow_up / patch / question.

    new_plan:   required profile fields unknown OR message has location/number.
    follow_up:  plan exists AND message contains a changed fact (number, crop, risk word).
    patch:      profile_patch is set (farmer edited the card directly, no message).
    question:   plan exists AND message is a question with no changed fact.
    """
    if state.get("profile_patch"):
        return {"route": "patch"}

    has_plan = bool(state.get("strategies"))
    message = state.get("message", "")

    # Check for changed facts in message
    has_number = bool(re.search(r"\d", _devanagari_to_ascii(message)))
    risk_words = {"safe", "balanced", "aggressive", "सुरक्षित", "संतुलित"}
    has_risk_word = any(w in message.lower() for w in risk_words)
    changed_fact = has_number or has_risk_word

    if not has_plan:
        return {"route": "new_plan"}
    if changed_fact:
        return {"route": "follow_up"}
    # Question about the existing plan
    return {"route": "question"}


# ─────────────────────────────────────────────────────────────────────────────
# merge_patch — rule-based, no LLM  (profile card edit via E1 profile_patch)
# ─────────────────────────────────────────────────────────────────────────────

def merge_patch_node(state: dict) -> dict:
    """Merge profile_patch into profile. No LLM call."""
    patch = state.get("profile_patch") or {}
    profile: FarmProfile | None = state.get("profile")

    if profile is None:
        return {
            "profile_patch": None,
            "route": "new_plan",
            "missing": ["location_text", "land_acres", "budget_rs"],
        }

    # Build updated profile
    profile_data = profile.model_dump()
    defaults_used: list[DefaultUsed] = list(profile.defaults_used)
    for field, value in patch.items():
        profile_data[field] = value
        defaults_used.append(DefaultUsed(
            field=field,
            value=str(value),
            basis="farmer_input (card edit)",
        ))
    profile_data["defaults_used"] = defaults_used

    for f in ("land_acres", "budget_rs"):
        try:
            if float(profile_data.get(f) or 0) <= 0:
                profile_data[f] = 0.0
        except (TypeError, ValueError):
            profile_data[f] = 0.0
    missing = compute_missing(profile_data)
    profile_data["missing"] = list(missing)
    updated = FarmProfile(**profile_data)
    return {
        "profile": updated,
        "profile_patch": None,
        "missing": missing,
        "route": "follow_up",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AG.3 extract_profile — LLM call 1
# ─────────────────────────────────────────────────────────────────────────────

async def _llm_extract(state: dict, language: str, message: str) -> dict:
    """LLM call 1 with regex fallback. Returns raw (un-normalised) profile fields."""
    from app.agent.client import SarvamAllModelsFailed, get_sarvam_client
    from app.agent.prompts import EXTRACT_PROFILE_SYSTEM

    system_prompt = EXTRACT_PROFILE_SYSTEM.get(language, EXTRACT_PROFILE_SYSTEM["en"])
    try:
        client = get_sarvam_client()
        resp = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2500,
        )
        raw = client.extract_text(resp)
        if not raw:
            raise ValueError("Sarvam returned empty content")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Sarvam returned non-object JSON")
        return data
    except SarvamAllModelsFailed:
        logger.warning("extract_profile: all Sarvam models failed — using regex fallback")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("extract_profile: parse error %s — using regex fallback", exc)
    except Exception as exc:
        logger.warning("extract_profile: unexpected error %s — using regex fallback", exc)
    data = _regex_profile_fallback(message)
    if state.get("profile") is not None:
        # Follow-up turn: never let the crude regex replace a known location.
        data.pop("location_text", None)
    return data


_DONT_KNOW_RE = re.compile(
    r"don'?t know|do not know|dont know|not sure|no idea|unknown|"
    r"माहीत नाही|माहित नाही|माहिती नाही|कल्पना नाही|नकळत|"
    r"पता नहीं|पता नही|मालूम नहीं|नहीं पता|नहीं मालूम|पता नहि",
    re.IGNORECASE,
)
_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h\b|तास|घंटे|घंटा|घण्टे|घन्टे)", re.IGNORECASE)
_LITRES_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:litres?|liters?|ltrs?|lit\b|lph|l/h|लीटर|लिटर|लिटर्स)", re.IGNORECASE
)
_COUNT_RE = re.compile(r"(\d+)\s*(?:borewells?|bore wells?|बोअरवेल|बोरवेल|बोर)", re.IGNORECASE)


def parse_borewell_answer(message: str) -> dict:
    """Rule-based reading of the answer to the borewell question (no LLM).

    Returns {"dont_know": bool, "values": {borewell_yield_lph?, pump_hours_per_day?, borewell_count?}}.
    """
    text = _devanagari_to_ascii(message or "")
    text = re.sub(r"(\d),(\d{3})", r"\1\2", text)
    values: dict[str, float] = {}
    m = _LITRES_RE.search(text)
    if m:
        values["borewell_yield_lph"] = float(m.group(1))
    m = _HOURS_RE.search(text)
    if m:
        values["pump_hours_per_day"] = float(m.group(1))
    m = _COUNT_RE.search(text)
    if m:
        values["borewell_count"] = float(m.group(1))
    return {"dont_know": bool(_DONT_KNOW_RE.search(message or "")), "values": values}


def compute_missing(data: dict) -> list[str]:
    """Required fields that are unknown. Numbers must be > 0 (0 = unknown)."""
    missing: list[str] = []
    loc = data.get("location_text")
    if not loc or str(loc).strip().lower() in ("", "unknown"):
        missing.append("location_text")
    for field in ("land_acres", "budget_rs"):
        try:
            ok = float(data.get(field) or 0) > 0
        except (TypeError, ValueError):
            ok = False
        if not ok:
            missing.append(field)
    return missing


async def extract_profile_node(state: dict) -> dict:
    """LLM call 1: turn farmer's message into a FarmProfile."""
    language = state.get("language", "en")
    message = state.get("message", "")
    trace = list(state.get("trace", []))
    t0 = _now()
    existing: FarmProfile | None = state.get("profile")
    pending = state.get("pending_field")
    asked = list(state.get("asked_fields") or [])

    # If the previous turn asked the borewell question, read the answer with rules
    # first: "5000 litres, 6 hours" or "I don't know" needs no LLM call.
    answer = parse_borewell_answer(message) if pending == "borewell_capacity" and existing else None
    answered_by_rules = bool(answer and (answer["dont_know"] or answer["values"]))

    if answered_by_rules:
        profile_data: dict = {}
        step = "rules"
    else:
        profile_data = await _llm_extract(state, language, message)
        step = "llm"
    if answer and answer["values"]:
        profile_data.update(answer["values"])

    # Post-LLM normalisation (plain code)
    profile_data = _normalise_profile(profile_data, existing)
    if answer and answer["dont_know"] and not answer["values"] and existing is not None:
        # Do not let a hallucinated number stand in for "I don't know".
        profile_data["borewell_yield_lph"] = existing.borewell_yield_lph
        profile_data["pump_hours_per_day"] = existing.pump_hours_per_day

    # Work out which required fields are still missing
    missing = compute_missing(profile_data)

    # Fill in placeholder values for required fields so Pydantic doesn't fail.
    # The 'missing' list tells ask_missing_node to prompt the farmer for the real values.
    safe_data = {k: v for k, v in profile_data.items() if k in FarmProfile.model_fields}
    for f in ("land_acres", "budget_rs"):
        if f in missing:
            safe_data[f] = 0.0   # 0 / negative / unknown = "missing", never planned with
    safe_data.setdefault("location_text", "unknown")  # placeholder until farmer provides it
    safe_data.setdefault("land_acres", 0.0)
    safe_data.setdefault("budget_rs", 0.0)
    safe_data["missing"] = list(missing)
    if language in ("mr", "hi", "en"):
        safe_data["language"] = language

    duration_ms = int((_now() - t0).total_seconds() * 1000)
    trace.append(_trace("extract_profile", step, "ok", f"Extracted profile; missing={missing}", duration_ms))

    try:
        profile_obj = FarmProfile(**safe_data)
    except Exception as exc:
        logger.warning("extract_profile: FarmProfile construction failed %s — empty profile", exc)
        profile_obj = FarmProfile(location_text="unknown", land_acres=0.0, budget_rs=0.0)
        missing = ["location_text", "land_acres", "budget_rs"]

    from app.services.water import normalise_borewell, wants_borewell_capacity
    profile_obj = normalise_borewell(profile_obj)

    # Optional question: borewell declared but no discharge/pump hours. Asked ONCE only.
    optional_ask = None
    if (
        not missing
        and "borewell_capacity" not in asked
        and wants_borewell_capacity(profile_obj)
    ):
        optional_ask = "borewell_capacity"

    return {
        "profile": profile_obj,
        "missing": missing,
        "optional_ask": optional_ask,
        "pending_field": None,
        "trace": trace,
    }


def _regex_profile_fallback(message: str) -> dict:
    """Best-effort profile extraction without the LLM."""
    data: dict[str, Any] = {}
    msg_norm = _devanagari_to_ascii(message)
    msg_norm = _parse_number_words(msg_norm)

    # Location — first title-case word > 3 chars
    loc = re.search(r"\b([A-Z][a-z]{3,})\b", message)
    if loc:
        data["location_text"] = loc.group(1)

    # Acres (English: acre/acres, Marathi: एकर, Hindi: एकड़)
    acres = re.search(r"(\d+(?:\.\d+)?)\s*(?:एकर|एकड़|acre|acres?)", msg_norm, re.IGNORECASE)
    if acres:
        data["land_acres"] = float(acres.group(1))

    # Guntha
    guntha = re.search(r"(\d+(?:\.\d+)?)\s*(?:गुंठे?|guntha)", msg_norm, re.IGNORECASE)
    if guntha:
        data["land_acres"] = float(guntha.group(1)) * 0.025

    # Budget: lakh/hazar are already expanded by _parse_number_words above; "thousand"/"k"
    # are handled here. Accepted with a currency or budget word (English, Marathi भांडवल, Hindi बजट).
    budget = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|hazar|हजार|k|lakhs?|लाख)?\s*(?:रुपये?|₹|rs\.?|rupees?)?",
        re.sub(r"(\d[\d,]*(?:\.\d+)?)\s*(?:एकर|एकड़|acres?|गुंठे?|guntha|hectares?)", " ", msg_norm, flags=re.IGNORECASE),
        re.IGNORECASE,
    )
    if budget and (budget.group(2) or re.search(r"रुपये?|₹|rs|rupees?|budget|भांडवल|बजट", msg_norm, re.IGNORECASE)):
        raw = _extract_float(budget.group(1).replace(",", ""))
        mult = (budget.group(2) or "").lower()
        if raw:
            if mult in ("thousand", "hazar", "हजार", "k"):
                raw *= 1000
            elif mult in ("lakh", "lakhs", "लाख"):
                raw *= 100000
            data["budget_rs"] = raw

    # Water source
    if re.search(r"borewell|बोअरवेल|boring|बोरवेल|बोरिंग", msg_norm, re.IGNORECASE):
        data["water_source"] = "borewell"
    elif re.search(r"canal|कालवा|नहर", msg_norm, re.IGNORECASE):
        data["water_source"] = "canal"
    elif re.search(r"rainfed|कोरडवाहू|rain|बारिश", msg_norm, re.IGNORECASE):
        data["water_source"] = "rainfed"

    return data


def _normalise_profile(data: dict, existing: FarmProfile | None) -> dict:
    """Apply unit conversions and merge with existing profile."""
    base: dict = {}
    if existing:
        base = existing.model_dump()
    base.update({k: v for k, v in data.items() if v is not None})

    # Hectare → acres
    if "land_ha" in base and base["land_ha"] and "land_acres" not in data:
        base["land_acres"] = float(base.pop("land_ha")) * 2.471

    # Ensure numeric types
    for field in ("land_acres", "budget_rs", "borewell_count", "borewell_yield_lph", "pump_hours_per_day"):
        if field in base and base[field] is not None:
            try:
                base[field] = float(base[field]) if field != "borewell_count" else int(float(base[field]))
            except (TypeError, ValueError):
                base[field] = None

    # Language default
    base.setdefault("language", "en")
    base.setdefault("missing", [])
    base.setdefault("defaults_used", [])

    return base


# ─────────────────────────────────────────────────────────────────────────────
# AG.4 ask_missing — rule-based translated template, NO LLM
# ─────────────────────────────────────────────────────────────────────────────

def ask_missing_node(state: dict) -> dict:
    """Emit a question event for the first missing required field. No LLM call."""
    missing = state.get("missing", [])
    language = state.get("language", "en")
    trace = list(state.get("trace", []))

    field = missing[0] if missing else state.get("optional_ask")
    if not field:
        return {}

    from app.agent.prompts import ASK_MISSING
    questions = ASK_MISSING.get(field, {})
    question_text = questions.get(language, questions.get("en", f"Please provide {field}."))

    trace.append(_trace("ask_missing", field, "ok", f"Asking for {field}"))
    asked = list(state.get("asked_fields") or [])
    if field not in asked:
        asked.append(field)
    # The question_text is picked up by the SSE mapper in agent.py via state["question"].
    # pending_field tells the next turn which answer to expect; asked_fields makes
    # sure each field is asked at most once.
    return {
        "question": {"text": question_text, "field": field, "language": language},
        "pending_field": field,
        "asked_fields": asked,
        "optional_ask": None,
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# gather_data — parallel service calls, no LLM
# ─────────────────────────────────────────────────────────────────────────────

async def gather_data_node(state: dict) -> dict:
    """Run location + weather + soil in parallel, then scenarios + water + prices + costs."""
    from app.agent import tools
    from app.core.errors import AppError

    profile: FarmProfile = state["profile"]
    trace = list(state.get("trace", []))
    updates: dict = {}
    t0 = _now()

    # Stage 1 — parallel: location, weather, soil
    async def _locate():
        try:
            loc = await tools.get_location(profile.location_text)
            return "location", loc, None
        except AppError:
            # An unknown / non-agricultural place is a user-facing error, not
            # "no profitable plan": surface it as the same structured error that
            # /api/plan returns (LOCATION_NOT_FOUND etc.) via the SSE error event.
            raise
        except Exception as e:
            return "location", None, str(e)

    async def _weather(location):
        try:
            wx = await tools.get_weather(location)
            return "weather", wx, None
        except Exception as e:
            return "weather", {}, str(e)

    async def _soil(location):
        try:
            s = await tools.get_soil(profile, location)
            return "soil", s, None
        except Exception as e:
            return "soil", {}, str(e)

    # Resolve location first (others depend on it)
    _, location, loc_err = await _locate()
    if location is None:
        trace.append(_trace("gather_data", "location", "failed", f"Location error: {loc_err}"))
        return {"location": None, "no_data": True, "trace": trace}

    updates["location"] = location
    trace.append(_trace("gather_data", "location", "ok", f"Resolved: {location.district}"))

    # Parallel weather + soil
    results = await asyncio.gather(_weather(location), _soil(location), return_exceptions=False)
    for key, value, err in results:
        updates[key] = value
        status = "ok" if err is None else "failed"
        trace.append(_trace("gather_data", key, status, err or f"{key} fetched"))

    # Stage 2 — sequential: scenarios, water, prices, costs
    season: Season = state.get("season") or _build_fallback_season()

    # Build scenarios
    try:
        scenarios = tools.build_scenarios(location, season)
        updates["scenarios"] = scenarios
        trace.append(_trace("gather_data", "scenarios", "ok", f"{len(scenarios)} scenarios"))
    except NotImplementedError:
        updates["scenarios"] = []
        trace.append(_trace("gather_data", "scenarios", "skipped", "ML stub not implemented"))
    except Exception as e:
        updates["scenarios"] = []
        trace.append(_trace("gather_data", "scenarios", "failed", str(e)))

    # Water budgets
    if updates.get("scenarios"):
        try:
            wb = await tools.get_water_budget(profile, location, updates["scenarios"], updates.get("weather", {}))
            updates["water"] = wb
            trace.append(_trace("gather_data", "water", "ok", f"{len(wb)} water budgets"))
        except Exception as e:
            updates["water"] = []
            trace.append(_trace("gather_data", "water", "failed", str(e)))
    else:
        updates["water"] = []

    # Prices and costs (crop_ids unknown until recommend_crops — pass empty list for warming)
    try:
        prices = await tools.get_prices(location.district, [])
        updates["prices"] = prices
        trace.append(_trace("gather_data", "prices", "ok", "Prices warmed"))
    except Exception as e:
        updates["prices"] = {}
        trace.append(_trace("gather_data", "prices", "failed", str(e)))

    duration_ms = int((_now() - t0).total_seconds() * 1000)
    trace.append(_trace("gather_data", "complete", "ok", "All data gathered", duration_ms))
    updates["trace"] = trace
    updates["no_data"] = False
    return updates


def _build_fallback_season() -> Season:
    """Season for today, detected from the crop calendar (same logic as the plan pipeline)."""
    from app.pipeline import _detect_season
    return _detect_season(date.today())


# ─────────────────────────────────────────────────────────────────────────────
# recommend_crops — calls ML stubs, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def recommend_crops_node(state: dict) -> dict:
    from app.agent import tools
    trace = list(state.get("trace", []))
    profile: FarmProfile = state["profile"]
    location: Location = state["location"]
    season: Season = state.get("season") or _build_fallback_season()
    water: list = state.get("water", [])

    try:
        candidates, excluded = tools.recommend_crops(profile, location, season, water)
        trace.append(_trace("recommend_crops", "Crop recommendations", "ok", f"{len(candidates)} candidates, {len(excluded)} excluded"))
        return {"candidates": candidates, "excluded": excluded, "trace": trace}
    except NotImplementedError:
        trace.append(_trace("recommend_crops", "Crop recommendations", "skipped", "Crop recommendation service is unavailable"))
        return {"candidates": [], "excluded": [], "no_data": True, "trace": trace}
    except Exception as exc:
        logger.warning("recommend_crops failed: %s", exc)
        trace.append(_trace("recommend_crops", "Crop recommendations", "failed", "Crop recommendation service failed"))
        return {"candidates": [], "excluded": [], "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# predict_yield — calls ML stubs per scenario, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def predict_yield_node(state: dict) -> dict:
    from app.agent import tools
    trace = list(state.get("trace", []))
    candidates = state.get("candidates", [])
    scenarios = state.get("scenarios", [])
    location: Location = state["location"]
    season: Season = state.get("season") or _build_fallback_season()

    scenario_yields: dict = {}
    long_duration_crops: set = set()

    try:
        for candidate in candidates:
            crop_id = candidate.crop_id
            scenario_yields[crop_id] = {}
            # Check long-duration
            from app.ml.constants import LONG_DURATION_DAYS
            if getattr(candidate, "duration_days", 0) > LONG_DURATION_DAYS:
                long_duration_crops.add(crop_id)

            for scenario in scenarios:
                try:
                    yp = tools.predict_yield(crop_id, location, season, scenario)
                    scenario_yields[crop_id][scenario.id] = yp
                except NotImplementedError:
                    scenario_yields[crop_id][scenario.id] = None
                except Exception as exc:
                    logger.warning("predict_yield %s/%s: %s", crop_id, scenario.id, exc)
                    scenario_yields[crop_id][scenario.id] = None

        trace.append(_trace("predict_yield", "Yield forecasts", "ok", f"Yields forecast for {len(scenario_yields)} crops"))
    except Exception:
        trace.append(_trace("predict_yield", "Yield forecasts", "failed", "Yield forecast service failed"))

    return {"scenario_yields": scenario_yields, "long_duration_crops": long_duration_crops, "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# optimize — calls ML optimizer stubs, no LLM
# ─────────────────────────────────────────────────────────────────────────────

async def optimize_node(state: dict) -> dict:
    from app.ml.candidate_options import build_crop_options
    from app.ml.optimizer import compare_strategies
    from app.schemas import OptimizerInputs

    trace = list(state.get("trace", []))
    profile: FarmProfile = state["profile"]
    location: Location = state["location"]
    season: Season = state.get("season") or _build_fallback_season()
    candidates = state.get("candidates", [])
    water = state.get("water", [])
    scenarios = state.get("scenarios", [])
    excluded = list(state.get("excluded", []))

    try:
        crops, price_excluded = await build_crop_options(candidates, scenarios, location, season, profile)
        excluded.extend(price_excluded)
        if not crops:
            trace.append(_trace("optimize", "Plan optimization", "skipped", "No crop has complete price and cost data"))
            return {"crops": [], "excluded": excluded, "strategies": [], "impact": None,
                    "opt_warnings": [], "trace": trace}
        inputs = OptimizerInputs(
            profile=profile,
            location=location,
            season=season,
            candidates=crops,
            water_budgets=water,
            scenario_weights=[0.2, 0.6, 0.2],
            price_history_years={c.crop_id: 5 for c in crops},
        )
        strategies, impact, opt_warnings = compare_strategies(inputs)
        trace.append(_trace("optimize", "Plan optimization", "ok", f"Compared {len(strategies)} plan strategies"))
        return {"crops": crops, "excluded": excluded, "strategies": strategies, "impact": impact,
                "opt_warnings": opt_warnings, "trace": trace}
    except Exception as exc:
        logger.warning("optimize_node failed: %s", exc)
        trace.append(_trace("optimize", "Plan optimization", "failed", "Plan optimization failed"))
        return {"crops": [], "excluded": excluded, "strategies": [], "impact": None,
                "opt_warnings": [], "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# check_feasibility — code, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def _recommended_strategy(state: dict):
    strategies = state.get("strategies", [])
    profile = state.get("profile")
    # Keep chat aligned with the direct API: QP risk allocation is not
    # selected until aligned historical joint crop-profit samples exist.
    from app.ml.constants import RISK_QP_ENABLED

    rec_id = (
        ("qp_drought_safe" if getattr(profile, "risk_appetite", None) == "safe" else "qp_balanced")
        if RISK_QP_ENABLED
        else "lp_max_profit"
    )
    rec = next((x for x in strategies if x.id == rec_id), None)
    if not rec or not rec.feasible or not rec.allocations:
        rec = next(
            (x for x in strategies if x.id != "traditional" and x.feasible and x.allocations),
            rec,
        )
    if rec is None and strategies:
        rec = strategies[0]
    return rec


def check_feasibility_node(state: dict) -> dict:
    """The optimizer applies the 4-step relaxation ladder itself; here we only read the verdict."""
    trace = list(state.get("trace", []))
    recommended = _recommended_strategy(state)

    if recommended and recommended.feasible and recommended.allocations:
        trace.append(_trace("check_feasibility", "Plan feasibility check", "ok", "A profitable plan satisfies the available land, budget, and water constraints"))
        return {"feasibility": None, "trace": trace}

    # An infeasible plan is a valid optimizer outcome, not a runtime failure.
    # Keep the trace green so the farmer can distinguish it from a broken step.
    trace.append(_trace("check_feasibility", "Plan feasibility check", "ok",
                        "No profitable plan satisfies the available land, budget, and water constraints"))
    return {"feasibility": "INFEASIBLE", "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# relax_constraint — code ladder (AG.6), no LLM
# ─────────────────────────────────────────────────────────────────────────────

def relax_constraint_node(state: dict) -> dict:
    """Apply the next step of the relaxation ladder.

    Steps (fixed order, per ml/SPECS §8.4a):
      0: CAP_TO_1            — lift diversification cap to 1.0
      1: REDUCE_AREA         — reduce planned area to budget-feasible max
      2: DROP_WATER_HUNGRY   — drop most water-hungry candidate
      3: USE_NORMAL_WATER    — use normal-scenario water limit (no longer drought-safe)
    """
    relaxation_count = state.get("relaxation_count", 0)
    relaxations = list(state.get("relaxations", []))
    trace = list(state.get("trace", []))
    candidates = list(state.get("candidates", []))

    steps = ["CAP_TO_1", "REDUCE_AREA", "DROP_WATER_HUNGRY_CROP", "USE_NORMAL_SCENARIO_WATER"]
    if relaxation_count < len(steps):
        step = steps[relaxation_count]
        relaxations.append(step)
        trace.append(_trace("relax_constraint", step, "ok", f"Applying relaxation step {relaxation_count + 1}: {step}"))

        # DROP_WATER_HUNGRY_CROP: remove the candidate with the highest normal water need
        if step == "DROP_WATER_HUNGRY_CROP" and candidates:
            def _water_need(c) -> float:
                wn = getattr(c, "water_need_m3_per_acre", None)
                if wn is None:
                    return 0.0
                sv = getattr(wn, "normal", None) or getattr(wn, "value", 0)
                return float(getattr(sv, "value", sv) or 0)

            candidates = sorted(candidates, key=_water_need)[:-1]   # drop highest

    return {
        "relaxation_count": relaxation_count + 1,
        "relaxations": relaxations,
        "candidates": candidates,
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AG.8 explain — LLM call 2 (+ retry on grounding fail)
# ─────────────────────────────────────────────────────────────────────────────

async def explain_node(state: dict) -> dict:
    """LLM call 2: generate natural-language explanation of the plan."""
    from app.agent.client import SarvamAllModelsFailed, get_sarvam_client
    from app.agent.grounding import grounding_check
    from app.agent.prompts import EXPLAIN_SYSTEM, build_explain_user_prompt, long_duration_facts
    from app.agent.templates import build_template_explanation

    language = state.get("language", "en")
    strategies = state.get("strategies", [])
    profile: FarmProfile | None = state.get("profile")
    trace = list(state.get("trace", []))

    recommended = _recommended_strategy(state)

    # Compute water saved % for the prompt
    traditional = next((s for s in strategies if s.id == "traditional"), None)
    water_saved = 0.0
    if recommended and traditional:
        rec_w = getattr(recommended, "totals", None)
        trad_w = getattr(traditional, "totals", None)
        if rec_w and trad_w:
            rw = getattr(rec_w, "water_m3", 0)
            tw = getattr(trad_w, "water_m3", 1)
            water_saved = max(0.0, (tw - rw) / max(tw, 1) * 100)

    # SHAP top factors of the first *recommended* crop that has model factors
    # (baseline-yield crops have none). Never another candidate's factors.
    rec_crop_ids = [a.crop_id for a in getattr(recommended, "allocations", []) or []]
    shap_factors: list[dict] = []
    for c in state.get("crops", []):
        if c.crop_id not in rec_crop_ids:
            continue
        s = getattr(c, "suitability", None)
        if s and getattr(s, "top_factors", None):
            shap_factors = [f.model_dump() for f in s.top_factors]
            break

    # Which farmer limits the plan actually reaches (within 1%), from plan data,
    # so the LLM never has to guess the "active" constraints.
    limiting: list[str] = []
    rec_totals = getattr(recommended, "totals", None)
    if rec_totals is not None and profile is not None:
        if rec_totals.land_used_acres >= 0.99 * profile.land_acres:
            limiting.append("land")
        if rec_totals.budget_used_rs >= 0.99 * profile.budget_rs:
            limiting.append("budget")
        wb = next((w for w in state.get("water", [])
                   if getattr(w, "scenario", None) == getattr(recommended, "safety_scenario", "normal")), None)
        avail = getattr(getattr(getattr(wb, "available_m3", None), "total", None), "value", None)
        if avail and rec_totals.water_m3 >= 0.99 * float(avail):
            limiting.append("water")
        from app.ml.optimizer import _div_cap
        cap_acres = _div_cap(len(state.get("crops", []))) * profile.land_acres
        if any(a.acres >= 0.99 * cap_acres for a in recommended.allocations):
            limiting.append("max share of land per crop (diversification rule)")

    farmer_limits = {
        "farmer_land_acres": getattr(profile, "land_acres", None),
        "farmer_budget_rs": getattr(profile, "budget_rs", None),
        "limiting_constraints": ", ".join(limiting) or "none",
    }
    system = EXPLAIN_SYSTEM.get(language, EXPLAIN_SYSTEM["en"])
    user_prompt = build_explain_user_prompt(
        recommended, water_saved, shap_factors, language, state.get("crops", []),
        limits=farmer_limits,
    )
    long_facts = long_duration_facts(recommended, state.get("crops", []))

    explanation_text = ""
    try:
        client = get_sarvam_client()
        resp = await client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1500,
        )
        raw = client.extract_text(resp)
        if not raw:
            raise ValueError("Sarvam returned empty content")
        parsed = json.loads(raw)
        explanation_text = parsed.get("text", "")
        provider = "sarvam"
    except (SarvamAllModelsFailed, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("explain: LLM failed (%s: %s); using template", type(exc).__name__, str(exc)[:200])
        # No LLM → template
        fallback = build_template_explanation(language, getattr(profile, "land_acres", 0), recommended, water_saved)
        trace.append(_trace("explain", "llm", "failed", "All models failed; using template"))
        return {
            "explanation_text": fallback.text,
            "explanation_grounded": False,
            "explanation_provider": "template",
            "water_saved_pct": water_saved,
            "trace": trace,
        }

    # Grounding check
    tool_outputs = {"strategies": [s.model_dump() for s in strategies], "water_saved_pct": water_saved,
                    "shap_factors": shap_factors, "long_crop_facts": long_facts,
                    "farmer_limits": farmer_limits}
    grounded = grounding_check(explanation_text, tool_outputs)
    retry_count = state.get("grounding_retry_count", 0)

    trace.append(_trace("explain", "llm", "ok" if grounded else "running",
                        f"Explanation generated; grounded={grounded}"))

    return {
        "explanation_text": explanation_text,
        "explanation_grounded": grounded,
        "explanation_provider": provider,
        "grounding_retry_count": retry_count + 1,
        "water_saved_pct": water_saved,
        "shap_factors": shap_factors,
        "long_crop_facts": long_facts,
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AG.9 grounding_check node — delegates to grounding.py
# ─────────────────────────────────────────────────────────────────────────────

def grounding_check_node(state: dict) -> dict:
    from app.agent.grounding import grounding_check
    from app.agent.templates import build_template_explanation

    explanation_text = state.get("explanation_text", "")
    strategies = state.get("strategies", [])
    language = state.get("language", "en")
    profile: FarmProfile | None = state.get("profile")
    retry_count = state.get("grounding_retry_count", 0)
    trace = list(state.get("trace", []))
    water_saved = state.get("water_saved_pct", 0.0)

    tool_outputs = {"strategies": [s.model_dump() for s in strategies], "water_saved_pct": water_saved,
                    "shap_factors": state.get("shap_factors", []),
                    "long_crop_facts": state.get("long_crop_facts", []),
                    # Same facts the explain prompt was given (explain_node).
                    "farmer_limits": {
                        "farmer_land_acres": getattr(profile, "land_acres", None),
                        "farmer_budget_rs": getattr(profile, "budget_rs", None),
                    }}
    grounded = grounding_check(explanation_text, tool_outputs)

    if not grounded and retry_count >= 2:
        # Max retries reached — fall back to template
        recommended = _recommended_strategy(state)
        fallback = build_template_explanation(language, getattr(profile, "land_acres", 0), recommended, water_saved)
        trace.append(_trace("grounding_check", "check", "failed", "Grounding failed twice — using template"))
        return {
            "explanation_text": fallback.text,
            "explanation_grounded": False,
            "explanation_provider": "template",
            "trace": trace,
        }

    trace.append(_trace("grounding_check", "check", "ok" if grounded else "running",
                        f"Grounded={grounded} retry={retry_count}"))
    return {"explanation_grounded": grounded, "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# respond — builds the PlanResult and emits SSE events via state
# ─────────────────────────────────────────────────────────────────────────────

def respond_node(state: dict) -> dict:
    """Build the final PlanResult from accumulated state. No LLM call."""
    from app.schemas import (
        DataStatus, FarmProfile, KeyPoint,
        Warning,
    )
    import uuid
    from datetime import datetime, timezone

    profile: FarmProfile = state.get("profile") or FarmProfile(
        location_text="unknown", land_acres=0, budget_rs=0
    )
    location: Location | None = state.get("location")
    season: Season = state.get("season") or _build_fallback_season()
    crops = state.get("crops", [])
    excluded = state.get("excluded", [])
    water = state.get("water", [])
    scenarios = state.get("scenarios", [])
    language = state.get("language", "en")
    impact = state.get("impact")

    explanation_text = state.get("explanation_text", "")
    grounded = state.get("explanation_grounded", False)
    provider = state.get("explanation_provider", "template")

    recommended = _recommended_strategy(state)
    recommended_strategy = recommended.id if recommended else None

    if not explanation_text:
        from app.agent.templates import build_template_explanation
        fallback = build_template_explanation(
            language, getattr(profile, "land_acres", 0), recommended, state.get("water_saved_pct", 0.0)
        )
        explanation_text, grounded, provider = fallback.text, False, "template"

    key_points: list[KeyPoint] = []
    if location:
        key_points.append(KeyPoint(icon="map-pin", text=f"{location.district}, {location.state}"))
    if recommended and recommended.allocations:
        key_points.append(KeyPoint(icon="coins", text=f"Rs.{recommended.expected_profit_rs:,.0f} expected profit"))

    explanation = Explanation(
        language=language,  # type: ignore[arg-type]
        text=explanation_text,
        key_points=key_points,
        grounded=grounded,
        provider=provider,
    )

    warnings: list[Warning] = list(state.get("opt_warnings", []))
    if not any(w.code == "OLD_COST_YEAR" for w in warnings):
        warnings.append(Warning(code="OLD_COST_YEAR", params={"year": "2022-23"}))
    from app.pipeline import price_warnings
    warnings.extend(price_warnings(crops, warnings))

    # Same borewell disclosure as run_plan (/api/plan): unknown capacity => 0 m3 credited, said openly.
    from app.services.water import borewell_disclosure
    profile, bw_warnings = borewell_disclosure(profile)
    warnings.extend(w for w in bw_warnings if not any(x.code == w.code for x in warnings))

    infeasibility = None
    if recommended and not recommended.feasible:
        infeasibility = recommended.infeasibility
    if recommended:
        from app.pipeline import _populate_water_needs
        water = _populate_water_needs(water, crops, state.get("strategies", []), recommended_strategy)

    # A later chat turn on the same thread is a new VERSION of the same plan.
    prior = state.get("plan_result")
    prior_version = getattr(prior, "version", None)
    prior_id = getattr(prior, "plan_id", None)

    plan = PlanResult(
        plan_id=prior_id or state.get("plan_id") or f"pl_{uuid.uuid4().hex}",
        thread_id=state.get("thread_id", f"th_{uuid.uuid4().hex}"),
        version=(prior_version + 1) if prior_version else 1,
        previous_version=prior_version or None,
        created_at=datetime.now(tz=timezone.utc),
        profile=profile,
        location=location or Location(
            input=profile.location_text,
            resolved_name=profile.location_text,
            district="Unknown",
            state="Maharashtra",
            latitude=0.0,
            longitude=0.0,
        ),
        season=season,
        scenarios=scenarios,
        crops=crops,
        excluded_crops=excluded,
        water=water,
        strategies=state.get("strategies", []),
        recommended_strategy=recommended_strategy,
        impact=impact,
        infeasibility=infeasibility,
        explanation=explanation,
        warnings=warnings,
        data_status=DataStatus(live=0, cached=0, official_dataset=0),
    )
    # Real counts from the SourcedValue statuses inside the plan (same helper as /api/plan).
    from app.services.data_status import count_data_status
    plan = plan.model_copy(update={"data_status": count_data_status(plan)})

    return {"plan_result": plan}


# ─────────────────────────────────────────────────────────────────────────────
# answer_from_memory — follow-up / question handler, no LLM for routing
# ─────────────────────────────────────────────────────────────────────────────

async def answer_from_memory_node(state: dict) -> dict:
    """Answer an informational follow-up from the saved farm profile.

    Fact updates are re-extracted by the graph; questions without changed facts
    are answered directly so they do not re-run the optimizer.
    """
    # A changed fact (number, irrigation detail, risk preference) is a
    # follow-up update, not a question. Let the graph extract and optimize it.
    if state.get("route") == "follow_up":
        return {"route": "follow_up"}

    profile: FarmProfile | None = state.get("profile")
    if profile is None:
        return {"route": "follow_up"}

    language = state.get("language", "en")
    location = profile.location_text
    acres = f"{profile.land_acres:g}"
    budget = f"{profile.budget_rs:,.0f}"
    if language == "mr":
        text = f"तुमच्या जतन केलेल्या शेत माहितीनुसार ठिकाण {location}, क्षेत्र {acres} एकर आणि बजेट ₹{budget} आहे."
    elif language == "hi":
        text = f"आपकी सहेजी हुई खेत जानकारी के अनुसार स्थान {location}, क्षेत्र {acres} एकड़ और बजट ₹{budget} है।"
    else:
        text = f"From your saved farm profile: the location is {location}, the farm size is {acres} acres, and the budget is ₹{budget}."

    trace = list(state.get("trace", []))
    trace.append(_trace("answer_from_memory", "Saved farm profile", "ok", "Answered from this conversation's saved farm details"))
    return {
        "route": "question_answered",
        "explanation_text": text,
        "explanation_grounded": True,
        "explanation_provider": "memory",
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# save_memory — persist state to checkpointer (LangGraph does this automatically;
# this node is a no-op hook for any extra app-level persistence)
# ─────────────────────────────────────────────────────────────────────────────

async def save_memory_node(state: dict) -> dict:
    """LangGraph checkpoints state automatically. LangGraph requires every node to
    write at least one key, so this re-writes an unchanged value."""
    return {"no_data": state.get("no_data", False)}
