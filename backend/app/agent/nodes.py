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
        id=f"ev_{uuid.uuid4().hex[:6]}",
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
        return {"profile_patch": None, "route": "new_plan"}

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

    updated = FarmProfile(**profile_data)
    return {
        "profile": updated,
        "profile_patch": None,
        "route": "follow_up",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AG.3 extract_profile — LLM call 1
# ─────────────────────────────────────────────────────────────────────────────

async def extract_profile_node(state: dict) -> dict:
    """LLM call 1: turn farmer's message into a FarmProfile."""
    from app.agent.client import SarvamAllModelsFailed, get_sarvam_client
    from app.agent.prompts import EXTRACT_PROFILE_SYSTEM

    language = state.get("language", "en")
    message = state.get("message", "")
    trace = list(state.get("trace", []))
    t0 = _now()

    system_prompt = EXTRACT_PROFILE_SYSTEM.get(language, EXTRACT_PROFILE_SYSTEM["en"])

    profile_data: dict = {}
    try:
        client = get_sarvam_client()
        resp = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=400,
        )
        raw = client.extract_text(resp)
        if not raw:
            raise ValueError("Sarvam returned empty content")
        profile_data = json.loads(raw)
    except SarvamAllModelsFailed:
        logger.warning("extract_profile: all Sarvam models failed — using regex fallback")
        profile_data = _regex_profile_fallback(message)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("extract_profile: parse error %s — using regex fallback", exc)
        profile_data = _regex_profile_fallback(message)
    except Exception as exc:
        logger.warning("extract_profile: unexpected error %s — using regex fallback", exc)
        profile_data = _regex_profile_fallback(message)

    # Post-LLM normalisation (plain code)
    profile_data = _normalise_profile(profile_data, state.get("profile"))

    # Work out which required fields are still missing
    missing = []
    for field in ("location_text", "land_acres", "budget_rs"):
        val = profile_data.get(field)
        if not val:
            missing.append(field)

    # Fill in placeholder values for required fields so Pydantic doesn't fail.
    # The 'missing' list tells ask_missing_node to prompt the farmer for the real values.
    safe_data = {k: v for k, v in profile_data.items() if k in FarmProfile.model_fields}
    safe_data.setdefault("location_text", "unknown")  # placeholder until farmer provides it
    safe_data.setdefault("land_acres", 0.0)
    safe_data.setdefault("budget_rs", 0.0)

    duration_ms = int((_now() - t0).total_seconds() * 1000)
    trace.append(_trace("extract_profile", "llm", "ok", f"Extracted profile; missing={missing}", duration_ms))

    try:
        profile_obj = FarmProfile(**safe_data)
    except Exception as exc:
        logger.warning("extract_profile: FarmProfile construction failed %s — empty profile", exc)
        profile_obj = FarmProfile(location_text="unknown", land_acres=0.0, budget_rs=0.0)
        missing = ["location_text", "land_acres", "budget_rs"]

    return {"profile": profile_obj, "missing": missing, "trace": trace}


