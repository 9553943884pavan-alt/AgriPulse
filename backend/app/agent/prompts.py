"""Prompt templates for the LangGraph agent nodes.

Rules:
1. Every prompt ends with the exact JSON instruction so the model outputs only JSON.
2. extract_profile lists every FarmProfile field with type and unit.
   Includes: "If the farmer did not mention a number, output null for that field."
3. explain lists all source numbers inline in the user prompt — model cannot invent values.
4. Language is injected per call; prompts are templates, not hardcoded strings.
5. For crops with duration_days > 120, the explanation must state the
   per-acre-per-year profit and say the crop "occupies the land for N months".

ask_missing: rule-based per-field questions (NOT an LLM call).
  See ml/SPECS §8.4 prose: "route and ask_missing are rule-based."
"""

from __future__ import annotations

# ── ask_missing: rule-based translated templates ──────────────────────────────
# NOT an LLM call. One question per required field, in all three languages.
ASK_MISSING: dict[str, dict[str, str]] = {
    "location_text": {
        "mr": "तुमचे गाव किंवा जिल्हा कोणता आहे?",
        "hi": "आपका गांव या जिला कौन सा है?",
        "en": "Which village or district is your farm in?",
    },
    "land_acres": {
        "mr": "तुमच्याकडे किती एकर जमीन आहे?",
        "hi": "आपके पास कितने एकड़ जमीन है?",
        "en": "How many acres of land do you have?",
    },
    "budget_rs": {
        "mr": "शेतीसाठी तुमच्याकडे किती रुपये आहेत?",
        "hi": "खेती के लिए आपके पास कितना बजट है (रुपयों में)?",
        "en": "What is your farming budget in rupees?",
    },
    # Optional (asked at most once): only when the farmer has a borewell but gave
    # no discharge / pump hours. "I don't know" is an accepted answer.
    "borewell_capacity": {
        "mr": "तुमच्या बोअरवेलमधून तासाला किती लिटर पाणी मिळते आणि पंप दिवसाला किती तास चालतो? माहीत नसल्यास 'माहीत नाही' सांगा.",
        "hi": "आपके बोरवेल से प्रति घंटा कितने लीटर पानी मिलता है और पंप दिन में कितने घंटे चलता है? पता न हो तो 'पता नहीं' कहें।",
        "en": "How many litres per hour does your borewell give, and how many hours a day does the pump run? If you don't know, just say 'I don't know'.",
    },
}

# ── extract_profile system prompts ────────────────────────────────────────────
_EXTRACT_PROFILE_COMMON = """\
You are a farm-profile extractor. Your ONLY job is to parse the farmer's message \
and output a JSON object with these exact fields:

  location_text      (string | null)  — village name, district name, or any place the farmer mentioned
  land_acres         (number | null)  — total farm area in acres (convert if needed; see rules)
  budget_rs          (number | null)  — total farming budget in rupees (convert if needed)
  water_source       (string | null)  — one of: rainfed, borewell, canal, both
  borewell_count     (integer | null) — number of borewells
  borewell_yield_lph (number | null)  — borewell yield in litres per hour
  pump_hours_per_day (number | null)  — pump run hours per day
  canal_access       (boolean | null) — true if the farmer mentioned canal access
  irrigation_method  (string | null)  — one of: flood, sprinkler, drip
  risk_appetite      (string | null)  — one of: safe, balanced, max_profit
  soil_test          (object | null)  — {{n, p, k, ph}} if the farmer gave soil test results

Conversion rules (apply in code, output in the standard units above):
  1 guntha   = 0.025 acres
  1 hectare  = 2.471 acres
  "70 हजार" → 70000   (हजार/hazar = × 1000)
  "५ एकर"   → 5       (Devanagari digits: ०=0 … ९=9)
  "2 lakh"  → 200000

If the farmer did not mention a field, output null for that field. \
NEVER invent or guess a number they did not say.

Output ONLY the JSON object. No markdown, no prose, no explanation."""

EXTRACT_PROFILE_SYSTEM: dict[str, str] = {
    "mr": "तुम्ही मराठी भाषेत शेतकऱ्याचे संदेश समजता. " + _EXTRACT_PROFILE_COMMON,
    "hi": "आप हिंदी में किसान के संदेश समझते हैं। " + _EXTRACT_PROFILE_COMMON,
    "en": _EXTRACT_PROFILE_COMMON,
}

