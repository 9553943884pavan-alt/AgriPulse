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


# One mapping table: (node, step) or node -> (tool_name, display_name).
_TRACE_TOOLS: dict[tuple[str, str] | str, tuple[str, str]] = {
    ("plan", "started"): ("planner", "Planning Started"),
    ("plan", "failed"): ("planner", "Planning Failed"),
    ("persist", "saved"): ("plan_saved", "Plan Saved"),
    ("persist", "failed"): ("plan_saved", "Plan Saved"),
    ("gather_data", "location"): ("location_resolver", "Location Lookup"),
    ("gather_data", "weather"): ("weather_service", "Weather Data"),
    ("gather_data", "soil"): ("soil_service", "Soil Data"),
    ("gather_data", "scenarios"): ("scenario_builder", "Weather Scenarios"),
    ("gather_data", "water"): ("water_analyzer", "Water Availability Analysis"),
    ("gather_data", "prices"): ("market_price_service", "Market Price Analysis"),
    ("gather_data", "complete"): ("data_collector", "Data Collection"),
    ("optimize", "costs"): ("cost_calculator", "Cultivation Cost Estimation"),
    ("optimize", "prices"): ("market_price_service", "Market Price Analysis"),
    "extract_profile": ("profile_extractor", "Farm Profile"),
    "merge_patch": ("profile_extractor", "Farm Profile"),
    "ask_missing": ("profile_extractor", "Farm Profile"),
    "recommend_crops": ("crop_recommender", "Crop Recommendation"),
    "predict_yield": ("yield_predictor", "Yield Prediction"),
    "optimize": ("optimizer", "Farm Plan Optimization"),
    "check_feasibility": ("strategy_selector", "Strategy Comparison"),
    "relax_constraint": ("constraint_relaxer", "Constraint Relaxation"),
    "explain": ("plan_explainer", "Plan Explanation"),
    "grounding_check": ("plan_reviewer", "Plan Review"),
    "answer_from_memory": ("saved_plan_reader", "Answer from Saved Plan"),
    "respond": ("plan_builder", "Plan Result"),
}


