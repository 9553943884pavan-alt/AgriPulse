"""Data integrity gate for the collected datasets. Run from the repo root:  python -I ml/data_prep/check_data.py

Exit code 0 = all checks pass. Each failed check prints what is wrong. Checks encode the problems found in the
2026-10-31 data review so they cannot come back silently.
"""

import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
A = REPO_ROOT / "data" / "processed"
B = REPO_ROOT / "data" / "processed"
KEY_PATTERN = re.compile(r"579b464db66ec23bdd[0-9a-f]{20,}|AIza[0-9A-Za-z_-]{30,}|gsk_[0-9A-Za-z]{20,}")
failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("[PASS] " if ok else "[FAIL] ") + message)
    if not ok:
        failures.append(message)


yield_df = pd.read_csv(B / "yield_training.csv")
check(not yield_df["crop"].str.contains(r"total|^other", case=False, regex=True).any(),
      "yield_training has no aggregate crop rows (Total foodgrain, Pulses total, Other ...)")
check(yield_df["groundwater_category"].nunique() > 1 and yield_df["groundwater_extraction_pct"].nunique() > 1,
      "groundwater columns vary by district (not one constant value)")
check(yield_df["groundwater_category"].notna().all(), "no missing groundwater category")
check({"crop_id", "irrigated_pct", "fertilizer_use_kg_per_ha"} <= set(yield_df.columns),
      "yield_training has crop_id, irrigated_pct, fertilizer_use_kg_per_ha")
check((yield_df["yield_t_per_ha"] > 0).all(), "all yields are positive")
check(yield_df["district"].nunique() >= 33, f"districts covered: {yield_df['district'].nunique()}")

weather = pd.read_csv(B / "district_rainfall_history.csv")
check(weather["district"].nunique() == 36, f"weather covers 36 districts (found {weather['district'].nunique()})")
check(weather["year"].min() <= 1997 and weather["year"].max() >= 2024, "weather covers 1997-2024")
check(weather["mean_humidity_pct"].notna().all(), "weather has humidity for every row")

check(not (B / "fertilizer_response.csv").exists(), "generated fertilizer_response.csv is not in the repo")

prices = pd.read_csv(B / "price_history_monthly.csv")
prices["t"] = prices["year"] * 12 + prices["month"]
relative = prices["modal_price_rs_per_quintal"] / prices.groupby(["district", "commodity"])["modal_price_rs_per_quintal"].transform("mean")
spread = relative.groupby([prices["commodity"], prices["t"]]).std().median()
check(spread > 0.01,
      f"price history varies across districts (real markets differ; modelled data gave 0.00005, now {spread:.3f})")
check(prices["district"].nunique() >= 30, f"price history covers {prices['district'].nunique()} districts")
check((B / "price_history_state_monthly.csv").exists(), "state-level price history exists (used for price risk)")

master = pd.read_csv(B / "crops_master.csv")
check(not master["des_crop_name"].fillna("").str.contains(r"total|^other", case=False, regex=True).any(),
      "crops_master maps no crop to an aggregate DES row")

reservoir = pd.read_csv(A / "reservoir_storage.csv")
check(reservoir["live_storage_pct_of_capacity"].between(0, 100).all(), "reservoir storage percentages are 0-100")
check(pd.to_datetime(reservoir["observation_date"]).max() >= pd.Timestamp("2026-01-01"), "reservoir data is from 2026 (CWC weekly bulletin), not the old 2023 snapshot")

empty = [str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "data" / "raw").rglob("*.json") if p.stat().st_size < 10]
check(not empty, f"no empty raw JSON files {empty or ''}")

leaks = [str(p.relative_to(REPO_ROOT)) for p in REPO_ROOT.rglob("*")
         if p.is_file() and p.suffix.lower() in {".md", ".csv", ".json", ".txt", ".py"} and ".git" not in p.parts
         and KEY_PATTERN.search(p.read_text(encoding="utf-8", errors="ignore"))]
check(not leaks, f"no API keys in tracked text files {leaks or ''}")

print(f"\n{len(failures)} check(s) failed" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
