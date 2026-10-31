"""AG.10 — No-LLM fallback explanation builder.

Triggered when:
  - SarvamAllModelsFailed is raised (all chat models exhausted), OR
  - grounding check fails twice in a row.

Never returns an empty answer — the demo never shows a blank screen.

Templates are parameterised by language × crop_count (1 / 2 / 3+).
All numbers come from the optimizer StrategyResult already in state.
provider field in Explanation is set to "template"; grounded is False.
"""

from __future__ import annotations

from app.schemas import Explanation, KeyPoint, StrategyResult


# ── Template strings ──────────────────────────────────────────────────────────
# {land} = land_acres, {crop_1} = first crop name, {acres_1} = acres for crop_1,
# {profit} = expected_profit_rs, {water_saved} = water saved % (may be 0)

_1CROP = {
    "mr": (
        "तुमच्या {land:.1f} एकर जमिनीसाठी {crop_1} ({acres_1:.1f} एकर) "
        "लावणे सर्वोत्तम आहे. अपेक्षित नफा: Rs.{profit:,.0f}. "
        "पाणी बचत: {water_saved:.0f}%."
    ),
    "hi": (
        "आपकी {land:.1f} एकड़ जमीन के लिए {crop_1} ({acres_1:.1f} एकड़) "
        "सबसे अच्छा है. अनुमानित लाभ: Rs.{profit:,.0f}. "
        "पानी की बचत: {water_saved:.0f}%."
    ),
    "en": (
        "For your {land:.1f}-acre farm, {crop_1} ({acres_1:.1f} ac) gives the best return. "
        "Expected profit: Rs.{profit:,.0f}. Water saved: {water_saved:.0f}%."
    ),
}

_2CROP = {
    "mr": (
        "तुमच्या {land:.1f} एकर जमिनीसाठी {crop_1} ({acres_1:.1f} एकर) आणि "
        "{crop_2} ({acres_2:.1f} एकर) लावणे सर्वोत्तम आहे. "
        "अपेक्षित नफा: Rs.{profit:,.0f}. पाणी बचत: {water_saved:.0f}%."
    ),
    "hi": (
        "आपकी {land:.1f} एकड़ जमीन के लिए {crop_1} ({acres_1:.1f} एकड़) और "
        "{crop_2} ({acres_2:.1f} एकड़) सबसे अच्छे हैं. "
        "अनुमानित लाभ: Rs.{profit:,.0f}. पानी की बचत: {water_saved:.0f}%."
    ),
    "en": (
        "For your {land:.1f}-acre farm, {crop_1} ({acres_1:.1f} ac) and "
        "{crop_2} ({acres_2:.1f} ac) give the best return. "
        "Expected profit: Rs.{profit:,.0f}. Water saved: {water_saved:.0f}%."
    ),
}

_3PLUS_CROP = {
    "mr": (
        "तुमच्या {land:.1f} एकर जमिनीसाठी {crop_1}, {crop_2} आणि इतर "
        "पिकांचे मिश्रण ({n_crops} पिके) सर्वोत्तम आहे. "
        "अपेक्षित नफा: Rs.{profit:,.0f}. पाणी बचत: {water_saved:.0f}%."
    ),
    "hi": (
        "आपकी {land:.1f} एकड़ जमीन के लिए {crop_1}, {crop_2} और अन्य "
        "फसलों का मिश्रण ({n_crops} फसलें) सबसे अच्छा है. "
        "अनुमानित लाभ: Rs.{profit:,.0f}. पानी की बचत: {water_saved:.0f}%."
    ),
    "en": (
        "For your {land:.1f}-acre farm, a mix of {crop_1}, {crop_2} and others "
        "({n_crops} crops) gives the best return. "
        "Expected profit: Rs.{profit:,.0f}. Water saved: {water_saved:.0f}%."
    ),
}


def _crop_name(allocation: object, language: str) -> str:
    """Extract a crop name from an Allocation object."""
    crop_id = getattr(allocation, "crop_id", str(allocation))
    # If a names dict is available (added by the graph before template is called), use it
    names = getattr(allocation, "names", {})
    return names.get(language) or names.get("en") or crop_id


def build_template_explanation(
    language: str,
    land_acres: float,
    strategy: StrategyResult | None,
    water_saved_pct: float = 0.0,
) -> Explanation:
    """Build a fallback Explanation without any LLM call.

    Args:
        language:       "mr" | "hi" | "en"
        land_acres:     farmer's land in acres
        strategy:       the recommended StrategyResult (may be None if no plan)
        water_saved_pct: water saved % vs Traditional (0 if not computed)
    """
    lang = language if language in ("mr", "hi", "en") else "en"

    if strategy is None or not strategy.allocations:
        # No plan at all
        no_plan = {
            "mr": "सध्या कोणताही पिक आराखडा तयार करता आला नाही. कृपया पुन्हा प्रयत्न करा.",
            "hi": "अभी कोई फसल योजना नहीं बना सकते। कृपया पुनः प्रयास करें।",
            "en": "No crop plan could be built at this time. Please try again.",
        }
        return Explanation(
            language=lang,  # type: ignore[arg-type]
            text=no_plan[lang],
            key_points=[],
            grounded=False,
            provider="template",
        )

    allocs = strategy.allocations
    profit = strategy.expected_profit_rs
    n = len(allocs)

    if n == 1:
        tmpl = _1CROP[lang]
        text = tmpl.format(
            land=land_acres,
            crop_1=_crop_name(allocs[0], lang),
            acres_1=allocs[0].acres,
            profit=profit,
            water_saved=water_saved_pct,
        )
    elif n == 2:
        tmpl = _2CROP[lang]
        text = tmpl.format(
            land=land_acres,
            crop_1=_crop_name(allocs[0], lang),
            acres_1=allocs[0].acres,
            crop_2=_crop_name(allocs[1], lang),
            acres_2=allocs[1].acres,
            profit=profit,
            water_saved=water_saved_pct,
        )
    else:
        tmpl = _3PLUS_CROP[lang]
        text = tmpl.format(
            land=land_acres,
            crop_1=_crop_name(allocs[0], lang),
            crop_2=_crop_name(allocs[1], lang),
            n_crops=n,
            profit=profit,
            water_saved=water_saved_pct,
        )

    key_points = [
        KeyPoint(
            icon="coins",
            text=f"Rs.{profit:,.0f}",
        ),
        KeyPoint(
            icon="droplets",
            text=f"{water_saved_pct:.0f}% water saved",
        ),
    ]

    return Explanation(
        language=lang,  # type: ignore[arg-type]
        text=text,
        key_points=key_points,
        grounded=False,
        provider="template",
    )