def _trace(
    node: str,
    step: str,
    status: str,
    summary: str,
    duration_ms: int = 0,
    *,
    started: datetime | None = None,
    completed: datetime | None = None,
    fallback_used: str | None = None,
) -> TraceEvent:
    """Build a trace item. Pass `started` (a _now() taken before the work) so that
    started_at / completed_at / duration_ms are measured, not guessed."""
    completed = completed or _now()
    if started is not None:
        started_at = started
        duration_ms = max(0, int((completed - started).total_seconds() * 1000))
    else:
        started_at = completed
    tool_name, display_name = _TRACE_TOOLS.get((node, step)) or _TRACE_TOOLS.get(node) or (None, None)
    return TraceEvent(
        id=f"ev_{uuid.uuid4().hex}",
        node=node,
        step=step,
        status=status,  # type: ignore[arg-type]
        started_at=started_at,
        duration_ms=duration_ms,
        summary=summary,
        source=None,
        fallback_used=fallback_used,
        tool_name=tool_name,
        display_name=display_name,
        completed_at=completed,
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

# Words that change the farm itself (water source / irrigation) and phrases that
# introduce a location. Either one means "re-plan", never a canned memory answer.
_FARM_CHANGE_WORDS = (
    "borewell", "bore well", "canal", "rainfed", "drip", "sprinkler", "flood",
    "बोअरवेल", "बोरवेल", "कालवा", "नहर", "ठिबक", "तुषार", "कोरडवाहू", "बारिश",
    # Marathi / Hindi location words ("my farm is in ...", district, village)
    "येथे", "येथील", "जिल्हा", "जिल्ह्यात", "गावात", "ज़िला", "जिला", "गांव", "गाँव", "मेरा खेत",
)
_LOCATION_PHRASE_RE = re.compile(
    r"\b(i am from|i'm from|my farm is (in|at|near)|my village|i live in|located in|change (my )?location)\b",
    re.IGNORECASE,
)


def _mentions_farm_change(message: str, profile) -> bool:
    """True when the message changes the farm: a district other than the saved one,
    a location phrase, or a water / irrigation word."""
    msg = message.lower()
    if _LOCATION_PHRASE_RE.search(msg) or any(w in msg for w in _FARM_CHANGE_WORDS):
        return True
    current = (getattr(profile, "location_text", "") or "").lower()
    try:
        from app.data.loaders import load_districts
        variants = load_districts()["name_variants"]
    except Exception:
        return False
    for names in variants:
        for name in str(names).split("|"):
            name = name.strip().lower()
            if len(name) >= 4 and name not in current and re.search(rf"\b{re.escape(name)}\b", msg):
                return True
    return False


# Small-talk: the WHOLE message is a greeting / thanks / help request. Anything
# longer ("hi, plan my farm") is a real request and goes through the normal route.
_SMALLTALK_RE = re.compile(
    r"^\s*(?:"
    r"(?P<greet>hello|hi+|hey+|namaste|namaskar|namaskara|namaskaara|good\s+(?:morning|afternoon|evening|night)"
    r"|नमस्कार|नमस्ते|राम\s*राम)"
    r"|(?P<thanks>thanks?(?:\s+a\s+lot)?|thank\s+you(?:\s+(?:so\s+much|very\s+much))?|thx|dhanyavad|dhanyawad"
    r"|धन्यवाद|आभारी\s+आहे|आभार|शुक्रिया)"
    r"|(?P<help>help(?:\s+me)?|what\s+can\s+you\s+do|who\s+are\s+you|what\s+are\s+you|what\s+is\s+this"
    r"|मदत|मदत\s+करा|तुम्ही\s+कोण\s+आहात|आप\s+कौन\s+हैं|आप\s+क्या\s+कर\s+सकते\s+हैं|मदद|मदद\s+करो|सहायता)"
    r")(?:\s+(?:there|friend|sir|madam|ji|bhai))?[\s!.,?🙏👋]*$",
    re.IGNORECASE,
)
_KANNADA_RE = re.compile("[ಀ-೿]")
_KANNADA_GREETING_RE = re.compile(r"^\s*(?:namaskara|namaskaara|ನಮಸ್ಕಾರ)[\s!.,?🙏👋]*$", re.IGNORECASE)

# A request to (re)make a plan. Question-style messages about an existing plan
# ("why ... plan") are excluded so they stay plan Q&A.
_PLANNING_INTENT_RE = re.compile(
    r"\b(plan|planning|replan|recommend\w*|suggest\w*|profitable|optimi[sz]e\w*|"
    r"(?:what|which)\s+(?:crops?\s+)?(?:should|can|do|to)\s+i\s+(?:grow|sow|plant|cultivate|raise)|"
    r"which\s+crops?|best\s+crops?|crop\s+advice)\b"
    r"|आराखडा|आराखडे|योजना|नियोजन|पीक\s*सुचवा|पिके\s*सुचवा|पीक\s*सुझाव|कोणते\s+पीक|"
    r"फसल\s*योजना|फसल\s*सुझाव|फसलें?\s*सुझाइए|कौन\s*सी\s*फसल|कौनसी\s*फसल",
    re.IGNORECASE,
)
_PLAN_QUESTION_RE = re.compile(
    r"\b(why|explain|how\s+come|reason|because)\b|क्यों|क्यूँ|कारण|का\s+निवडले|कशासाठी|कशाला|समजावून|समझाइए|समझाओ",
    re.IGNORECASE,
)


def is_planning_intent(message: str) -> bool:
    """True when the farmer asks for a (new) plan / crop recommendation."""
    msg = message or ""
    return bool(_PLANNING_INTENT_RE.search(msg)) and not _PLAN_QUESTION_RE.search(msg)


def smalltalk_kind(message: str) -> str | None:
    """'greeting' | 'thanks' | 'help' | 'kannada' | 'kannada_greeting' | None.

    Deterministic and tool-free: no LLM, no extraction."""
    msg = message or ""
    if _KANNADA_GREETING_RE.match(msg):
        return "kannada_greeting"
    if _KANNADA_RE.search(msg):
        return "kannada"
    m = _SMALLTALK_RE.match(msg)
    if not m:
        return None
    if m.group("greet"):
        return "greeting"
    if m.group("thanks"):
        return "thanks"
    return "help"


def route_node(state: dict) -> dict:
    """Decide the path: smalltalk / new_plan / follow_up / patch / question.

    patch:      profile_patch is set (farmer edited the card directly, no message).
    smalltalk:  greeting / thanks / help / Kannada text: a fixed reply, no tools, no LLM.
    new_plan:   no plan yet, or the farmer asked for a plan (saved profile is reused).
    follow_up:  plan exists AND message contains a changed fact (number, crop, risk word).
    question:   plan exists AND message is a question with no changed fact.
    """
    if state.get("intent") == "optimize":
        # Optimize button: re-plan from the saved profile. No routing guess, no extraction.
        return {"route": "new_plan", "plan_only": True}

    if state.get("profile_patch"):
        return {"route": "patch"}

    message = state.get("message", "") or ""

    if smalltalk_kind(message):
        return {"route": "smalltalk"}

    has_plan = bool(state.get("strategies"))

    # Check for changed facts in message
    has_number = bool(re.search(r"\d", _devanagari_to_ascii(message)))
    risk_words = {"safe", "balanced", "aggressive", "सुरक्षित", "संतुलित"}
    has_risk_word = any(w in message.lower() for w in risk_words)
    changed_fact = has_number or has_risk_word or _mentions_farm_change(message, state.get("profile"))

    if is_planning_intent(message):
        # "Make a plan" re-uses the saved profile as-is. Without a new fact in the
        # message there is nothing for the LLM to extract, so it is skipped.
        return {"route": "new_plan", "plan_only": not changed_fact}
    if not has_plan:
        return {"route": "new_plan", "plan_only": False}
    if changed_fact:
        return {"route": "follow_up", "plan_only": False}
    # Question about the existing plan
    return {"route": "question", "plan_only": False}


# ─────────────────────────────────────────────────────────────────────────────
# merge_patch — rule-based, no LLM  (profile card edit via E1 profile_patch)
# ─────────────────────────────────────────────────────────────────────────────

def merge_patch_node(state: dict) -> dict:
    """Merge profile_patch into profile. No LLM call."""
    t0 = _now()
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
    trace = list(state.get("trace", []))
    if not missing:
        # First item of the turn: the data tools run next.
        trace.append(_trace("plan", "started", "ok", "Planning started for your farm", started=t0, completed=t0))
    trace.append(_trace("merge_patch", "card_edit", "ok", "Farm profile updated from your edit", started=t0))
    return {
        "profile": updated,
        "profile_patch": None,
        "missing": missing,
        "route": "follow_up",
        "trace": trace,
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
    first_new = len(trace)   # this node's trace items start here
    existing: FarmProfile | None = state.get("profile")
    pending = state.get("pending_field")
    asked = list(state.get("asked_fields") or [])

    # If the previous turn asked the borewell question, read the answer with rules
    # first: "5000 litres, 6 hours" or "I don't know" needs no LLM call.
    answer = parse_borewell_answer(message) if pending == "borewell_capacity" and existing else None
    answered_by_rules = bool(answer and (answer["dont_know"] or answer["values"]))
    # "Make a plan" with a saved profile and no new fact in the message: nothing to extract.
    plan_only = bool(state.get("plan_only")) and existing is not None

    if answered_by_rules or plan_only:
        profile_data: dict = {}
        step = "rules"
    else:
        profile_data = await _llm_extract(state, language, message)
        step = "llm"
        if existing is not None:
            # A clear money amount ("only Rs 50,000") is read by rule so a missed or
            # hallucinated LLM value can never decide the new budget.
            explicit_budget = _explicit_budget(message)
            if explicit_budget:
                profile_data["budget_rs"] = explicit_budget
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

    _field_names = {"location_text": "location", "land_acres": "farm size", "budget_rs": "budget"}
    if missing:
        profile_summary = "Farm profile read; still needed: " + ", ".join(_field_names.get(m, m) for m in missing)
    elif plan_only:
        profile_summary = "Using your saved farm profile"
    else:
        profile_summary = "Farm profile read from your message"
    trace.append(_trace("extract_profile", step, "ok", profile_summary, started=t0))

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

    if not missing and not optional_ask:
        # The next node runs the data tools: "Planning started" is the first item of the turn.
        trace.insert(first_new, _trace("plan", "started", "ok", "Planning started for your farm", started=t0, completed=t0))
    profile_obj = _drop_stale_seed_marks(profile_obj)

    return {
        "profile": profile_obj,
        "missing": missing,
        "optional_ask": optional_ask,
        "pending_field": None,
        "trace": trace,
    }


SEED_BASIS = "farmer_input (saved Farm Profile)"


def _drop_stale_seed_marks(profile: FarmProfile) -> FarmProfile:
    """A field the farmer has since changed is no longer the saved-profile value: drop its mark."""
    keep = []
    for d in profile.defaults_used:
        if d.basis == SEED_BASIS:
            current = getattr(profile, d.field, None)
            try:
                same = float(current) == float(d.value)
            except (TypeError, ValueError):
                same = str(current) == str(d.value)
            if not same:
                continue
        keep.append(d)
    if len(keep) == len(profile.defaults_used):
        return profile
    return profile.model_copy(update={"defaults_used": keep})


_BUDGET_CUE_RE = re.compile(
    r"\b(budget|capital|only|just|now|have|with|total|left|spend|invest\w*|if)\b"
    r"|बजेट|बजट|भांडवल|फक्त|केवळ|सिर्फ|केवल|आता|अब|पैसे|पैसा",
    re.IGNORECASE,
)
_NOT_BUDGET_RE = re.compile(r"quintal|क्विंटल|per\s+kg|/\s*kg|per\s+acre|/\s*acre|प्रति|per\s+hectare", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?P<pre>₹|\brs\b\.?|\binr\b|\brupees?\b|रुपये|रुपए|रुपया|\bरु\b\.?)?\s*"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<mult>lakhs?|lacs?|लाख|crores?|करोड़?|thousand|hazar|हजार|हज़ार|k\b)?\s*"
    r"(?P<post>₹|\brs\b|\binr\b|\brupees?\b|रुपये|रुपए|रुपया|\bरु\b)?",
    re.IGNORECASE,
)
_MULT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "लाख": 1e5, "crore": 1e7, "crores": 1e7,
         "करोड": 1e7, "करोड़": 1e7, "thousand": 1e3, "hazar": 1e3, "हजार": 1e3, "हज़ार": 1e3, "k": 1e3}


