"""Pytest wrapper for the live scenario harness. Skipped when the backend is not running."""
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_scenarios as rs  # noqa: E402

pytestmark = pytest.mark.skipif(not rs.server_up(), reason="live backend at http://127.0.0.1:8000 not reachable")

rs.RESULTS.mkdir(exist_ok=True)
_SCENARIOS = rs.load_scenarios()


@pytest.mark.parametrize("sc", _SCENARIOS, ids=[s["name"] for s in _SCENARIOS])
def test_scenario(sc):
    rec = rs.run_one(rs.BASE, sc)
    if rec["status"] == "BLOCKED":
        pytest.skip(rec["reason"])
    assert rec["status"] in ("PASS", "PASS-NOPLAN"), f"{rec['status']}: {rec['reason']}"
