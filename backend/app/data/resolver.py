"""District name resolver: any spelling → canonical district name (DATA.2).

Uses the `name_variants` column in districts.csv which lists every known
spelling including old names, Agmarknet spellings and LGD variants,
pipe-separated.

Usage:
    canonical = resolve_district("Ahmadnagar")   # → "Ahilyanagar"
    canonical = resolve_district("Chattrapati Sambhajinagar")  # → "Chhatrapati Sambhajinagar"
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from app.data.loaders import load_districts

logger = logging.getLogger(__name__)


def _norm(name: str) -> str:
    """Lowercase, strip non-alpha chars for fuzzy matching."""
    return re.sub(r"[^a-z]", "", name.lower())


@lru_cache(maxsize=1)
def _build_lookup() -> dict[str, str]:
    """Build normalised-name → canonical-name lookup from districts.csv."""
    df = load_districts()
    lookup: dict[str, str] = {}
    for _, row in df.iterrows():
        canonical = row["district"]
        # Add canonical name itself
        lookup[_norm(canonical)] = canonical
        # Add all name variants
        variants = str(row.get("name_variants", ""))
        for variant in variants.split("|"):
            v = variant.strip()
            if v:
                lookup[_norm(v)] = canonical
    logger.debug("District lookup built: %d entries", len(lookup))
    return lookup


def resolve_district(name: str) -> str | None:
    """Return the canonical district name, or None if not found."""
    lookup = _build_lookup()
    return lookup.get(_norm(name))


def get_district_row(district: str) -> dict | None:
    """Return the full districts.csv row for a canonical district name."""
    df = load_districts()
    rows = df[df["district"] == district]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def list_districts() -> list[str]:
    """Return sorted list of all 36 canonical district names."""
    return sorted(load_districts()["district"].tolist())


def is_agricultural(district: str) -> bool:
    """Return True if the district has DES crop statistics (not Mumbai City/Suburban)."""
    row = get_district_row(district)
    if row is None:
        return False
    return bool(row.get("is_agricultural_district", False))
