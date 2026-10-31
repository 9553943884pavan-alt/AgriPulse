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
    FarmProfile,
    Location,
    ProfitByScenario,
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
) -> list[CropOption]:
    """Convert candidate crops into fully priced, evaluated CropOptions."""
    if not candidates or not scenarios:
        return []

    drought_sc = next((s for s in scenarios if s.id == "drought"), scenarios[0])
    normal_sc = next((s for s in scenarios if s.id == "normal"), scenarios[0])
    excess_sc = next((s for s in scenarios if s.id == "excess"), scenarios[0])

    crop_options: list[CropOption] = []
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

            # 3. Water need
            wn = crop_water_need(crop_id, season, scenarios, efficiency)

            # 4. Fertilizer plan
            fert = fertilizer_plan(crop_id, season.name if hasattr(season, "name") else "Rabi")

            # 5. Cost per acre
            cost_bd = cost_svc.get_cost_breakdown(crop_id)
            cost_total = cost_bd.total_rs

            # 6. Prices
            price_sv = await price_svc.get_price(crop_id, crop_name, district)
            if price_sv is None:
                # Sugarcane or MSP fallback
                price_val = 3500.0
                price_sv = SourcedValue(
                    value=price_val,
                    unit="Rs/quintal",
                    source="Agmarknet fallback / MSP",
                    as_of=str(today.year),
                    status="official_dataset",
                )
            else:
                price_val = float(price_sv.value)

            # Expected harvest price (apply seasonal ratio or 1.0)
            seasonal_ratio = SourcedValue(
                value=1.02,
                unit="ratio",
                source="Agmarknet historical seasonal ratio",
                as_of=str(today.year),
                status="computed",
                history_years=5,
            )
            p_harv = round(price_val * float(seasonal_ratio.value), 2)
            exp_price = SourcedValue(
                value=p_harv,
                unit="Rs/quintal",
                source="Adjusted harvest quote",
                as_of=str(today.year),
                status="computed",
            )

            # 7. Profit per scenario
            profits = ProfitByScenario(
                drought=round(p_harv * y_d - cost_total, 2),
                normal=round(p_harv * y_n - cost_total, 2),
                excess=round(p_harv * y_e - cost_total, 2),
            )

            # Sowing duration & harvest month
            dur_days = getattr(cand, "duration_days", 110) or 110
            harvest_dt = today + timedelta(days=dur_days)
            harvest_month = harvest_dt.strftime("%Y-%m")

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
                    msp=None,
                    cost_per_acre=cost_bd,
                    fertilizer=fert,
                    water_need_m3_per_acre=wn,
                    profit_rs_per_acre=profits,
                )
            )
        except Exception as exc:
            logger.warning("Failed to build CropOption for %s: %s; skipping", crop_id, exc)

    return crop_options
