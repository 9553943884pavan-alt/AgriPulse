"""Borewell question, real data_status, Sarvam client fallback, health, speech, breakers."""

from __future__ import annotations

import httpx
import pytest

from app.agent import client as client_mod
from app.agent import nodes
from app.schemas import FarmProfile
from app.services import prices, water
from app.services.data_status import count_data_status


def _profile(**kw) -> FarmProfile:
    base = dict(location_text="Nashik", land_acres=5, budget_rs=80000, water_source="borewell")
    base.update(kw)
    return FarmProfile(**base)


# ── Borewell answer parsing ──────────────────────────────────────────────────

def test_parse_borewell_answer_english_numbers():
    r = nodes.parse_borewell_answer("about 6,000 litres per hour and 6 hours a day")
    assert r["values"] == {"borewell_yield_lph": 6000.0, "pump_hours_per_day": 6.0}
    assert r["dont_know"] is False


def test_parse_borewell_answer_marathi_digits():
    r = nodes.parse_borewell_answer("५००० लिटर आणि ४ तास")
    assert r["values"]["borewell_yield_lph"] == 5000.0
    assert r["values"]["pump_hours_per_day"] == 4.0


@pytest.mark.parametrize("text", ["I don't know", "माहीत नाही", "पता नहीं"])
def test_parse_borewell_answer_dont_know(text):
    r = nodes.parse_borewell_answer(text)
    assert r["dont_know"] is True and r["values"] == {}


# ── Agent asks ONCE ──────────────────────────────────────────────────────────

async def test_borewell_question_asked_once(monkeypatch):
    async def fake_llm(state, language, message):
        return {"location_text": "Nashik", "land_acres": 5, "budget_rs": 80000, "water_source": "borewell"}

    monkeypatch.setattr(nodes, "_llm_extract", fake_llm)
    out = await nodes.extract_profile_node({"message": "x", "language": "mr", "trace": []})
    assert out["optional_ask"] == "borewell_capacity" and not out["missing"]

    q = nodes.ask_missing_node({"missing": [], "optional_ask": "borewell_capacity", "language": "mr", "trace": []})
    assert q["question"]["field"] == "borewell_capacity"
    assert "बोअरवेल" in q["question"]["text"]
    assert q["pending_field"] == "borewell_capacity" and q["asked_fields"] == ["borewell_capacity"]

    # Already asked: no second question even though the data is still missing.
    out2 = await nodes.extract_profile_node({
        "message": "ok", "language": "mr", "trace": [], "asked_fields": ["borewell_capacity"],
        "profile": out["profile"],
    })
    assert out2["optional_ask"] is None


async def test_dont_know_answer_skips_llm_and_proceeds(monkeypatch):
    async def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("LLM must not be called for a rule-readable answer")

    monkeypatch.setattr(nodes, "_llm_extract", boom)
    out = await nodes.extract_profile_node({
        "message": "I don't know", "language": "en", "trace": [],
        "pending_field": "borewell_capacity", "asked_fields": ["borewell_capacity"],
        "profile": _profile(),
    })
    assert out["optional_ask"] is None and out["missing"] == []
    assert out["profile"].borewell_yield_lph is None


async def test_numeric_answer_fills_profile_and_assumes_one_borewell(monkeypatch):
    async def boom(*a, **k):  # pragma: no cover
        raise AssertionError("no LLM expected")

    monkeypatch.setattr(nodes, "_llm_extract", boom)
    out = await nodes.extract_profile_node({
        "message": "6000 litres, 5 hours", "language": "en", "trace": [],
        "pending_field": "borewell_capacity", "profile": _profile(),
    })
    p = out["profile"]
    assert (p.borewell_yield_lph, p.pump_hours_per_day, p.borewell_count) == (6000.0, 5.0, 1)
    assert any(d.field == "borewell_count" for d in p.defaults_used)


