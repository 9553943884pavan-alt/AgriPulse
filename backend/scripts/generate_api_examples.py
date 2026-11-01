"""Generate real API contract examples into docs/api_examples/live/."""

import asyncio
import json
import os
from pathlib import Path
import sys

# Ensure thread safety on Windows / BLAS
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline import run_plan  # noqa: E402
from app.schemas import FarmProfile  # noqa: E402


PROFILES = {
    "plan_pune": FarmProfile(
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
    "plan_jalgaon": FarmProfile(
        location_text="Jalgaon",
        land_acres=8.0,
        budget_rs=120000.0,
        water_source="canal",
        irrigation_method="sprinkler",
        risk_appetite="safe",
        language="mr",
    ),
    "plan_ahilyanagar": FarmProfile(
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
}


async def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    live_dir = repo_root / "docs" / "api_examples" / "live"
    contract_dir = repo_root / "docs" / "api_examples" / "contract"
    live_dir.mkdir(parents=True, exist_ok=True)
    contract_dir.mkdir(parents=True, exist_ok=True)

    print("Generating live PlanResult examples from real ML pipeline...")
    for name, profile in PROFILES.items():
        print(f"  Running plan for {name} ({profile.location_text})...")
        plan = await run_plan(profile)
        data = plan.model_dump(mode="json")
        out_path = live_dir / f"{name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Saved {out_path} ({len(plan.crops)} crops, {len(plan.strategies)} strategies)")

    # Also capture endpoint outputs via TestClient
    print("\nCapturing live endpoint outputs via FastAPI TestClient...")
    with TestClient(app) as client:
        # 1. Districts
        resp = client.get("/api/districts")
        if resp.status_code == 200:
            with open(live_dir / "districts.json", "w", encoding="utf-8") as f:
                json.dump(resp.json(), f, indent=2, ensure_ascii=False)
            print("  Saved districts.json")

        # 2. Sources
        resp = client.get("/api/sources")
        if resp.status_code == 200:
            with open(live_dir / "sources.json", "w", encoding="utf-8") as f:
                json.dump(resp.json(), f, indent=2, ensure_ascii=False)
            print("  Saved sources.json")

        # 3. Sources Health
        resp = client.get("/api/sources/health")
        if resp.status_code == 200:
            with open(live_dir / "sources_health.json", "w", encoding="utf-8") as f:
                json.dump(resp.json(), f, indent=2, ensure_ascii=False)
            print("  Saved sources_health.json")

        # 4. District Context (Pune)
        resp = client.get("/api/districts/Pune/context")
        if resp.status_code == 200:
            with open(live_dir / "district_context_pune.json", "w", encoding="utf-8") as f:
                json.dump(resp.json(), f, indent=2, ensure_ascii=False)
            print("  Saved district_context_pune.json")

        # 5. OpenAPI schema
        resp = client.get("/openapi.json")
        if resp.status_code == 200:
            with open(repo_root / "docs" / "openapi.json", "w", encoding="utf-8") as f:
                json.dump(resp.json(), f, indent=2, ensure_ascii=False)
            print("  Saved docs/openapi.json")

    # Mirror to contract_dir as reference contract
    for fpath in live_dir.glob("*.json"):
        with open(fpath, "r", encoding="utf-8") as rf:
            content = rf.read()
        with open(contract_dir / fpath.name, "w", encoding="utf-8") as wf:
            wf.write(content)
    print("Mirrored live files to docs/api_examples/contract/")

    print("\nAll live API examples generated successfully!")


if __name__ == "__main__":
    asyncio.run(main())
