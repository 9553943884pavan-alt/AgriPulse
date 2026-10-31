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
- Mention: the best crop or mix, WHY (the top factor from the SHAP analysis), \
the expected profit, and how much water is saved versus the traditional plan.
- Round crop yields to 2 significant figures (e.g. "8.3 quintals/acre").
- Round money to the nearest Rs. 100.
- For any crop with duration > 120 days (e.g. sugarcane), state the \
per-acre-per-year profit AND say it "occupies the land for N months". \
This keeps the comparison with shorter crops honest.
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


def build_explain_user_prompt(
    strategy_result: object,
    water_saved_pct: float,
    shap_top_factors: list[dict],
    language: str,
) -> str:
    """Build the user-turn prompt for the explain node.

    All source numbers are listed inline so the model cannot invent values.
    """

    lines = [
        "=== PLAN DATA (use only these numbers) ===",
        f"expected_profit_rs: {getattr(strategy_result, 'expected_profit_rs', 0):.0f}",
        f"worst_case_profit_rs: {getattr(strategy_result, 'worst_case_profit_rs', 0):.0f}",
        f"water_saved_pct: {water_saved_pct:.1f}",
    ]

    allocs = getattr(strategy_result, "allocations", [])
    for a in allocs:
        crop_id = getattr(a, "crop_id", "?")
        acres = getattr(a, "acres", 0)
        profit = getattr(a, "profit_rs", {})
        normal_profit = profit.get("normal", 0) if isinstance(profit, dict) else getattr(profit, "normal", 0)
        lines.append(f"crop: {crop_id}  acres: {acres:.2f}  profit_normal_rs: {normal_profit:.0f}")

    if shap_top_factors:
        lines.append("top_shap_factors:")
        for f in shap_top_factors[:3]:
            lines.append(f"  {f.get('feature')}: effect {f.get('effect_quintal_per_acre', 0):.2f} qt/acre ({f.get('direction', '?')})")

    return "\n".join(lines)
