"""Phase 1: small talk, planning intent, saved-profile reuse, budget follow-ups, loop guards.

Unit level: no network, no LLM (the Sarvam client is replaced where a node would call it).
"""

import asyncio
import json

import pytest

from app.agent import nodes
from app.agent.nodes import (
    answer_from_memory_node,
    explain_node,
    extract_profile_node,
    grounding_check_node,
    is_planning_intent,
    respond_node,
    route_node,
    smalltalk_kind,
    smalltalk_node,
)
from app.schemas import FarmProfile

COMPLETE = FarmProfile(location_text="Nashik, Maharashtra", land_acres=2, budget_rs=200000)
PLACEHOLDER = FarmProfile(location_text="unknown", land_acres=0, budget_rs=0, missing=["location_text"])


def _boom(*_a, **_k):
    raise AssertionError("small talk must not call a tool or the LLM")


# ── small talk ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Hi", "greeting"), ("hello!", "greeting"), ("Hey there", "greeting"), ("नमस्कार", "greeting"),
        ("thanks", "thanks"), ("Thank you so much", "thanks"), ("धन्यवाद", "thanks"),
        ("help", "help"), ("who are you", "help"), ("What can you do?", "help"),
        ("Namaskara", "kannada_greeting"), ("namaskaara!", "kannada_greeting"), ("ನಮಸ್ಕಾರ", "kannada_greeting"),
        ("ನನಗೆ ಬೆಳೆ ಯೋಜನೆ ಬೇಕು", "kannada"),
        ("hi, plan my farm", None), ("help me plan my crops", None), ("Why onion?", None),
        ("What if I have only 50000?", None),
    ],
)
def test_smalltalk_kind(text, kind):
    assert smalltalk_kind(text) == kind


@pytest.mark.parametrize("state", [
    {},
    {"strategies": [object()], "profile": COMPLETE},
    {"profile": COMPLETE},
])
def test_greeting_routes_to_smalltalk_with_or_without_plan(state):
    assert route_node({**state, "message": "Hi"})["route"] == "smalltalk"


def test_fresh_hi_is_a_fixed_greeting_with_no_remembered_data():
    out = smalltalk_node({"message": "Hi", "language": "en"})
    assert out["explanation_text"] == "Hello! 👋 How can I help you with your farming plan today?"
    assert out["route"] == "question_answered"
    assert out["trace"] == []                       # no tool step, nothing invented


def test_placeholder_profile_is_never_reported_as_remembered():
    text = smalltalk_node({"message": "Hi", "language": "en", "profile": PLACEHOLDER})["explanation_text"]
    assert "unknown" not in text and "saved" not in text


def test_greeting_mentions_saved_profile_accurately():
    text = smalltalk_node({"message": "Hi", "language": "en", "profile": COMPLETE})["explanation_text"]
    assert "Nashik, Maharashtra" in text and "2 acres" in text and "₹200,000" in text and "make a plan" in text


@pytest.mark.parametrize("language", ["mr", "hi", "en"])
@pytest.mark.parametrize("message", ["Hi", "thanks", "help"])
def test_smalltalk_is_deterministic_in_each_language(language, message):
    a = smalltalk_node({"message": message, "language": language})
    b = smalltalk_node({"message": message, "language": language})
    assert a["explanation_text"] == b["explanation_text"] and a["explanation_text"]


def test_kannada_gets_greeting_and_honest_note_without_tools():
    greet = smalltalk_node({"message": "Namaskara", "language": "en"})["explanation_text"]
    assert greet.startswith("ನಮಸ್ಕಾರ") and "English, Marathi and Hindi" in greet
    note = smalltalk_node({"message": "ನನಗೆ ಸಹಾಯ ಬೇಕು", "language": "en"})["explanation_text"]
    assert not note.startswith("ನಮಸ್ಕಾರ") and "English, Marathi and Hindi" in note
    assert route_node({"message": "ನನಗೆ ಸಹಾಯ ಬೇಕು"})["route"] == "smalltalk"


def test_kannada_is_not_added_to_the_language_literal():
    from typing import get_args

    from app.schemas import Language

    assert set(get_args(Language)) == {"mr", "hi", "en"}


def test_respond_after_smalltalk_is_message_only():
    out = respond_node({"route": "question_answered", "explanation_text": "Hello!", "language": "en",
                        "explanation_provider": "template"})
    assert out == {"reply": {"text": "Hello!", "language": "en", "provider": "template"}}
    assert "plan_result" not in out


def test_smalltalk_graph_path_runs_no_tool(monkeypatch):
    from app.agent import tools
    from app.agent.graph import build_graph
    from app.api.agent import _lg_event_to_sse

    for name in ("get_location", "get_weather", "get_soil", "get_water_budget"):
        monkeypatch.setattr(tools, name, _boom)
    monkeypatch.setattr(nodes, "_llm_extract", _boom)
    graph = build_graph().compile()

    async def run():
        seen = []
        async for ev in graph.astream_events({"message": "Hi", "language": "en", "trace": []}, version="v1"):
            out = _lg_event_to_sse(ev)
            if out:
                seen.extend(out if isinstance(out, list) else [out])
        return seen

    seen = asyncio.run(run())
    assert [e["event"] for e in seen] == ["message"]
    assert "Hello" in json.loads(seen[0]["data"])["text"]


# ── planning intent ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "I want to prepare a profitable crop plan for my farm", "recommend crops", "What should I grow?",
    "optimise my farm", "आराखडा तयार करा", "पीक सुचवा", "फसल योजना बनाओ", "कौन सी फसल लगाऊं",
])
def test_planning_intent_detected(text):
    assert is_planning_intent(text)


