"""Emergency backend fixes: grounding units, honest source status, agent location errors."""

from __future__ import annotations

import pytest

from app.agent.grounding import extract_numbers, grounding_check


def test_unit_digits_are_not_quantities():
    assert extract_numbers("uses 3805 m3 of water") == [3805.0]
    assert extract_numbers("44 kg P2O5 and 30 kg K2O") == [44.0, 30.0]
    # real quantities are untouched
    assert extract_numbers("Rs 12,475 on 1.3 acres") == [12475.0, 1.3]


def test_water_volume_with_unit_passes_grounding():
    outputs = {"totals": {"water_m3": 3805.0, "budget_used_rs": 55558.0}}
    assert grounding_check("You use 3805 m3 of water and Rs 55,558.", outputs)
    # a genuinely invented figure must still fail
    assert not grounding_check("You use 9000 m3 of water.", outputs)


def test_runtime_status_is_truthful(monkeypatch):
    from app.api import sources

    monkeypatch.setattr("app.config.settings.SARVAM_API_KEY", "")
    monkeypatch.setattr("app.config.settings.DATA_GOV_IN_API_KEY", "")
    by_id = {s["id"]: s for s in sources._SOURCES}

    assert sources._runtime_status(by_id["sarvam"])[0] == "unavailable"
    assert sources._runtime_status(by_id["agmarknet"])[0] == "cached"   # no key -> never "live"
    assert sources._runtime_status(by_id["cwc"])[0] == "official_dataset"
    assert sources._runtime_status(by_id["price_history"])[0] == "historical"

    monkeypatch.setattr("app.config.settings.DATA_GOV_IN_API_KEY", "x")
    monkeypatch.setattr(sources, "_health_cache", {"sources": [
        {"id": "agmarknet", "status": "green", "latency_ms": 10, "last_ok": "t", "note": ""},
        {"id": "soilgrids", "status": "red", "latency_ms": -1, "last_ok": "", "note": "HTTP 503"},
    ]})
    assert sources._runtime_status(by_id["agmarknet"])[0] == "live"
    assert sources._runtime_status(by_id["soilgrids"])[0] == "cached"
    # never probed -> not claimed live
    assert sources._runtime_status(by_id["open_meteo_forecast"])[0] == "cached"


def test_sources_endpoint_has_status_fields():
    from fastapi.testclient import TestClient

    from app.main import app

    rows = TestClient(app).get("/api/sources").json()["sources"]
    allowed = {"live", "cached", "historical", "official_dataset", "unavailable"}
    assert all(r["status"] in allowed and r["status_evidence"] for r in rows)


async def test_agent_unknown_location_raises_app_error(monkeypatch):
    from app.agent import nodes, tools
    from app.core.errors import AppError
    from app.schemas import FarmProfile

    async def boom(_text):
        raise AppError("LOCATION_NOT_FOUND", {"location": "Atlantis"})

    monkeypatch.setattr(tools, "get_location", boom)
    profile = FarmProfile(location_text="Atlantis", land_acres=2.0, budget_rs=50000.0)
    with pytest.raises(AppError) as exc:
        await nodes.gather_data_node({"profile": profile, "trace": []})
    assert exc.value.code == "LOCATION_NOT_FOUND"
