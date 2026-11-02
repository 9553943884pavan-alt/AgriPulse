"""Follow-up turns after a plan exists must not all get the same canned reply."""

import asyncio

import pytest

from app.agent.nodes import answer_from_memory_node, route_node
from app.schemas import FarmProfile
from app.services.water import _borewell_capacity

PROFILE = FarmProfile(location_text="Nashik, Maharashtra", land_acres=2, budget_rs=200000)
WITH_PLAN = {"strategies": [object()], "profile": PROFILE}


@pytest.mark.parametrize(
    ("message", "route"),
    [
        ("Hello", "smalltalk"),  # small talk never reaches plan Q&A or extraction
        ("Why did you choose onion?", "question"),
        ("What is my budget?", "question"),
        ("I am from Pune, Maharashtra", "follow_up"),   # new location -> re-plan
        ("Pune", "follow_up"),
        ("Now I have canal water instead", "follow_up"),  # water change -> re-plan
        ("change budget to 3 lakh", "follow_up"),
        ("माझे शेत सातारा येथे आहे", "follow_up"),
    ],
)
def test_route_after_plan(message, route):
    assert route_node({**WITH_PLAN, "message": message})["route"] == route


def _answer(message: str) -> dict:
    state = {"profile": PROFILE, "strategies": [], "message": message, "language": "en", "route": "question"}
    return asyncio.run(answer_from_memory_node(state))


def test_greeting_and_profile_recall_get_different_answers():
    greeting = _answer("Hello")["explanation_text"]
    recall = _answer("What is my budget?")["explanation_text"]
    assert greeting.startswith("Hello!")
    assert "200,000" in recall
    assert greeting != recall


def test_canal_only_profile_gets_no_groundwater_from_leftover_borewell_numbers():
    canal = FarmProfile(
        location_text="Nashik", land_acres=2, budget_rs=200000, water_source="canal",
        canal_access=True, borewell_count=1, borewell_yield_lph=8000, pump_hours_per_day=6,
    )
    assert _borewell_capacity(canal) == 0.0
    assert _borewell_capacity(canal.model_copy(update={"water_source": "both"})) > 0
