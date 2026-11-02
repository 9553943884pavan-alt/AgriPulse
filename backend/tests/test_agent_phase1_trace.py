"""Phase 1: the trace is real, ordered, honest and safe to show. No network, no LLM."""

import asyncio
import json
import time
from datetime import timedelta

from app.agent import nodes, tools
from app.agent.nodes import _trace, gather_data_node
from app.api.agent import TraceContext, _lg_event_to_sse
from app.schemas import FarmProfile, Location, TraceEvent

PROFILE = FarmProfile(location_text="Nashik, Maharashtra", land_acres=2, budget_rs=200000)
LOCATION = Location(input="Nashik", resolved_name="Nashik", district="Nashik", state="Maharashtra",
                    latitude=20.0, longitude=73.8)


def _node_end(name, **output):
    return {"event": "on_chain_end", "name": name, "data": {"output": output}}


def _as_list(out):
    return out if isinstance(out, list) else ([out] if out else [])


# ── fields ────────────────────────────────────────────────────────────────────

def test_trace_carries_tool_and_display_names_and_real_times():
    started = nodes._now()
    time.sleep(0.02)
    t = _trace("recommend_crops", "Crop recommendations", "ok", "done", started=started)
    assert (t.tool_name, t.display_name) == ("crop_recommender", "Crop Recommendation")
    assert t.started_at == started and t.completed_at >= started + timedelta(milliseconds=15)
    assert t.duration_ms >= 15
    assert t.run_id is None and t.sequence is None        # stamped when emitted


def test_every_node_in_the_graph_has_a_friendly_name():
    from app.agent.graph import build_graph

    for node in build_graph().nodes:
        if node in ("router", "save_memory", "smalltalk", "gather_data"):  # gather_data is named per step; the others emit no trace
            continue
        t = _trace(node, "x", "ok", "s")
        assert t.display_name, node


def test_old_clients_can_still_parse_a_trace_event():
    old = {"id": "e", "node": "n", "step": "s", "status": "ok", "started_at": "2026-01-01T00:00:00Z",
           "duration_ms": 1, "summary": "x"}
    t = TraceEvent.model_validate(old)
    assert t.run_id is None and t.sequence is None and t.display_name is None


# ── SSE mapper ────────────────────────────────────────────────────────────────

def test_every_new_trace_item_is_streamed_in_order_once():
    ctx = TraceContext(run_id="run-1")
    a, b, c = (_trace("gather_data", s, "ok", s) for s in ("location", "weather", "soil"))
    first = _as_list(_lg_event_to_sse(_node_end("gather_data", trace=[a, b, c]), ctx))
    assert [json.loads(e["data"])["step"] for e in first] == ["location", "weather", "soil"]
    assert [json.loads(e["data"])["sequence"] for e in first] == [1, 2, 3]
    d = _trace("recommend_crops", "x", "ok", "x")
    # the next node's patch repeats the earlier items: only the new one is streamed
    second = _as_list(_lg_event_to_sse(_node_end("recommend_crops", trace=[a, b, c, d]), ctx))
    assert len(second) == 1 and json.loads(second[0]["data"])["sequence"] == 4
    assert {json.loads(e["data"])["run_id"] for e in first + second} == {"run-1"}


def test_nodes_that_were_never_streamed_before_are_streamed_now():
    ctx = TraceContext()
    extract = _trace("extract_profile", "llm", "ok", "Farm profile read")
    out = _as_list(_lg_event_to_sse(_node_end("extract_profile", profile=PROFILE, trace=[extract]), ctx))
    assert [e["event"] for e in out] == ["profile", "trace"]
    ask = _trace("ask_missing", "land_acres", "ok", "Asked")
    out = _as_list(_lg_event_to_sse(
        _node_end("ask_missing", question={"text": "q", "field": "land_acres", "language": "en"}, trace=[extract, ask]), ctx))
    assert [e["event"] for e in out] == ["trace", "question"]
    mem = _trace("answer_from_memory", "Plan question", "ok", "Answered")
    out = _as_list(_lg_event_to_sse(_node_end("answer_from_memory", trace=[mem]), ctx))
    assert json.loads(out[0]["data"])["display_name"] == "Answer from Saved Plan"
    patch = _trace("merge_patch", "card_edit", "ok", "edited")
    assert _as_list(_lg_event_to_sse(_node_end("merge_patch", profile=PROFILE, trace=[patch]), ctx))


