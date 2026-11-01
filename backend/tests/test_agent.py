"""Agent Conversational & Node Unit Tests (AG.1-AG.10, ml/SPECS §8.5).

Tests:
  1. Devanagari numerals, Indian number words, and digit grouping normalization.
  2. Profile extraction across Marathi, Hindi, and English sentences.
  3. Missing required field detection and language-specific question generation.
  4. Number grounding checker (AG.9): exact matches, tolerance, and hallucination rejection.
  5. Rule-based template fallback (AG.10) for 1, 2, and 3+ crop allocations.
  6. Constraint relaxation ladder (AG.6) and feasibility checks.
  7. Route decision and patch merging (AG.5).
"""

from __future__ import annotations

import pytest

from app.agent.grounding import grounding_check
from app.agent.nodes import (
    _devanagari_to_ascii,
    _extract_float,
    _parse_number_words,
    _regex_profile_fallback,
    ask_missing_node,
    check_feasibility_node,
    merge_patch_node,
    relax_constraint_node,
    route_node,
)
from app.agent.templates import build_template_explanation
from app.schemas import (
    Allocation,
    FarmProfile,
    ProfitByScenario,
    StrategyResult,
    StrategyTotals,
)


# ── 1. Numeral & Unit Normalisation ──────────────────────────────────────────

def test_devanagari_digit_conversion():
    assert _devanagari_to_ascii("०१२३४५६७८९") == "0123456789"
    assert _devanagari_to_ascii("५ एकर") == "5 एकर"
    assert _devanagari_to_ascii("बजेट ७०००० रुपये") == "बजेट 70000 रुपये"


def test_indian_number_word_expansion():
    assert "50000.0" in _parse_number_words("50 हजार")
    assert "50000.0" in _parse_number_words("50 hazar")
    assert "150000.0" in _parse_number_words("1.5 lakh")
    assert "200000.0" in _parse_number_words("2 लाख")
    assert "10000000.0" in _parse_number_words("1 crore")
    assert "10000000.0" in _parse_number_words("1 करोड़")


def test_extract_float_with_grouping_and_words():
    assert _extract_float("1,00,000") == 100000.0
    assert _extract_float("२,५०,०००") == 250000.0
    assert _extract_float("75 hazar") == 75000.0
    assert _extract_float("३.५") == 3.5


# ── 2. Profile Extraction Fallback ───────────────────────────────────────────

@pytest.mark.parametrize(
    "sentence,expected_acres,expected_budget,expected_water",
    [
        # Marathi sentences
        ("माझ्याकडे Pune येथे ५ एकर जमीन आहे आणि ७०००० रुपये बजेट आहे, बोअरवेल आहे", 5.0, 70000.0, "borewell"),
        ("Nashik मध्ये 8 एकर शेती आहे आणि 1.2 lakh रुपये भांडवल आहे, कालवा पाणी आहे", 8.0, 120000.0, "canal"),
        ("Solapur मध्ये 10 एकर जमीन आणि कोरडवाहू शेती आहे, बजेट 50 हजार रुपये", 10.0, 50000.0, "rainfed"),
        # Hindi sentences
        ("मेरे पास Jalgaon में ८ एकड़ जमीन है और १२०००० रुपये का बजट है, बोरिंग है", 8.0, 120000.0, "borewell"),
        ("Nagpur में 4 एकड़ जमीन और 60,000 रुपये का बजट है, नहर का पानी मिलता है", 4.0, 60000.0, "canal"),
        ("Kolhapur में 2.5 एकड़ खेत है और 40 हजार रुपये बजट है", 2.5, 40000.0, None),
        # English sentences
        ("I have 6 acres in Nashik with borewell and 90,000 rupees budget", 6.0, 90000.0, "borewell"),
        ("My farm is 12 acres in Satara with canal access and 1.5 lakh budget", 12.0, 150000.0, "canal"),
        ("I have 40 guntha land in Pune with 50000 rs budget", 1.0, 50000.0, None),  # 40 guntha = 1 acre
        ("Farm size 3 acres, budget 45,000 rs in Sangli", 3.0, 45000.0, None),
    ],
)
def test_regex_profile_extraction_multi_language(sentence, expected_acres, expected_budget, expected_water):
    res = _regex_profile_fallback(sentence)
    if expected_acres is not None:
        assert res.get("land_acres") == pytest.approx(expected_acres, 0.01)
    if expected_budget is not None:
        assert res.get("budget_rs") == pytest.approx(expected_budget, 1.0)
    if expected_water is not None:
        assert res.get("water_source") == expected_water