def _explicit_budget(message: str) -> float | None:
    """A money amount the farmer states with a currency sign or word (₹50,000, Rs 2 lakh,
    50 हजार रुपये). Bare numbers are ignored. Returns rupees, or None."""
    text = _devanagari_to_ascii(message or "")
    if _NOT_BUDGET_RE.search(text) or not _BUDGET_CUE_RE.search(text):
        return None
    for m in _MONEY_RE.finditer(text):
        if not (m.group("pre") or m.group("post") or m.group("mult")):
            continue
        try:
            value = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        mult = _MULT.get((m.group("mult") or "").lower(), 1.0)
        value *= mult
        if value > 0:
            return value
    return None


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

    _asked = {"location_text": "your location", "land_acres": "your farm size", "budget_rs": "your budget",
              "borewell_capacity": "your borewell details"}.get(field, "one more detail")
    trace.append(_trace("ask_missing", field, "ok", f"Asked for {_asked}", started=_now()))
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

def _live_or_cached(values) -> tuple[str, str | None]:
    """('ok' | 'cached', fallback_used) from the SourcedValue statuses of a fetched dict."""
    items = values.values() if isinstance(values, dict) else values
    statuses = {getattr(v, "status", None) for v in items if v is not None}
    if "cached" in statuses and "live" not in statuses:
        return "cached", "cached data (live source unavailable)"
    return "ok", None


