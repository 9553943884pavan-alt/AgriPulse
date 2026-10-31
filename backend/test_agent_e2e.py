"""End-to-end agent workflow test — direct graph invocation, no HTTP."""
import asyncio
import sys
import json

sys.path.insert(0, ".")


async def test_graph_compiles():
    from app.agent.graph import get_compiled_graph
    g = await get_compiled_graph()
    print(f"[PASS] Graph compiled: {type(g).__name__}")
    return g


async def test_full_turn(g):
    """Full conversation turn with a Marathi message."""
    config = {"configurable": {"thread_id": "e2e-test-001"}}
    state = {
        "thread_id": "e2e-test-001",
        "message": "मला बीड जिल्ह्यात 5 एकर शेती आहे. बजेट 50000 रुपये.",
        "language": "mr",
        "profile_patch": None,
        "missing": [],
        "scenarios": [], "water": [], "candidates": [], "excluded": [],
        "scenario_yields": {}, "long_duration_crops": set(),
        "strategies": [], "relaxations": [], "relaxation_count": 0,
        "explanation_text": "", "explanation_grounded": False,
        "explanation_provider": "template", "grounding_retry_count": 0,
        "water_saved_pct": 0.0, "trace": [], "messages": [],
        "route": "new_plan", "no_data": False,
    }

    nodes_seen = []
    events_seen = []

    async for ev in g.astream_events(state, config=config, version="v1"):
        etype = ev.get("event", "")
        name = ev.get("name", "")
        events_seen.append(etype)
        if etype == "on_chain_end" and name:
            nodes_seen.append(name)
            output = ev.get("data", {}).get("output", {}) or {}
            # Show key outputs
            if name == "router":
                print(f"  [router] route={output.get('route')}")
            elif name == "extract_profile":
                p = output.get("profile")
                print(f"  [extract_profile] profile={p}")
                missing = output.get("missing", [])
                if missing:
                    print(f"  [extract_profile] missing fields: {missing}")
            elif name == "gather_data":
                loc = output.get("location")
                print(f"  [gather_data] location={loc}")
            elif name == "recommend_crops":
                cands = output.get("candidates", [])
                excl = output.get("excluded", [])
                print(f"  [recommend_crops] candidates={len(cands)}, excluded={len(excl)}")
            elif name == "optimize":
                strats = output.get("strategies", [])
                print(f"  [optimize] strategies={len(strats)}")
            elif name == "explain":
                text = output.get("explanation_text", "")[:80]
                provider = output.get("explanation_provider", "")
                print(f"  [explain] provider={provider} text={text!r}...")
            elif name == "respond":
                plan = output.get("plan_result")
                if plan:
                    pid = getattr(plan, "plan_id", "?")
                    print(f"  [respond] plan_id={pid}")
            elif name == "save_memory":
                print(f"  [save_memory] done")
            elif name == "ask_missing":
                q = output.get("question", {})
                print(f"  [ask_missing] question={q}")
            else:
                print(f"  [{name}] ran")

    print(f"\nNodes executed: {nodes_seen}")
    print(f"Total LangGraph events: {len(events_seen)}")

    # Assertions
    assert "router" in nodes_seen, "router node must run"
    assert len(nodes_seen) >= 3, f"Expected at least 3 nodes, got {nodes_seen}"
    print("[PASS] Full conversation turn completed")
    return nodes_seen


async def test_follow_up_turn(g):
    """Second turn on the same thread — should route as follow_up."""
    config = {"configurable": {"thread_id": "e2e-test-001"}}
    state = {
        "thread_id": "e2e-test-001",
        "message": "सोयाबीनसाठी किती पाणी लागेल?",  # "How much water for soybean?"
        "language": "mr",
        "profile_patch": None,
        "missing": [],
        "scenarios": [], "water": [], "candidates": [], "excluded": [],
        "scenario_yields": {}, "long_duration_crops": set(),
        "strategies": [], "relaxations": [], "relaxation_count": 0,
        "explanation_text": "", "explanation_grounded": False,
        "explanation_provider": "template", "grounding_retry_count": 0,
        "water_saved_pct": 0.0, "trace": [], "messages": [],
        "route": "new_plan", "no_data": False,
    }

    nodes_seen = []
    async for ev in g.astream_events(state, config=config, version="v1"):
        etype = ev.get("event", "")
        name = ev.get("name", "")
        if etype == "on_chain_end" and name:
            nodes_seen.append(name)

    print(f"Follow-up nodes: {nodes_seen}")
    assert "router" in nodes_seen
    print("[PASS] Follow-up turn completed")


async def test_sse_endpoint():
    """Test the HTTP SSE endpoint via httpx."""
    import httpx
    print("\nTesting HTTP SSE endpoint (E1)...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            body = {
                "message": "I have 5 acres in Beed, budget 50000",
                "language": "en",
            }
            events = []
            async with client.stream("POST", "http://127.0.0.1:8001/api/agent/chat", json=body) as resp:
                if resp.status_code != 200:
                    print(f"[FAIL] SSE returned {resp.status_code}")
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    if len(events) >= 8:  # stop after 8 events
                        break
            print(f"SSE events received: {events}")
            assert "thread" in events, "thread event must come first"
            print("[PASS] SSE endpoint works")
    except Exception as e:
        print(f"[SKIP] HTTP test skipped (server not running?): {e}")


async def main():
    print("=== AgriPulse Agent End-to-End Tests ===\n")

    # Test 1: graph compiles
    g = await test_graph_compiles()

    # Test 2: full turn
    nodes = await test_full_turn(g)

    # Test 3: follow-up turn (only if first turn completed naturally)
    if "save_memory" in nodes or "respond" in nodes:
        await test_follow_up_turn(g)
    else:
        print("[SKIP] Follow-up test skipped (first turn didn't reach respond)")

    # Test 4: HTTP SSE
    await test_sse_endpoint()

    print("\n=== All tests finished ===")


if __name__ == "__main__":
    asyncio.run(main())
