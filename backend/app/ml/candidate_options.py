"""Build CropOption objects for candidate crops across climate scenarios."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.units import t_per_ha_to_q_per_acre
from app.ml.fertilizer import fertilizer_plan
from app.ml.suitability_scoring import suitability
from app.ml.water_need import crop_water_need
from app.ml.yield_model import predict_yield
from app.schemas import (
    Candidate,
    CropOption,
    ExcludedCrop,
    FarmProfile,
    Location,
    ProfitByScenario,
    RevenueByScenario,
    Scenario,
    Season,
    SourcedValue,
    YieldByScenario,
)
from app.services import costs as cost_svc
from app.services import prices as price_svc

logger = logging.getLogger(__name__)


async def build_crop_options(
    candidates: list[Candidate],
    scenarios: list[Scenario],
    location: Location,
    season: Season,
    profile: FarmProfile,
) -> tuple[list[CropOption], list[ExcludedCrop]]:
    """Convert candidates into priced options and report candidates without prices."""
    if not candidates or not scenarios:
        return [], []

    drought_sc = next((s for s in scenarios if s.id == "drought"), scenarios[0])
    normal_sc = next((s for s in scenarios if s.id == "normal"), scenarios[0])
    excess_sc = next((s for s in scenarios if s.id == "excess"), scenarios[0])

    crop_options: list[CropOption] = []
    excluded_crops: list[ExcludedCrop] = []
    district = location.district
    today = date.today()

    irr_method = str(profile.irrigation_method or "flood").lower()
    efficiency = {"drip": 0.90, "sprinkler": 0.75, "flood": 0.60}.get(irr_method, 0.60)

    for cand in candidates:
        crop_id = cand.crop_id
        names = cand.names if hasattr(cand, "names") and isinstance(cand.names, dict) else {"en": crop_id, "mr": crop_id, "hi": crop_id}
        crop_name = names.get("en", crop_id)

        try:
            # 1. Yields per scenario (convert t/ha to quintals/acre)
            yp_d = predict_yield(crop_id, location, season, drought_sc)
            yp_n = predict_yield(crop_id, location, season, normal_sc)
            yp_e = predict_yield(crop_id, location, season, excess_sc)

            y_d = t_per_ha_to_q_per_acre(float(yp_d.t_per_ha.value))
            y_n = t_per_ha_to_q_per_acre(float(yp_n.t_per_ha.value))
            y_e = t_per_ha_to_q_per_acre(float(yp_e.t_per_ha.value))

            yields = YieldByScenario(drought=y_d, normal=y_n, excess=y_e)

            # 2. Suitability score and factors (evaluated on normal scenario)
            suit = suitability(crop_id, location, season, normal_sc)

            # 3. Water need. A crop without sourced FAO coefficients cannot
            # enter the optimizer with an invented default requirement.
            try:
                wn = crop_water_need(crop_id, season, scenarios, efficiency)
            except (ValueError, FileNotFoundError) as exc:
                logger.info("Source-backed water input unavailable for %s: %s", crop_id, exc)
                excluded_crops.append(
                    ExcludedCrop(
                        crop_id=crop_id,
                        reason_code="DATA_UNAVAILABLE",
                        params={"field": "crop_water_coefficient"},
                    )
                )
                continue

            # 4-5. Required source-backed fertilizer and cost inputs
            try:
                fert = fertilizer_plan(crop_id, season.name if hasattr(season, "name") else "Rabi")
                cost_bd = cost_svc.get_cost_breakdown(crop_id)
            except (ValueError, FileNotFoundError) as exc:
                logger.info("Source-backed cost inputs unavailable for %s: %s", crop_id, exc)
                excluded_crops.append(
                    ExcludedCrop(
                        crop_id=crop_id,
                        reason_code="DATA_UNAVAILABLE",
                        params={"field": "cost_or_fertilizer"},
                    )
                )
                continue
            cost_total = cost_bd.total_rs

            # 6. Prices
            price_sv = await price_svc.get_price(crop_id, district)
            if price_sv is None:
                excluded_crops.append(
                    ExcludedCrop(
                        crop_id=crop_id,
                        reason_code="NO_REAL_PRICE",
                        params={"crop_name": crop_name},
                    )
                )
                continue
            price_val = float(price_sv.value)

            # Sowing duration & harvest month
            dur_days = cand.duration_days
            harvest_dt = today + timedelta(days=dur_days)
            harvest_month = harvest_dt.strftime("%Y-%m")

            ratio, history_years, ratio_source = price_svc.seasonal_price_ratio(
                crop_id,
                district,
                price_svc.quote_month(price_sv.as_of, today.month),
                harvest_dt.month,
            )
            seasonal_ratio = SourcedValue(
                value=ratio,
                unit="ratio",
                source=ratio_source,
                as_of=str(today.year),
                status="computed" if history_years >= price_svc.MIN_PRICE_YEARS else "assumption",
                history_years=history_years,
                note=(
                    None if history_years >= price_svc.MIN_PRICE_YEARS
                    else "Harvest-price seasonal adjustment unavailable; current sourced quote is used unadjusted"
                ),
            )
            msp = price_svc.get_msp(crop_id, season.name)
            p_harv = round(price_val * ratio, 2)
            if msp is not None:
                p_harv = max(p_harv, float(msp.value))
            exp_price = SourcedValue(
                value=p_harv,
                unit="Rs/quintal",
                source=(
                    "Current quote x historical seasonal ratio; floored at MSP"
                    if msp is not None
                    else "Current quote x historical seasonal ratio"
                ),
                as_of=str(today.year),
                status="computed",
            )

            # 7. Revenue and profit per scenario.  These are the exact values
            # subsequently used by the optimizer, so dashboard finance cannot
            # silently use a different price or yield definition.
            revenue = RevenueByScenario(
                drought=round(p_harv * y_d, 2),
                normal=round(p_harv * y_n, 2),
                excess=round(p_harv * y_e, 2),
            )
            profits = ProfitByScenario(
                drought=round(revenue.drought - cost_total, 2),
                normal=round(revenue.normal - cost_total, 2),
                excess=round(revenue.excess - cost_total, 2),
            )

            crop_options.append(
                CropOption(
                    crop_id=crop_id,
                    names=names,
                    season=cand.season,
                    suitability=suit,
                    yield_quintal_per_acre=yields,
                    price=price_sv,
                    expected_harvest_price=exp_price,
                    seasonal_ratio=seasonal_ratio,
                    duration_days=dur_days,
                    harvest_month=harvest_month,
                    opens_on=cand.opens_on,
                    msp=msp,
                    cost_per_acre=cost_bd,
                    fertilizer=fert,
                    water_need_m3_per_acre=wn,
                    profit_rs_per_acre=profits,
                    revenue_rs_per_acre=revenue,
                )
            )
        except Exception:
            logger.exception("Unexpected failure building CropOption for %s", crop_id)
            raise

    return crop_options, excluded_crops
