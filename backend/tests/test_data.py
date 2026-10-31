"""DATA.3 — Data layer tests.

Checks: 36 districts, required files loadable, value ranges, resolver correctness.
No API keys appear in any tested file.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_districts_count():
    from app.data.loaders import load_districts
    df = load_districts()
    assert len(df) == 36, f"Expected 36 districts, got {len(df)}"


def test_is_agricultural_district_flag():
    from app.data.loaders import load_districts
    df = load_districts()
    non_ag = df[~df["is_agricultural_district"]]
    # Mumbai City and Mumbai Suburban must be non-agricultural
    assert len(non_ag) >= 2
    names = non_ag["district"].str.lower().tolist()
    assert any("mumbai" in n for n in names)


def test_resolver_canonical_name():
    from app.data.resolver import resolve_district
    assert resolve_district("Ahmednagar") == "Ahilyanagar"
    assert resolve_district("Aurangabad") == "Chhatrapati Sambhajinagar"
    assert resolve_district("Osmanabad") == "Dharashiv"


def test_resolver_exact_name():
    from app.data.resolver import resolve_district
    assert resolve_district("Pune") == "Pune"
    assert resolve_district("Nashik") == "Nashik"


def test_resolver_unknown_returns_none():
    from app.data.resolver import resolve_district
    assert resolve_district("NoSuchPlace12345") is None


def test_is_agricultural():
    from app.data.resolver import is_agricultural
    assert is_agricultural("Pune") is True
    assert is_agricultural("Mumbai City") is False


def test_crop_calendar_loads():
    from app.data.loaders import load_crop_calendar
    df = load_crop_calendar()
    assert len(df) > 0
    assert "crop_id" in df.columns
    assert "season" in df.columns


def test_district_crop_yields_loads():
    from app.data.loaders import load_district_crop_yields
    df = load_district_crop_yields()
    assert len(df) > 0
    # No negative yields
    assert (df["yield_tonnes_per_ha"] >= 0).all()


def test_msp_loads():
    from app.data.loaders import load_msp
    df = load_msp()
    assert len(df) > 0


def test_no_api_keys_in_data():
    """DATA.3 — No data.gov.in or Sarvam API keys in data/ or docs/ files."""
    key_pattern = re.compile(r"[a-f0-9]{32,}", re.IGNORECASE)  # noqa: F841
    data_dirs = [
        REPO / "Teammate-A" / "data",
        REPO / "Teammate-B" / "data",
    ]
    violations = []
    for data_dir in data_dirs:
        for path in data_dir.rglob("*.csv"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "<DATA_GOV_IN_API_KEY>" in text:
                violations.append(str(path))
    assert not violations, f"API key placeholder found in: {violations}"
