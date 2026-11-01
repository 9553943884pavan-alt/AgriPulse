"""Tests for core infrastructure: units, errors, timing, cache."""

import asyncio

from app.core import http_client
from app.core.units import (
    ha_to_acres, acres_to_ha, tonnes_to_quintals,
    t_per_ha_to_q_per_acre, mm_to_m3_per_acre,
    format_inr, normalize_number_string,
)
from app.core.errors import AppError
from app.core.timing import StageTimer
import time


# ── Unit conversions ──────────────────────────────────────────────────────────

def test_ha_to_acres():
    assert abs(ha_to_acres(1.0) - 2.47105) < 0.001

def test_acres_to_ha():
    assert abs(acres_to_ha(2.47105) - 1.0) < 0.001

def test_round_trip():
    assert abs(ha_to_acres(acres_to_ha(5.0)) - 5.0) < 0.001

def test_tonnes_to_quintals():
    assert tonnes_to_quintals(1.0) == 10.0

def test_t_per_ha_to_q_per_acre():
    # 1 t/ha × 10 q/t × 0.40469 ha/acre = 4.0469 q/acre
    result = t_per_ha_to_q_per_acre(1.0)
    assert abs(result - 4.0469) < 0.01

def test_mm_to_m3_per_acre():
    assert abs(mm_to_m3_per_acre(1.0) - 4.047) < 0.01

def test_format_inr():
    assert format_inr(150000) == "₹1,50,000"
    assert format_inr(70000) == "₹70,000"
    assert format_inr(1000000) == "₹10,00,000"

def test_normalize_devanagari():
    assert normalize_number_string("५०,०००") == "50000"

def test_normalize_hazar():
    assert "000" in normalize_number_string("70 hazar")


# ── Errors ────────────────────────────────────────────────────────────────────

def test_app_error_creates_response():
    err = AppError("LOCATION_NOT_FOUND")
    r = err.to_response()
    assert r.error.code == "LOCATION_NOT_FOUND"
    assert r.error.retryable is False
    assert "mr" in r.error.user_message

def test_app_error_http_exception():
    err = AppError("PLAN_NOT_FOUND")
    exc = err.to_http_exception()
    assert exc.status_code == 404

def test_upstream_unavailable_retryable():
    err = AppError("UPSTREAM_UNAVAILABLE")
    assert err.to_response().error.retryable is True


# ── Timing ────────────────────────────────────────────────────────────────────

def test_stage_timer():
    timer = StageTimer()
    with timer.stage("step_a"):
        time.sleep(0.01)
    with timer.stage("step_b"):
        time.sleep(0.01)
    header = timer.server_timing_header()
    assert "step_a" in header
    assert "step_b" in header
    assert "total" in header

def test_stage_timer_as_dict():
    timer = StageTimer()
    with timer.stage("geocoding"):
        pass
    d = timer.as_dict()
    assert "geocoding" in d
    assert d["geocoding"] >= 0


def test_http_client_is_recreated_for_a_different_event_loop():
    async def current_client():
        return http_client.get_client()

    first_loop = asyncio.new_event_loop()
    second_loop = asyncio.new_event_loop()
    try:
        first_client = first_loop.run_until_complete(current_client())
        second_client = second_loop.run_until_complete(current_client())

        assert first_client is not second_client

        second_loop.run_until_complete(http_client.close_client())
        first_loop.run_until_complete(first_client.aclose())
    finally:
        first_loop.close()
        second_loop.close()
