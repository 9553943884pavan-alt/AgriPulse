"""Phase 0 smoke tests — P0.5 done-when: pytest green on an empty test."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_schemas_import():
    """C.1 — all 25 types import without error."""
    from app.schemas import (  # noqa: F401
        Allocation,
        Candidate,
        ChatMessage,
        CostBreakdown,
        ErrorResponse,
        ExcludedCrop,
        FarmProfile,
        FertilizerPlan,
        Impact,
        Infeasibility,
        Location,
        Message,
        OptimizerInputs,
        PlanResult,
        Scenario,
        Season,
        SourcedValue,
        StrategyResult,
        Suitability,
        SuitabilityFactor,
        TraceEvent,
        WaterBudget,
        WaterNeed,
        YieldPrediction,
        SSEEventExamples,
    )
    assert SourcedValue is not None
    assert PlanResult is not None
    assert ErrorResponse is not None


def test_request_id_header():
    r = client.get("/api/health")
    assert "x-request-id" in r.headers


def test_server_timing_header():
    r = client.get("/api/health")
    assert "server-timing" in r.headers
