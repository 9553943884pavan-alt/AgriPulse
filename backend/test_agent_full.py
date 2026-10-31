"""Full agent + HTTP test — spins up an in-process ASGI server via httpx."""
import asyncio
import json
import sys

sys.path.insert(0, ".")


# ── Test 1: Graph compiles ────────────────────────────────────────────────────

async def test_graph_compiles():
    from app.agent.graph import get_compiled_graph
    g = await get_compiled_graph()
    print(f"[PASS] graph compiled: {type(g).__name__}")
    return g


# ── Test 2: Full turn — new_plan path ─────────────────────────────────────────

async def test_new_plan_turn(g):
    """Route: new_plan → extract_profile → (ask_missing or gather_data →…→ respond)."""
    config = {"configurable": {"thread_id": "full-test-001"}}
    state = {
        "thread_id": "full-test-001",
        "message": "Beed district, 5 acres, budget 50000 rupees, borewell",
        "language": "en",
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
    final_state = {}

    async for ev in g.astream_events(state, config=config, version="v1"):
        etype = ev.get("event", "")
        name = ev.get("name", "")
        if etype == "on_chain_end" and name and not name.startswith("_") and name != "LangGraph":
            nodes_seen.append(name)
            output = ev.get("data", {}).get("output") or {}
            if isinstance(output, dict):
                final_state.update(output)
            route = output.get("route") if isinstance(output, dict) else None
            profile = output.get("profile") if isinstance(output, dict) else None
            missing = output.get("missing") if isinstance(output, dict) else None

            if route:
                print(f"  [{name}] route={route}")
            elif profile and name == "extract_profile":
                loc = getattr(profile, "location_text", "?")
                acres = getattr(profile, "land_acres", "?")
                budget = getattr(profile, "budget_rs", "?")
                ws = getattr(profile, "water_source", "?")
                print(f"  [extract_profile] location={loc!r} acres={acres} budget={budget} water={ws} missing={missing}")
            elif name == "gather_data":
                loc = output.get("location") if isinstance(output, dict) else None
                print(f"  [gather_data] location={loc}")
            elif name == "recommend_crops":
                cands = len(output.get("candidates", [])) if isinstance(output, dict) else 0
                print(f"  [recommend_crops] candidates={cands}")
            elif name == "optimize":
                strats = len(output.get("strategies", [])) if isinstance(output, dict) else 0
                print(f"  [optimize] strategies={strats}")
            elif name == "explain":
                text = (output.get("explanation_text", "") or "")[:60] if isinstance(output, dict) else ""
                prov = output.get("explanation_provider", "") if isinstance(output, dict) else ""
                print(f"  [explain] provider={prov!r} text={text!r}...")
            elif name == "respond":
                plan = output.get("plan_result") if isinstance(output, dict) else None
                if plan:
                    pid = getattr(plan, "plan_id", "?")
                    ver = getattr(plan, "version", "?")
                    expl = getattr(plan, "explanation", None)
                    expl_text = (getattr(expl, "text", "") or "")[:60] if expl else ""
                    print(f"  [respond] plan_id={pid} version={ver} explanation={expl_text!r}...")
                else:
                    ans = output.get("answer") if isinstance(output, dict) else None
                    print(f"  [respond] answer={str(ans)[:60]!r}")
            elif name == "ask_missing":
                q = output.get("question") if isinstance(output, dict) else None
                print(f"  [ask_missing] question={q}")
            elif name == "save_memory":
                print(f"  [save_memory] done")
            else:
                print(f"  [{name}]")

    print(f"\n  Nodes executed: {nodes_seen}")

    # Assertions
    assert "router" in nodes_seen, f"router must run; got {nodes_seen}"
    assert "extract_profile" in nodes_seen, "extract_profile must run"
    # Either plan was produced or question was asked — both are valid graph endings
    plan_done = "respond" in nodes_seen
    question_asked = "ask_missing" in nodes_seen
    assert plan_done or question_asked, f"Graph must end at respond or ask_missing; got {nodes_seen}"

    if plan_done:
        print(f"[PASS] new_plan turn → full plan produced")
    else:
        print(f"[PASS] new_plan turn → missing fields asked (expected when LLM is offline)")

    return nodes_seen, final_state


# ── Test 3: Profile patch path ────────────────────────────────────────────────

async def test_profile_patch_turn(g):
    """Route: patch → merge_patch → gather_data (no LLM call)."""
    config = {"configurable": {"thread_id": "full-test-002"}}
    state = {
        "thread_id": "full-test-002",
        "message": "",
        "language": "en",
        "profile_patch": {"land_acres": 8.0, "budget_rs": 75000.0},
        "profile": None,
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
        if etype == "on_chain_end" and name and not name.startswith("_") and name != "LangGraph":
            nodes_seen.append(name)

    print(f"  Nodes: {nodes_seen}")
    assert "router" in nodes_seen
    assert "merge_patch" in nodes_seen, f"merge_patch must run for profile_patch; got {nodes_seen}"
    assert "extract_profile" not in nodes_seen, "extract_profile must NOT run for patch route"
    print("[PASS] profile_patch turn → merge_patch path (no LLM)")

# ── Test 4: SSE via in-process ASGI ──────────────────────────────────────────

async def test_sse_in_process():
    """Spin up the FastAPI app in-process and call the SSE endpoint."""
    try:
        import httpx
        from httpx import ASGITransport
        from app.main import app

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Health check
            r = await client.get("/api/health")
            assert r.status_code == 200
            print(f"[PASS] /api/health → {r.json()['status']}")

            # Districts
            r = await client.get("/api/districts")
            assert r.status_code == 200
            districts = r.json()["districts"]
            assert len(districts) == 36, f"Expected 36 districts, got {len(districts)}"
            print(f"[PASS] /api/districts → {len(districts)} districts")

            # SSE chat — collect first few events only (avoid long Sarvam timeout)
            body = {"message": "Beed, 5 acres, 50000 budget, borewell", "language": "en"}
            events_collected = []
            # Use a short timeout to avoid waiting for Sarvam
            try:
                async with client.stream("POST", "/api/agent/chat", json=body, timeout=20.0) as resp:
                    assert resp.status_code == 200, f"SSE returned {resp.status_code}"
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if line.startswith("event:"):
                            events_collected.append(line.split(":", 1)[1].strip())
                        if "done" in events_collected or len(events_collected) >= 10:
                            break
            except Exception as e:
                print(f"  SSE stream ended early: {e}")

            print(f"  SSE events: {events_collected}")
            assert "thread" in events_collected, f"'thread' event must be first; got {events_collected}"
            print(f"[PASS] E1 SSE chat → received events: {events_collected}")

            # Plan (E2)
            plan_body = {
                "location_text": "Beed",
                "land_acres": 5.0,
                "budget_rs": 50000.0,
                "water_source": "borewell",
                "language": "en",
            }
            r = await client.post("/api/plan", json=plan_body)
            assert r.status_code == 200, f"E2 returned {r.status_code}: {r.text[:200]}"
            plan = r.json()
            assert "plan_id" in plan, f"plan_id missing: {list(plan.keys())}"
            plan_id = plan["plan_id"]
            thread_id = plan.get("thread_id", "")
            print(f"[PASS] E2 /api/plan → plan_id={plan_id} thread_id={thread_id}")

            # Thread restore (E4)
            if thread_id:
                r = await client.get(f"/api/threads/{thread_id}")
                assert r.status_code == 200, f"E4 returned {r.status_code}: {r.text[:200]}"
                print(f"[PASS] E4 /api/threads/{thread_id} → restored")

            # Reoptimize (E3)
            reopt_body = {"land_acres": 6.0}
            r = await client.post(f"/api/plans/{plan_id}/reoptimize", json=reopt_body)
            assert r.status_code == 200, f"E3 returned {r.status_code}: {r.text[:200]}"
            reopt = r.json()
            assert reopt.get("version") == 2, f"version should be 2, got {reopt.get('version')}"
            assert reopt.get("previous_version") == 1
            print(f"[PASS] E3 /api/plans/{plan_id}/reoptimize → version={reopt['version']}")

            # Sources (E11)
            r = await client.get("/api/sources")
            assert r.status_code == 200
            print(f"[PASS] E11 /api/sources → {len(r.json())} sources")

            # District context (E10)
            r = await client.get("/api/districts/Beed/context")
            assert r.status_code == 200
            ctx = r.json()
            assert "district" in ctx
            print(f"[PASS] E10 /api/districts/Beed/context → district={ctx['district']}")

            # Transcribe (E5) — expect 422 with no audio file
            r = await client.post("/api/transcribe", content=b"", headers={"content-type": "audio/webm"})
            assert r.status_code in (400, 415, 422), f"E5 with empty body returned {r.status_code}"
            print(f"[PASS] E5 /api/transcribe → correctly rejects empty body ({r.status_code})")

            # Speak (E6) — missing required fields
            r = await client.post("/api/speak", json={})
            assert r.status_code == 422, f"E6 with empty body returned {r.status_code}"
            print(f"[PASS] E6 /api/speak → correctly rejects empty body (422)")

    except ImportError as e:
        print(f"[SKIP] In-process ASGI test skipped: {e}")
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise
    except Exception as e:
        print(f"[FAIL] Unexpected error: {type(e).__name__}: {e}")
        raise


# ── Test 5: Existing pytest suite ────────────────────────────────────────────

async def test_pytest_suite():
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short", "--no-header"],
        capture_output=True, text=True,
        cwd=r"C:\Users\hp\Downloads\AgriPulse-main\backend",
    )
    print("\n--- pytest output ---")
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode != 0 and result.stderr:
        print("STDERR:", result.stderr[-500:])
    assert result.returncode == 0, f"pytest failed with code {result.returncode}"
    print("[PASS] pytest suite")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=== AgriPulse Agent Full Test Suite ===\n")
    passed = []
    failed = []

    tests = [
        ("Graph compiles", test_graph_compiles),
        ("In-process ASGI endpoints", test_sse_in_process),
        ("pytest suite (42 tests)", test_pytest_suite),
    ]

    g = None
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            if name == "Graph compiles":
                g = await fn()
                passed.append(name)
            else:
                await fn()
                passed.append(name)
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed.append((name, str(e)))

    # Run graph turn tests only if graph compiled
    if g is not None:
        for name, fn in [
            ("New plan turn (direct graph)", lambda: test_new_plan_turn(g)),
            ("Profile patch turn (direct graph)", lambda: test_profile_patch_turn(g)),
        ]:
            print(f"\n--- {name} ---")
            try:
                await fn()
                passed.append(name)
            except Exception as e:
                print(f"[FAIL] {name}: {e}")
                failed.append((name, str(e)))

    print(f"\n{'='*50}")
    print(f"PASSED: {len(passed)}/{len(passed)+len(failed)}")
    for n in passed:
        print(f"  ✓ {n}")
    if failed:
        print(f"FAILED: {len(failed)}")
        for n, e in failed:
            print(f"  ✗ {n}: {e}")
    print("="*50)

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())
