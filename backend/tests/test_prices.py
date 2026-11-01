from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import prices


def _previous_month() -> tuple[int, int]:
    today = date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def test_price_history_uses_processed_schema_and_requested_district(monkeypatch):
    year, month = _previous_month()
    frame = pd.DataFrame([
        {
            "commodity": "Soyabean",
            "district": "Pune",
            "year": year,
            "month": month,
            "modal_price_rs_per_quintal": 4200.0,
        },
        {
            "commodity": "Soyabean",
            "district": "Nashik",
            "year": year,
            "month": month,
            "modal_price_rs_per_quintal": 5000.0,
        },
    ])
    monkeypatch.setattr(prices, "load_price_history", lambda: frame)

    quote = prices._lookup_price_history("Soyabean", "Pune", "Maharashtra")

    assert quote == {
        "price": 4200.0,
        "date": f"{year}-{month:02d}",
        "district": "Pune",
    }


def test_price_history_state_fallback_selects_latest_month(monkeypatch):
    year, month = _previous_month()
    frame = pd.DataFrame([
        {
            "commodity": "Paddy(Common)",
            "year": year - 1,
            "month": month,
            "median_modal_rs_per_quintal": 2000.0,
        },
        {
            "commodity": "Paddy(Common)",
            "year": year,
            "month": month,
            "median_modal_rs_per_quintal": 2200.0,
        },
    ])
    monkeypatch.setattr(prices, "load_price_history_state", lambda: frame)

    quote = prices._lookup_price_history("Paddy(Common)", None, "Maharashtra")

    assert quote["price"] == 2200.0
    assert quote["district"] == "Maharashtra"
    assert quote["date"] == f"{year}-{month:02d}"


def test_price_history_rejects_stale_and_nonpositive_rows(monkeypatch):
    today = date.today()
    frame = pd.DataFrame([
        {
            "commodity": "Soyabean",
            "district": "Pune",
            "year": today.year - 2,
            "month": today.month,
            "modal_price_rs_per_quintal": 4000.0,
        },
        {
            "commodity": "Soyabean",
            "district": "Pune",
            "year": today.year,
            "month": today.month,
            "modal_price_rs_per_quintal": 0.0,
        },
    ])
    monkeypatch.setattr(prices, "load_price_history", lambda: frame)

    assert prices._lookup_price_history("Soyabean", "Pune", "Maharashtra") is None


def test_agmarknet_commodity_comes_from_crop_master(monkeypatch):
    frame = pd.DataFrame([
        {"crop_id": "soybean", "agmarknet_commodity": "Soyabean"},
    ])
    monkeypatch.setattr(prices, "load_crops_master", lambda: frame)

    assert prices._agmarknet_commodity("soybean") == "Soyabean"


def test_seasonal_price_ratio_uses_historical_harvest_month_prices(monkeypatch):
    rows = []
    for year, harvest_price in ((2020, 1200.0), (2021, 1300.0), (2022, 1400.0)):
        rows.extend([
            {
                "commodity": "Soyabean",
                "district": "Pune",
                "year": year,
                "month": 10,
                "modal_price_rs_per_quintal": 1000.0,
            },
            {
                "commodity": "Soyabean",
                "district": "Pune",
                "year": year + 1,
                "month": 2,
                "modal_price_rs_per_quintal": harvest_price,
            },
        ])
    monkeypatch.setattr(
        prices,
        "load_crops_master",
        lambda: pd.DataFrame([{"crop_id": "soybean", "agmarknet_commodity": "Soyabean"}]),
    )
    monkeypatch.setattr(prices, "load_price_history", lambda: pd.DataFrame(rows))

    ratio, years, source = prices.seasonal_price_ratio("soybean", "Pune", 10, 2)

    assert ratio == pytest.approx(1.3)
    assert years == 3
    assert "Pune" in source


def test_seasonal_price_ratio_is_unadjusted_with_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        prices,
        "load_crops_master",
        lambda: pd.DataFrame([{"crop_id": "soybean", "agmarknet_commodity": "Soyabean"}]),
    )
    monkeypatch.setattr(
        prices,
        "load_price_history",
        lambda: pd.DataFrame([{
            "commodity": "Soyabean",
            "district": "Pune",
            "year": 2024,
            "month": 10,
            "modal_price_rs_per_quintal": 1000.0,
        }]),
    )

    ratio, years, source = prices.seasonal_price_ratio("soybean", "Pune", 10, 2)

    assert ratio == 1.0
    assert years == 0
    assert "Insufficient" in source


def test_get_msp_returns_latest_supported_crop_value(monkeypatch):
    monkeypatch.setattr(
        prices,
        "load_msp",
        lambda: pd.DataFrame([
            {"crop_id": "soybean", "season": "Kharif", "year": "2024-25",
             "msp_rs_per_quintal": 4892.0, "source_notification": "older"},
            {"crop_id": "soybean", "season": "Kharif", "year": "2025-26",
             "msp_rs_per_quintal": 5328.0, "source_notification": "newer"},
        ]),
    )

    quote = prices.get_msp("soybean", "Kharif")

    assert quote is not None
    assert quote.value == 5328.0
    assert quote.as_of == "2025-26"


def test_sugarcane_frp_has_no_hardcoded_fallback(monkeypatch):
    monkeypatch.setattr(prices, "load_msp", lambda: pd.DataFrame(columns=["crop", "year", "msp_rs_per_quintal"]))

    assert prices._sugarcane_frp() is None


@pytest.mark.asyncio
async def test_crop_without_real_price_is_excluded_before_optimization(monkeypatch):
    from app.ml import candidate_options

    monkeypatch.setattr(
        candidate_options,
        "predict_yield",
        lambda *args: SimpleNamespace(t_per_ha=SimpleNamespace(value=4.0)),
    )
    monkeypatch.setattr(candidate_options, "suitability", lambda *args: SimpleNamespace())
    monkeypatch.setattr(candidate_options, "crop_water_need", lambda *args: SimpleNamespace())
    monkeypatch.setattr(candidate_options, "fertilizer_plan", lambda *args: SimpleNamespace())
    monkeypatch.setattr(
        candidate_options.cost_svc,
        "get_cost_breakdown",
        lambda crop_id: SimpleNamespace(total_rs=1000.0),
    )

    async def no_price(*args):
        return None

    monkeypatch.setattr(candidate_options.price_svc, "get_price", no_price)
    candidate = SimpleNamespace(
        crop_id="unpriced_crop",
        names={"en": "Unpriced crop", "mr": "", "hi": ""},
        season="Rabi",
        opens_on=None,
    )
    scenarios = [
        SimpleNamespace(id="drought"),
        SimpleNamespace(id="normal"),
        SimpleNamespace(id="excess"),
    ]

    crops, excluded = await candidate_options.build_crop_options(
        [candidate],
        scenarios,
        SimpleNamespace(district="Pune"),
        SimpleNamespace(name="Rabi"),
        SimpleNamespace(irrigation_method="flood"),
    )

    assert crops == []
    assert [(item.crop_id, item.reason_code) for item in excluded] == [
        ("unpriced_crop", "NO_REAL_PRICE"),
    ]

@pytest.mark.parametrize(
    ("as_of", "expected"),
    [("2026-05", 5), ("2026-05-14", 5), ("14/05/2026", 5), ("", 11), (None, 11), ("bad", 11)],
)
def test_quote_month_anchors_seasonal_ratio_on_quote_not_today(as_of, expected):
    # A May quote must use a May-based seasonal ratio, not today's month (11).
    assert prices.quote_month(as_of, 11) == expected