async def gather_data_node(state: dict) -> dict:
    """Run location + weather + soil in parallel, then scenarios + water.

    Every sub-step is traced with its real timing and outcome. A step that failed or
    returned nothing is marked "failed"/"skipped", never "ok". Exception text is only
    logged server-side; the trace carries a short friendly summary.
    """
    from app.agent import tools
    from app.core.errors import AppError

    profile: FarmProfile = state["profile"]
    trace = list(state.get("trace", []))
    updates: dict = {}
    t0 = _now()

    # Stage 1 — parallel: location, weather, soil. Each returns (key, value, failed, started, completed).
    async def _locate():
        started = _now()
        try:
            loc = await tools.get_location(profile.location_text)
            return "location", loc, False, started, _now()
        except AppError:
            # An unknown / non-agricultural place is a user-facing error, not
            # "no profitable plan": surface it as the same structured error that
            # /api/plan returns (LOCATION_NOT_FOUND etc.) via the SSE error event.
            raise
        except Exception:
            logger.warning("gather_data: location lookup failed", exc_info=True)
            return "location", None, True, started, _now()

    async def _weather(location):
        started = _now()
        try:
            wx = await tools.get_weather(location)
            return "weather", wx, False, started, _now()
        except Exception:
            logger.warning("gather_data: weather fetch failed", exc_info=True)
            return "weather", {}, True, started, _now()

    async def _soil(location):
        started = _now()
        try:
            s = await tools.get_soil(profile, location)
            return "soil", s, False, started, _now()
        except Exception:
            logger.warning("gather_data: soil fetch failed", exc_info=True)
            return "soil", {}, True, started, _now()

    # Resolve location first (others depend on it)
    _, location, loc_failed, loc_started, loc_done = await _locate()
    if location is None:
        trace.append(_trace("gather_data", "location", "failed",
                            "Could not look up this location", started=loc_started, completed=loc_done))
        return {"location": None, "no_data": True, "trace": trace}

    updates["location"] = location
    trace.append(_trace("gather_data", "location", "ok", f"Location found: {location.district}",
                        started=loc_started, completed=loc_done))

    gaps: list[str] = []      # non-critical sub-steps that did not deliver
    critical: list[str] = []  # sub-steps the plan cannot be built without

    # Parallel weather + soil
    results = await asyncio.gather(_weather(location), _soil(location), return_exceptions=False)
    labels = {"weather": ("Weather data", "weather forecast and recent rainfall"),
              "soil": ("Soil data", "soil properties")}
    for key, value, failed, started, done in results:
        updates[key] = value
        title, what = labels[key]
        if failed:
            gaps.append(key)
            trace.append(_trace("gather_data", key, "failed",
                                f"{title} unavailable; planning continues without it",
                                started=started, completed=done))
        elif not value:
            gaps.append(key)
            trace.append(_trace("gather_data", key, "skipped", f"No {what} returned",
                                started=started, completed=done))
        else:
            status, fallback = _live_or_cached(value)
            if key == "soil" and {getattr(v, "status", None) for v in value.values() if v is not None} == {"official_dataset"}:
                fallback = "district soil dataset"
            summary = f"{title} loaded" + (f" (using {fallback})" if fallback else "")
            trace.append(_trace("gather_data", key, status, summary,
                                started=started, completed=done, fallback_used=fallback))

    # Stage 2 — sequential: scenarios, then water budgets
    season: Season = state.get("season") or _build_fallback_season()

    s_started = _now()
    try:
        scenarios = tools.build_scenarios(location, season)
        updates["scenarios"] = scenarios
        if scenarios:
            trace.append(_trace("gather_data", "scenarios", "ok",
                                f"{len(scenarios)} weather scenarios built", started=s_started))
        else:
            critical.append("scenarios")
            trace.append(_trace("gather_data", "scenarios", "failed",
                                "No weather scenarios could be built", started=s_started))
    except NotImplementedError:
        updates["scenarios"] = []
        critical.append("scenarios")
        trace.append(_trace("gather_data", "scenarios", "skipped",
                            "Weather scenarios are not available", started=s_started))
    except Exception:
        logger.warning("gather_data: scenario build failed", exc_info=True)
        updates["scenarios"] = []
        critical.append("scenarios")
        trace.append(_trace("gather_data", "scenarios", "failed",
                            "Weather scenarios could not be built", started=s_started))

    # Water budgets
    if updates.get("scenarios"):
        w_started = _now()
        try:
            wb = await tools.get_water_budget(profile, location, updates["scenarios"], updates.get("weather", {}))
            updates["water"] = wb
            if wb:
                trace.append(_trace("gather_data", "water", "ok",
                                    f"Water availability worked out for {len(wb)} scenarios", started=w_started))
            else:
                critical.append("water")
                trace.append(_trace("gather_data", "water", "failed",
                                    "No water availability could be worked out", started=w_started))
        except Exception:
            logger.warning("gather_data: water budget failed", exc_info=True)
            updates["water"] = []
            critical.append("water")
            trace.append(_trace("gather_data", "water", "failed",
                                "Water availability could not be worked out", started=w_started))
    else:
        updates["water"] = []
        critical.append("water")
        trace.append(_trace("gather_data", "water", "skipped",
                            "Skipped: no weather scenarios to work from"))

    # Crop prices and costs are fetched per crop inside the optimisation step, which
    # traces them itself. Nothing is fetched here, so nothing is reported here.
    updates["prices"] = {}

    if critical:
        status, summary = "failed", "Data collection incomplete: " + ", ".join(critical) + " unavailable"
    elif gaps:
        status, summary = "ok", "Data collected; unavailable: " + ", ".join(gaps)
    else:
        status, summary = "ok", "Location, weather, soil, scenarios and water data collected"
    trace.append(_trace("gather_data", "complete", status, summary, started=t0))
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
    t0 = _now()

    try:
        candidates, excluded = tools.recommend_crops(profile, location, season, water)
        trace.append(_trace("recommend_crops", "Crop recommendations", "ok", f"{len(candidates)} suitable crops found, {len(excluded)} excluded", started=t0))
        return {"candidates": candidates, "excluded": excluded, "trace": trace}
    except NotImplementedError:
        trace.append(_trace("recommend_crops", "Crop recommendations", "skipped", "Crop recommendation service is unavailable", started=t0))
        return {"candidates": [], "excluded": [], "no_data": True, "trace": trace}
    except Exception as exc:
        logger.warning("recommend_crops failed: %s", exc)
        trace.append(_trace("recommend_crops", "Crop recommendations", "failed", "Crop recommendation service failed", started=t0))
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
    t0 = _now()

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

        missing_yields = sum(1 for per in scenario_yields.values() for v in per.values() if v is None)
        if scenario_yields and missing_yields == sum(len(per) for per in scenario_yields.values()):
            trace.append(_trace("predict_yield", "Yield forecasts", "failed",
                                "Yield forecasts could not be produced", started=t0))
        elif missing_yields:
            trace.append(_trace("predict_yield", "Yield forecasts", "ok",
                                f"Yields forecast for {len(scenario_yields)} crops ({missing_yields} scenario forecasts unavailable)",
                                started=t0))
        else:
            trace.append(_trace("predict_yield", "Yield forecasts", "ok",
                                f"Yields forecast for {len(scenario_yields)} crops", started=t0))
    except Exception:
        logger.warning("predict_yield failed", exc_info=True)
        trace.append(_trace("predict_yield", "Yield forecasts", "failed", "Yield forecast service failed", started=t0))

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
    t0 = _now()

    try:
        crops, price_excluded = await build_crop_options(candidates, scenarios, location, season, profile)
        excluded.extend(price_excluded)
        # build_crop_options really does the cost and price work; report each outcome.
        n_no_price = sum(1 for e in price_excluded if getattr(e, "reason_code", "") == "NO_REAL_PRICE")
        n_no_cost = sum(
            1 for e in price_excluded
            if getattr(e, "reason_code", "") == "DATA_UNAVAILABLE"
            and (getattr(e, "params", None) or {}).get("field") == "cost_or_fertilizer"
        )
        costs_ok = len(crops) + n_no_price
        trace.append(_trace(
            "optimize", "costs", "ok" if costs_ok else "failed",
            f"Cultivation cost estimated for {costs_ok} of {len(candidates)} crops"
            + (f" ({n_no_cost} without cost data)" if n_no_cost else ""),
            started=t0,
        ))
        trace.append(_trace(
            "optimize", "prices", "ok" if crops else "failed",
            f"Market prices found for {len(crops)} of {costs_ok} crops"
            + (f" ({n_no_price} without a real price)" if n_no_price else ""),
            started=t0,
        ))
        if not crops:
            trace.append(_trace("optimize", "Plan optimization", "skipped",
                                "No crop has complete price and cost data", started=t0))
            return {"crops": [], "excluded": excluded, "strategies": [], "impact": None,
                    "opt_warnings": [], "trace": trace}
        t_opt = _now()
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
        trace.append(_trace("optimize", "Plan optimization", "ok",
                            f"Compared {len(strategies)} plan strategies", started=t_opt))
        return {"crops": crops, "excluded": excluded, "strategies": strategies, "impact": impact,
                "opt_warnings": opt_warnings, "trace": trace}
    except Exception as exc:
        logger.warning("optimize_node failed: %s", exc)
        trace.append(_trace("optimize", "Plan optimization", "failed", "Plan optimization failed", started=t0))
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
    t0 = _now()
    recommended = _recommended_strategy(state)

    if recommended and recommended.feasible and recommended.allocations:
        trace.append(_trace("check_feasibility", "Plan feasibility check", "ok", "A profitable plan satisfies the available land, budget, and water constraints", started=t0))
        return {"feasibility": None, "trace": trace}

    # An infeasible plan is a valid optimizer outcome, not a runtime failure.
    # Keep the trace green so the farmer can distinguish it from a broken step.
    trace.append(_trace("check_feasibility", "Plan feasibility check", "ok",
                        "No profitable plan satisfies the available land, budget, and water constraints", started=t0))
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
    t0 = _now()

    steps = ["CAP_TO_1", "REDUCE_AREA", "DROP_WATER_HUNGRY_CROP", "USE_NORMAL_SCENARIO_WATER"]
    if relaxation_count < len(steps):
        step = steps[relaxation_count]
        relaxations.append(step)
        trace.append(_trace("relax_constraint", step, "ok", f"Applying relaxation step {relaxation_count + 1}: {step}", started=t0))

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

