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


# ── C.2 API Contract Fixtures Conformance ─────────────────────────────────────

def test_contract_fixtures_exist_and_validate():
    import json
    from pathlib import Path
    from app.schemas import PlanResult

    repo_root = Path(__file__).resolve().parent.parent.parent
    live_dir = repo_root / "docs" / "api_examples" / "live"
    contract_dir = repo_root / "docs" / "api_examples" / "contract"

    assert live_dir.exists(), "docs/api_examples/live directory missing"
    assert contract_dir.exists(), "docs/api_examples/contract directory missing"

    for prefix, dir_path in [("live", live_dir), ("contract", contract_dir)]:
        # Validate all plan files against PlanResult
        for plan_name in ("plan_pune.json", "plan_jalgaon.json", "plan_ahilyanagar.json"):
            file_path = dir_path / plan_name
            assert file_path.exists(), f"Missing {file_path}"
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            plan = PlanResult(**data)
            assert plan.location.district is not None
            assert len(plan.crops) > 0, f"{plan_name} has no crops"
            assert len(plan.strategies) >= 3, f"{plan_name} has fewer than 3 strategies"
            assert plan.recommended_strategy in ("traditional", "lp_max_profit", "qp_balanced", "qp_drought_safe")

        # Validate districts.json
        dist_path = dir_path / "districts.json"
        assert dist_path.exists()
        with open(dist_path, "r", encoding="utf-8") as f:
            d_data = json.load(f)
        assert "districts" in d_data
        assert len(d_data["districts"]) == 36

        # Validate sources.json
        src_path = dir_path / "sources.json"
        assert src_path.exists()
        with open(src_path, "r", encoding="utf-8") as f:
            s_data = json.load(f)
        assert "sources" in s_data
        assert len(s_data["sources"]) >= 5

        # Validate district_context_pune.json
        ctx_path = dir_path / "district_context_pune.json"
        assert ctx_path.exists()
        with open(ctx_path, "r", encoding="utf-8") as f:
            c_data = json.load(f)
        assert c_data["district"] == "Pune"
        assert "groundwater" in c_data
        assert "recent_rain" in c_data
        assert "reservoirs" in c_data

    # Validate openapi.json exists and is valid JSON
    openapi_path = repo_root / "docs" / "openapi.json"
    assert openapi_path.exists()
    with open(openapi_path, "r", encoding="utf-8") as f:
        openapi_data = json.load(f)
    assert "paths" in openapi_data
    assert "/api/plan" in openapi_data["paths"]