def test_borewell_disclosure_matches_run_plan_rule():
    p, warns = water.borewell_disclosure(_profile())
    assert [w.code for w in warns] == ["ASSUMED_BOREWELL"]
    assert any(d.field == "borewell_capacity" for d in p.defaults_used)
    full = _profile(borewell_count=1, borewell_yield_lph=5000, pump_hours_per_day=5)
    assert water.borewell_disclosure(full)[1] == []


# ── data_status ──────────────────────────────────────────────────────────────

def _sv(value, status, source="s"):
    return {"value": value, "unit": "x", "source": source, "as_of": "2026", "status": status}


def test_count_data_status_counts_distinct_real_statuses():
    plan = {
        "a": _sv(1, "live"),
        "b": [_sv(2, "cached"), _sv(2, "cached"), _sv(3, "cached")],   # duplicate counted once
        "c": {"d": _sv(4, "official_dataset"), "e": _sv(5, "computed"), "f": _sv(6, "assumption")},
    }
    ds = count_data_status(plan)
    assert (ds.live, ds.cached, ds.official_dataset) == (1, 2, 1)


# ── Sarvam client: empty content => next model ───────────────────────────────

class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _ok(text):
    return _Resp(200, {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]})


async def test_client_skips_empty_content_and_disables_thinking(monkeypatch):
    monkeypatch.setattr(client_mod.settings, "SARVAM_API_KEY", "k")
    monkeypatch.setattr(client_mod.settings, "SARVAM_CHAT_MODEL", "m1")
    monkeypatch.setattr(client_mod.settings, "SARVAM_FALLBACK_MODELS", "m2")
    seen = []

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            seen.append(json)
            if json["model"] == "m1":
                return _Resp(200, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
            return _ok('{"text": "hello"}')

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeClient)
    resp = await client_mod.SarvamClient().chat([{"role": "user", "content": "hi"}])
    assert resp["choices"][0]["message"]["content"] == '{"text": "hello"}'
    assert [p["model"] for p in seen] == ["m1", "m2"]
    assert all(p["chat_template_kwargs"] == {"enable_thinking": False} for p in seen)
    assert all("reasoning_effort" not in p for p in seen)


async def test_client_raises_when_all_models_empty(monkeypatch):
    monkeypatch.setattr(client_mod.settings, "SARVAM_API_KEY", "k")
    monkeypatch.setattr(client_mod.settings, "SARVAM_CHAT_MODEL", "m1")
    monkeypatch.setattr(client_mod.settings, "SARVAM_FALLBACK_MODELS", "")

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            return _ok("")

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeClient)
    with pytest.raises(client_mod.SarvamAllModelsFailed):
        await client_mod.SarvamClient().chat([{"role": "user", "content": "hi"}])


async def test_client_retries_without_extras_on_400(monkeypatch):
    monkeypatch.setattr(client_mod.settings, "SARVAM_API_KEY", "k")
    monkeypatch.setattr(client_mod.settings, "SARVAM_CHAT_MODEL", "m1")
    monkeypatch.setattr(client_mod.settings, "SARVAM_FALLBACK_MODELS", "")
    seen = []

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            seen.append(json)
            return _Resp(400, {}) if "chat_template_kwargs" in json else _ok("fine")

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeClient)
    await client_mod.SarvamClient().chat([{"role": "user", "content": "hi"}])
    assert len(seen) == 2 and "chat_template_kwargs" not in seen[1]


# ── Agmarknet circuit breaker ────────────────────────────────────────────────

async def test_agmarknet_breaker_skips_live_after_failure(monkeypatch):
    monkeypatch.setattr(prices.settings, "DATA_GOV_IN_API_KEY", "k")
    prices.reset_agmarknet_breaker()
    calls = []

    async def failing_fetch(*a, **k):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(prices, "fetch", failing_fetch)
    assert await prices._fetch_agmarknet("Wheat", "Pune", "Maharashtra") is None
    assert await prices._fetch_agmarknet("Wheat", "Pune", "Maharashtra") is None
    assert len(calls) == 1          # second call short-circuited
    prices.reset_agmarknet_breaker()


