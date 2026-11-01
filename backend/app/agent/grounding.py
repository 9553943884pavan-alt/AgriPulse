"""AG.9 — Number grounding checker.

Every number in the LLM explanation must be traceable to the tool outputs.
This prevents the model from hallucinating crop yields, prices or profit figures.

Normalisation pipeline (applied to both explanation text and source values):
  1. Devanagari digits → ASCII  (०→0 … ९→9)
  2. Strip Indian digit grouping  ("1,00,000" → "100000")
  3. Expand written number words:
       hazar / हज़ार / हजार    → × 1,000
       lakh  / लाख             → × 100,000
       crore / करोड़ / करोड    → × 10,000,000
  4. Extract all decimal numbers from the normalised text
  5. For each extracted number: pass if |n - sv| / max(|sv|, 1) ≤ GROUNDING_TOLERANCE
     (5 % — covers "2 sig fig" rounding on yields and "nearest Rs. 100" on money)
  6. A number with no matching source value → grounding fails
"""

from __future__ import annotations

import re

from app.ml.constants import GROUNDING_TOLERANCE

# Devanagari digit map
_DEVA_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

# Written number multipliers (case-insensitive, match whole words)
_WORD_MULTIPLIERS = [
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:crore|करोड़?)\b", re.IGNORECASE), 1e7),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:lakh|लाख)\b", re.IGNORECASE), 1e5),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:hazar|हज़ार|हजार)\b", re.IGNORECASE), 1e3),
]

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# Digits that belong to a unit or chemical formula, not to a quantity: "3805 m3",
# "km2", "P2O5", "K2O", "CO2".  Without this the "3" in "m3" is read as a stray
# figure and every explanation that states a water volume fails grounding.
_UNIT_DIGITS_RE = re.compile(r"(?i)\b(?:m|cm|mm|km)[23]\b|\b[PK]2O5?\b|\bCO2\b")


def _normalise(text: str) -> str:
    """Apply steps 1–2: Devanagari digits + strip Indian digit grouping."""
    text = text.translate(_DEVA_MAP)
    # Remove commas that are Indian digit separators (between digits)
    text = re.sub(r"(\d),(\d{2,3})", r"\1\2", text)
    text = re.sub(r"(\d),(\d{2,3})", r"\1\2", text)   # second pass for 1,00,000
    return text


def _expand_words(text: str) -> str:
    """Replace written number words with their numeric value."""
    for pattern, multiplier in _WORD_MULTIPLIERS:
        def replace(m: re.Match, mult: float = multiplier) -> str:
            return str(float(m.group(1)) * mult)
        text = pattern.sub(replace, text)
    return text


def extract_numbers(text: str) -> list[float]:
    """Full pipeline: normalise → expand words → extract floats."""
    text = _UNIT_DIGITS_RE.sub(" ", text)
    text = _normalise(text)
    text = _expand_words(text)
    return [float(m) for m in _NUMBER_RE.findall(text)]


def _numbers_from_sources(tool_outputs: dict) -> list[float]:
    """Recursively collect all numeric values from tool outputs."""
    nums: list[float] = []

    def _walk(obj: object) -> None:
        if isinstance(obj, (int, float)):
            nums.append(float(obj))
        elif isinstance(obj, str):
            # Normalise and extract from source strings too (e.g. "50,000 Rs.")
            nums.extend(extract_numbers(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
        # Pydantic models expose __dict__
        elif hasattr(obj, "__dict__"):
            _walk(obj.__dict__)

    _walk(tool_outputs)
    return nums


def grounding_check(explanation_text: str, tool_outputs: dict) -> bool:
    """Return True if every number in *explanation_text* is present in *tool_outputs*.

    A number passes if there exists a source value sv such that
      abs(n - sv) / max(abs(sv), 1) <= GROUNDING_TOLERANCE  (5%)

    Any single number with no such match causes the whole check to fail.
    """
    candidate_numbers = extract_numbers(explanation_text)
    if not candidate_numbers:
        return True   # no numbers to check → pass

    source_numbers = _numbers_from_sources(tool_outputs)
    if not source_numbers:
        # No source numbers at all but explanation has numbers → fail
        return False

    for n in candidate_numbers:
        # The text writes "loss of Rs 3,380" while the source holds -3380, so compare magnitudes.
        matched = any(
            abs(n - abs(sv)) / max(abs(sv), 1.0) <= GROUNDING_TOLERANCE
            for sv in source_numbers
        )
        if not matched:
            return False
    return True
