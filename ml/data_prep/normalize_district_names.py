"""Use the current official district names everywhere (Ahilyanagar, Chhatrapati Sambhajinagar, Dharashiv, ...).

1. Rewrite data/processed/districts.csv (36 districts, Nominatim coordinates, LGD `district_code`):
   rename Ahmednagar -> Ahilyanagar (old name stays in name_variants) and add the extra spelling variants.
2. Rewrite the `district` column of every processed CSV under data/ to the canonical name.
   For all-India files only Maharashtra rows are touched. Raw folders and original source files are never edited.

Run from the repo root:  python -I ml/data_prep/normalize_district_names.py [--dry-run]
"""

import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DISTRICTS_CSV = DATA_DIR / "processed" / "districts.csv"
RENAMES = {"Ahmednagar": "Ahilyanagar"}
EXTRA_VARIANTS = {"Amravati": ["Amarawati"], "Chhatrapati Sambhajinagar": ["Chattrapati Sambhajinagar"], "Ahilyanagar": ["Ahmednagar", "Ahmadnagar"]}
DRY_RUN = "--dry-run" in sys.argv
# Original downloads kept exactly as published (not cleaned tables).
SOURCE_FILES = {"CostofCultivation.csv", "DistrictwiseSoilData_all_india.csv", "India_District_Soil_NPK_Climate.csv"}


def norm(value: str) -> str:
    return re.sub(r"[^a-z]", "", str(value).lower())


def merged_districts() -> pd.DataFrame:
    """districts.csv with the current official names and the full variant list.

    The LGD `district_code` / `is_agricultural_district` columns are already in the consolidated file
    (they were merged in when the two teammate copies became one), so they are kept as they are.
    """
    a = pd.read_csv(DISTRICTS_CSV)
    a["district"] = a["district"].replace(RENAMES)
    if "district_code" not in a.columns:
        a["district_code"] = ""
    if "is_agricultural_district" not in a.columns:
        a["is_agricultural_district"] = "false"
    a["district_code"] = a["district_code"].fillna("")
    a["is_agricultural_district"] = a["is_agricultural_district"].fillna("false")
    variants = []
    for _, row in a.iterrows():
        names = [row["district"], *str(row["name_variants"]).split("|")]
        names += EXTRA_VARIANTS.get(row["district"], [])
        variants.append("|".join(dict.fromkeys(n for n in names if n and n != "nan")))
    a["name_variants"] = variants
    columns = ["district", "state", "hq_name", "latitude", "longitude", "district_code",
               "is_agricultural_district", "name_variants", "coord_source"]
    return a[columns]


def main() -> int:
    districts = merged_districts()
    lookup = {norm(n): row.district for row in districts.itertuples() for n in [row.district, *row.name_variants.split("|")]}
    print(f"[districts] {len(districts)} rows; agricultural = {(districts.is_agricultural_district == 'true').sum()}")

    changed_files = unmatched_total = 0
    for path in sorted(DATA_DIR.rglob("*.csv")):
        relative = path.relative_to(REPO_ROOT)
        if "raw" in path.parts or path.name in SOURCE_FILES:
            continue
        if path.name == "districts.csv":
            if not DRY_RUN:
                districts.to_csv(path, index=False, encoding="utf-8")
            print(f"[districts.csv] replaced {relative}")
            changed_files += 1
            continue
        frame = pd.read_csv(path)
        if "district" not in frame.columns:
            continue
        is_mh = frame["state"].astype(str).str.upper().eq("MAHARASHTRA") if "state" in frame.columns else pd.Series(True, index=frame.index)
        mapped = frame["district"].map(lambda v: lookup.get(norm(v)))
        new = frame["district"].where(~is_mh | mapped.isna(), mapped)
        unmatched = sorted(frame.loc[is_mh & mapped.isna(), "district"].astype(str).unique())
        if unmatched:
            unmatched_total += len(unmatched)
            print(f"[WARN] {relative}: unmatched {unmatched[:6]}")
        changes = int((new != frame["district"]).sum())
        if changes:
            changed_files += 1
            print(f"[rename] {relative}: {changes} rows")
            if not DRY_RUN:
                frame["district"] = new
                frame.to_csv(path, index=False, encoding="utf-8")
    print(f"[SUCCESS] files changed: {changed_files}; unmatched names: {unmatched_total}" + (" (dry run)" if DRY_RUN else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
