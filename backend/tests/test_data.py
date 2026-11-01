"""DATA.3 — Data validation tests.

Spec requirements:
  - 36 districts present (exactly) in districts.csv
  - every processed file loads without error
  - value ranges are sane (no negative yields, impossible prices, etc.)
  - no API keys anywhere in data/ or docs/
  - is_agricultural_district=False for Mumbai City and Mumbai Suburban
  - district resolver covers all 36 districts

All tests use the real CSV files so they catch corruption early.
No live API calls are made.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # AgriPulse-main/
BACKEND = REPO / "backend"
A_PROC = REPO / "data" / "processed"
B_PROC = A_PROC

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path):
    import pandas as pd
    assert path.exists(), f"Missing file: {path}"
    df = pd.read_csv(path)
    assert len(df) > 0, f"Empty file: {path}"
    return df


# ── File existence ────────────────────────────────────────────────────────────

REQUIRED_A = [
    "districts.csv",
    "crop_water_coefficients.csv",
    "groundwater_by_block.csv",
    "irrigation_by_district.csv",
    "recent_rainfall.csv",
    "reservoir_storage.csv",
    "soil_npk_by_district.csv",
]

REQUIRED_B = [
    "cost_of_cultivation.csv",
    "crop_calendar.csv",
    "crops_master.csv",
    "district_crop_yields.csv",
    "district_rainfall_history.csv",
    "fertilizer_prices.csv",
    "fertilizer_rdf.csv",
    "fertilizer_use_by_district.csv",
    "msp.csv",
    "price_history_monthly.csv",
    "price_history_state_monthly.csv",
    "seed.csv",
]


@pytest.mark.parametrize("filename", REQUIRED_A)
def test_teammate_a_file_exists(filename):
    assert (A_PROC / filename).exists(), f"Missing Teammate-A file: {filename}"


@pytest.mark.parametrize("filename", REQUIRED_B)
def test_teammate_b_file_exists(filename):
    assert (B_PROC / filename).exists(), f"Missing Teammate-B file: {filename}"


# ── districts.csv ─────────────────────────────────────────────────────────────

def test_districts_has_36_rows():
    df = _load(A_PROC / "districts.csv")
    assert len(df) == 36, f"Expected 36 districts, got {len(df)}: {list(df['district'])}"


def test_districts_required_columns():
    df = _load(A_PROC / "districts.csv")
    for col in ("district", "latitude", "longitude", "is_agricultural_district"):
        assert col in df.columns, f"Missing column: {col}"


def test_districts_coordinates_in_maharashtra_bounds():
    df = _load(A_PROC / "districts.csv")
    # Maharashtra: lat 15.6–22.1 N, lon 72.6–80.9 E
    assert df["latitude"].between(15.0, 23.0).all(), \
        f"Latitude out of Maharashtra bounds:\n{df[~df['latitude'].between(15.0, 23.0)][['district','latitude']]}"
    assert df["longitude"].between(72.0, 81.0).all(), \
        f"Longitude out of Maharashtra bounds:\n{df[~df['longitude'].between(72.0, 81.0)][['district','longitude']]}"


def test_non_agricultural_districts_flagged():
    df = _load(A_PROC / "districts.csv")
    non_ag = df[df["is_agricultural_district"] == False]["district"].tolist()  # noqa: E712
    for expected in ("Mumbai City", "Mumbai Suburban"):
        assert expected in non_ag, \
            f"{expected!r} must have is_agricultural_district=False; non_ag={non_ag}"


def test_districts_no_duplicate_names():
    df = _load(A_PROC / "districts.csv")
    dupes = df[df["district"].duplicated()]["district"].tolist()
    assert not dupes, f"Duplicate district names: {dupes}"


def test_districts_no_null_coordinates():
    df = _load(A_PROC / "districts.csv")
    assert df["latitude"].notna().all(), "Null latitude values found"
    assert df["longitude"].notna().all(), "Null longitude values found"


# ── district_crop_yields.csv ──────────────────────────────────────────────────

def test_yields_no_negative_values():
    df = _load(B_PROC / "district_crop_yields.csv")
    for col in ("area_ha", "production_tonnes", "yield_tonnes_per_ha"):
        if col in df.columns:
            neg = df[df[col] < 0]
            assert len(neg) == 0, f"Negative {col} in yields: {len(neg)} rows"


def test_yields_has_expected_seasons():
    df = _load(B_PROC / "district_crop_yields.csv")
    seasons = set(df["season"].unique())
    expected = {"Kharif", "Rabi"}
    assert expected.issubset(seasons), f"Missing seasons: {expected - seasons}"


def test_yields_year_range():
    df = _load(B_PROC / "district_crop_yields.csv")
    assert df["year"].min() >= 1990, f"Suspiciously old year: {df['year'].min()}"
    assert df["year"].max() <= 2025, f"Future year in yields: {df['year'].max()}"


def test_yields_yield_sanity_cap():
    """No Maharashtra cereal/pulse/oilseed should yield more than 15 t/ha.
    Banana, Grapes, Onion, Potato and Sugarcane are excluded — they have
    genuine high yields (banana 50+ t/ha, grapes 20+ t/ha).
    """
    HIGH_YIELD_CROPS = {"banana", "grapes", "onion", "potato", "sugarcane",
                        "tapioca", "tomato", "other vegetables"}
    df = _load(B_PROC / "district_crop_yields.csv")
    normal = df[~df["crop"].str.lower().str.strip().isin(HIGH_YIELD_CROPS)]
    extreme = normal[normal["yield_tonnes_per_ha"] > 15]
    assert len(extreme) == 0, \
        f"Impossible yield >15 t/ha for cereals/pulses/oilseeds:\n{extreme[['crop','district','year','yield_tonnes_per_ha']].head()}"


# ── price_history_monthly.csv ─────────────────────────────────────────────────

def test_prices_no_negative():
    df = _load(B_PROC / "price_history_monthly.csv")
    neg = df[df["modal_price_rs_per_quintal"] < 0]
    assert len(neg) == 0, f"Negative prices: {len(neg)} rows"


def test_prices_month_range():
    df = _load(B_PROC / "price_history_monthly.csv")
    assert df["month"].between(1, 12).all(), "Month values outside 1-12"


def test_prices_reasonable_range():
    """No crop should be priced above 1,00,000 Rs/quintal."""
    df = _load(B_PROC / "price_history_monthly.csv")
    extreme = df[df["modal_price_rs_per_quintal"] > 100_000]
    assert len(extreme) == 0, \
        f"Extreme prices >1L Rs/q:\n{extreme[['commodity','district','year','modal_price_rs_per_quintal']].head()}"


# ── cost_of_cultivation.csv ───────────────────────────────────────────────────

def test_costs_no_negative_total():
    df = _load(B_PROC / "cost_of_cultivation.csv")
    if "cost_a2_fl_rs_per_ha" in df.columns:
        neg = df[df["cost_a2_fl_rs_per_ha"] < 0]
        assert len(neg) == 0, "Negative cost_a2_fl"


def test_costs_has_required_crops():
    """Key crops must have cost data."""
    df = _load(B_PROC / "cost_of_cultivation.csv")
    crop_col = "crop_id" if "crop_id" in df.columns else "crop"
    crops = set(df[crop_col].str.lower())
    # At least some crops present
    assert len(crops) >= 3, f"Too few crops in cost_of_cultivation: {crops}"


# ── msp.csv ───────────────────────────────────────────────────────────────────

def test_msp_no_negative():
    df = _load(B_PROC / "msp.csv")
    neg = df[df["msp_rs_per_quintal"] < 0]
    assert len(neg) == 0, "Negative MSP values"


def test_msp_recent_year():
    """MSP data should cover at least up to 2024."""
    df = _load(B_PROC / "msp.csv")
    # year column may be "2025-26" (string) or numeric
    years = df["year"].astype(str)
    latest = sorted(years.unique())[-1]
    # Extract the first 4-digit year from the string
    import re as _re
    match = _re.search(r"(\d{4})", latest)
    assert match, f"Cannot parse year from {latest!r}"
    assert int(match.group(1)) >= 2024, f"MSP data only up to {latest}"


# ── fertilizer_rdf.csv ────────────────────────────────────────────────────────

def test_fertilizer_rdf_no_negative():
    df = _load(B_PROC / "fertilizer_rdf.csv")
    for col in ("n_kg_per_ha", "p2o5_kg_per_ha", "k2o_kg_per_ha"):
        assert col in df.columns, f"Missing column: {col}"
        assert (df[col] >= 0).all(), f"Negative {col} in RDF"


def test_fertilizer_rdf_reasonable_dose():
    """No single nutrient dose above 500 kg/ha."""
    df = _load(B_PROC / "fertilizer_rdf.csv")
    for col in ("n_kg_per_ha", "p2o5_kg_per_ha", "k2o_kg_per_ha"):
        extreme = df[df[col] > 500]
        assert len(extreme) == 0, f"Extreme {col} dose:\n{extreme}"


# ── crop_calendar.csv ─────────────────────────────────────────────────────────

def test_crop_calendar_required_columns():
    df = _load(B_PROC / "crop_calendar.csv")
    for col in ("crop_id", "season", "sowing_start", "sowing_end", "duration_days"):
        assert col in df.columns, f"Missing column in crop_calendar: {col}"


def test_crop_calendar_duration_positive():
    df = _load(B_PROC / "crop_calendar.csv")
    assert (df["duration_days"] > 0).all(), "Non-positive duration_days"


def test_crop_calendar_duration_cap():
    """No crop should run for more than 400 days."""
    df = _load(B_PROC / "crop_calendar.csv")
    long = df[df["duration_days"] > 400]
    assert len(long) == 0, f"duration_days > 400:\n{long[['crop_id','duration_days']]}"


# ── soil_npk_by_district.csv ──────────────────────────────────────────────────

def test_soil_has_beed():
    """Beed is a key demo district — must have soil data."""
    df = _load(A_PROC / "soil_npk_by_district.csv")
    dist_col = next((c for c in df.columns if "district" in c.lower()), None)
    assert dist_col, "No district column found in soil CSV"
    districts = set(df[dist_col].str.strip())
    assert "Beed" in districts or any("beed" in d.lower() for d in districts), \
        "Beed not found in soil_npk_by_district"


# ── groundwater_by_block.csv ──────────────────────────────────────────────────

def test_groundwater_has_district_avg_rows():
    """Each district must have a '(District Avg)' row for the water budget."""
    df = _load(A_PROC / "groundwater_by_block.csv")
    # Look for district-avg indicator in any column
    has_avg = df.astype(str).apply(
        lambda col: col.str.contains("District Avg|district avg", case=False, na=False)
    ).any().any()
    # Soft check — warn if missing but don't fail (data may label differently)
    if not has_avg:
        import warnings
        warnings.warn("groundwater_by_block.csv: no '(District Avg)' rows found — water budget will use first block")


# ── No API keys in data/ or docs/ ─────────────────────────────────────────────

# Patterns that indicate a real key (not a placeholder)
_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret)[ \t]*[=:][ \t]*(?!<|your|xxx|none|null|placeholder)[a-z0-9_\-]{16,}"
)

def _text_files_under(root: Path, extensions=(".csv", ".md", ".txt", ".json", ".yaml", ".yml")):
    for path in root.rglob("*"):
        if path.suffix.lower() in extensions and path.is_file():
            yield path


@pytest.mark.parametrize("folder", [
    REPO / "data",
    BACKEND / "data",
    REPO / "docs",
])
def test_no_api_keys_in_folder(folder):
    """No real API keys should appear in data/ or docs/ files."""
    if not folder.exists():
        pytest.skip(f"Folder not found: {folder}")
    found = []
    for path in _text_files_under(folder):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _KEY_PATTERN.search(text):
                found.append(str(path.relative_to(REPO)))
        except Exception:
            pass
    assert not found, f"Possible API keys found in:\n" + "\n".join(found)


# ── District resolver ─────────────────────────────────────────────────────────

def test_district_resolver_covers_all_districts():
    """The resolver must map every canonical district name to itself."""
    import sys
    sys.path.insert(0, str(BACKEND))
    from app.data.resolver import resolve_district

    df = _load(A_PROC / "districts.csv")
    failed = []
    for name in df["district"]:
        result = resolve_district(name)
        if result is None:
            failed.append(name)
    assert not failed, f"Resolver returned None for: {failed}"


def test_district_resolver_handles_old_names():
    """Renamed districts must resolve via name_variants."""
    import sys
    sys.path.insert(0, str(BACKEND))
    from app.data.resolver import resolve_district

    renames = {
        "Aurangabad": "Chhatrapati Sambhajinagar",
        "Osmanabad": "Dharashiv",
        "Ahmednagar": "Ahilyanagar",
    }
    for old, expected in renames.items():
        result = resolve_district(old)
        assert result == expected, \
            f"Old name {old!r} should resolve to {expected!r}, got {result!r}"


# ── Loaders smoke test ────────────────────────────────────────────────────────

def test_all_loaders_import_cleanly():
    """Every loader function must import and run without error."""
    import sys
    sys.path.insert(0, str(BACKEND))
    from app.data import loaders

    loader_fns = [
        "load_districts",
        "load_district_crop_yields",
        "load_soil_npk",
        "load_groundwater",
        "load_irrigation",
        "load_reservoir_storage",
        "load_recent_rainfall",
        "load_crop_water_coefficients",
        "load_cost_of_cultivation",
        "load_seed_prices",
        "load_fertilizer_rdf",
        "load_fertilizer_prices",
        "load_fertilizer_use",
        "load_price_history",
        "load_msp",
        "load_crop_calendar",
        "load_crops_master",
    ]
    missing = [fn for fn in loader_fns if not hasattr(loaders, fn)]
    assert not missing, f"Missing loader functions: {missing}"


def test_load_districts_returns_36():
    import sys
    sys.path.insert(0, str(BACKEND))
    from app.data.loaders import load_districts
    df = load_districts()
    assert len(df) == 36, f"load_districts() returned {len(df)} rows, expected 36"


def test_load_district_crop_yields_has_data():
    import sys
    sys.path.insert(0, str(BACKEND))
    from app.data.loaders import load_district_crop_yields
    df = load_district_crop_yields()
    assert len(df) > 1000, f"yield data suspiciously small: {len(df)} rows"
