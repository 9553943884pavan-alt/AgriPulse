"""SVC.10 — run_plan(profile) → PlanResult.

This is the ONLY orchestration path. Both /api/plan (E2) and the agent
call exactly this function, so the two can never return different plans
for the same profile.

Stages (in order):
  1. location → SVC.2
  2. weather  → SVC.3
  3. soil     → SVC.4
  4. prices   → SVC.5   (per candidate crop)
  5. costs    → SVC.6
  6. water    → SVC.7   (after ML scenarios are available)
  7. ML pipeline: build_scenarios, candidate_crops, predict_yield,
               suitability, crop_water_need, fertilizer_plan
  8. optimizer: compare_strategies
  9. impact metrics
 10. template explanation

Required planning stages fail with AppError rather than returning a partial
success-shaped plan.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.core.errors import AppError
from app.data.loaders import load_crop_calendar
from app.schemas import (
    DataStatus,
    DefaultUsed,
    ExcludedCrop,
    Explanation,
    FarmProfile,
    Infeasibility,
    KeyPoint,
    Location,
    PlanResult,
    Season,
    SowingWindow,
    Warning,
)
from app.services import location as loc_svc
from app.services import soil as soil_svc  # noqa: F401
from app.services import weather as wx_svc
from app.services import water as water_svc

logger = logging.getLogger(__name__)


async def run_plan(profile: FarmProfile, thread_id: str | None = None, plan_id: str | None = None) -> PlanResult:
    """Orchestrate all stages and return a complete PlanResult.

    Source-backed exclusions are returned in excluded_crops. Unexpected failures
    are raised as AppError so the API cannot return a success-shaped empty plan.
    """
    # These IDs are used as opaque capabilities by the unauthenticated pilot API.
    # Keep all UUID entropy so they cannot be feasibly guessed.
    tid = thread_id or f"th_{uuid.uuid4().hex}"
    pid = plan_id or f"pl_{uuid.uuid4().hex}"
    now = datetime.now(tz=timezone.utc)
    warnings: list[Warning] = []
    excluded: list[ExcludedCrop] = []

    # ── Stage 1: Location ─────────────────────────────────────────────────────
    try:
        location: Location = await loc_svc.locate(profile.location_text)
    except AppError:
        raise  # location is required; propagate to API layer

    # ── Stage 2: Season (from crop calendar — ml/SPECS §3A) ──────────────────
    season = _detect_season(now.date())

    # ── Stage 3: Weather ──────────────────────────────────────────────────────
    weather = await wx_svc.get_weather(location)
    if not weather:
        warnings.append(Warning(code="CACHED_WEATHER", params={"district": location.district}))

    # ── Stages 4–8: ML pipeline (stubs for now) ───────────────────────────────
    try:
        from app.ml.stubs import build_scenarios, candidate_crops
        scenarios = build_scenarios(location, season)
    except Exception as exc:
        logger.exception("Scenario construction failed")
        raise AppError(
            "UPSTREAM_UNAVAILABLE",
            {"service": "scenario_builder"},
            "Climate scenarios could not be calculated from the available data.",
        ) from exc
    if len(scenarios) != 3:
        raise AppError(
            "UPSTREAM_UNAVAILABLE",
            {"service": "scenario_builder", "scenario_count": len(scenarios)},
            "A complete three-scenario plan is required before optimizing.",
        )

    water_budgets = []
    if scenarios:
        try:
            water_budgets = water_svc.build_water_budgets(profile, location, scenarios, weather)
        except Exception as exc:
            logger.exception("Water budget failed")
            raise AppError(
                "UPSTREAM_UNAVAILABLE",
                {"service": "water_budget"},
                "The water budget could not be calculated from the available source data.",
            ) from exc
        if len(water_budgets) != 3:
            raise AppError(
                "UPSTREAM_UNAVAILABLE",
                {"service": "water_budget", "scenario_count": len(water_budgets)},
                "A complete water budget is required before optimizing a plan.",
            )

    crops = []
    strategies = []
    recommended_strategy = None
    impact = None
    infeasibility: Infeasibility | None = None

    if scenarios:
        try:
            candidates, excluded_crops = candidate_crops(profile, location, season, water_budgets)
            excluded.extend(excluded_crops)

            if candidates:
                from app.ml.candidate_options import build_crop_options
                from app.ml.optimizer import compare_strategies
                from app.schemas import OptimizerInputs

                crops, price_excluded = await build_crop_options(
                    candidates, scenarios, location, season, profile
                )
                excluded.extend(price_excluded)
                if crops:
                    opt_inputs = OptimizerInputs(
                        profile=profile,
                        location=location,
                        season=season,
                        candidates=crops,
                        water_budgets=water_budgets,
                        scenario_weights=[0.2, 0.6, 0.2],
                        price_history_years={c.crop_id: 5 for c in crops},
                    )
                    strategies, impact, opt_warnings = compare_strategies(opt_inputs)
                    warnings.extend(opt_warnings)

                    # Three constructed weather scenarios are useful for
                    # deterministic comparisons, but not a calibrated joint
                    # crop-profit covariance model.  Until that evidence is
                    # available, select the verified LP baseline rather than
                    # a legacy QP-compatible response id.
                    from app.ml.constants import RISK_QP_ENABLED

                    rec_id = (
                        ("qp_drought_safe" if profile.risk_appetite == "safe" else "qp_balanced")
                        if RISK_QP_ENABLED
                        else "lp_max_profit"
                    )
                    rec_strat = next((s for s in strategies if s.id == rec_id), None)
                    if rec_strat is None and strategies:
                        rec_strat = strategies[0]
                    recommended_strategy = rec_strat.id if rec_strat else None
                    water_budgets = _populate_water_needs(
                        water_budgets,
                        crops,
                        strategies,
                        recommended_strategy,
                    )
                    if rec_strat and not rec_strat.feasible:
                        infeasibility = rec_strat.infeasibility
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Pipeline optimization stage failed")
            raise AppError(
                "UPSTREAM_UNAVAILABLE",
                {"service": "crop_optimization"},
                "The crop plan could not be calculated from the available source data.",
            ) from exc

    # ── Stage 9: OLD_COST_YEAR warning (always) ───────────────────────────────
    if not any(w.code == "OLD_COST_YEAR" for w in warnings):
        warnings.append(Warning(code="OLD_COST_YEAR", params={"year": "2022-23"}))
    warnings.extend(price_warnings(crops, warnings))

    # ── Stage 10: Template explanation ───────────────────────────────────────
    from app.agent.templates import build_template_explanation

    rec_for_text = next((s for s in strategies if s.id == recommended_strategy), None)
    water_saved_pct = 0.0
    if impact is not None:
        ws = getattr(impact, "water_saved_pct", None)
        # Same rule as the agent path (nodes.py): a plan that uses more water
        # than Traditional saved 0%, it never "saved -10%".
        water_saved_pct = max(0.0, float(getattr(ws, "value", ws) or 0.0))
    explanation = build_template_explanation(
        profile.language, profile.land_acres, rec_for_text, water_saved_pct
    )

    # Borewell declared but capacity inputs missing: groundwater is NOT credited
    # (no sourced district median exists). Disclose it instead of hiding it.
    if profile.water_source in ("borewell", "both") and not (
        profile.borewell_count and profile.borewell_yield_lph and profile.pump_hours_per_day
    ):
        warnings.append(Warning(code="ASSUMED_BOREWELL", params={"groundwater_credited_m3": 0}))
        profile = profile.model_copy(update={"defaults_used": [
            *profile.defaults_used,
            DefaultUsed(
                field="borewell_capacity",
                value=0,
                basis="Borewell yield / pump hours not provided; groundwater not counted in the water budget",
            ),
        ]})

    # Canal access declared but no sourced canal duty exists (water.py credits
    # 0 m³ rather than inventing one). Tell the farmer why the plan ignores it.
    if (profile.canal_access or profile.water_source in ("canal", "both")) and not any(
        w.code == "CANAL_NOT_CREDITED" for w in warnings
    ):
        warnings.append(Warning(code="CANAL_NOT_CREDITED", params={"canal_credited_m3": 0}))

    # Count sourced values for data_status
    live_count = sum(1 for sv in _iter_sourced_values(weather) if getattr(sv, "status", "") == "live")
    cached_count = sum(1 for sv in _iter_sourced_values(weather) if getattr(sv, "status", "") == "cached")

    return PlanResult(
        plan_id=pid,
        thread_id=tid,
        version=1,
        previous_version=None,
        created_at=now,
        profile=profile,
        location=location,
        season=season,
        scenarios=scenarios,
        crops=crops,
        excluded_crops=excluded,
        water=water_budgets,
        strategies=strategies,
        recommended_strategy=recommended_strategy,
        impact=impact,
        infeasibility=infeasibility,
        explanation=explanation,
        warnings=warnings,
        data_status=DataStatus(live=live_count, cached=cached_count, official_dataset=18),
    )


def price_warnings(crops, existing) -> list[Warning]:
    """CACHED_PRICES when any crop price is not a live quote (disclosed, never silent)."""
    if any(w.code == "CACHED_PRICES" for w in existing):
        return []
    stale = [c.crop_id for c in crops if getattr(c.price, "status", "") == "cached"]
    return [Warning(code="CACHED_PRICES", params={"crops": stale})] if stale else []


def _populate_water_needs(water_budgets, crops, strategies, recommended_strategy):
    """Set Traditional and recommended water totals for each climate scenario."""
    from app.schemas import SourcedValue, WaterNeedSummary

    crop_by_id = {crop.crop_id: crop for crop in crops}
    traditional = next((item for item in strategies if item.id == "traditional"), None)
    recommended = next(
        (item for item in strategies if item.id == recommended_strategy),
        None,
    )

    def total_for(strategy, scenario: str) -> float:
        if strategy is None:
            return 0.0
        total = 0.0
        for allocation in strategy.allocations:
            crop = crop_by_id.get(allocation.crop_id)
            if crop is not None:
                need = getattr(crop.water_need_m3_per_acre, scenario)
                total += allocation.acres * float(need.value)
        return round(total, 1)

    updated = []
    for budget in water_budgets:
        scenario = budget.scenario
        traditional_total = total_for(traditional, scenario)
        recommended_total = total_for(recommended, scenario)
        source = f"Computed: sum(acres × per-crop {scenario} water need)"
        as_of = datetime.now(tz=timezone.utc).date().isoformat()
        updated.append(budget.model_copy(update={
            "need_m3": WaterNeedSummary(
                traditional_plan=SourcedValue(
                    value=traditional_total,
                    unit="m3",
                    source=source,
                    source_url="",
                    as_of=as_of,
                    status="computed",
                ),
                recommended_plan=SourcedValue(
                    value=recommended_total,
                    unit="m3",
                    source=source,
                    source_url="",
                    as_of=as_of,
                    status="computed",
                ),
            ),
        }))
    return updated


def _detect_season(today) -> Season:
    """Detect the current sowable season from crop_calendar.csv (ml/SPECS §3A).

    Returns the dominant season for crops sowable today or opening in 21 days.
    Falls back to Rabi (Oct–Mar) if no crops found.
    """
    from datetime import date, timedelta

    grace_days = 7
    opens_days = 21

    try:
        cal = load_crop_calendar()
        sowable_seasons = set()

        for _, row in cal.iterrows():
            sm = int(row.get("sowing_start_month", 0) or 0)
            em = int(row.get("sowing_end_month", 0) or 0)
            season = str(row.get("season", ""))
            if not sm or not em:
                continue
            # Build approximate sowing window for this year
            year = today.year
            from datetime import date
            try:
                sow_start = date(year, sm, 1)
                sow_end = date(year if em >= sm else year, em, 28)
            except ValueError:
                continue
            # Sowable: today in [sow_start-7, sow_end] or opens in next 21 days
            if (sow_start - timedelta(days=grace_days)) <= today <= sow_end:
                sowable_seasons.add(season)
            elif sow_start > today and (sow_start - today).days <= opens_days:
                sowable_seasons.add(season)

        if "Rabi" in sowable_seasons:
            preferred = "Rabi"
        elif "Kharif" in sowable_seasons:
            preferred = "Kharif"
        elif sowable_seasons:
            preferred = next(iter(sowable_seasons))
        else:
            preferred = "Rabi"  # safe default Oct-Mar

    except Exception as exc:
        logger.warning("Season detection failed: %s", exc)
        preferred = "Rabi"

    # Sowing windows per season (approximate)
    _windows = {
        "Kharif": ("06-01", "07-31"),
        "Rabi": ("10-15", "12-15"),
        "Summer": ("02-01", "03-31"),
        "Whole Year": ("06-01", "12-31"),
    }
    start_s, end_s = _windows.get(preferred, ("10-15", "12-15"))
    year = today.year

    return Season(
        name=preferred,
        sowing_window=SowingWindow(
            start=f"{year}-{start_s}",
            end=f"{year}-{end_s}",
        ),
        status="official_dataset",
    )


def _template_explanation(language: str, location: Location, season: Season) -> Explanation:
    """Generate a template explanation without an LLM call."""
    texts = {
        "mr": (
            f"{location.district} जिल्ह्यासाठी {season.name} हंगामाची योजना तयार करत आहोत. "
            "ML मॉडेल्स लवकरच उपलब्ध होतील."
        ),
        "hi": (
            f"{location.district} जिले के लिए {season.name} मौसम की योजना तैयार की जा रही है। "
            "ML मॉडल शीघ्र ही उपलब्ध होंगे।"
        ),
        "en": (
            f"Building a {season.name} plan for {location.district}. "
            "ML models will be integrated shortly."
        ),
    }
    return Explanation(
        language=language,  # type: ignore[arg-type]
        text=texts.get(language, texts["en"]),
        key_points=[KeyPoint(icon="map-pin", text=f"{location.district}, {location.state}")],
        grounded=False,
        provider="template",
    )


def _iter_sourced_values(weather: dict):
    """Yield SourcedValue objects from the weather dict."""
    for v in weather.values():
        if hasattr(v, "status"):
            yield v
