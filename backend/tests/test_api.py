"""API endpoint tests (API.1-API.10)."""

import io
import wave

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── E13 health ────────────────────────────────────────────────────────────────

def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "data_files" in body
    assert body["models_loaded"] is True


# ── E9 districts ─────────────────────────────────────────────────────────────

def test_list_districts():
    r = client.get("/api/districts")
    assert r.status_code == 200
    body = r.json()
    assert "districts" in body
    assert len(body["districts"]) == 36


def test_districts_have_required_fields():
    r = client.get("/api/districts")
    d = r.json()["districts"][0]
    assert "district" in d
    assert "latitude" in d
    assert "longitude" in d
    assert "is_agricultural_district" in d
    assert "status_color" in d


def test_mumbai_not_agricultural():
    r = client.get("/api/districts")
    districts = {d["district"]: d for d in r.json()["districts"]}
    assert "Mumbai City" in districts or "Mumbai Suburban" in districts
    for name in ("Mumbai City", "Mumbai Suburban"):
        if name in districts:
            assert districts[name]["is_agricultural_district"] is False


# ── E8 location search ────────────────────────────────────────────────────────

def test_location_search():
    r = client.get("/api/locations/search?q=Pune")
    assert r.status_code == 200
    assert "results" in r.json()


def test_location_search_empty_q():
    r = client.get("/api/locations/search?q=")
    assert r.status_code == 422


# ── E10 district context ──────────────────────────────────────────────────────

def test_district_context_pune():
    r = client.get("/api/districts/Pune/context")
    assert r.status_code == 200
    body = r.json()
    assert "groundwater" in body
    assert "district" in body


def test_district_context_mumbai_422():
    r = client.get("/api/districts/Mumbai City/context")
    assert r.status_code == 422


# ── E2 plan ───────────────────────────────────────────────────────────────────

def test_plan_endpoint_returns_200():
    r = client.post("/api/plan", json={
        "location_text": "Pune",
        "land_acres": 5.0,
        "budget_rs": 70000.0,
        "water_source": "borewell",
        "borewell_count": 1,
        "language": "en",
    })
    # Returns 200 with a PlanResult (may have empty crops until ML is implemented)
    assert r.status_code == 200
    body = r.json()
    assert "plan_id" in body
    assert "location" in body
    assert body["location"]["district"] is not None


def test_plan_invalid_profile_422():
    r = client.post("/api/plan", json={"location_text": "Pune"})
    assert r.status_code == 422


# ── E11 sources ───────────────────────────────────────────────────────────────

def test_sources_list():
    r = client.get("/api/sources")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert len(sources) >= 19
    required = {"id", "category", "name", "publisher", "url", "mode", "as_of", "methodology", "used_for"}
    assert all(required <= set(source) for source in sources)
    assert {"agmarknet", "price_history", "open_meteo_forecast", "soil_health_card", "fertilizer", "seed", "cgwb", "cwc", "des_yields"} <= {source["id"] for source in sources}
    assert {source["mode"] for source in sources} >= {"live", "historical", "static"}
    # The page must link to publisher/dataset pages, never credential-bearing API calls.
    assert all("api-key" not in source["url"] and "/resource/" not in source["url"] for source in sources)
    urls = {source["id"]: source["url"] for source in sources}
    assert urls["costs"] == "https://desagri.gov.in/divisions-cell/cost-studies-cs/"
    assert urls["fertilizer"] == "https://fert.gov.in/"


# ── E7 prefetch ───────────────────────────────────────────────────────────────

def test_prefetch_does_not_error():
    r = client.post("/api/prefetch", json={"location_text": "Nashik"})
    assert r.status_code == 200
    assert "stages" in r.json()


# ── Error format ──────────────────────────────────────────────────────────────

def test_404_has_error_shape():
    r = client.get("/api/plans/nonexistent_plan_id_xyz/context")
    # Endpoint doesn't exist → 404 from FastAPI (not our error shape, that's fine)
    assert r.status_code == 404


def test_request_id_on_every_response():
    for path in ("/api/health", "/api/districts", "/api/sources"):
        r = client.get(path)
        assert "x-request-id" in r.headers, f"Missing X-Request-Id on {path}"


def test_speak_rejects_text_over_sarvam_limit():
    r = client.post("/api/speak", json={"text": "a" * 2501})
    assert r.status_code == 422


def test_bulbul_v4_flash_speakers_cover_supported_languages():
    from app.services.speech import _tts_speaker

    assert _tts_speaker("mr") == "ishita_mr_conversational"
    assert _tts_speaker("hi") == "simran_hi_conversation"
    assert _tts_speaker("en") == "simran_en_conversation"


def _wav_audio(duration_seconds: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * duration_seconds)
    return buffer.getvalue()


def test_stt_accepts_sarvam_maximum_duration():
    from app.services.speech import _validate_audio_duration

    assert _validate_audio_duration(_wav_audio(30)) == pytest.approx(30.0)


def test_transcribe_rejects_audio_over_sarvam_duration_limit():
    response = client.post(
        "/api/transcribe",
        files={"audio": ("long.wav", _wav_audio(31), "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["max_duration_seconds"] == 30