# ── Source health ────────────────────────────────────────────────────────────

async def test_health_names_missing_key_and_http_status(monkeypatch):
    from app.api import sources

    monkeypatch.setattr(sources, "_health_cache", {})
    monkeypatch.setattr(sources, "_health_cache_time", 0.0)
    monkeypatch.setattr("app.config.settings.DATA_GOV_IN_API_KEY", "")

    async def fake_fetch(url, **k):
        req = httpx.Request("GET", url)
        if "isric" in url:
            raise httpx.HTTPStatusError("503", request=req, response=httpx.Response(503, request=req))
        return httpx.Response(200, request=req)

    monkeypatch.setattr(sources, "fetch", fake_fetch)
    out = {s["id"]: s for s in (await sources.sources_health())["sources"]}
    assert out["agmarknet"]["status"] == "red" and "DATA_GOV_IN_API_KEY" in out["agmarknet"]["note"]
    assert out["soilgrids"]["status"] == "red" and "503" in out["soilgrids"]["note"]
    assert out["open_meteo_forecast"]["status"] == "green"
    # ids must match /api/sources ids so the Sources page can join them
    source_ids = {s["id"] for s in sources._SOURCES}
    assert set(out) <= source_ids


# ── Speech ───────────────────────────────────────────────────────────────────

def test_stt_filename_has_extension_sarvam_needs():
    from app.services.speech import _stt_filename

    assert _stt_filename("audio/wav") == "audio.wav"
    assert _stt_filename("audio/webm;codecs=opus") == "audio.webm"
    assert _stt_filename("audio/mp4") == "audio.mp4"
    assert _stt_filename("audio/aac") == "audio.aac"




# ── Grounding / explain prompt ───────────────────────────────────────────────

def test_grounding_accepts_loss_written_without_minus_sign():
    from app.agent.grounding import grounding_check

    assert grounding_check("Expected loss of Rs 3,380", {"profit": -3380})
    assert not grounding_check("Expected profit of Rs 9,999", {"profit": -3380})


def test_explain_prompt_has_no_example_numbers_and_long_crop_facts():
    from types import SimpleNamespace as NS

    from app.agent.prompts import EXPLAIN_SYSTEM, build_explain_user_prompt

    assert "8.3" not in EXPLAIN_SYSTEM["en"]
    alloc = NS(crop_id="sugarcane", acres=2.0, profit_rs={"normal": 100000})
    strat = NS(expected_profit_rs=100000, worst_case_profit_rs=50000, allocations=[alloc])
    prompt = build_explain_user_prompt(strat, 10.0, [], "en", [NS(crop_id="sugarcane", duration_days=360)])
    assert "occupies_land_months: 12" in prompt and "profit_per_acre_per_year_rs: 50694" in prompt


# ── Devanagari place names ───────────────────────────────────────────────────

async def test_devanagari_place_is_geocoded_via_marathi_then_english(monkeypatch):
    from app.services import location as loc

    calls = []

    async def fake_fetch(url, params=None, **k):
        calls.append((url, params))
        req = httpx.Request("GET", url)
        if url == loc._GEOCODING_URL:
            body = {"results": [{"id": 1, "name": "नाशिक", "country_code": "IN"}]}
        else:
            body = {"id": 1, "name": "Nashik", "latitude": 19.99, "longitude": 73.79,
                    "country_code": "IN", "admin1": "Maharashtra", "admin2": "Nashik"}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(loc, "fetch", fake_fetch)
    results = await loc._geocode("नाशिक", 5)
    assert calls[0][1]["language"] == "mr" and calls[1][1]["language"] == "en"
    picked = loc._pick_maharashtra(results, "नाशिक")
    assert picked is not None and picked.district == "Nashik"
