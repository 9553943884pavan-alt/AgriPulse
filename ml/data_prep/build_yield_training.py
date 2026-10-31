"""Rebuild yield_training.csv and the seasonal weather table from official data only.

Fixes found in the data review (see Teammate-B/data/DATA_FIXES.md):
  * weather from ONE source (Open-Meteo ERA5 archive, 1997-2025) instead of two disagreeing files
  * groundwater category / extraction joined per district (was "Safe" / 55.0 for every row)
  * aggregate DES rows removed ("Total foodgrain", "Pulses total", "Other ...")
  * crop names joined through crops_master.csv (adds crop_id)
  * irrigated_pct and fertilizer_use_kg_per_ha added (were planned in DATA_COLLECTION.md 5A but missing)
  * yield lags recomputed from the cleaned rows (past years only)

Season windows for DES crop year Y. The Indian crop year runs July to June (Arthapedia / DES); Kharif is the
south-west monsoon crop, Rabi the winter crop (Oct-Mar), Summer/Zaid the Mar-Jun crop. Non-overlapping windows used:
  Kharif Jun 1 Y - Oct 31 Y | Rabi Nov 1 Y - Mar 31 Y+1 | Summer Apr 1 Y+1 - Jun 30 Y+1 | Whole Year Jul 1 Y - Jun 30 Y+1
(Exact season dates vary by crop and state; this is a documented assumption.)
Rainfall "normal" for the departure % = district mean over 1997-2008 (training years only, no look-ahead).

Run from the repo root:  python -I ml/data_prep/build_yield_training.py
Test on partial weather data without touching the repo files:  python -I ml/data_prep/build_yield_training.py --test-out <folder>
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
A_PROC = REPO_ROOT / "Teammate-A" / "data" / "processed"
B_PROC = REPO_ROOT / "Teammate-B" / "data" / "processed"
B_B12 = REPO_ROOT / "Teammate-B" / "teammate_b" / "B12_yield_training_dataset"
RAW_WEATHER = REPO_ROOT / "Teammate-A" / "data" / "raw" / "open_meteo_archive_1997_2025"

RAIN_DAY_MM = 2.5  # IMD rainy-day threshold
HEAT_C = 35.0
NORMAL_YEARS = (1997, 2008)
FIRST_YEAR, LAST_YEAR = 1997, 2024  # last year with a full window (needs Jun 2025; archive runs to Dec 2025)
SEASON_WINDOWS = {  # (start_month, start_year_offset, end_month, end_year_offset)
    "Kharif": (6, 0, 10, 0),
    "Rabi": (11, 0, 3, 1),
    "Summer": (4, 1, 6, 1),
    "Whole Year": (7, 0, 6, 1),
}
AGGREGATE = re.compile(r"total|^other", re.IGNORECASE)


def norm(value: str) -> str:
    return re.sub(r"[^a-z]", "", str(value).lower())


def district_lookup() -> dict[str, str]:
    districts = pd.read_csv(A_PROC / "districts.csv")
    lookup = {}
    for row in districts.itertuples():
        for name in [row.district, *str(row.name_variants).split("|")]:
            lookup[norm(name)] = row.district
    return lookup


def longest_run(mask: np.ndarray) -> int:
    best = run = 0
    for flag in mask:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def seasonal_weather(lookup: dict[str, str]) -> pd.DataFrame:
    rows = []
    for path in sorted(RAW_WEATHER.glob("*.json")):
        district = lookup[norm(path.stem.replace("_", " "))]
        daily = pd.DataFrame(json.loads(path.read_text(encoding="utf-8"))["daily"])
        daily["time"] = pd.to_datetime(daily["time"])
        for year in range(FIRST_YEAR, LAST_YEAR + 1):
            for season, (sm, so, em, eo) in SEASON_WINDOWS.items():
                start = pd.Timestamp(year + so, sm, 1)
                end = pd.Timestamp(year + eo, em, 1) + pd.offsets.MonthEnd(0)
                window = daily[(daily["time"] >= start) & (daily["time"] <= end)]
                if window.empty or window["precipitation_sum"].isna().any():
                    continue
                rain = window["precipitation_sum"].to_numpy()
                tmax, tmin = window["temperature_2m_max"], window["temperature_2m_min"]
                rows.append({
                    "district": district, "year": year, "season": season,
                    "rainfall_mm": round(float(rain.sum()), 2),
                    "et0_mm": round(float(window["et0_fao_evapotranspiration"].sum()), 2),
                    "rainy_days": int((rain >= RAIN_DAY_MM).sum()),
                    "max_dry_spell_days": longest_run(rain < RAIN_DAY_MM),
                    "mean_temp_c": round(float(((tmax + tmin) / 2).mean()), 2),
                    "max_temp_c": round(float(tmax.max()), 2),
                    "heat_stress_days": int((tmax > HEAT_C).sum()),
                    "mean_humidity_pct": round(float(window["relative_humidity_2m_mean"].mean()), 2),
                })
    weather = pd.DataFrame(rows)
    normal = (
        weather[weather["year"].between(*NORMAL_YEARS)]
        .groupby(["district", "season"])["rainfall_mm"].mean().rename("normal_mm").reset_index()
    )
    weather = weather.merge(normal, on=["district", "season"], how="left")
    weather["rainfall_departure_pct"] = ((weather["rainfall_mm"] - weather["normal_mm"]) / weather["normal_mm"] * 100).round(2)
    return weather.drop(columns="normal_mm")[
        ["district", "year", "season", "rainfall_mm", "et0_mm", "rainfall_departure_pct", "rainy_days",
         "max_dry_spell_days", "mean_temp_c", "max_temp_c", "heat_stress_days", "mean_humidity_pct"]
    ]


def static_tables(lookup: dict[str, str]) -> pd.DataFrame:
    soil = pd.read_csv(A_PROC / "soil_npk_by_district.csv")
    soil = soil[soil["state"].str.upper() == "MAHARASHTRA"].copy()
    soil["district"] = soil["district"].map(lambda v: lookup.get(norm(v)))
    soil = soil.dropna(subset=["district"]).rename(columns={
        "n_kg_per_ha": "soil_n_kg_ha", "p_kg_per_ha": "soil_p_kg_ha", "k_kg_per_ha": "soil_k_kg_ha", "ph": "soil_ph"})
    soil = soil[["district", "soil_n_kg_ha", "soil_p_kg_ha", "soil_k_kg_ha", "soil_ph", "organic_carbon_pct"]]

    gw = pd.read_csv(A_PROC / "groundwater_by_block.csv")
    gw = gw[gw["block"].str.contains("District Avg", case=False)].copy()
    gw["district"] = gw["district"].map(lambda v: lookup.get(norm(v)))
    gw = gw.rename(columns={"category": "groundwater_category", "extraction_pct": "groundwater_extraction_pct"})
    gw = gw[["district", "groundwater_category", "groundwater_extraction_pct"]]

    irr = pd.read_csv(A_PROC / "irrigation_by_district.csv")
    irr["district"] = irr["district"].map(lambda v: lookup.get(norm(v)))
    irr = irr.rename(columns={"net_irrigated_area_pct": "irrigated_pct"})[["district", "irrigated_pct"]]

    fert = pd.read_csv(B_PROC / "fertilizer_use_by_district.csv")
    fert["district"] = fert["district"].map(lambda v: lookup.get(norm(v)))
    fert = fert.rename(columns={"fertilizer_use_kg_per_ha": "fertilizer_use_kg_per_ha"})[["district", "fertilizer_use_kg_per_ha"]]

    table = soil
    for other in (gw, irr, fert):
        table = table.merge(other.dropna(subset=["district"]).drop_duplicates("district"), on="district", how="outer")
    return table


def main() -> int:
    lookup = district_lookup()
    test_out = Path(sys.argv[sys.argv.index("--test-out") + 1]) if "--test-out" in sys.argv else None
    if test_out is None and len(list(RAW_WEATHER.glob("*.json"))) < 36:
        print("[ERROR] weather download incomplete; run ml/data_prep/fetch_weather.py first")
        return 1

    weather = seasonal_weather(lookup)
    if test_out is None:
        weather.to_csv(B_PROC / "district_rainfall_history.csv", index=False, encoding="utf-8")
        weather.to_csv(A_PROC / "district_weather_seasonal.csv", index=False, encoding="utf-8")
    else:
        test_out.mkdir(parents=True, exist_ok=True)
        weather.to_csv(test_out / "district_weather_seasonal.csv", index=False, encoding="utf-8")
    print(f"[OK] weather: {len(weather)} rows, {weather['district'].nunique()} districts, {weather['year'].min()}-{weather['year'].max()}")

    des = pd.read_csv(B_PROC / "district_crop_yields.csv")
    report = {"input_rows": len(des)}
    des["district"] = des["district"].map(lambda v: lookup.get(norm(v)))
    report["rows_unmatched_district"] = int(des["district"].isna().sum())
    des = des.dropna(subset=["district"])

    aggregate = des["crop"].map(lambda c: bool(AGGREGATE.search(c)))
    report["aggregate_rows_removed"] = int(aggregate.sum())
    report["aggregate_names"] = sorted(des.loc[aggregate, "crop"].unique())
    des = des[~aggregate]

    master = pd.read_csv(B_PROC / "crops_master.csv")
    to_id = dict(zip(master["des_crop_name"].dropna().map(str.casefold), master["crop_id"]))
    des["crop_id"] = des["crop"].map(lambda c: to_id.get(c.casefold()))
    report["crops_without_master_id"] = sorted(des.loc[des["crop_id"].isna(), "crop"].unique())

    data = des.merge(weather, on=["district", "year", "season"], how="left", validate="many_to_one")
    report["rows_without_weather"] = int(data["rainfall_mm"].isna().sum())
    data = data.dropna(subset=["rainfall_mm"])

    data = data.merge(static_tables(lookup), on="district", how="left")
    for column in ("soil_n_kg_ha", "groundwater_category", "irrigated_pct", "fertilizer_use_kg_per_ha"):
        report[f"rows_missing_{column}"] = int(data[column].isna().sum())

    data = data.sort_values(["district", "crop", "season", "year"]).reset_index(drop=True)
    keyed = data.set_index(["district", "crop", "season", "year"])["yield_tonnes_per_ha"]
    prev, avg3 = [], []
    for district, crop, season, year in zip(data["district"], data["crop"], data["season"], data["year"]):
        prev.append(keyed.get((district, crop, season, year - 1), np.nan))
        past = [keyed.get((district, crop, season, year - k), np.nan) for k in (1, 2, 3)]
        past = [v for v in past if not np.isnan(v)]
        avg3.append(round(float(np.mean(past)), 4) if past else np.nan)
    data["yield_prev_year"], data["yield_3yr_avg"] = prev, avg3
    data = data.rename(columns={"yield_tonnes_per_ha": "yield_t_per_ha"})

    columns = ["state", "district", "crop", "crop_id", "season", "year", "area_ha", "season_rainfall_mm",
               "rainfall_departure_pct", "rainy_days", "max_dry_spell_days", "mean_temp_c", "max_temp_c",
               "heat_stress_days", "et0_total_mm", "mean_humidity_pct", "soil_n_kg_ha", "soil_p_kg_ha",
               "soil_k_kg_ha", "soil_ph", "organic_carbon_pct", "groundwater_category",
               "groundwater_extraction_pct", "irrigated_pct", "fertilizer_use_kg_per_ha",
               "yield_prev_year", "yield_3yr_avg", "yield_t_per_ha"]
    data = data.rename(columns={"rainfall_mm": "season_rainfall_mm", "et0_mm": "et0_total_mm"})[columns]
    if test_out is None:
        data.to_csv(B_PROC / "yield_training.csv", index=False, encoding="utf-8")
        data.to_csv(B_B12 / "yield_training.csv", index=False, encoding="utf-8")
    else:
        data.to_csv(test_out / "yield_training.csv", index=False, encoding="utf-8")
    report["output_rows"] = len(data)
    report["groundwater_categories"] = data["groundwater_category"].value_counts(dropna=False).to_dict()
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