# ── 3. Missing Field Prompting (AG.4) ─────────────────────────────────────────

def test_ask_missing_budget_in_marathi():
    state = {
        "missing": ["budget_rs"],
        "language": "mr",
        "trace": [],
    }
    res = ask_missing_node(state)
    assert "question" in res
    assert res["question"]["field"] == "budget_rs"
    assert "बजेट" in res["question"]["text"] or "रुपये" in res["question"]["text"]


def test_ask_missing_land_in_hindi():
    state = {
        "missing": ["land_acres"],
        "language": "hi",
        "trace": [],
    }
    res = ask_missing_node(state)
    assert "question" in res
    assert res["question"]["field"] == "land_acres"
    assert "एकड़" in res["question"]["text"] or "जमीन" in res["question"]["text"]


def test_ask_missing_location_in_english():
    state = {
        "missing": ["location_text"],
        "language": "en",
        "trace": [],
    }
    res = ask_missing_node(state)
    assert "question" in res
    assert res["question"]["field"] == "location_text"
    assert "village" in res["question"]["text"].lower() or "district" in res["question"]["text"].lower()


# ── 4. Number Grounding Checker (AG.9) ───────────────────────────────────────

def test_grounding_passes_when_all_numbers_grounded():
    tool_outputs = {
        "expected_profit_rs": 85000.0,
        "yield_quintal": 14.5,
        "water_saved_pct": 20.0,
        "land_acres": 5.0,
    }
    explanation = "तुमच्या 5.0 एकर जमिनीसाठी अपेक्षित नफा Rs.85,000 आहे आणि पाणी बचत 20% होईल."
    assert grounding_check(explanation, tool_outputs) is True


def test_grounding_passes_with_five_percent_tolerance():
    # 84,000 is within 5% of 85,000 (|84000 - 85000| / 85000 = 1.17%)
    tool_outputs = {"expected_profit_rs": 85000.0}
    explanation = "Expected return is about Rs. 84,000."
    assert grounding_check(explanation, tool_outputs) is True


def test_grounding_fails_on_hallucinated_number():
    tool_outputs = {
        "expected_profit_rs": 85000.0,
        "land_acres": 5.0,
    }
    # 9,99,999 is completely fabricated
    explanation = "Your profit will be Rs. 9,99,999 on 5.0 acres."
    assert grounding_check(explanation, tool_outputs) is False


def test_grounding_supports_devanagari_numerals():
    tool_outputs = {
        "expected_profit_rs": 75000.0,
        "land_acres": 4.0,
    }
    explanation = "४.० एकर क्षेत्रावर ७५,००० रुपये नफा मिळेल."
    assert grounding_check(explanation, tool_outputs) is True


def test_grounding_empty_text_passes():
    assert grounding_check("कोणतेही आकडे नसलेला साधा मजकूर", {}) is True


# ── 5. Template Explanation Fallback (AG.10) ─────────────────────────────────

def _make_strategy(crop_ids: list[str], profit: float, water_saved: float) -> StrategyResult:
    allocs = [
        Allocation(
            crop_id=cid,
            acres=2.5,
            share_pct=0.5,
            cost_rs=30000.0,
            water_m3=2000.0,
            profit_rs=ProfitByScenario(drought=20000, normal=35000, excess=40000),
        )
        for cid in crop_ids
    ]
    return StrategyResult(
        id="qp_balanced",
        label="QP Balanced",
        kind="qp",
        risk_lambda=0.5,
        allocations=allocs,
        totals=StrategyTotals(
            land_used_acres=5.0,
            budget_used_rs=60000.0,
            fertilizer_kg={"n": 40.0, "p2o5": 20.0, "k2o": 10.0},
            water_m3=4000.0,
        ),
        profit_by_scenario_rs=ProfitByScenario(drought=40000, normal=70000, excess=80000),
        expected_profit_rs=profit,
        worst_case_profit_rs=40000.0,
        feasible=True,
        binding_constraints=[],
        safety_scenario="drought",
    )


