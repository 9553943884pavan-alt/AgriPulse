"""ML.3 — Hierarchical Median Yield Baseline.

Four-tier lookup hierarchy:
  1. (district, crop_id, season) -> median yield (t/ha)
  2. (district, crop_id) -> median yield (t/ha)
  3. (crop_id, season) -> median yield (t/ha)
  4. (crop_id) -> statewide median yield (t/ha)
  Fallback: statewide all-crops median yield.

Also tracks historical maximum yields per (district, crop_id) for sanity bounds.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import NamedTuple

import pandas as pd

from app.data.loaders import load_yield_training
from app.data.resolver import resolve_district

logger = logging.getLogger(__name__)


class BaselineResult(NamedTuple):
    yield_t_per_ha: float
    tier: str
    max_yield_t_per_ha: float


class YieldBaseline:
    """Hierarchical median yield lookup and historical bounds."""

    def __init__(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = load_yield_training()
        self.df = df.copy()

        # Clean invalid values if any
        valid = self.df[self.df["yield_t_per_ha"] > 0].copy()

        # Build hierarchical lookup tables
        self._t1 = valid.groupby(["district", "crop_id", "season"])["yield_t_per_ha"].median().to_dict()
        self._t2 = valid.groupby(["district", "crop_id"])["yield_t_per_ha"].median().to_dict()
        self._t3 = valid.groupby(["crop_id", "season"])["yield_t_per_ha"].median().to_dict()
        self._t4 = valid.groupby("crop_id")["yield_t_per_ha"].median().to_dict()
        self._statewide_median = float(valid["yield_t_per_ha"].median())

        # Historical maximum yields (used to bound predictions)
        self._max_dc = valid.groupby(["district", "crop_id"])["yield_t_per_ha"].max().to_dict()
        self._max_c = valid.groupby("crop_id")["yield_t_per_ha"].max().to_dict()
        self._statewide_max = float(valid["yield_t_per_ha"].max())

    def lookup(self, district: str, crop_id: str, season: str) -> BaselineResult:
        """Hierarchical lookup returning estimated yield and tier used."""
        dist = resolve_district(district)
        crop = crop_id.lower().strip()
        szn = season.title().strip()

        # Max historical yield bound
        max_y = self._max_dc.get((dist, crop))
        if max_y is None:
            max_y = self._max_c.get(crop, self._statewide_max)

        k1 = (dist, crop, szn)
        if k1 in self._t1:
            return BaselineResult(round(float(self._t1[k1]), 3), "district_crop_season", float(max_y))

        k2 = (dist, crop)
        if k2 in self._t2:
            return BaselineResult(round(float(self._t2[k2]), 3), "district_crop", float(max_y))

        k3 = (crop, szn)
        if k3 in self._t3:
            return BaselineResult(round(float(self._t3[k3]), 3), "crop_season", float(max_y))

        if crop in self._t4:
            return BaselineResult(round(float(self._t4[crop]), 3), "crop", float(max_y))

        return BaselineResult(round(self._statewide_median, 3), "statewide_fallback", float(max_y))

    def get_3yr_normal_yield(self, district: str, crop_id: str, season: str) -> float:
        """Return the crop's normal yield in the district for suitability calculation."""
        res = self.lookup(district, crop_id, season)
        return res.yield_t_per_ha


@lru_cache(maxsize=1)
def get_yield_baseline() -> YieldBaseline:
    """Singleton cached YieldBaseline instance."""
    return YieldBaseline()