def _plan_facts(state: dict, recommended, profile) -> tuple[list[dict], dict]:
    """Facts the LLM may cite about the recommended plan (explain + plan Q&A share this)."""
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
    return shap_factors, farmer_limits


async def explain_node(state: dict) -> dict:
    """LLM call 2: generate natural-language explanation of the plan."""
    from app.agent.client import get_sarvam_client
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

    shap_factors, farmer_limits = _plan_facts(state, recommended, profile)
    system = EXPLAIN_SYSTEM.get(language, EXPLAIN_SYSTEM["en"])
    user_prompt = build_explain_user_prompt(
        recommended, water_saved, shap_factors, language, state.get("crops", []),
        limits=farmer_limits,
    )
    long_facts = long_duration_facts(recommended, state.get("crops", []))

    explanation_text = ""
    t0 = _now()
    retry_count = state.get("grounding_retry_count", 0)
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
        if not isinstance(parsed, dict):
            raise ValueError("Sarvam returned non-object JSON")
        explanation_text = parsed.get("text")
        if not isinstance(explanation_text, str) or not explanation_text.strip():
            raise ValueError("Sarvam returned no text")
        provider = "sarvam"
    except Exception as exc:  # SarvamAllModelsFailed, bad JSON, wrong types, network: all fall back
        logger.warning("explain: LLM failed (%s: %s); using template", type(exc).__name__, str(exc)[:200])
        # No LLM -> deterministic template. Setting the retry counter to its limit means
        # the grounding loop can never come back here for another failing LLM call.
        fallback = build_template_explanation(language, getattr(profile, "land_acres", 0), recommended, water_saved)
        trace.append(_trace("explain", "llm", "failed", "AI explanation unavailable; used the built-in summary",
                            started=t0, fallback_used="template"))
        return {
            "explanation_text": fallback.text,
            "explanation_grounded": True,
            "explanation_provider": "template",
            "grounding_retry_count": max(retry_count + 1, 2),
            "water_saved_pct": water_saved,
            "trace": trace,
        }

    # Grounding check
    tool_outputs = {"strategies": [s.model_dump() for s in strategies], "water_saved_pct": water_saved,
                    "shap_factors": shap_factors, "long_crop_facts": long_facts,
                    "farmer_limits": farmer_limits}
    grounded = grounding_check(explanation_text, tool_outputs)

    trace.append(_trace(
        "explain", "llm", "ok" if grounded else "failed",
        "Explanation written from the plan numbers" if grounded
        else "Draft explanation did not match the plan numbers",
        started=t0,
    ))

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
    t0 = _now()
    # A deterministic template is built from the plan's own numbers: nothing to verify.
    if state.get("explanation_provider") == "template":
        trace.append(_trace("grounding_check", "check", "ok",
                            "Summary is built directly from the plan numbers", started=t0))
        return {"explanation_grounded": True, "trace": trace}

    grounded = grounding_check(explanation_text, tool_outputs)

    if not grounded and retry_count >= 2:
        # Max retries reached: fall back to the deterministic template.
        recommended = _recommended_strategy(state)
        fallback = build_template_explanation(language, getattr(profile, "land_acres", 0), recommended, water_saved)
        trace.append(_trace("grounding_check", "check", "failed",
                            "Explanation did not match the plan numbers twice; used the built-in summary",
                            started=t0, fallback_used="template"))
        return {
            "explanation_text": fallback.text,
            "explanation_grounded": True,
            "explanation_provider": "template",
            "trace": trace,
        }

    trace.append(_trace(
        "grounding_check", "check", "ok" if grounded else "failed",
        "Explanation matches the plan numbers" if grounded
        else "Explanation did not match the plan numbers; writing it again",
        started=t0,
    ))
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

    if state.get("route") == "question_answered":
        # A question or small talk: emit the answer only. No new plan version, and the
        # stored plan's explanation is left exactly as it was.
        return {"reply": {
            "text": state.get("explanation_text", ""),
            "language": state.get("language", "en"),
            "provider": state.get("explanation_provider", "template"),
        }}

    t0 = _now()
    trace = list(state.get("trace", []))
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
    # Same canal disclosure as run_plan: no sourced canal duty, so 0 m3 is credited.
    if profile is not None and (profile.canal_access or profile.water_source in ("canal", "both")) and not any(
        w.code == "CANAL_NOT_CREDITED" for w in warnings
    ):
        warnings.append(Warning(code="CANAL_NOT_CREDITED", params={"canal_credited_m3": 0}))

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

    if recommended and recommended.feasible and recommended.allocations:
        trace.append(_trace("respond", "complete", "ok", "Planning completed", started=t0))
    else:
        trace.append(_trace("respond", "complete", "failed",
                            "Planning finished without a feasible plan for these inputs", started=t0))
    return {"plan_result": plan, "reply": None, "trace": trace}