# ── explain system prompts ────────────────────────────────────────────────────
_EXPLAIN_COMMON = """\
You are an agricultural advisor explaining a crop plan to a smallholder farmer.

Rules:
- Reply ONLY in {language}.
- Address the farmer directly: {pronoun} (second person).
- Use ONLY the numbers provided below in the user message. Do NOT invent any figure.
- Explain the selected crop or mix from the PLAN DATA: its allocated acreage,
  plan profit, investment/water values when supplied, and the active constraints.
- Explain acreage as the optimizer's result under the stated land, budget and
  water limits. Do not claim that a predictive-model feature caused an acreage.
- If ``yield_model_attribution`` is supplied, describe it only as an attribution
  of the yield prediction. It is not a causal claim and is not an explanation
  of the optimizer allocation.
- State rainfall/price downside only using the supplied scenario profit values.
  If they are equal across scenarios, say so; do not claim there is "no risk".
- The *_used values are amounts the plan uses, NOT the farmer's limits. Never say
  land, budget or water is "full", "fully used" or "exhausted" unless that
  constraint is listed under binding_constraints.
- farmer_land_acres and farmer_budget_rs are the farmer's limits. Name as
  "active" or "limiting" ONLY the constraints in limiting_constraints; if it is
  "none", do not call any constraint active.
- If no yield_model_attribution is supplied, say nothing about what drives the yield.
- Every number you write must appear in the PLAN DATA; never write any other number. Do not mention rounding, significant figures or these rules.
- Round money to the nearest Rs. 100.
- Do not describe a long-duration crop as annualised: this is a single-period
  plan unless the PLAN DATA explicitly provides a multi-period result.
- Maximum 120 words.
- Output JSON: {{"text": "<explanation>", "language": "<code>"}}

Output ONLY the JSON object. No markdown, no prose."""

_PRONOUN = {"mr": "आपण", "hi": "आप", "en": "you"}
_LANG_NAME = {"mr": "Marathi", "hi": "Hindi", "en": "English"}

EXPLAIN_SYSTEM: dict[str, str] = {
    lang: _EXPLAIN_COMMON.format(
        language=_LANG_NAME[lang],
        pronoun=_PRONOUN[lang],
    )
    for lang in ("mr", "hi", "en")
}


_PLAN_QA_COMMON = """\
You are an agricultural advisor answering a smallholder farmer's follow-up
question about the crop plan they already received.

Rules:
- Reply ONLY in {language}. Address the farmer as {pronoun}.
- Answer the FARMER QUESTION using ONLY the PLAN DATA. Never write a number that
  is not in the PLAN DATA, and never invent reasons, prices, yields or advice.
- Acreage is the optimizer's result under the farmer's limits; name as limiting
  only the constraints in limiting_constraints. Any yield_model_attribution
  explains the yield prediction only, not the acreage.
- If the PLAN DATA cannot answer the question, say so plainly and tell the
  farmer they can change land, budget, water source or location to get a new plan.
- Maximum 80 words.
- Output JSON: {{"text": "<answer>", "language": "<code>"}}

Output ONLY the JSON object. No markdown, no prose."""

PLAN_QA_SYSTEM: dict[str, str] = {
    lang: _PLAN_QA_COMMON.format(language=_LANG_NAME[lang], pronoun=_PRONOUN[lang])
    for lang in ("mr", "hi", "en")
}


def long_duration_facts(strategy_result: object, crops: list | None) -> list[dict]:
    """Per-acre-per-year profit and months occupied for crops > 120 days (computed from plan data)."""
    from app.ml.constants import LONG_DURATION_DAYS

    by_id = {getattr(c, "crop_id", None): c for c in (crops or [])}
    facts = []
    for a in getattr(strategy_result, "allocations", []) or []:
        crop = by_id.get(getattr(a, "crop_id", None))
        days = getattr(crop, "duration_days", None) if crop is not None else None
        acres = getattr(a, "acres", 0) or 0
        if not days or days <= LONG_DURATION_DAYS or acres <= 0:
            continue
        profit = getattr(a, "profit_rs", None)
        normal = profit.get("normal", 0) if isinstance(profit, dict) else getattr(profit, "normal", 0)
        facts.append({
            "crop_id": a.crop_id,
            "months_occupied": round(days / 30),
            "profit_per_acre_per_year_rs": round(normal / acres * 365 / days),
        })
    return facts


