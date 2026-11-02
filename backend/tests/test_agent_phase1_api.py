"""Phase 1: chat request validation, profile seeding, message cap, thread isolation,
reoptimize memory sync, message-only question turns. No network and no LLM."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.memory import MAX_STORED_MESSAGES, cap_messages
from app.api import agent as agent_api
from app.api.agent import restore_thread_state, seed_profile_from_body
from app.main import app
from app.schemas import FarmProfile, PlanResult

client = TestClient(app)
THREAD = "th_" + "ab12cd34" * 4
PLAN_FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "api_examples" / "contract" / "plan_pune.json"
SAVED_PROFILE = {"location_text": "Nashik, Maharashtra", "land_acres": 2, "budget_rs": 200000,
                 "water_source": "borewell", "borewell_count": 1, "borewell_yield_lph": 8000,
                 "pump_hours_per_day": 6, "irrigation_method": "drip"}


class FakeCache:
    """Same get/set_memory contract as the SQLite cache: rows keyed by (thread_id, key)."""

    def __init__(self):
        self.mem: dict = {}
        self.plans: dict = {}

    async def get_memory(self, thread_id, key):
        return self.mem.get((thread_id, key))

    async def set_memory(self, thread_id, key, value):
        self.mem[(thread_id, key)] = value

    async def get_all_memory(self, thread_id):
        return {k: v for (t, k), v in self.mem.items() if t == thread_id}

    async def set_plan(self, plan_id, data):
        self.plans[plan_id] = data

    async def get_plan(self, plan_id):
        return self.plans.get(plan_id)


class RecordingGraph:
    """Stands in for the compiled graph: records the initial state and replays given events."""

    def __init__(self, events=()):
        self.events = list(events)
        self.state = None
        self.config = None

    async def astream_events(self, state, config=None, version=None):
        self.state, self.config = state, config
        for ev in self.events:
            yield ev


def _reply_event(text="Because onion pays best."):
    return {"event": "on_chain_end", "name": "respond",
            "data": {"output": {"reply": {"text": text, "language": "en", "provider": "template"}}}}


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

    monkeypatch.setattr("app.core.cache.get_cache", fake_get_cache)
    old = getattr(app.state, "agent_graph", None)
    yield cache
    app.state.agent_graph = old


def _chat(body, graph=None):
    app.state.agent_graph = graph
    return client.post("/api/agent/chat", json=body)


# ── validation ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {}, {"message": 5}, {"message": "x" * 2001},
    {"message": "hi", "thread_id": "abc"}, {"message": "hi", "thread_id": "th_" + "A" * 32},
    {"message": "hi", "thread_id": "th_" + "a" * 31}, {"message": "hi", "thread_id": 7},
    {"message": "hi", "profile_patch": {"bogus": 1}}, {"message": "hi", "profile_patch": {"land_acres": "abc"}},
    {"message": "hi", "profile_patch": {"water_source": "lake"}}, {"message": "hi", "profile_patch": [1]},
    {"message": "hi", "profile_patch": {"missing": ["land_acres"]}},
])
def test_bad_chat_requests_are_structured_422(body):
    r = _chat(body, RecordingGraph())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"]["fields"]


def test_good_requests_pass_and_message_is_stripped():
    graph = RecordingGraph()
    r = _chat({"message": "  hello  ", "thread_id": THREAD, "language": "hi"}, graph)
    assert r.status_code == 200
    assert graph.state["message"] == "hello" and graph.state["thread_id"] == THREAD
    assert graph.config["recursion_limit"] == agent_api.RECURSION_LIMIT


def test_message_of_exactly_2000_chars_is_accepted():
    assert _chat({"message": "a" * 2000}, RecordingGraph()).status_code == 200


def test_card_edit_without_message_is_still_allowed():
    graph = RecordingGraph()
    r = _chat({"profile_patch": {"budget_rs": 90000}}, graph)
    assert r.status_code == 200 and graph.state["profile_patch"] == {"budget_rs": 90000}


@pytest.mark.parametrize(("sent", "expected"), [(None, "en"), ("xx", "en"), ("kn", "en"), (5, "en"),
                                                 ("mr", "mr"), ("hi", "hi"), ("en", "en")])
def test_language_defaults_to_en(sent, expected):
    graph = RecordingGraph()
    body = {"message": "hi"} if sent is None else {"message": "hi", "language": sent}
    _chat(body, graph)
    assert graph.state["language"] == expected


def test_missing_graph_is_a_real_error_event_not_a_message():
    r = _chat({"message": "hi"}, None)
    names = [n for n, _ in _events(r.text)]
    assert names == ["thread", "error", "done"]
    err = dict(_events(r.text))["error"]["error"]
    assert err["code"] == "UPSTREAM_UNAVAILABLE" and set(err["user_message"]) == {"mr", "hi", "en"}


# ── profile seeding ───────────────────────────────────────────────────────────

def test_seed_marks_every_seeded_field_and_normalises():
    p = seed_profile_from_body(SAVED_PROFILE, "en")
    assert p.location_text == "Nashik, Maharashtra" and p.land_acres == 2 and p.budget_rs == 200000
    assert p.missing == []
    assert {d.field for d in p.defaults_used} >= {"location_text", "land_acres", "budget_rs", "water_source"}
    assert {d.basis for d in p.defaults_used} == {"farmer_input (saved Farm Profile)"}


@pytest.mark.parametrize("raw", [
    None, "x", [], {}, {"location_text": "unknown", "land_acres": 0, "budget_rs": 0},
    {"location_text": "", "land_acres": -1, "budget_rs": "abc"}, {"water_source": "borewell"},
])
def test_unusable_seed_is_ignored(raw):
    assert seed_profile_from_body(raw, "en") is None


def test_partial_seed_keeps_unusable_fields_missing():
    p = seed_profile_from_body({"location_text": "Beed", "land_acres": 4, "budget_rs": 0}, "en")
    assert p.location_text == "Beed" and p.land_acres == 4 and p.budget_rs == 0
    assert p.missing == ["budget_rs"]
    assert {d.field for d in p.defaults_used} == {"location_text", "land_acres"}
    p2 = seed_profile_from_body({"location_text": "unknown", "land_acres": 3}, "en")
    assert p2.location_text == "unknown" and p2.missing == ["location_text", "budget_rs"]


def test_seed_drops_invalid_optional_fields_only():
    p = seed_profile_from_body({**SAVED_PROFILE, "water_source": "lake", "bogus": 1}, "en")
    assert p.water_source is None and p.land_acres == 2


def test_seed_starts_a_thread_without_a_stored_profile_and_is_saved(_env):
    graph = RecordingGraph()
    _chat({"message": "plan", "thread_id": THREAD, "profile": SAVED_PROFILE}, graph)
    assert graph.state["profile"].budget_rs == 200000
    assert _env.mem[(THREAD, "profile")]["location_text"] == "Nashik, Maharashtra"   # refresh keeps it


def test_stored_profile_always_beats_the_client_profile(_env):
    _env.mem[(THREAD, "profile")] = {"location_text": "Pune", "land_acres": 5, "budget_rs": 70000}
    graph = RecordingGraph()
    _chat({"message": "plan", "thread_id": THREAD, "profile": SAVED_PROFILE}, graph)
    assert graph.state["profile"].location_text == "Pune" and graph.state["profile"].budget_rs == 70000
    assert _env.mem[(THREAD, "profile")]["land_acres"] == 5


def test_partial_seed_is_used_but_not_stored(_env):
    graph = RecordingGraph()
    _chat({"message": "plan", "thread_id": THREAD, "profile": {"location_text": "Beed", "land_acres": 4}}, graph)
    assert graph.state["profile"].missing == ["budget_rs"]
    assert (THREAD, "profile") not in _env.mem


# ── per-turn state, restore, isolation ────────────────────────────────────────

def test_every_per_turn_key_is_reset_each_request():
    graph = RecordingGraph()
    _chat({"message": "hi"}, graph)
    for key in ("crops", "impact", "opt_warnings", "shap_factors", "long_crop_facts", "feasibility", "plan_result",
                "no_data", "explanation_text", "grounding_retry_count", "relaxation_count", "reply", "candidates"):
        assert key in graph.state, key
    assert graph.state["plan_result"] is None and graph.state["crops"] == [] and graph.state["feasibility"] is None


def test_stored_plan_restores_crops_and_strategies_after_a_restart(_env):
    plan = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    _env.mem[(THREAD, "plan")] = plan
    _env.mem[(THREAD, "profile")] = plan["profile"]
    graph = RecordingGraph()
    _chat({"message": "Why onion?", "thread_id": THREAD}, graph)
    s = graph.state
    assert s["strategies"] and s["crops"] and s["water"] and s["scenarios"]
    assert s["plan_result"].plan_id == plan["plan_id"] and s["location"].district == plan["location"]["district"]
    assert len(s["crops"]) == len(plan["crops"])


def test_thread_a_profile_is_not_visible_in_thread_b(_env):
    other = "th_" + "0f" * 16
    _env.mem[(THREAD, "profile")] = {"location_text": "Pune", "land_acres": 5, "budget_rs": 70000}
    _env.mem[(THREAD, "messages")] = [{"role": "farmer", "text": "secret", "language": "en", "at": "x"}]
    _env.mem[(THREAD, "plan")] = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    messages, state = asyncio.run(restore_thread_state(_env, other))
    assert messages == [] and state == {}
    graph = RecordingGraph()
    _chat({"message": "hi", "thread_id": other}, graph)
    assert graph.state["strategies"] == [] and "profile" not in graph.state


# ── message cap ───────────────────────────────────────────────────────────────

def test_cap_messages_keeps_the_newest():
    msgs = [{"n": i} for i in range(100)]
    capped = cap_messages(msgs)
    assert len(capped) == MAX_STORED_MESSAGES == 40
    assert capped[0] == {"n": 60} and capped[-1] == {"n": 99}


def test_loaded_and_saved_messages_are_capped(_env):
    _env.mem[(THREAD, "messages")] = [{"role": "farmer", "text": str(i), "language": "en", "at": "x"} for i in range(90)]
    graph = RecordingGraph([_reply_event()])
    r = _chat({"message": "Why onion?", "thread_id": THREAD}, graph)
    saved = _env.mem[(THREAD, "messages")]
    assert len(saved) == 40
    assert saved[-1]["role"] == "agent" and saved[-2]["text"] == "Why onion?"
    assert ("message" in [n for n, _ in _events(r.text)])


def test_thread_endpoint_caps_returned_messages(_env, monkeypatch):
    async def fake_get_cache():
        return _env

    monkeypatch.setattr("app.api.threads.get_cache", fake_get_cache)
    _env.mem[(THREAD, "messages")] = [{"role": "agent", "text": str(i), "language": "en",
                                       "at": "2026-01-01T00:00:00Z"} for i in range(70)]
    r = client.get(f"/api/threads/{THREAD}")
    assert r.status_code == 200 and len(r.json()["messages"]) == 40


# ── question turns do not touch the plan ──────────────────────────────────────

def test_question_turn_emits_only_a_message_and_leaves_the_stored_plan_alone(_env):
    plan = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    _env.mem[(THREAD, "plan")] = plan
    graph = RecordingGraph([_reply_event()])
    r = _chat({"message": "Why onion?", "thread_id": THREAD}, graph)
    names = [n for n, _ in _events(r.text)]
    assert names == ["thread", "message", "done"]                 # no plan event
    assert _env.mem[(THREAD, "plan")] == plan                     # version and explanation untouched
    assert _env.plans == {}


# ── reoptimize keeps the thread memory in step ────────────────────────────────

def test_reoptimize_writes_the_new_plan_to_agent_memory(_env, monkeypatch):
    from app.api import plan as plan_api

    old = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    old.update(thread_id=THREAD, version=1)
    _env.plans[old["plan_id"]] = old

    async def fake_get_cache():
        return _env

    async def fake_run_plan(profile, thread_id=None, plan_id=None):
        data = {**old, "profile": profile.model_dump(mode="json")}
        return PlanResult(**data)

    async def no_writeback(*_a, **_k):
        return None

    monkeypatch.setattr(plan_api, "get_cache", fake_get_cache)
    monkeypatch.setattr(plan_api, "run_plan", fake_run_plan)
    monkeypatch.setattr("app.agent.memory.update_profile_fields", no_writeback)
    r = client.post(f"/api/plans/{old['plan_id']}/reoptimize", json={"budget_rs": 90000})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    stored_plan = _env.mem[(THREAD, "plan")]
    assert stored_plan["version"] == 2 and stored_plan["plan_id"] == old["plan_id"]
    assert _env.mem[(THREAD, "profile")]["budget_rs"] == 90000
    assert _env.plans[old["plan_id"]]["version"] == 2
    # ...and the next chat turn restores exactly that plan
    _, state = asyncio.run(restore_thread_state(_env, THREAD))
    assert state["plan_result"].version == 2 and FarmProfile.model_validate(_env.mem[(THREAD, "profile")]).budget_rs == 90000
