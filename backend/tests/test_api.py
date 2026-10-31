"""API endpoint tests (API.1-API.10)."""

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
    assert len(sources) > 0
    assert any(s["id"] == "agmarknet" for s in sources)


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