# ─────────────────────────────────────────────────────────────────────────────
# answer_from_memory — follow-up / question handler, no LLM for routing
# ─────────────────────────────────────────────────────────────────────────────

_GREETING_RE = re.compile(
    r"^\s*(hello|hi|hey|hii+|namaste|namaskar|good (morning|afternoon|evening)|नमस्कार|नमस्ते|राम राम)\b[\s!.,?]*$",
    re.IGNORECASE,
)
_PROFILE_RECALL_RE = re.compile(
    r"\b(my (budget|land|farm size|farm details|location|district|profile)|saved|"
    r"what did i (tell|give|say)|did i (tell|give|say))\b|बजेट|बजट|प्रोफाइल|जतन",
    re.IGNORECASE,
)
_NEXT_STEP_HINT = {
    "en": "Ask me why a crop was chosen, or tell me a change (budget, land, water source or location) and I will make a new plan.",
    "mr": "एखादे पीक का निवडले ते विचारा, किंवा बदल सांगा (बजेट, जमीन, पाणी किंवा ठिकाण) — मी नवीन आराखडा तयार करेन.",
    "hi": "पूछिए कोई फसल क्यों चुनी गई, या बदलाव बताइए (बजट, ज़मीन, पानी या जगह) — मैं नई योजना बनाऊँगा।",
}
_GREETING = {"en": "Hello! ", "mr": "नमस्कार! ", "hi": "नमस्ते! "}


