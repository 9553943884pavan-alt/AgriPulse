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
  7. ML stubs: build_scenarios, candidate_crops, predict_yield,
               suitability, crop_water_need, fertilizer_plan
  8. optimizer: compare_strategies
  9. impact metrics
 10. template explanation

When ML stubs raise NotImplementedError the pipeline returns a partial
PlanResult with an empty crops list and an infeasibility note, so the
API always responds rather than crashing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.core.errors import AppError
from app.data.loaders import load_crop_calendar
from app.schemas import (
    DataStatus,
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

    Never raises — always returns a PlanResult even if some stages fail.
    Errors are surfaced in warnings[] and excluded_crops[].
    """
    tid = thread_id or f"th_{uuid.uuid4().hex[:8]}"
    pid = plan_id or f"pl_{uuid.uuid4().hex[:6]}"
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
    except NotImplementedError:
        scenarios = []
        logger.info("ML stubs not implemented yet — returning empty plan")

    water_budgets = []
    if scenarios:
        try:
            water_budgets = water_svc.build_water_budgets(profile, location, scenarios, weather)
        except Exception as exc:
            logger.warning("Water budget failed: %s", exc)

    crops = []
    strategies = []
    recommended_strategy = None
    impact = None
    infeasibility: Infeasibility | None = None

    if scenarios:
        try:
            from app.ml.stubs import candidate_crops
            candidates, excluded_crops = candidate_crops(profile, location, season, water_budgets)
            excluded.extend(excluded_crops)

            if candidates:
                from app.ml.candidate_options import build_crop_options
                from app.ml.optimizer import compare_strategies
                from app.schemas import OptimizerInputs

                crops = await build_crop_options(candidates, scenarios, location, season, profile)
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

                    rec_id = "qp_drought_safe" if profile.risk_appetite == "safe" else "qp_balanced"
                    rec_strat = next((s for s in strategies if s.id == rec_id), None)
                    if rec_strat is None and strategies:
                        rec_strat = strategies[0]
                    recommended_strategy = rec_strat.id if rec_strat else None
                    if rec_strat and not rec_strat.feasible:
                        infeasibility = rec_strat.infeasibility
        except Exception as exc:
            logger.warning("Pipeline optimization stage failed: %s", exc)

    # ── Stage 9: OLD_COST_YEAR warning (always) ───────────────────────────────
    warnings.append(Warning(code="OLD_COST_YEAR", params={"year": "2022-23"}))

    # ── Stage 10: Template explanation ───────────────────────────────────────
    explanation = _template_explanation(profile.language, location, season)

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
