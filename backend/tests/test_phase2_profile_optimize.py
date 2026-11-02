"""Phase 2: PUT /api/profile, profile/plan versions, the Optimize intent, the per-thread
run lock and the atomic 'plan saved' contract. No network and no LLM."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.api.profile import effective_version, meta_for_profile_write, meta_with_plan, plan_is_stale
from app.core.errors import AppError
from app.main import app
from app.schemas import FarmProfile, Location, PlanResult

client = TestClient(app)
THREAD = "th_" + "ab12cd34" * 4
OTHER = "th_" + "0f" * 16
PLAN_FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "api_examples" / "contract" / "plan_pune.json"
GOOD = {"location_text": "Nashik", "land_acres": 2, "budget_rs": 200000, "water_source": "borewell",
        "borewell_count": 1, "borewell_yield_lph": 8000, "pump_hours_per_day": 6, "canal_access": False}
NASHIK = Location(input="Nashik", resolved_name="Nashik, Maharashtra", district="Nashik",
                  state="Maharashtra", latitude=20.0, longitude=73.8)


class FakeCache:
    def __init__(self):
        self.mem: dict = {}
        self.plans: dict = {}
        self.fail_keys: set = set()

    async def get_memory(self, thread_id, key):
        return self.mem.get((thread_id, key))

    async def set_memory(self, thread_id, key, value):
        if key in self.fail_keys:
            raise RuntimeError("disk full")
        self.mem[(thread_id, key)] = value

    async def get_all_memory(self, thread_id):
        return {k: v for (t, k), v in self.mem.items() if t == thread_id}

    async def set_plan(self, plan_id, data):
        self.plans[plan_id] = data

    async def get_plan(self, plan_id):
        return self.plans.get(plan_id)


class RecordingGraph:
    def __init__(self, events=(), boom=None):
        self.events, self.boom, self.state = list(events), boom, None

    async def astream_events(self, state, config=None, version=None):
        self.state = state
        for ev in self.events:
            yield ev
        if self.boom:
            raise self.boom


def _plan_events(profile=None):
    plan = PlanResult.model_validate(json.loads(PLAN_FIXTURE.read_text(encoding="utf-8")))
    evs = []
    if profile is not None:
        evs.append({"event": "on_chain_end", "name": "merge_patch", "data": {"output": {"profile": profile}}})
    evs.append({"event": "on_chain_end", "name": "respond", "data": {"output": {"plan_result": plan}}})
    return evs


def _events(text):
    out, ev = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            ev = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and ev:
            out.append((ev, json.loads(line.split(":", 1)[1].strip())))
            ev = None
    return out


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    cache = FakeCache()

    async def fake_get_cache():
        return cache

    async def fake_locate(text):
        return NASHIK

    monkeypatch.setattr("app.core.cache.get_cache", fake_get_cache)
    monkeypatch.setattr("app.api.threads.get_cache", fake_get_cache)
    monkeypatch.setattr("app.api.plan.get_cache", fake_get_cache)
    monkeypatch.setattr("app.services.location.locate", fake_locate)
    agent_api._INFLIGHT.clear()
    old = getattr(app.state, "agent_graph", None)
    yield cache
    app.state.agent_graph = old
    agent_api._INFLIGHT.clear()


def _put(profile=None, thread_id=None):
    body = {"profile": GOOD if profile is None else profile}
    if thread_id:
        body["thread_id"] = thread_id
    return client.put("/api/profile", json=body)


def _chat(body, graph=None):
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None      # one event loop per TestClient call
    app.state.agent_graph = graph
    return client.post("/api/agent/chat", json=body)


# ── PUT /api/profile: validation ──────────────────────────────────────────────

@pytest.mark.parametrize(("change", "field"), [
    ({"land_acres": 0}, "land_acres"), ({"land_acres": -3}, "land_acres"), ({"land_acres": 10001}, "land_acres"),
    ({"land_acres": "2"}, "land_acres"), ({"land_acres": True}, "land_acres"), ({"land_acres": None}, "land_acres"),
    ({"budget_rs": 0}, "budget_rs"), ({"budget_rs": -1}, "budget_rs"), ({"budget_rs": "lots"}, "budget_rs"),
    ({"location_text": ""}, "location_text"), ({"location_text": "   "}, "location_text"),
    ({"location_text": "unknown"}, "location_text"), ({"location_text": "Unknown"}, "location_text"),
    ({"location_text": 5}, "location_text"), ({"location_text": None}, "location_text"),
    ({"bogus": 1}, "bogus"), ({"water_source": "lake"}, "water_source"),
    ({"borewell_count": 0}, "borewell_count"), ({"borewell_count": 1.5}, "borewell_count"),
    ({"borewell_yield_lph": 0}, "borewell_yield_lph"), ({"borewell_yield_lph": -5}, "borewell_yield_lph"),
    ({"pump_hours_per_day": 0}, "pump_hours_per_day"), ({"pump_hours_per_day": 25}, "pump_hours_per_day"),
    ({"canal_access": "yes"}, "canal_access"), ({"canal_access": 1}, "canal_access"),
    ({"risk_appetite": "reckless"}, "risk_appetite"),
])
def test_put_rejects_bad_values_with_structured_field_errors(change, field, _env):
    profile = {**GOOD, **change}
    if change.get("land_acres", 1) is None:
        profile.pop("land_acres")
    r = _put(profile)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and set(err["user_message"]) == {"mr", "hi", "en"}
    assert field in err["details"]["fields"] and isinstance(err["details"]["fields"][field], str)
    assert _env.mem == {}                      # nothing was stored


def test_put_partial_borewell_values_are_accepted_when_positive():
    r = _put({"location_text": "Nashik", "land_acres": 2, "budget_rs": 1000, "water_source": "borewell",
              "borewell_yield_lph": 5000})
    assert r.status_code == 200 and r.json()["profile"]["borewell_yield_lph"] == 5000


@pytest.mark.parametrize("body", [
    [], "x", {}, {"profile": []}, {"profile": GOOD, "extra": 1},
    {"profile": GOOD, "thread_id": "abc"}, {"profile": GOOD, "thread_id": "th_" + "A" * 32}, {"profile": GOOD, "thread_id": 5},
])
def test_put_rejects_bad_envelopes(body):
    r = client.put("/api/profile", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"]["fields"]


def test_put_collects_every_bad_field_at_once():
    r = _put({**GOOD, "land_acres": 0, "budget_rs": 0, "location_text": ""})
    assert set(r.json()["error"]["details"]["fields"]) == {"land_acres", "budget_rs", "location_text"}


def test_put_location_not_found_is_422_on_location_text(monkeypatch, _env):
    async def not_found(text):
        raise AppError("LOCATION_NOT_FOUND", {"location_text": text})

    monkeypatch.setattr("app.services.location.locate", not_found)
    r = _put({**GOOD, "location_text": "Atlantis"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "LOCATION_NOT_FOUND" and "location_text" in err["details"]["fields"]
    assert set(err["user_message"]) == {"mr", "hi", "en"} and _env.mem == {}


def test_put_upstream_failure_still_saves_with_a_warning(monkeypatch, _env):
    async def blip(text):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.services.location.locate", blip)
    r = _put()
    assert r.status_code == 200
    body = r.json()
    assert body["profile_version"] == 1 and [w["code"] for w in body["warnings"]] == ["LOCATION_UNVERIFIED"]
    assert (body["thread_id"], "profile") in _env.mem


# ── PUT /api/profile: saving, versions, isolation ─────────────────────────────

def test_put_saves_v1_then_v2_and_never_plans(_env):
    r1 = _put()
    assert r1.status_code == 200
    b1 = r1.json()
    assert set(b1) == {"thread_id", "profile", "profile_version", "saved_at", "plan_stale", "warnings"}
    assert b1["profile_version"] == 1 and b1["plan_stale"] is False and b1["warnings"] == []
    assert b1["thread_id"].startswith("th_") and len(b1["thread_id"]) == 35
    assert b1["profile"]["land_acres"] == 2 and b1["profile"]["location_text"] == "Nashik"
    r2 = _put({**GOOD, "budget_rs": 250000}, thread_id=b1["thread_id"])
    assert r2.json()["profile_version"] == 2 and r2.json()["thread_id"] == b1["thread_id"]
    # an identical save is still a successful save: every one counts
    assert _put({**GOOD, "budget_rs": 250000}, thread_id=b1["thread_id"]).json()["profile_version"] == 3
    assert _env.plans == {} and (b1["thread_id"], "plan") not in _env.mem
    meta = _env.mem[(b1["thread_id"], "profile_meta")]
    assert meta["version"] == 3 and meta["saved_at"] and _env.mem[(b1["thread_id"], "profile")]["budget_rs"] == 250000


def test_put_creates_an_unknown_thread_with_the_given_id_and_keeps_messages(_env):
    msgs = [{"role": "farmer", "text": "hi", "language": "en", "at": "x"}]
    _env.mem[(THREAD, "messages")] = msgs
    r = _put(thread_id=THREAD)
    assert r.json()["thread_id"] == THREAD and _env.mem[(THREAD, "messages")] == msgs


def test_put_borewell_count_is_normalised_like_api_plan():
    r = _put({"location_text": "Nashik", "land_acres": 2, "budget_rs": 1000, "water_source": "borewell",
              "borewell_yield_lph": 5000, "pump_hours_per_day": 4})
    p = r.json()["profile"]
    assert p["borewell_count"] == 1 and any(d["field"] == "borewell_count" for d in p["defaults_used"])


def test_threads_have_independent_versions(_env):
    a = _put(thread_id=THREAD).json()
    _put({**GOOD, "budget_rs": 5}, thread_id=THREAD)
    b = _put(thread_id=OTHER).json()
    assert a["profile_version"] == 1 and b["profile_version"] == 1
    assert _env.mem[(THREAD, "profile_meta")]["version"] == 2 and _env.mem[(OTHER, "profile_meta")]["version"] == 1
    assert _env.mem[(OTHER, "profile")]["budget_rs"] == 200000


def test_legacy_profile_without_meta_counts_as_version_1_then_2(_env):
    _env.mem[(THREAD, "profile")] = dict(GOOD)
    _env.mem[(THREAD, "plan")] = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    got = client.get(f"/api/threads/{THREAD}").json()
    assert got["profile_version"] == 1 and got["plan_stale"] is False and got["profile_saved_at"] is None
    r = _put({**GOOD, "budget_rs": 1}, thread_id=THREAD)
    assert r.json()["profile_version"] == 2 and r.json()["plan_stale"] is True


# ── plan_stale ────────────────────────────────────────────────────────────────

def test_plan_stale_after_a_save_that_follows_a_plan(_env):
    tid = _put().json()["thread_id"]
    r = _chat({"intent": "optimize", "thread_id": tid, "profile_version": 1}, RecordingGraph(_plan_events()))
    assert r.status_code == 200
    assert _env.mem[(tid, "profile_meta")]["plan_profile_version"] == 1
    assert client.get(f"/api/threads/{tid}").json()["plan_stale"] is False
    again = _put({**GOOD, "budget_rs": 300000}, thread_id=tid).json()
    assert again["profile_version"] == 2 and again["plan_stale"] is True
    got = client.get(f"/api/threads/{tid}").json()
    assert got["plan_stale"] is True and got["profile_version"] == 2 and got["profile_saved_at"] == again["saved_at"]
    # re-optimizing against the new version clears it
    _chat({"intent": "optimize", "thread_id": tid, "profile_version": 2}, RecordingGraph(_plan_events()))
    assert client.get(f"/api/threads/{tid}").json()["plan_stale"] is False


def test_thread_without_a_plan_is_never_stale(_env):
    tid = _put().json()["thread_id"]
    _put(thread_id=tid)
    got = client.get(f"/api/threads/{tid}").json()
    assert got["plan_stale"] is False and got["plan"] is None and got["profile_version"] == 2


def test_version_helpers():
    assert effective_version(None, False) is None and effective_version(None, True) == 1
    assert effective_version({"version": 4}, True) == 4
    assert plan_is_stale(None, True, True) is False
    assert plan_is_stale({"version": 2, "plan_profile_version": 1}, True, True) is True
    assert plan_is_stale({"version": 2, "plan_profile_version": 2}, True, True) is False
    assert plan_is_stale({"version": 2, "plan_profile_version": 1}, True, False) is False
    assert meta_with_plan({"version": 3, "saved_at": "t"})["plan_profile_version"] == 3
    same = meta_for_profile_write({"version": 2, "saved_at": "t"}, dict(GOOD), {**GOOD, "language": "mr"})
    assert same["version"] == 2                                   # language alone is not a profile change
    assert meta_for_profile_write({"version": 2}, dict(GOOD), {**GOOD, "budget_rs": 1})["version"] == 3
    assert meta_for_profile_write(None, None, dict(GOOD))["version"] == 1


def test_new_error_codes_are_trilingual_with_the_right_status():
    for code, status in (("PROFILE_STALE", 409), ("RUN_IN_PROGRESS", 409), ("NO_SAVED_PROFILE", 422)):
        e = AppError(code)
        assert e.status_code == status and set(e.user_message) == {"mr", "hi", "en"}
        assert e.to_response().error.code == code


# ── Optimize intent ───────────────────────────────────────────────────────────

def test_optimize_without_a_saved_profile_is_422_no_saved_profile(_env):
    for body in ({"intent": "optimize"}, {"intent": "optimize", "thread_id": THREAD},
                 {"intent": "optimize", "thread_id": THREAD, "profile": GOOD, "message": "plan"}):
        r = _chat(body, RecordingGraph())
        assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SAVED_PROFILE"
        assert set(r.json()["error"]["user_message"]) == {"mr", "hi", "en"}
    _env.mem[(THREAD, "profile")] = {"location_text": "unknown", "land_acres": 0, "budget_rs": 0}
    assert _chat({"intent": "optimize", "thread_id": THREAD}, RecordingGraph()).status_code == 422
    assert agent_api._INFLIGHT == {}                              # failed checks never leave a lock behind


def test_optimize_with_a_stale_version_is_409_before_streaming(_env):
    tid = _put().json()["thread_id"]
    _put({**GOOD, "budget_rs": 1}, thread_id=tid)
    graph = RecordingGraph()
    r = _chat({"intent": "optimize", "thread_id": tid, "profile_version": 1}, graph)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROFILE_STALE"
    assert r.json()["error"]["details"]["profile_version"] == 2
    assert graph.state is None and agent_api._INFLIGHT == {}
    assert _chat({"intent": "optimize", "thread_id": tid, "profile_version": 2}, RecordingGraph()).status_code == 200
    assert _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph()).status_code == 200   # version optional


@pytest.mark.parametrize("bad", [{"intent": "reset"}, {"intent": "optimize", "profile_version": "2"},
                                 {"intent": "optimize", "profile_version": 0}, {"intent": "optimize", "profile_version": True},
                                 {"message": "hi", "profile_version": 1.5}])
def test_bad_intent_or_version_is_a_validation_error(bad):
    r = _chat({"thread_id": THREAD, **bad}, RecordingGraph())
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_optimize_uses_only_the_server_profile_and_needs_no_message(_env):
    tid = _put().json()["thread_id"]
    graph = RecordingGraph()
    body = {"intent": "optimize", "thread_id": tid, "profile_version": 1, "language": "mr",
            "profile": {**GOOD, "budget_rs": 1, "land_acres": 99}, "profile_patch": {"budget_rs": 5},
            "message": "ignore me, give me cotton"}
    r = _chat(body, graph)
    assert r.status_code == 200
    s = graph.state
    assert s["intent"] == "optimize" and s["plan_only"] is True and s["profile_patch"] is None
    assert s["profile"].budget_rs == 200000 and s["profile"].land_acres == 2
    assert s["message"] != body["message"] and s["message"]
    assert _env.mem[(tid, "profile")]["budget_rs"] == 200000        # request-body profile never stored
    assert _env.mem[(tid, "profile_meta")]["version"] == 1


def test_optimize_turn_does_not_change_the_saved_profile_version(_env):
    tid = _put().json()["thread_id"]
    changed = FarmProfile.model_validate({**GOOD, "budget_rs": 7})
    r = _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(_plan_events(changed)))
    assert _env.mem[(tid, "profile")]["budget_rs"] == 200000
    assert dict(_events(r.text))["done"]["profile_version"] == 1


def test_optimize_streams_plan_then_plan_saved_then_message_then_done(_env):
    tid = _put().json()["thread_id"]
    r = _chat({"intent": "optimize", "thread_id": tid, "profile_version": 1}, RecordingGraph(_plan_events()))
    evs = _events(r.text)
    names = [n for n, _ in evs]
    assert names == ["thread", "plan", "trace", "message", "done"]
    trace = dict(evs)["trace"]
    assert (trace["tool_name"], trace["display_name"], trace["status"]) == ("plan_saved", "Plan Saved", "ok")
    plan = dict(evs)["plan"]
    assert _env.plans[plan["plan_id"]]["plan_id"] == plan["plan_id"] and _env.mem[(tid, "plan")]["plan_id"] == plan["plan_id"]
    assert dict(evs)["done"]["profile_version"] == 1 and "ms" in dict(evs)["done"]
    transcript = _env.mem[(tid, "messages")]
    assert (transcript[0]["role"], transcript[0]["text"]) == ("farmer", "Optimize my plan")
    assert transcript[-1]["role"] == "agent"


# ── per-thread run lock ───────────────────────────────────────────────────────

def test_second_run_on_a_busy_thread_is_409_run_in_progress(_env):
    tid = _put().json()["thread_id"]
    token = agent_api.acquire_thread(tid)                          # a run is already streaming
    for body in ({"intent": "optimize", "thread_id": tid}, {"message": "hello", "thread_id": tid}):
        r = _chat(body, RecordingGraph())
        assert r.status_code == 409 and r.json()["error"]["code"] == "RUN_IN_PROGRESS"
        assert set(r.json()["error"]["user_message"]) == {"mr", "hi", "en"}
    # another thread is not blocked
    other = _put(thread_id=OTHER).json()["thread_id"]
    assert _chat({"intent": "optimize", "thread_id": other}, RecordingGraph()).status_code == 200
    agent_api.release_thread(tid, token)
    assert _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph()).status_code == 200


def test_lock_is_released_after_success_graph_failure_and_persist_failure(_env):
    tid = _put().json()["thread_id"]
    assert _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(_plan_events())).status_code == 200
    assert agent_api._INFLIGHT == {}
    r = _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(boom=RuntimeError("graph exploded")))
    assert "error" in [n for n, _ in _events(r.text)] and agent_api._INFLIGHT == {}
    assert "graph exploded" not in r.text                           # internals never reach the client
    _env.fail_keys.add("plan")
    _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(_plan_events()))
    assert agent_api._INFLIGHT == {}
    assert _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph()).status_code == 200


def test_a_dead_lock_expires(monkeypatch):
    token = agent_api.acquire_thread(THREAD)
    with pytest.raises(AppError):
        agent_api.acquire_thread(THREAD)
    monkeypatch.setattr(agent_api, "INFLIGHT_MAX_AGE_S", 0.0)
    assert agent_api.acquire_thread(THREAD) != token
    agent_api.release_thread(THREAD, token)                         # the old owner cannot free the new run
    assert THREAD in agent_api._INFLIGHT


# ── chat-driven profile changes bump the version ──────────────────────────────

def test_done_carries_the_new_profile_version_after_a_chat_change(_env):
    tid = _put().json()["thread_id"]
    changed = FarmProfile.model_validate({**GOOD, "budget_rs": 90000})
    r = _chat({"message": "my budget is now 90000", "thread_id": tid}, RecordingGraph(_plan_events(changed)))
    done = dict(_events(r.text))["done"]
    assert done["profile_version"] == 2
    assert _env.mem[(tid, "profile")]["budget_rs"] == 90000
    meta = _env.mem[(tid, "profile_meta")]
    assert meta["version"] == 2 and meta["plan_profile_version"] == 2     # the plan belongs to the new version
    assert client.get(f"/api/threads/{tid}").json()["plan_stale"] is False


def test_unchanged_profile_event_does_not_bump_the_version(_env):
    tid = _put().json()["thread_id"]
    same = FarmProfile.model_validate(GOOD)
    r = _chat({"message": "make a plan", "thread_id": tid}, RecordingGraph(_plan_events(same)))
    assert dict(_events(r.text))["done"]["profile_version"] == 1


def test_seeded_profile_is_version_1_and_a_plain_chat_reports_none_without_one(_env):
    r = _chat({"message": "plan", "thread_id": THREAD, "profile": GOOD}, RecordingGraph())
    assert dict(_events(r.text))["done"]["profile_version"] == 1
    assert _env.mem[(THREAD, "profile_meta")]["version"] == 1
    r2 = _chat({"message": "hi", "thread_id": OTHER}, RecordingGraph())
    assert dict(_events(r2.text))["done"]["profile_version"] is None


# ── atomic 'plan saved' ───────────────────────────────────────────────────────

def test_plan_persist_failure_means_no_plan_event_no_ok_trace_and_an_error(_env):
    tid = _put().json()["thread_id"]
    _env.fail_keys.add("plan")                                      # agent_memory write fails
    r = _chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(_plan_events()))
    evs = _events(r.text)
    names = [n for n, _ in evs]
    assert "plan" not in names and "message" not in names
    assert names == ["thread", "trace", "error", "done"]
    trace = dict(evs)["trace"]
    assert trace["tool_name"] == "plan_saved" and trace["status"] == "failed"
    err = dict(evs)["error"]["error"]
    assert err["code"] == "INTERNAL" and set(err["user_message"]) == {"mr", "hi", "en"}
    assert "disk full" not in r.text
    assert not any(t == tid and k == "plan" for (t, k) in _env.mem)


def test_plan_persist_failure_in_the_plans_table_is_also_atomic(_env, monkeypatch):
    tid = _put().json()["thread_id"]

    async def broken(*_a, **_k):
        raise RuntimeError("db locked")

    monkeypatch.setattr(_env, "set_plan", broken)
    names = [n for n, _ in _events(_chat({"intent": "optimize", "thread_id": tid}, RecordingGraph(_plan_events())).text)]
    assert "plan" not in names and "error" in names and names[-1] == "done"
    assert (tid, "plan") not in _env.mem


def test_no_cache_means_no_plan_is_claimed(monkeypatch):
    async def no_cache():
        raise RuntimeError("cache down")

    monkeypatch.setattr("app.core.cache.get_cache", no_cache)
    r = _chat({"message": "plan", "thread_id": THREAD}, RecordingGraph(_plan_events()))
    names = [n for n, _ in _events(r.text)]
    assert "plan" not in names and "error" in names