async def answer_from_memory_node(state: dict) -> dict:
    """Answer a message about the existing plan without re-running the optimizer.

    Greeting -> greeting + current plan summary. Profile recall ("what is my
    budget?") -> saved profile. Any other question -> LLM answer grounded in the
    plan's own numbers, falling back to the plan summary if grounding fails.
    Fact updates (route == "follow_up") go back to extraction and re-planning.
    """
    from app.agent.templates import build_template_explanation

    if state.get("route") == "follow_up":
        return {"route": "follow_up"}

    profile: FarmProfile | None = state.get("profile")
    if profile is None:
        return {"route": "follow_up"}

    language = state.get("language", "en")
    lang = language if language in ("mr", "hi", "en") else "en"
    message = state.get("message", "") or ""
    trace = list(state.get("trace", []))
    t0 = _now()
    recommended = _recommended_strategy(state)
    summary = build_template_explanation(lang, profile.land_acres, recommended, 0.0).text
    provider = "memory"
    grounded = True

    if _GREETING_RE.match(message):
        text = f"{_GREETING[lang]}{summary} {_NEXT_STEP_HINT[lang]}"
        step = "Greeting"
    elif _PROFILE_RECALL_RE.search(message):
        location = profile.location_text
        acres = f"{profile.land_acres:g}"
        budget = f"{profile.budget_rs:,.0f}"
        if lang == "mr":
            text = f"तुमच्या जतन केलेल्या शेत माहितीनुसार ठिकाण {location}, क्षेत्र {acres} एकर आणि बजेट ₹{budget} आहे."
        elif lang == "hi":
            text = f"आपकी सहेजी हुई खेत जानकारी के अनुसार स्थान {location}, क्षेत्र {acres} एकड़ और बजट ₹{budget} है।"
        else:
            text = f"From your saved farm profile: the location is {location}, the farm size is {acres} acres, and the budget is ₹{budget}."
        step = "Saved farm profile"
    else:
        step = "Plan question"
        text = ""
        if recommended is not None and recommended.allocations:
            from app.agent.client import get_sarvam_client
            from app.agent.grounding import grounding_check
            from app.agent.prompts import PLAN_QA_SYSTEM, build_explain_user_prompt

            shap_factors, farmer_limits = _plan_facts(state, recommended, profile)
            # Every evaluated crop's margin, so "why this crop?" is answered from data.
            crop_margins = [
                {"crop_id": c.crop_id, "profit_normal_rs_per_acre": round(c.profit_rs_per_acre.normal)}
                for c in state.get("crops", []) if getattr(c, "profit_rs_per_acre", None) is not None
            ]
            user_prompt = build_explain_user_prompt(
                recommended, 0.0, shap_factors, lang, state.get("crops", []), limits=farmer_limits,
            ) + "".join(
                f"\nevaluated_crop: {m['crop_id']} profit_normal_rs_per_acre: {m['profit_normal_rs_per_acre']}"
                for m in crop_margins
            ) + f"\n\nFARMER QUESTION: {message}"
            try:
                client = get_sarvam_client()
                resp = await client.chat(
                    messages=[
                        {"role": "system", "content": PLAN_QA_SYSTEM[lang]},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=800,
                )
                parsed = json.loads(client.extract_text(resp) or "{}")
                answer = parsed.get("text") if isinstance(parsed, dict) else None
                if not isinstance(answer, str):
                    answer = ""
                tool_outputs = {
                    "strategies": [s.model_dump() for s in state.get("strategies", [])],
                    "shap_factors": shap_factors,
                    "farmer_limits": farmer_limits,
                    "crop_margins": crop_margins,
                }
                if answer and grounding_check(answer, tool_outputs):
                    text, provider = answer, "sarvam"
            except Exception as exc:  # LLM down or bad JSON: fall back to the plan summary
                logger.warning("answer_from_memory: plan Q&A failed (%s)", type(exc).__name__)
        if not text:
            text = f"{summary} {_NEXT_STEP_HINT[lang]}"
            provider = "template"
            grounded = False

    trace.append(_trace("answer_from_memory", step, "ok", "Answered from this conversation's saved plan", started=t0))
    return {
        "route": "question_answered",
        "explanation_text": text,
        "explanation_grounded": grounded,
        "explanation_provider": provider,
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# smalltalk — greeting / thanks / help / Kannada. Fixed text: no tools, no LLM.
# ─────────────────────────────────────────────────────────────────────────────

_SMALLTALK_TEXT = {
    "greeting": {
        "en": "Hello! 👋 How can I help you with your farming plan today?",
        "mr": "नमस्कार! 👋 आज तुमच्या शेतीच्या आराखड्यात मी तुम्हाला कशी मदत करू?",
        "hi": "नमस्ते! 👋 आज मैं आपकी खेती की योजना में कैसे मदद कर सकता हूँ?",
    },
    "thanks": {
        "en": "You're welcome! Tell me if you want to change anything or make a new plan.",
        "mr": "तुमचे स्वागत आहे! काही बदल करायचा असेल किंवा नवीन आराखडा हवा असेल तर सांगा.",
        "hi": "आपका स्वागत है! कुछ बदलना हो या नई योजना चाहिए तो बताइए।",
    },
    "help": {
        "en": "I'm AgriPulse, a farming assistant for Maharashtra. Tell me your location, farm size in acres "
              "and budget, and I will suggest crops, water use and expected profit. You can also ask me "
              "questions about your plan.",
        "mr": "मी AgriPulse आहे, महाराष्ट्रातील शेतीसाठी मदतनीस. तुमचे ठिकाण, शेताचे क्षेत्र (एकर) आणि बजेट सांगा, "
              "मी पिके, पाण्याचा वापर आणि अपेक्षित नफा सुचवेन. तुमच्या आराखड्याबद्दल प्रश्नही विचारू शकता.",
        "hi": "मैं AgriPulse हूँ, महाराष्ट्र की खेती के लिए सहायक। अपनी जगह, खेत का क्षेत्र (एकड़) और बजट बताइए, "
              "मैं फसलें, पानी का उपयोग और अनुमानित मुनाफ़ा सुझाऊँगा। आप अपनी योजना के बारे में सवाल भी पूछ सकते हैं।",
    },
}
_SMALLTALK_SAVED_PROFILE = {
    "en": "I have your farm saved: {location}, {acres} acres, budget ₹{budget}. Say \"make a plan\" and I will plan crops for it.",
    "mr": "तुमची शेत माहिती जतन आहे: {location}, {acres} एकर, बजेट ₹{budget}. \"आराखडा तयार करा\" म्हणा, मी पिकांचे नियोजन करेन.",
    "hi": "आपकी खेत जानकारी सहेजी है: {location}, {acres} एकड़, बजट ₹{budget}। \"योजना बनाइए\" कहिए, मैं फसलों की योजना बनाऊँगा।",
}
# Kannada is not a planning language yet: greet in Kannada and say so honestly.
_KANNADA_GREETING = "ನಮಸ್ಕಾರ! 🙏"
_KANNADA_NOTE = (
    "ಕ್ಷಮಿಸಿ, ಸದ್ಯಕ್ಕೆ ಕೃಷಿ ಯೋಜನೆ ಇಂಗ್ಲಿಷ್, ಮರಾಠಿ ಮತ್ತು ಹಿಂದಿ ಭಾಷೆಗಳಲ್ಲಿ ಮಾತ್ರ ಲಭ್ಯವಿದೆ (ಪೈಲಟ್ ಮಹಾರಾಷ್ಟ್ರಕ್ಕೆ ಮಾತ್ರ). "
    "Farm planning currently works in English, Marathi and Hindi (the pilot covers Maharashtra)."
)


def _complete_profile(profile) -> bool:
    """A saved profile that is really usable (never the 'unknown' placeholder)."""
    if profile is None:
        return False
    try:
        return not compute_missing(profile.model_dump())
    except Exception:
        return False


def smalltalk_node(state: dict) -> dict:
    """Reply to small talk with fixed text. Never calls a tool or the LLM, and never
    claims to remember anything that is not in the saved profile."""
    language = state.get("language", "en")
    lang = language if language in ("mr", "hi", "en") else "en"
    kind = smalltalk_kind(state.get("message", "")) or "greeting"

    if kind == "kannada_greeting":
        text = f"{_KANNADA_GREETING} {_KANNADA_NOTE}"
    elif kind == "kannada":
        text = _KANNADA_NOTE
    else:
        text = _SMALLTALK_TEXT[kind][lang]
        profile = state.get("profile")
        if kind == "greeting" and _complete_profile(profile):
            text += " " + _SMALLTALK_SAVED_PROFILE[lang].format(
                location=profile.location_text, acres=f"{profile.land_acres:g}", budget=f"{profile.budget_rs:,.0f}",
            )
            if state.get("strategies"):
                text += " " + _NEXT_STEP_HINT[lang]
    return {
        "route": "question_answered",
        "explanation_text": text,
        "explanation_grounded": True,
        "explanation_provider": "template",
        "trace": list(state.get("trace", [])),
    }


# ─────────────────────────────────────────────────────────────────────────────
# save_memory — persist state to checkpointer (LangGraph does this automatically;
# this node is a no-op hook for any extra app-level persistence)
# ─────────────────────────────────────────────────────────────────────────────

async def save_memory_node(state: dict) -> dict:
    """LangGraph checkpoints state automatically. LangGraph requires every node to
    write at least one key, so this re-writes an unchanged value."""
    return {"no_data": state.get("no_data", False)}