def _regex_profile_fallback(message: str) -> dict:
    """Best-effort profile extraction without the LLM."""
    data: dict[str, Any] = {}
    msg_norm = _devanagari_to_ascii(message)

    # Location — first title-case word > 3 chars
    loc = re.search(r"\b([A-Z][a-z]{3,})\b", message)
    if loc:
        data["location_text"] = loc.group(1)

    # Acres
    acres = re.search(r"(\d+(?:\.\d+)?)\s*(?:एकर|acre|acres?)", msg_norm, re.IGNORECASE)
    if acres:
        data["land_acres"] = float(acres.group(1))

    # Guntha
    guntha = re.search(r"(\d+(?:\.\d+)?)\s*(?:गुंठे?|guntha)", msg_norm, re.IGNORECASE)
    if guntha:
        data["land_acres"] = float(guntha.group(1)) * 0.025

    # Budget
    budget = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(?:रुपये?|₹|rs\.?|rupees?)", msg_norm, re.IGNORECASE)
    if budget:
        raw = _extract_float(_parse_number_words(budget.group(1)))
        if raw:
            data["budget_rs"] = raw

    # Water source
    if re.search(r"borewell|बोअरवेल|boring", msg_norm, re.IGNORECASE):
        data["water_source"] = "borewell"
    elif re.search(r"canal|कालवा", msg_norm, re.IGNORECASE):
        data["water_source"] = "canal"
    elif re.search(r"rainfed|कोरडवाहू|rain", msg_norm, re.IGNORECASE):
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

    if not missing:
        return {}

    from app.agent.prompts import ASK_MISSING
    field = missing[0]
    questions = ASK_MISSING.get(field, {})
    question_text = questions.get(language, questions.get("en", f"Please provide {field}."))

    trace.append(_trace("ask_missing", field, "ok", f"Asking for {field}"))
    # The question_text is picked up by the SSE mapper in agent.py via state["question"]
    return {"question": {"text": question_text, "field": field, "language": language}, "trace": trace}


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
        except AppError as e:
            return "location", None, str(e)
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
            s = await tools.get_soil(location)
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
    from app.schemas import SowingWindow
    today = date.today()
    year = today.year
    return Season(
        name="Rabi",
        sowing_window=SowingWindow(start=f"{year}-10-15", end=f"{year}-12-15"),
        status="official_dataset",
    )


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
        trace.append(_trace("recommend_crops", "ml1", "ok", f"{len(candidates)} candidates, {len(excluded)} excluded"))
        return {"candidates": candidates, "excluded": excluded, "trace": trace}
    except NotImplementedError:
        trace.append(_trace("recommend_crops", "ml1", "skipped", "ML stub not implemented"))
        return {"candidates": [], "excluded": [], "no_data": True, "trace": trace}
    except Exception as exc:
        logger.warning("recommend_crops failed: %s", exc)
        trace.append(_trace("recommend_crops", "ml1", "failed", str(exc)))
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

        trace.append(_trace("predict_yield", "ml4", "ok", f"Yields for {len(scenario_yields)} crops"))
    except Exception as exc:
        trace.append(_trace("predict_yield", "ml4", "failed", str(exc)))

    return {"scenario_yields": scenario_yields, "long_duration_crops": long_duration_crops, "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# optimize — calls ML optimizer stubs, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def optimize_node(state: dict) -> dict:
    from app.agent import tools
    from app.schemas import OptimizerInputs

    trace = list(state.get("trace", []))
    profile: FarmProfile = state["profile"]
    location: Location = state["location"]
    season: Season = state.get("season") or _build_fallback_season()
    candidates = state.get("candidates", [])
    water = state.get("water", [])

    try:
        inputs = OptimizerInputs(
            profile=profile,
            location=location,
            season=season,
            candidates=candidates,
            water_budgets=water,
            scenario_weights=[0.2, 0.6, 0.2],
            price_history_years={},
        )
        strategies = tools.compare_strategies(inputs)
        trace.append(_trace("optimize", "opt3", "ok", f"{len(strategies)} strategies"))
        return {"strategies": strategies, "trace": trace}
    except NotImplementedError:
        trace.append(_trace("optimize", "opt3", "skipped", "ML optimizer stub not implemented"))
        return {"strategies": [], "trace": trace}
    except Exception as exc:
        logger.warning("optimize_node failed: %s", exc)
        trace.append(_trace("optimize", "opt3", "failed", str(exc)))
        return {"strategies": [], "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# check_feasibility — code, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def check_feasibility_node(state: dict) -> dict:
    strategies = state.get("strategies", [])
    relaxation_count = state.get("relaxation_count", 0)
    trace = list(state.get("trace", []))

    # Find the recommended (QP balanced) strategy
    recommended = next((s for s in strategies if s.id == "qp_balanced"), None)
    if recommended is None and strategies:
        recommended = strategies[0]

    if recommended and recommended.feasible:
        trace.append(_trace("check_feasibility", "check", "ok", "Plan feasible"))
        return {"feasibility": None, "trace": trace}

    if relaxation_count >= 4:
        trace.append(_trace("check_feasibility", "check", "failed", "Still infeasible after max relaxations"))
        return {"feasibility": "INFEASIBLE", "trace": trace}

    trace.append(_trace("check_feasibility", "check", "running", f"Infeasible; relaxation attempt {relaxation_count + 1}"))
    return {"feasibility": "NEEDS_RELAX", "trace": trace}


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
    from app.agent.prompts import EXPLAIN_SYSTEM, build_explain_user_prompt
    from app.agent.templates import build_template_explanation

    language = state.get("language", "en")
    strategies = state.get("strategies", [])
    profile: FarmProfile | None = state.get("profile")
    trace = list(state.get("trace", []))

    recommended = next((s for s in strategies if s.id == "qp_balanced"), None)
    if recommended is None and strategies:
        recommended = strategies[0]

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

    # SHAP top factors from first candidate's suitability
    shap_factors: list[dict] = []
    for c in state.get("candidates", [])[:1]:
        s = getattr(c, "suitability", None)
        if s:
            shap_factors = [f.model_dump() for f in (getattr(s, "top_factors", []) or [])]

    system = EXPLAIN_SYSTEM.get(language, EXPLAIN_SYSTEM["en"])
    user_prompt = build_explain_user_prompt(recommended, water_saved, shap_factors, language)

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
            max_tokens=300,
        )
        raw = client.extract_text(resp)
        if not raw:
            raise ValueError("Sarvam returned empty content")
        parsed = json.loads(raw)
        explanation_text = parsed.get("text", "")
        provider = "sarvam"
    except (SarvamAllModelsFailed, json.JSONDecodeError, ValueError, TypeError):
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
    tool_outputs = {"strategies": [s.model_dump() for s in strategies], "water_saved_pct": water_saved}
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

    tool_outputs = {"strategies": [s.model_dump() for s in strategies], "water_saved_pct": water_saved}
    grounded = grounding_check(explanation_text, tool_outputs)

    if not grounded and retry_count >= 2:
        # Max retries reached — fall back to template
        recommended = next((s for s in strategies if s.id == "qp_balanced"), None)
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
    strategies = state.get("strategies", [])
    candidates = state.get("candidates", [])
    excluded = state.get("excluded", [])
    water = state.get("water", [])
    scenarios = state.get("scenarios", [])
    language = state.get("language", "en")

    explanation_text = state.get("explanation_text", "")
    grounded = state.get("explanation_grounded", False)
    provider = state.get("explanation_provider", "template")

    # Build explanation
    key_points: list[KeyPoint] = []
    if location:
        key_points.append(KeyPoint(icon="map-pin", text=f"{location.district}, {location.state}"))

    recommended_strategy = None
    if strategies:
        qp = next((s for s in strategies if s.id == "qp_balanced"), None)
        if qp:
            recommended_strategy = qp.id
            key_points.append(KeyPoint(icon="coins", text=f"Rs.{qp.expected_profit_rs:,.0f} expected profit"))

    explanation = Explanation(
        language=language,  # type: ignore[arg-type]
        text=explanation_text or f"Plan for {location.district if location else 'your farm'}.",
        key_points=key_points,
        grounded=grounded,
        provider=provider,
    )

    warnings: list[Warning] = [Warning(code="OLD_COST_YEAR", params={"year": "2022-23"})]

    plan = PlanResult(
        plan_id=state.get("plan_id") or f"pl_{uuid.uuid4().hex[:6]}",
        thread_id=state.get("thread_id", f"th_{uuid.uuid4().hex[:8]}"),
        version=1,
        previous_version=None,
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
        crops=candidates,
        excluded_crops=excluded,
        water=water,
        strategies=strategies,
        recommended_strategy=recommended_strategy,
        impact=None,
        infeasibility=None,
        explanation=explanation,
        warnings=warnings,
        data_status=DataStatus(live=0, cached=0, official_dataset=18),
    )

    return {"plan_result": plan}


# ─────────────────────────────────────────────────────────────────────────────
# answer_from_memory — follow-up / question handler, no LLM for routing
# ─────────────────────────────────────────────────────────────────────────────

async def answer_from_memory_node(state: dict) -> dict:
    """Handle follow-ups and questions about the existing plan.

    For a changed-fact follow-up: patch the profile and re-run from gather_data.
    For a question: use the LLM to answer from stored state (counts as call 1 of 3).
    """
    # For now, treat both as re-run triggers — the graph loops back to gather_data
    # via the follow_up route, which reuses cached data and is fast.
    return {"route": "follow_up"}


# ─────────────────────────────────────────────────────────────────────────────
# save_memory — persist state to checkpointer (LangGraph does this automatically;
# this node is a no-op hook for any extra app-level persistence)
# ─────────────────────────────────────────────────────────────────────────────

async def save_memory_node(state: dict) -> dict:
    """LangGraph saves state automatically. This node is a no-op."""
    return {}
