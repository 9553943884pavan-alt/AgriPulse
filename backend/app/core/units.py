"""Unit conversion helpers (backend/SPECS.md §5, ml/SPECS.md §6).

Rules from the spec:
  1 ha = 2.47105 acres
  1 tonne = 10 quintals
  1 mm over 1 acre = 4.047 m3   (mm × 4.047 = m3/acre)
  Money: Indian number grouping (en-IN)
  Devanagari digits optional per language.
"""

from __future__ import annotations

# ── Conversion constants ──────────────────────────────────────────────────────
HA_PER_ACRE = 1 / 2.47105          # 0.40469 ha per acre
ACRES_PER_HA = 2.47105
QUINTALS_PER_TONNE = 10.0
TONNES_PER_QUINTAL = 0.1
MM_TO_M3_PER_ACRE = 4.047          # 1 mm rain over 1 acre = 4.047 m3

DEVANAGARI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def ha_to_acres(ha: float) -> float:
    return round(ha * ACRES_PER_HA, 4)


def acres_to_ha(acres: float) -> float:
    return round(acres * HA_PER_ACRE, 6)


def tonnes_to_quintals(t: float) -> float:
    return round(t * QUINTALS_PER_TONNE, 4)


def quintals_to_tonnes(q: float) -> float:
    return round(q * TONNES_PER_QUINTAL, 6)


def t_per_ha_to_q_per_acre(t_per_ha: float) -> float:
    """Convert yield in tonnes/ha to quintals/acre (the farmer-facing unit)."""
    return round(t_per_ha * QUINTALS_PER_TONNE * HA_PER_ACRE, 4)


def mm_to_m3_per_acre(mm: float) -> float:
    """Effective rain / crop-water need: mm × 4.047 = m3 per acre."""
    return round(mm * MM_TO_M3_PER_ACRE, 2)


def format_inr(amount: float, language: str = "en") -> str:
    """Format money in Indian grouping with the ₹ symbol.

    E.g. 150000 → '₹1,50,000' (en/hi) or '₹१,५०,०००' (mr with Devanagari).
    """
    amount_int = int(round(amount))
    s = str(amount_int)
    # Indian grouping: last 3 digits, then groups of 2
    if len(s) <= 3:
        grouped = s
    else:
        grouped = s[-3:]
        s = s[:-3]
        while s:
            grouped = s[-2:] + "," + grouped
            s = s[:-2]
    result = f"₹{grouped}"
    if language == "mr":
        result = result.translate(DEVANAGARI_DIGITS)
    return result


def normalize_number_string(text: str) -> str:
    """Normalize Devanagari digits and Indian grouping to plain ASCII integers.

    Used by the grounding check (ml/SPECS §8.6) when comparing LLM answer
    numbers against tool output values.
    """
    rev = str.maketrans("०१२३४५६७८९", "0123456789")
    text = text.translate(rev)
    text = text.replace(",", "")
    # Expand common Hindi/Marathi number words
    text = text.replace("हजार", "000")
    text = text.replace("लाख", "00000")
    text = text.replace("करोड", "0000000")
    text = text.replace("hazar", "000")
    text = text.replace("lakh", "00000")
    text = text.replace("crore", "0000000")
    return text
