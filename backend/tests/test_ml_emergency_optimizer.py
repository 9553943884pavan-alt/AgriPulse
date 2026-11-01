"""Regression tests for optimizer invariants, empty-plan diagnosis and SHAP factors."""
from __future__ import annotations

import pytest

from app.ml.optimizer import compare_strategies, optimize
from tests.test_optimizer import _crop, _inputs

WEIGHTS = {"drought": 0.2, "normal": 0.6, "excess": 0.2}


def _check_invariants(inputs, strategy):
    crops = {c.crop_id: c for c in inputs.candidates}
    land = inputs.profile.land_acres
    acres = sum(a.acres for a in strategy.allocations)
    assert all(a.acres >= 0 for a in strategy.allocations)
    assert acres <= land + 1e-9
    assert abs(strategy.totals.land_used_acres - acres) < 1e-6
    for a in strategy.allocations:
        crop = crops[a.crop_id]
        assert a.revenue_rs is not None
        for s in WEIGHTS:
            assert getattr(a.profit_rs, s) == pytest.approx(a.acres * getattr(crop.profit_rs_per_acre, s))
            # R = C + P per allocation (cost_rs is rounded to whole rupees)
            assert getattr(a.revenue_rs, s) == pytest.approx(
                a.cost_rs + getattr(a.profit_rs, s), abs=1.0
            )
    expected = sum(w * getattr(strategy.profit_by_scenario_rs, s) for s, w in WEIGHTS.items())
    assert strategy.expected_profit_rs == pytest.approx(expected, abs=1.0)
    if strategy.id != "traditional":
        water_cap = {w.scenario: w.available_m3.total.value for w in inputs.water_budgets}
        water = sum(
            a.acres * getattr(crops[a.crop_id].water_need_m3_per_acre, strategy.safety_scenario).value
            for a in strategy.allocations
        )
        cost = sum(a.acres * crops[a.crop_id].cost_per_acre.total_rs for a in strategy.allocations)
        assert water <= water_cap[strategy.safety_scenario] + 1e-6
        assert cost <= inputs.profile.budget_rs + 1e-6


@pytest.mark.parametrize("kwargs", [
    {}, {"budget": 30000}, {"budget": 5000}, {"land": 0.5}, {"land": 2.0, "budget": 1_000_000},
    {"water_total": 0},
])
def test_all_strategies_respect_limits_and_reconcile(kwargs):
    inputs = _inputs(**kwargs)
    strategies, _, _ = compare_strategies(inputs)
    assert {s.id for s in strategies} == {"traditional", "lp_max_profit", "qp_balanced", "qp_drought_safe"}
    for s in strategies:
        _check_invariants(inputs, s)


def test_traditional_reports_revenue_and_truthful_feasibility():
    over_budget = optimize("traditional", _inputs(budget=5000))
    assert over_budget.allocations and all(a.revenue_rs is not None for a in over_budget.allocations)
    assert "budget" in over_budget.traditional_exceeds
    assert over_budget.feasible is False

    within = optimize("traditional", _inputs(land=0.5, budget=1_000_000, water_total=1_000_000))
    assert within.traditional_exceeds == []
    assert within.feasible is True


def test_traditional_equal_split_never_exceeds_land():
    result = optimize("traditional", _inputs(land=2.0))
    assert sum(a.acres for a in result.allocations) <= 2.0
    assert sum(a.acres for a in result.allocations) == pytest.approx(2.0, abs=1e-3)


def test_empty_plan_from_negative_margins_is_no_positive_allocation():
    inputs = _inputs(crops=[_crop("a", -5000, -2000, -3000), _crop("b", -1000, -500, -800)])
    result = optimize("lp_max_profit", inputs)
    assert not result.feasible and result.allocations == []
    assert result.infeasibility.suggestion_code == "NO_POSITIVE_ALLOCATION"


def test_empty_plan_from_zero_water_names_water_not_unprofitability():
    inputs = _inputs()
    for budget in inputs.water_budgets:
        budget.available_m3.total.value = 0
    result = optimize("lp_max_profit", inputs)
    assert not result.feasible and result.allocations == []
    inf = result.infeasibility
    assert inf.suggestion_code == "RESOURCE_LIMIT_BLOCKS_ALLOCATION"
    assert inf.violated == ["water"]
    assert inf.detail[0].constraint == "water" and inf.detail[0].shortfall_m3 > 0


def test_empty_plan_from_tiny_budget_names_budget():
    result = optimize("lp_max_profit", _inputs(budget=100))
    assert result.infeasibility.suggestion_code == "RESOURCE_LIMIT_BLOCKS_ALLOCATION"
    assert result.infeasibility.violated == ["budget"]


# ── SHAP factors come from the trained model and differ by crop ──────────────

@pytest.fixture
def pune_normal():
    from app.ml.scenarios import build_scenarios
    from app.schemas import Location, Season, SowingWindow

    loc = Location(input="Pune", resolved_name="Pune, Maharashtra", district="Pune",
                   state="Maharashtra", latitude=18.5204, longitude=73.8567)
    season = Season(name="Rabi", sowing_window=SowingWindow(start="2026-10-15", end="2026-12-15"))
    normal = next(s for s in build_scenarios(loc, season) if s.id == "normal")
    return loc, season, normal


def test_shap_factors_are_crop_specific(pune_normal):
    from app.ml.suitability_scoring import suitability

    loc, season, normal = pune_normal
    chickpea = suitability("chickpea", loc, season, normal)
    maize = suitability("maize", loc, season, normal)
    assert not chickpea.fallback_used and not maize.fallback_used
    sig = lambda s: [(f.feature, f.effect_quintal_per_acre) for f in s.top_factors]  # noqa: E731
    assert sig(chickpea) != sig(maize)


def test_baseline_yield_crop_has_no_model_factors(pune_normal):
    from app.ml.suitability_scoring import suitability
    from app.ml.yield_model import predict_yield

    loc, season, normal = pune_normal
    assert predict_yield("onion", loc, season, normal).t_per_ha.status != "model"
    onion = suitability("onion", loc, season, normal)
    assert onion.fallback_used is True
    assert onion.top_factors == []