def build_explain_user_prompt(
    strategy_result: object,
    water_saved_pct: float,
    shap_top_factors: list[dict],
    language: str,
    crops: list | None = None,
    limits: dict | None = None,
) -> str:
    """Build the user-turn prompt for the explain node.

    All source numbers are listed inline so the model cannot invent values.
    """

    totals = getattr(strategy_result, "totals", None)
    solver = getattr(strategy_result, "solver", None)
    lines = [
        "=== PLAN DATA (use only these numbers) ===",
        *[f"{k}: {v:.0f}" if k.endswith("_rs") else f"{k}: {v}"
          for k, v in (limits or {}).items() if v is not None],
        f"strategy_kind: {getattr(strategy_result, 'kind', 'unknown')}",
        f"expected_profit_rs: {getattr(strategy_result, 'expected_profit_rs', 0):.0f}",
        f"worst_case_profit_rs: {getattr(strategy_result, 'worst_case_profit_rs', 0):.0f}",
        f"land_used_acres: {getattr(totals, 'land_used_acres', 0):.2f}",
        f"budget_used_rs: {getattr(totals, 'budget_used_rs', 0):.0f}",
        f"water_used_m3: {getattr(totals, 'water_m3', 0):.0f}",
        f"solver_status: {getattr(solver, 'status', 'unavailable')}",
    ]
    if water_saved_pct > 0:
        lines.append(f"water_saved_pct_vs_traditional: {water_saved_pct:.1f}")

    finance = getattr(strategy_result, "finance", None)
    if finance is not None:
        def finance_value(field: str) -> object:
            value = getattr(finance, field, None)
            return getattr(value, "value", value)

        for field in (
            "investment_rs",
            "expected_yield_quintal",
            "expected_revenue_rs",
            "expected_profit_rs",
            "roi_pct",
            "break_even_price_rs_per_quintal",
        ):
            value = finance_value(field)
            if value is not None:
                lines.append(f"{field}: {value}")

    binding = getattr(strategy_result, "binding_constraints", []) or []
    if binding:
        lines.append("binding_constraints:")
        for item in binding:
            code = item.get("code") if isinstance(item, dict) else getattr(item, "code", "constraint")
            lines.append(f"  {code}")

    allocs = getattr(strategy_result, "allocations", [])
    for a in allocs:
        crop_id = getattr(a, "crop_id", "?")
        acres = getattr(a, "acres", 0)
        profit = getattr(a, "profit_rs", {})
        normal_profit = profit.get("normal", 0) if isinstance(profit, dict) else getattr(profit, "normal", 0)
        drought_profit = profit.get("drought", 0) if isinstance(profit, dict) else getattr(profit, "drought", 0)
        excess_profit = profit.get("excess", 0) if isinstance(profit, dict) else getattr(profit, "excess", 0)
        lines.append(
            f"crop: {crop_id} acres: {acres:.2f} cost_rs: {getattr(a, 'cost_rs', 0):.0f} "
            f"water_m3: {getattr(a, 'water_m3', 0):.0f} profit_drought_rs: {drought_profit:.0f} "
            f"profit_normal_rs: {normal_profit:.0f} profit_excess_rs: {excess_profit:.0f}"
        )
        for field in ("revenue_rs",):
            value = getattr(a, field, None)
            if value is not None:
                lines.append(f"  {field}: {value}")

    for f in long_duration_facts(strategy_result, crops):
        lines.append(
            f"long_crop: {f['crop_id']}  occupies_land_months: {f['months_occupied']}"
            f"  profit_per_acre_per_year_rs: {f['profit_per_acre_per_year_rs']}"
        )

    if shap_top_factors:
        lines.append("yield_model_attribution_only_not_optimizer_reason:")
        for f in shap_top_factors[:3]:
            lines.append(f"  {f.get('feature')}: effect {f.get('effect_quintal_per_acre', 0):.2f} qt/acre ({f.get('direction', '?')})")

    return "\n".join(lines)
