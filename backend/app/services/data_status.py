"""Count the real provenance of a plan (replaces the hard-coded data_status).

Walks the serialised plan, finds every SourcedValue-shaped object and counts the
DISTINCT ones by status. Only live / cached / official_dataset are reported
(computed, assumption and farmer_input values are not "data fetched").
Both /api/plan (E2) and the agent (E1) call this so they report the same numbers.
"""

from __future__ import annotations

from typing import Any

from app.schemas import DataStatus

_SV_KEYS = {"value", "unit", "source", "status"}


def _walk(node: Any, seen: set[tuple], counts: dict[str, int]) -> None:
    if isinstance(node, dict):
        if _SV_KEYS.issubset(node.keys()):
            status = node.get("status")
            if status in counts:
                ident = (status, node.get("source"), node.get("as_of"), str(node.get("value")), node.get("unit"))
                if ident not in seen:
                    seen.add(ident)
                    counts[status] += 1
        for value in node.values():
            _walk(value, seen, counts)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, seen, counts)


def count_data_status(plan: Any) -> DataStatus:
    """plan: a PlanResult or its model_dump(mode='json') dict."""
    data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
    counts = {"live": 0, "cached": 0, "official_dataset": 0}
    _walk(data, set(), counts)
    return DataStatus(**counts)
