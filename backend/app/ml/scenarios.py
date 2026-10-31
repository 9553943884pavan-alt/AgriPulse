"""ML.5 — Climate Scenarios per district (analogue years P10 / P50 / P90).

Derives 3 deterministic, auditable climate scenarios (Drought, Normal, Excess)
for any given district and season using the 1997-2024 Open-Meteo ERA5 weather series.

Rabi ranking uses:
    water_index = 0.5 * Rabi rainfall + 0.5 * preceding Kharif rainfall
(because winter crops rely on stored soil moisture and reservoir carryover).
Kharif, Summer, and Whole Year use the season's rainfall directly.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.data.loaders import load_rainfall_history
from app.data.resolver import resolve_district
from app.schemas import Location, Scenario, Season, SourcedValue

logger = logging.getLogger(__name__)

SCENARIO_WEIGHTS = {"drought": 0.20, "normal": 0.60, "excess": 0.20}
SCENARIO_PERCENTILES = {"drought": 0.10, "normal": 0.50, "excess": 0.90}
SOURCE_NAME = "Open-Meteo ERA5 historical archive 1997-2025"


def build_scenarios(location: Location, season: Season) -> list[Scenario]:
    """Build Drought (P10), Normal (P50), Excess (P90) scenarios from historical weather."""
    district = resolve_district(location.district)
    season_name = season.name if hasattr(season, "name") else str(season)

    # Normalize season name (e.g. "Kharif", "Rabi", "Summer", "Whole Year")
    season_title = season_name.title()
    if season_title not in {"Kharif", "Rabi", "Summer", "Whole Year"}:
        season_title = "Rabi"  # safe default

    history = load_rainfall_history()
    dist_df = history[history["district"] == district].copy()

    if dist_df.empty:
        logger.warning("No rainfall history for district %s; using statewide fallback", district)
        dist_df = history.groupby(["year", "season"], as_index=False).mean(numeric_only=True)
        dist_df["district"] = district

    # Calculate water index
    if season_title == "Rabi":
        rabi_df = dist_df[dist_df["season"] == "Rabi"].set_index("year")
        kharif_df = dist_df[dist_df["season"] == "Kharif"].set_index("year")
        # Align years
        common_years = rabi_df.index.intersection(kharif_df.index)
        if len(common_years) > 0:
            wi = 0.5 * rabi_df.loc[common_years, "rainfall_mm"] + 0.5 * kharif_df.loc[common_years, "rainfall_mm"]
            season_df = dist_df[(dist_df["season"] == "Rabi") & (dist_df["year"].isin(common_years))].copy()
            season_df["water_index"] = season_df["year"].map(wi)
        else:
            season_df = dist_df[dist_df["season"] == "Rabi"].copy()
            season_df["water_index"] = season_df["rainfall_mm"]
    else:
        season_df = dist_df[dist_df["season"] == season_title].copy()
        if season_df.empty:
            # Fallback to Kharif or Rabi if season not found
            season_df = dist_df[dist_df["season"] == "Rabi"].copy()
        season_df["water_index"] = season_df["rainfall_mm"]

    sorted_df = season_df.sort_values("water_index").reset_index(drop=True)
    n = len(sorted_df)

    if n == 0:
        raise ValueError(f"No weather observations available for district {district} in {season_title}")

    # Build all-year samples for covariance risk estimation
    all_year_samples = [
        SourcedValue(
            value=round(float(row["rainfall_mm"]), 1),
            unit="mm",
            source=SOURCE_NAME,
            as_of=str(int(row["year"])),
            status="official_dataset",
        )
        for _, row in season_df.sort_values("year").iterrows()
    ]

    scenarios: list[Scenario] = []
    labels: dict[str, str] = {
        "drought": "Drought (10th percentile)",
        "normal": "Normal (median)",
        "excess": "Excess (90th percentile)",
    }

    for sc_id, pct in SCENARIO_PERCENTILES.items():
        idx = int(round(pct * (n - 1)))
        row = sorted_df.iloc[idx]
        year = int(row["year"])
        rain_val = round(float(row["rainfall_mm"]), 1)

        scenarios.append(
            Scenario(
                id=sc_id,  # type: ignore[arg-type]
                label=labels[sc_id],
                season_rain_mm=SourcedValue(
                    value=rain_val,
                    unit="mm",
                    source=SOURCE_NAME,
                    as_of=str(year),
                    status="official_dataset",
                ),
                probability=SCENARIO_WEIGHTS[sc_id],
                analogue_year=year,
                all_year_samples=all_year_samples,
                rainfall_mm=rain_val,
                et0_mm=round(float(row["et0_mm"]), 1) if "et0_mm" in row and not pd.isna(row["et0_mm"]) else None,
                rainy_days=int(row["rainy_days"]) if "rainy_days" in row and not pd.isna(row["rainy_days"]) else None,
                max_dry_spell_days=int(row["max_dry_spell_days"]) if "max_dry_spell_days" in row and not pd.isna(row["max_dry_spell_days"]) else None,
                mean_temp_c=round(float(row["mean_temp_c"]), 1) if "mean_temp_c" in row and not pd.isna(row["mean_temp_c"]) else None,
                max_temp_c=round(float(row["max_temp_c"]), 1) if "max_temp_c" in row and not pd.isna(row["max_temp_c"]) else None,
                heat_stress_days=int(row["heat_stress_days"]) if "heat_stress_days" in row and not pd.isna(row["heat_stress_days"]) else None,
                mean_humidity_pct=round(float(row["mean_humidity_pct"]), 1) if "mean_humidity_pct" in row and not pd.isna(row["mean_humidity_pct"]) else None,
            )
        )

    return scenarios
