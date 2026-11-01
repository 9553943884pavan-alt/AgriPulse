import asyncio
import json
from types import SimpleNamespace

from fastapi import Request

from app.api import agent


def test_respond_event_emits_plan_and_explanation_message():
    plan_result = SimpleNamespace(
        model_dump_json=lambda: '{"explanation":{"text":"A grounded plan.","language":"en","provider":"template"}}',
        model_dump=lambda mode: {
            "explanation": {
                "text": "A grounded plan.",
                "language": "en",
                "provider": "template",
            },
        },
    )

    events = agent._lg_event_to_sse({
        "event": "on_chain_end",
        "name": "respond",
        "data": {"output": {"plan_result": plan_result}},
    })

    assert isinstance(events, list)
    assert [event["event"] for event in events] == ["plan", "message"]
    assert json.loads(events[1]["data"]) == {
        "text": "A grounded plan.",
        "language": "en",
        "provider": "template",
    }


def test_fallback_stream_always_emits_done(monkeypatch):
    async def stub_stream(_state, _language):
        yield {"event": "message", "data": '{"text":"Fallback"}'}

    monkeypatch.setattr(agent, "_stub_stream", stub_stream)

    class _NoCache:
        async def get_memory(self, *_a, **_k):
            return None

        async def set_memory(self, *_a, **_k):
            return None

        async def set_plan(self, *_a, **_k):
            return None

    async def _fake_get_cache():
        return _NoCache()

    monkeypatch.setattr("app.core.cache.get_cache", _fake_get_cache)
    app = SimpleNamespace(state=SimpleNamespace(agent_graph=None))
    request = Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/agent/chat",
        "raw_path": b"/api/agent/chat",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "app": app,
    })

    async def collect():
        response = await agent.agent_chat(request, {"message": "hello", "language": "en"})
        parts = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, dict):
                parts.append(('event: %s' % chunk['event']).encode() + bytes([10]) + ('data: %s' % chunk['data']).encode() + bytes([10,10]))
            elif isinstance(chunk, str):
                parts.append(chunk.encode())
            else:
                parts.append(chunk)
        return b"".join(parts)

    body = asyncio.run(collect())

    assert b"event: message" in body
    assert b"event: done" in body