def test_template_explanation_one_crop_marathi():
    strat = _make_strategy(["soybean"], profit=55000.0, water_saved=15.0)
    exp = build_template_explanation(language="mr", land_acres=2.5, strategy=strat, water_saved_pct=15.0)
    assert exp.provider == "template"
    assert exp.grounded is False
    assert "soybean" in exp.text
    assert "Rs.55,000" in exp.text
    assert "15%" in exp.text


def test_template_explanation_two_crops_hindi():
    strat = _make_strategy(["soybean", "chickpea"], profit=82000.0, water_saved=22.0)
    exp = build_template_explanation(language="hi", land_acres=5.0, strategy=strat, water_saved_pct=22.0)
    assert exp.provider == "template"
    assert "soybean" in exp.text
    assert "chickpea" in exp.text
    assert "Rs.82,000" in exp.text


def test_template_explanation_no_plan():
    exp = build_template_explanation(language="en", land_acres=5.0, strategy=None)
    assert exp.provider == "template"
    # Current no-plan wording (pipeline/agent template): explains, never a Rs 0 plan.
    assert "no profitable crop plan was found" in exp.text


# ── 6. Constraint Relaxation Ladder (AG.6) ───────────────────────────────────

def test_relaxation_ladder_steps():
    state = {
        "relaxation_count": 0,
        "relaxations": [],
        "trace": [],
        "candidates": [],
    }

    # Step 0: CAP_TO_1
    s0 = relax_constraint_node(state)
    assert s0["relaxation_count"] == 1
    assert "CAP_TO_1" in s0["relaxations"]

    # Step 1: REDUCE_AREA
    s1 = relax_constraint_node(s0)
    assert s1["relaxation_count"] == 2
    assert "REDUCE_AREA" in s1["relaxations"]

    # Step 2: DROP_WATER_HUNGRY_CROP
    s2 = relax_constraint_node(s1)
    assert s2["relaxation_count"] == 3
    assert "DROP_WATER_HUNGRY_CROP" in s2["relaxations"]

    # Step 3: USE_NORMAL_SCENARIO_WATER
    s3 = relax_constraint_node(s2)
    assert s3["relaxation_count"] == 4
    assert "USE_NORMAL_SCENARIO_WATER" in s3["relaxations"]


def test_feasibility_check_infeasible_after_max_relaxations():
    state = {
        "strategies": [],
        "relaxation_count": 4,
        "trace": [],
    }
    res = check_feasibility_node(state)
    assert res.get("feasibility") == "INFEASIBLE"


def test_feasibility_check_reports_infeasible_when_no_allocation():
    # The optimizer runs the relaxation ladder itself; the agent only reads the verdict.
    state = {
        "strategies": [],
        "relaxation_count": 1,
        "trace": [],
    }
    res = check_feasibility_node(state)
    assert res.get("feasibility") == "INFEASIBLE"


# ── 7. Route and Patch Decisions (AG.5) ───────────────────────────────────────

def test_route_new_plan_when_no_strategies():
    state = {"strategies": [], "message": "मी पुणे येथील शेतकरी आहे"}
    res = route_node(state)
    assert res["route"] == "new_plan"


def test_route_follow_up_when_plan_exists_and_changed_fact():
    state = {
        "strategies": [{"id": "qp_balanced"}],
        "message": "माझे बजेट आता 90000 रुपये आहे",
    }
    res = route_node(state)
    assert res["route"] == "follow_up"


def test_route_question_when_plan_exists_no_changed_fact():
    state = {
        "strategies": [{"id": "qp_balanced"}],
        "message": "कोणते खत कधी द्यावे?",
    }
    res = route_node(state)
    assert res["route"] == "question"


def test_route_patch_when_profile_patch_present():
    state = {"profile_patch": {"budget_rs": 95000.0}}
    res = route_node(state)
    assert res["route"] == "patch"


def test_merge_patch_node_updates_profile():
    prof = FarmProfile(location_text="Pune", land_acres=5.0, budget_rs=60000.0)
    state = {
        "profile": prof,
        "profile_patch": {"budget_rs": 80000.0, "risk_appetite": "safe"},
    }
    res = merge_patch_node(state)
    updated = res["profile"]
    assert updated.budget_rs == 80000.0
    assert updated.risk_appetite == "safe"
    assert res["route"] == "follow_up"
    assert res["profile_patch"] is None