def test_the_final_graph_event_does_not_replay_the_trace():
    ctx = TraceContext()
    t = _trace("gather_data", "location", "ok", "x")
    assert _lg_event_to_sse(_node_end("LangGraph", trace=[t]), ctx) is None


def test_planning_started_sets_the_flag_and_reply_turns_stay_message_only():
    ctx = TraceContext()
    assert not ctx.tools_started
    _lg_event_to_sse(_node_end("extract_profile", trace=[_trace("plan", "started", "ok", "go")]), ctx)
    assert ctx.tools_started
    out = _as_list(_lg_event_to_sse(
        _node_end("respond", plan_result=None, reply={"text": "hi", "language": "en", "provider": "template"}), ctx))
    assert [e["event"] for e in out] == ["message"]


def test_api_level_item_is_stamped_with_the_same_run():
    ctx = TraceContext(run_id="r")
    ev = ctx.api_trace("persist", "saved", "ok", "Plan saved to this conversation")
    d = json.loads(ev["data"])
    assert (d["display_name"], d["run_id"], d["sequence"]) == ("Plan Saved", "r", 1)


# ── gather_data honesty ───────────────────────────────────────────────────────

def _patch_tools(monkeypatch, *, weather=None, soil=None, scenarios=None, water=None):
    async def get_location(_text):
        return LOCATION

    async def get_weather(_loc):
        if isinstance(weather, Exception):
            raise weather
        return {} if weather is None else weather

    async def get_soil(_p, _loc):
        if isinstance(soil, Exception):
            raise soil
        return {"n": None} if soil is None else soil

    def build_scenarios(_loc, _season):
        if isinstance(scenarios, Exception):
            raise scenarios
        return [] if scenarios is None else scenarios

    async def get_water_budget(*_a):
        if isinstance(water, Exception):
            raise water
        return [] if water is None else water

    for name, fn in (("get_location", get_location), ("get_weather", get_weather), ("get_soil", get_soil),
                     ("build_scenarios", build_scenarios), ("get_water_budget", get_water_budget)):
        monkeypatch.setattr(tools, name, fn)


def _gather(monkeypatch, **kw):
    _patch_tools(monkeypatch, **kw)
    monkeypatch.setattr(nodes, "_build_fallback_season", lambda: object())
    out = asyncio.run(gather_data_node({"profile": PROFILE, "trace": []}))
    return {f"{t.step}": t for t in out["trace"]}, out


def test_gather_data_does_not_claim_success_when_steps_failed(monkeypatch):
    steps, out = _gather(monkeypatch, weather={}, soil={}, scenarios=[])
    assert steps["weather"].status == "skipped"
    assert steps["scenarios"].status == "failed"
    assert steps["water"].status == "skipped"
    assert steps["complete"].status == "failed"
    assert "All data gathered" not in steps["complete"].summary
    assert "scenarios" in steps["complete"].summary and "water" in steps["complete"].summary
    assert out["scenarios"] == [] and out["water"] == []


def test_gather_data_failed_weather_is_marked_failed_but_not_critical(monkeypatch):
    scn = [object()]
    steps, _ = _gather(monkeypatch, weather=RuntimeError("down"), soil={"n": 1}, scenarios=scn, water=[object()])
    assert steps["weather"].status == "failed"
    assert steps["complete"].status == "ok" and "weather" in steps["complete"].summary
    assert "All data" not in steps["complete"].summary


def test_exception_text_never_reaches_the_trace(monkeypatch):
    boom = RuntimeError("Traceback secret-token-9 https://api.example.com/?key=abc")
    steps, _ = _gather(monkeypatch, weather=boom, soil=boom, scenarios=boom)
    for t in steps.values():
        assert "secret-token" not in t.summary and "Traceback" not in t.summary and "key=" not in t.summary


def test_no_trace_item_is_left_in_the_running_state(monkeypatch):
    import app.agent.client as client_mod

    class BadJson:
        async def chat(self, **_k):
            return {}

        def extract_text(self, _r):
            return '{"text": "Profit will be Rs 999999999."}'

    monkeypatch.setattr(client_mod, "get_sarvam_client", lambda: BadJson())
    state = {"language": "en", "strategies": [], "profile": PROFILE, "crops": [], "trace": []}
    explained = asyncio.run(nodes.explain_node(state))
    reviewed = nodes.grounding_check_node({**state, **explained})
    for t in explained["trace"] + reviewed["trace"]:
        assert t.status != "running"
