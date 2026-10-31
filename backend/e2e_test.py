"""End-to-end agent workflow test.
Run: python e2e_test.py
"""
import asyncio
import sys


async def run_e2e():
    from app.agent.graph import get_compiled_graph

    print("Compiling graph...")
    g = await get_compiled_graph()
    print(f"Graph compiled: {type(g).__name__}")

    state = {
        "thread_id": "th_e2e_001",
        "message": "I have 5 acres in Beed, my budget is 60000 rupees",
        "language": "en",
        "profile_patch": None,
        "missing": [],
        "scenarios": [],
        "water": [],
        "candidates": [],
        "excluded": [],
        "scenario_yields": {},
        "long_duration_crops": set(),
        "strategies": [],
        "relaxations": [],
        "relaxation_count": 0,
        "explanation_text": "",
        "explanation_grounded": False,
        "explanation_provider": "template",
        "grounding_retry_count": 0,
        "water_saved_pct": 0.0,
        "trace": [],
        "messages": [],
        "route": "new_plan",
        "no_data": False,
    }
    config = {"configurable": {"thread_id": "th_e2e_001"}}

    print("\nRunning graph (streaming events)...")
    nodes_visited = []
    results = {}

    async for event in g.astream_events(state, config=config, version="v1"):
        kind = event.get("event", "")
        name = event.get("name", "")

        if kind == "on_chain_end" and name:
            nodes_visited.append(name)
            output = (event.get("data") or {}).get("output") or {}

            if name == "router":
                route = output.get("route", "?")
                print(f"  [router]          route -> {route}")
                results["route"] = route

            elif name == "extract_profile":
                p = output.get("profile")
                miss = output.get("missing", [])
                if p:
                    print(f"  [extract_profile] location={p.location_text!r}  land={p.land_acres}  budget={p.budget_rs}  missing={miss}")
                results["profile"] = p
                results["missing"] = miss

            elif name == "gather_data":
                loc = output.get("location")
                sc = output.get("scenarios", [])
                wb = output.get("water", [])
                no_data = output.get("no_data", False)
                print(f"  [gather_data]     district={getattr(loc,'district','?')}  scenarios={len(sc)}  water_budgets={len(wb)}  no_data={no_data}")
                results["location"] = loc
                results["scenarios"] = sc

            elif name == "recommend_crops":
                cands = output.get("candidates", [])
                excl = output.get("excluded", [])
                print(f"  [recommend_crops] candidates={len(cands)}  excluded={len(excl)}")
                results["candidates"] = cands

            elif name == "predict_yield":
                sy = output.get("scenario_yields", {})
                print(f"  [predict_yield]   yield data for {len(sy)} crops")

            elif name == "optimize":
                strats = output.get("strategies", [])
                print(f"  [optimize]        strategies={len(strats)}")
                results["strategies"] = strats

            elif name == "check_feasibility":
                feas = output.get("feasibility")
                print(f"  [check_feasibility] feasibility={feas}")

            elif name == "explain":
                text = output.get("explanation_text", "")
                grounded = output.get("explanation_grounded", False)
                provider = output.get("explanation_provider", "?")
                print(f"  [explain]         provider={provider}  grounded={grounded}  text={text[:80]!r}")
                results["explanation"] = text
                results["provider"] = provider

            elif name == "respond":
                plan = output.get("plan_result")
                if plan:
                    print(f"  [respond]         plan_id={plan.plan_id}  warnings={len(plan.warnings)}")
                    print(f"                    explanation: {plan.explanation.text[:100]!r}")
                results["plan"] = plan

    print(f"\nNodes visited: {[n for n in nodes_visited if n]}")

    # ── Assertions ──────────────────────────────────────────────────────────────
    failures = []

    # 1. Router ran
    if "router" not in nodes_visited:
        failures.append("router node never ran")

    # 2. Profile extracted
    p = results.get("profile")
    if p is None:
        failures.append("no profile extracted")
    else:
        if not p.location_text:
            failures.append("location_text is empty")
        if not p.land_acres:
            failures.append("land_acres is 0/None")
        if not p.budget_rs:
            failures.append("budget_rs is 0/None")

    # 3. No missing required fields (message had all three)
    miss = results.get("missing", [])
    if miss:
        failures.append(f"required fields still missing after extraction: {miss}")

    # 4. gather_data ran
    if "gather_data" not in nodes_visited:
        failures.append("gather_data node never ran")

    # 5. respond ran and produced a plan
    if "respond" not in nodes_visited:
        failures.append("respond node never ran")
    plan = results.get("plan")
    if plan is None:
        failures.append("no plan_result produced")
    else:
        if not plan.plan_id:
            failures.append("plan_id is empty")
        if not plan.explanation.text:
            failures.append("explanation text is empty")
        if plan.location.district == "Unknown":
            failures.append("location.district is 'Unknown' — location service failed")

    # 6. SSE mapper test (profile event after extract_profile)
    # (tested via HTTP below)

    print("\n" + "="*60)
    if failures:
        print(f"FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  ✗ {f}")
        return False
    else:
        print("ALL ASSERTIONS PASS")
        if plan:
            print(f"  plan_id        : {plan.plan_id}")
            print(f"  district       : {plan.location.district}")
            print(f"  season         : {plan.season.name}")
            print(f"  scenarios      : {len(plan.scenarios)}")
            print(f"  strategies     : {len(plan.strategies)}")
            print(f"  explanation    : {plan.explanation.text[:120]!r}")
            print(f"  provider       : {plan.explanation.provider}")
        return True


if __name__ == "__main__":
    ok = asyncio.run(run_e2e())
    sys.exit(0 if ok else 1)
