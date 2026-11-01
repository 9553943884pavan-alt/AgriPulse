"""Chat must never return a bare 5xx; budget/land <= 0 is rejected or treated as missing."""

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.nodes import compute_missing, merge_patch_node
from app.core.errors import AppError
from app.main import app
from app.schemas import FarmProfile

client = TestClient(app)


def _events(text: str) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            ev = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and ev:
            out.append((ev, json.loads(line.split(":", 1)[1].strip())))
            ev = None
    return out


class _BoomGraph:
    def __init__(self, exc):
        self.exc = exc

    async def astream_events(self, *a, **k):
        raise self.exc
        yield  # pragma: no cover


@pytest.fixture(autouse=True)
def _reset_sse_event():
    # sse_starlette keeps a global asyncio.Event bound to the first TestClient loop.
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield


@pytest.fixture
def boom_graph():
    old = getattr(app.state, "agent_graph", None)

    def _set(exc):
        app.state.agent_graph = _BoomGraph(exc)

    yield _set
    app.state.agent_graph = old


def test_chat_internal_error_is_sse_error_then_done(boom_graph):
    boom_graph(RuntimeError("kaboom"))
    r = client.post("/api/agent/chat", json={"message": "hi", "language": "hi"})
    assert r.status_code == 200
    evs = _events(r.text)
    names = [n for n, _ in evs]
    assert names[0] == "thread" and names[-2:] == ["error", "done"]
    err = dict(evs)["error"]["error"]
    assert err["code"] == "INTERNAL" and err["retryable"] is True
    assert set(err["user_message"]) == {"mr", "hi", "en"}


def test_chat_upstream_error_keeps_code(boom_graph):
    boom_graph(AppError("UPSTREAM_UNAVAILABLE"))
    r = client.post("/api/agent/chat", json={"message": "hi"})
    assert r.status_code == 200
    evs = _events(r.text)
    assert dict(evs)["error"]["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert evs[-1][0] == "done"


def test_chat_cache_failure_does_not_break(monkeypatch, boom_graph):
    boom_graph(RuntimeError("x"))

    async def bad_cache():
        raise RuntimeError("db locked")

    monkeypatch.setattr("app.core.cache.get_cache", bad_cache)
    r = client.post("/api/agent/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert _events(r.text)[-1][0] == "done"


def test_chat_done_reports_elapsed_ms():
    r = client.post("/api/agent/chat", json={"message": "hi"})
    assert r.status_code == 200
    done = dict(_events(r.text))["done"]
    assert isinstance(done["ms"], int) and done["ms"] >= 0


def test_chat_bad_body_is_standard_422():
    r = client.post("/api/agent/chat", json=["not", "a", "dict"])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


# ── validation ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field", ["land_acres", "budget_rs"])
@pytest.mark.parametrize("value", [0, -5])
def test_plan_rejects_non_positive(field, value):
    body = {"location_text": "Beed", "land_acres": 3, "budget_rs": 50000, "language": "mr"}
    body[field] = value
    r = client.post("/api/plan", json=body)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["fields"] == [field]
    assert err["user_message"]["mr"]


def test_reoptimize_rejects_non_positive_budget(monkeypatch):
    class FakeCache:
        async def get_plan(self, pid):
            return {"profile": {"location_text": "Beed", "land_acres": 3, "budget_rs": 50000}}

    async def fake_get():
        return FakeCache()

    monkeypatch.setattr("app.api.plan.get_cache", fake_get)
    r = client.post("/api/plans/pl_x/reoptimize", json={"budget_rs": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_compute_missing_treats_zero_and_negative_as_missing():
    assert compute_missing({"location_text": "Beed", "land_acres": 3, "budget_rs": 0.0}) == ["budget_rs"]
    assert compute_missing({"location_text": "Beed", "land_acres": -1, "budget_rs": 5}) == ["land_acres"]
    assert compute_missing({"location_text": "unknown", "land_acres": 0, "budget_rs": 0}) == [
        "location_text", "land_acres", "budget_rs",
    ]
    assert compute_missing({"location_text": "Beed", "land_acres": 3, "budget_rs": 100}) == []


def test_card_edit_to_zero_budget_becomes_missing():
    p = FarmProfile(location_text="Beed", land_acres=3, budget_rs=50000)
    out = merge_patch_node({"profile": p, "profile_patch": {"budget_rs": 0}})
    assert out["missing"] == ["budget_rs"]
    assert out["profile"].budget_rs == 0.0