@pytest.mark.parametrize("text", ["Why onion?", "Why did you choose onion in the plan?", "Hello", "What is my budget?"])
def test_questions_are_not_planning_intent(text):
    assert not is_planning_intent(text)


def test_planning_request_with_saved_profile_skips_extraction_and_questions(monkeypatch):
    out = route_node({"message": "I want a profitable crop plan", "profile": COMPLETE})
    assert out == {"route": "new_plan", "plan_only": True}

    monkeypatch.setattr(nodes, "_llm_extract", _boom)
    result = asyncio.run(extract_profile_node({
        "message": "I want a profitable crop plan", "language": "en", "profile": COMPLETE, "plan_only": True,
    }))
    assert result["missing"] == [] and result["optional_ask"] is None
    first = result["trace"][0]
    assert (first.node, first.step) == ("plan", "started")      # first item says planning started
    assert result["profile"].budget_rs == 200000


def test_planning_request_asks_only_what_is_missing(monkeypatch):
    monkeypatch.setattr(nodes, "_llm_extract", _boom)
    partial = FarmProfile(location_text="Beed", land_acres=4, budget_rs=0, missing=["budget_rs"])
    result = asyncio.run(extract_profile_node({
        "message": "make a plan", "language": "en", "profile": partial, "plan_only": True,
    }))
    assert result["missing"] == ["budget_rs"]
    assert [t.node for t in result["trace"]] == ["extract_profile"]   # no "planning started": no tool will run


def test_planning_request_with_a_new_fact_still_extracts():
    assert route_node({"message": "plan for 3 acres", "profile": COMPLETE})["plan_only"] is False


# ── budget follow-up ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "What if I have only ₹50,000?", "just Rs 50000 now", "only 50,000 rupees", "budget is 50 हजार रुपये",
])
def test_budget_followup_replans_with_the_new_budget_even_if_llm_misses_it(monkeypatch, text):
    async def llm_misses_it(*_a, **_k):
        return {}

    monkeypatch.setattr(nodes, "_llm_extract", llm_misses_it)
    state = {"message": text, "language": "en", "profile": COMPLETE, "strategies": [object()]}
    assert route_node(state)["route"] == "follow_up"
    result = asyncio.run(extract_profile_node(state))
    assert result["profile"].budget_rs == 50000
    assert result["profile"].land_acres == 2 and result["profile"].location_text == "Nashik, Maharashtra"
    assert result["trace"][0].step == "started"


def test_rule_budget_beats_a_wrong_llm_budget(monkeypatch):
    async def llm_wrong(*_a, **_k):
        return {"budget_rs": 5}

    monkeypatch.setattr(nodes, "_llm_extract", llm_wrong)
    result = asyncio.run(extract_profile_node(
        {"message": "What if I have only ₹50,000?", "language": "en", "profile": COMPLETE}))
    assert result["profile"].budget_rs == 50000


def test_price_statement_is_not_read_as_a_budget():
    assert nodes._explicit_budget("onion sells at Rs 2000 per quintal") is None
    assert nodes._explicit_budget("I have 2 acres") is None


# ── plan Q&A guards ───────────────────────────────────────────────────────────

class _Client:
    def __init__(self, raw):
        self.raw = raw

    async def chat(self, **_k):
        return {}

    def extract_text(self, _resp):
        return self.raw


def test_non_dict_llm_json_in_plan_qa_falls_back_to_the_summary(monkeypatch):
    import app.agent.client as client_mod

    monkeypatch.setattr(client_mod, "get_sarvam_client", lambda: _Client("[1, 2, 3]"))
    out = asyncio.run(answer_from_memory_node({
        "profile": COMPLETE, "strategies": [], "message": "Why onion?", "language": "en", "route": "question",
    }))
    assert out["route"] == "question_answered" and out["explanation_text"]


# ── explain / grounding loop guard ────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["[1]", '{"text": 5}', '{"text": ""}', "not json", ""])
def test_explain_falls_back_to_template_on_bad_llm_output_and_cannot_loop(monkeypatch, raw):
    import app.agent.client as client_mod
    from app.agent.graph import _after_grounding_check

    monkeypatch.setattr(client_mod, "get_sarvam_client", lambda: _Client(raw))
    state = {"language": "en", "strategies": [], "profile": COMPLETE, "crops": [], "trace": []}
    out = asyncio.run(explain_node(state))
    assert out["explanation_provider"] == "template"
    assert out["grounding_retry_count"] >= 2                       # a failing template can never loop
    step = out["trace"][-1]
    assert step.status == "failed" and step.fallback_used == "template"
    after = grounding_check_node({**state, **out})
    assert after["explanation_grounded"] is True                    # deterministic template counts as grounded
    assert _after_grounding_check({**state, **out, **after}) == "respond"


def test_llm_exception_is_not_echoed_into_the_trace(monkeypatch):
    import app.agent.client as client_mod

    class Boom:
        async def chat(self, **_k):
            raise RuntimeError("secret-key-123 https://provider.example/v1")

    monkeypatch.setattr(client_mod, "get_sarvam_client", lambda: Boom())
    out = asyncio.run(explain_node({"language": "en", "strategies": [], "profile": COMPLETE, "crops": [], "trace": []}))
    assert "secret-key-123" not in out["trace"][-1].summary


def test_recursion_limit_is_set_for_the_graph():
    from app.api import agent

    assert 10 <= agent.RECURSION_LIMIT <= 100
