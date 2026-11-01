"""QA.1 — Quality Latency Benchmark Script.

Evaluates latency per stage across 5 saved real profiles in Maharashtra.
Asserts that every warm plan completes in under 5.0 seconds.

Stages measured:
  1. Location resolution
  2. Weather & rainfall fetch
  3. Climate scenarios generation (ML.5)
  4. Water budget calculation (SVC.7)
  5. Candidate crops selection (ML.1)
  6. Crop options & ML yield + SHAP (ML.4, ML.4b, ML.6, ML.8)
  7. Optimizer strategy comparison (OPT.1 - OPT.3)
  Total: End-to-end warm plan time
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# OpenBLAS thread safety on Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

# UTF-8 stdout encoding for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.pipeline import run_plan, _detect_season  # noqa: E402
from app.schemas import FarmProfile, OptimizerInputs  # noqa: E402
from app.services import location as loc_svc  # noqa: E402
from app.services import weather as wx_svc  # noqa: E402
from app.services import water as water_svc  # noqa: E402
from app.ml.stubs import build_scenarios, candidate_crops  # noqa: E402
from app.ml.candidate_options import build_crop_options  # noqa: E402
from app.ml.optimizer import compare_strategies  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


PROFILES = [
    (
        "Pune",
        FarmProfile(
            location_text="Pune",
            land_acres=5.0,
            budget_rs=70000.0,
            water_source="borewell",
            borewell_count=1,
            pump_hours_per_day=4.0,
            irrigation_method="drip",
            risk_appetite="balanced",
            language="mr",
        ),
    ),
    (
        "Jalgaon",
        FarmProfile(
            location_text="Jalgaon",
            land_acres=8.0,
            budget_rs=120000.0,
            water_source="canal",
            irrigation_method="sprinkler",
            risk_appetite="safe",
            language="mr",
        ),
    ),
    (
        "Ahilyanagar",
        FarmProfile(
            location_text="Ahilyanagar",
            land_acres=4.0,
            budget_rs=60000.0,
            water_source="borewell",
            borewell_count=1,
            pump_hours_per_day=3.0,
            irrigation_method="flood",
            risk_appetite="balanced",
            language="mr",
        ),
    ),
    (
        "Nashik",
        FarmProfile(
            location_text="Nashik",
            land_acres=6.0,
            budget_rs=90000.0,
            water_source="borewell",
            borewell_count=1,
            pump_hours_per_day=4.0,
            irrigation_method="drip",
            risk_appetite="balanced",
            language="mr",
        ),
    ),
    (
        "Solapur",
        FarmProfile(
            location_text="Solapur",
            land_acres=10.0,
            budget_rs=150000.0,
            water_source="canal",
            irrigation_method="drip",
            risk_appetite="safe",
            language="mr",
        ),
    ),
]


async def measure_stages(profile: FarmProfile) -> dict[str, float]:
    """Measure individual stage durations in milliseconds and total time in seconds."""
    t_start = time.perf_counter()
    timings = {}
    now = datetime.now(tz=timezone.utc)

    # Stage 1: Location
    t0 = time.perf_counter()
    location = await loc_svc.locate(profile.location_text)
    timings["location_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 2: Season
    season = _detect_season(now.date())

    # Stage 3: Weather
    t0 = time.perf_counter()
    weather = await wx_svc.get_weather(location)
    timings["weather_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 4: Scenarios
    t0 = time.perf_counter()
    scenarios = build_scenarios(location, season)
    timings["scenarios_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 5: Water budget
    t0 = time.perf_counter()
    water_budgets = water_svc.build_water_budgets(profile, location, scenarios, weather)
    timings["water_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 6: Candidates
    t0 = time.perf_counter()
    candidates, _ = candidate_crops(profile, location, season, water_budgets)
    timings["candidates_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 7: Crop options (ML yield + SHAP + fertilizer + prices + costs)
    t0 = time.perf_counter()
    crops = await build_crop_options(candidates, scenarios, location, season, profile)
    timings["crop_options_ms"] = (time.perf_counter() - t0) * 1000

    # Stage 8: Optimizer
    t0 = time.perf_counter()
    if crops:
        opt_inputs = OptimizerInputs(
            profile=profile,
            location=location,
            season=season,
            candidates=crops,
            water_budgets=water_budgets,
            scenario_weights=[0.2, 0.6, 0.2],
            price_history_years={c.crop_id: 5 for c in crops},
        )
        strategies, _, _ = compare_strategies(opt_inputs)
    timings["optimizer_ms"] = (time.perf_counter() - t0) * 1000

    timings["total_plan_s"] = time.perf_counter() - t_start
    return timings


async def run_benchmark():
    print("=" * 80)
    print("QA.1 Quality Latency Benchmark (5 Real Profiles)")
    print("Target: Warm plan under 5.0 seconds")
    print("=" * 80)

    # 1. Warm-up pass to populate memory cache & BLAS buffers
    print("\n[Warm-up] Warming data loaders, ML models, and SQLite cache with profile 1...")
    t_warm = time.perf_counter()
    await run_plan(PROFILES[0][1])
    warm_elapsed = time.perf_counter() - t_warm
    print(f"[Warm-up] Completed in {warm_elapsed:.2f} s\n")

    # 2. Benchmark each of the 5 profiles
    results = []
    print(f"{'Profile':<15} | {'Loc':<8} | {'Weather':<8} | {'Scen':<8} | {'Water':<8} | {'Cands':<8} | {'ML/Opts':<8} | {'Opt':<8} | {'Total (s)':<9} | {'Status'}")
    print("-" * 105)

    all_passed = True
    for name, profile in PROFILES:
        # Measure warm plan
        timings = await measure_stages(profile)
        # Also run end-to-end run_plan to verify total pipeline latency
        t0 = time.perf_counter()
        plan = await run_plan(profile)
        e2e_total_s = time.perf_counter() - t0

        passed = e2e_total_s < 5.0
        if not passed:
            all_passed = False

        status_str = "PASSED (< 5.0s)" if passed else "FAILED (>= 5.0s)"
        print(
            f"{name:<15} | "
            f"{timings['location_ms']:>6.1f}ms | "
            f"{timings['weather_ms']:>6.1f}ms | "
            f"{timings['scenarios_ms']:>6.1f}ms | "
            f"{timings['water_ms']:>6.1f}ms | "
            f"{timings['candidates_ms']:>6.1f}ms | "
            f"{timings['crop_options_ms']:>6.1f}ms | "
            f"{timings['optimizer_ms']:>6.1f}ms | "
            f"{e2e_total_s:>7.3f}s   | "
            f"{status_str}"
        )
        results.append({
            "name": name,
            "timings": timings,
            "e2e_s": e2e_total_s,
            "passed": passed,
            "crops_count": len(plan.crops),
            "strategies_count": len(plan.strategies),
        })

    print("-" * 105)
    max_time = max(r["e2e_s"] for r in results)
    avg_time = sum(r["e2e_s"] for r in results) / len(results)
    print("\nBenchmark Summary:")
    print(f"  Total Profiles Tested : {len(results)}")
    print(f"  Average Warm Latency  : {avg_time:.3f} s")
    print(f"  Maximum Warm Latency  : {max_time:.3f} s")
    print(f"  Latency SLA (< 5.0s)  : {'ALL MET' if all_passed else 'BREACHED'}")
    print("=" * 80)

    if not all_passed:
        print("\nERROR: One or more profiles exceeded the 5.0s latency SLA.")
        sys.exit(1)
    else:
        print("\nSUCCESS: All 5 profiles completed well within the 5.0s SLA!")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
    sys.exit(0)
