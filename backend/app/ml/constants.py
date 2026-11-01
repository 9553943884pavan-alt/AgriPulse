"""All declared modelling constants.

Every value used by ML code, the optimizer, or the agent must be declared
here. Never put a bare number in ml/ or agent/ code — import it from here.

Status annotations:
  measured   — from a published dataset (cite SOURCES.md)
  choice     — a modelling decision we made (document the reason)
  assumption — not yet sourced; shown with an assumption badge in the UI
               and must be cited in SOURCES.md before the demo
"""

from __future__ import annotations

from typing import Final

# ── Scenario building (ML.5) ──────────────────────────────────────────────────
SCENARIO_PERCENTILES: Final = (10, 50, 90)         # P10 / P50 / P90  [choice]
SCENARIO_WEIGHTS_DEFAULT: Final = (0.2, 0.6, 0.2)  # drought/normal/excess  [choice]
# Rabi water index: 0.5 × rabi_rain + 0.5 × preceding_kharif_rain  [choice]
RABI_WATER_INDEX: Final = (0.5, 0.5)               # (rabi_weight, kharif_weight)

# ── Water budget formula ──────────────────────────────────────────────────────
# ASSUMPTION — cite FAO-56 effective-rainfall method in SOURCES.md before demo
EFFECTIVE_RAIN_FACTOR: Final = 0.75

# ASSUMPTION — cite CGWB/GSDA in SOURCES.md before demo
CATEGORY_CAP: Final[dict[str, float]] = {
    "Safe": 1.0,
    "Semi-critical": 0.7,
    "Critical": 0.4,
    "Over-exploited": 0.15,
}

# ASSUMPTION — cite Maharashtra WRD duty tables in SOURCES.md before demo.
# When None: canal_share = 0 even when canal_access=True; emit WARN_ASSUMED_BOREWELL.
# Set to the real value once cited and change status to measured.
CANAL_DUTY: float | None = None  # m³ per acre per season for canal-irrigated farms

# ── Optimizer ─────────────────────────────────────────────────────────────────
DIVERSIFICATION_CAP: Final[dict[int, float]] = {1: 1.0, 2: 0.80}
DIVERSIFICATION_CAP_DEFAULT: Final = 0.65   # for n >= 3  [choice]
RISK_LAMBDA: Final[dict[str, float]] = {
    "safe": 1.0,
    "balanced": 0.3,
    "max_profit": 0.0,
}
RISK_OBJECTIVE_SCALE_RS: Final = 1000.0  # Scale quadratic Rs² risk into the Rs objective.
SATURATION_GAMMA: Final = 0.0    # negligible for a single farm  [choice]
PSD_RIDGE: Final = 1e-6          # multiplied by trace(Σ) for numerical stability  [choice]
# The repository has three constructed weather scenarios, not a sufficiently
# long, aligned history of joint crop-profit observations. A covariance matrix
# estimated from those three points is not a validated farm-risk model, so
# public planning uses the deterministic LP / explicit scenario guard.
RISK_QP_ENABLED: Final = False
RISK_QP_DISABLE_REASON: Final = "risk QP disabled: no validated joint crop-profit history"

# Long-duration crop threshold used for an explicit comparison warning. The
# current optimizer is one-season; it deliberately does not annualise these
# crops because it does not model displaced crops, capital, or water.
LONG_DURATION_DAYS: Final = 120

# ── Suitability labels (ML.4b) ────────────────────────────────────────────────
SUITABILITY_THRESHOLD_GOOD: Final = 1.05    # score >= this → "good"  [choice]
SUITABILITY_THRESHOLD_AVERAGE: Final = 0.90 # score >= this → "average"; below → "poor"

# ── Data quality thresholds ───────────────────────────────────────────────────
RAIN_DAY_MM: Final = 2.5    # IMD definition of a rainy day  [measured]
HEAT_STRESS_C: Final = 35.0 # common flowering-damage threshold  [choice]
MIN_PRICE_YEARS: Final = 3  # minimum years of price history for a seasonal ratio
MIN_RISK_YEARS: Final = 5   # minimum year samples for a per-crop risk term

# ── Agent grounding ───────────────────────────────────────────────────────────
# 5% covers "2 sig figs" rounding on yields and "nearest 100" on money.
GROUNDING_TOLERANCE: Final = 0.05

# ── Season windows used to build weather features (ml/data_prep/build_yield_training.py)
# Kharif Jun 1-Oct 31 | Rabi Nov 1-Mar 31 | Summer Apr 1-Jun 30 | Whole Year Jul 1-Jun 30.  [measured]
SEASON_WINDOW_DAYS: Final[dict[str, int]] = {
    "Kharif": 153,
    "Rabi": 151,
    "Summer": 91,
    "Whole Year": 365,
}

# ── Crop calendar rows that are a season-specific variant of one master crop ──
# crop_calendar.csv has separate rows (own sowing window and duration) for crops that
# crops_master / DES / cost / seed / fertilizer / Agmarknet / Kc tables carry once.  [measured]
CROP_ID_ALIASES: Final[dict[str, str]] = {
    "maize_rabi": "maize",
    "jowar_kharif": "jowar",
    "onion_kharif": "onion",
    "groundnut_summer": "groundnut",
}

# ── Crop calendar ─────────────────────────────────────────────────────────────
SOWABLE_GRACE_DAYS: Final = 7    # days before sowing_start the crop is still shown
OPENS_SOON_DAYS: Final = 21      # days ahead — crop flagged opens_on

# ── Non-agricultural districts (no DES crop data) ────────────────────────────
NON_AGRICULTURAL_DISTRICTS: Final[frozenset] = frozenset({
    "Mumbai City",
    "Mumbai Suburban",
})

# ── Demo districts (ml/SPECS §9A) ─────────────────────────────────────────────
DEMO_DISTRICTS: Final = ("Jalgaon", "Pune", "Ahilyanagar")
DEMO_DISTRICT_BACKUP: Final = "Nashik"

# ── Warning codes (must match WarningCode Literal in schemas.py exactly) ─────
WARN_CACHED_PRICES            = "CACHED_PRICES"
WARN_CACHED_WEATHER           = "CACHED_WEATHER"
WARN_ASSUMED_IRRIGATION       = "ASSUMED_IRRIGATION"
WARN_ASSUMED_BOREWELL         = "ASSUMED_BOREWELL"
WARN_DISTRICT_AVERAGE_SOIL    = "DISTRICT_AVERAGE_SOIL"
WARN_OLD_COST_YEAR            = "OLD_COST_YEAR"          # always emit; costs are 2022-23
WARN_PRICE_NOT_ADJUSTED       = "PRICE_NOT_ADJUSTED"     # < MIN_PRICE_YEARS history
WARN_SINGLE_CROP_ELIGIBLE     = "SINGLE_CROP_ELIGIBLE"
WARN_SINGLE_SEASON_COMPARISON = "SINGLE_SEASON_COMPARISON"  # emit when sugarcane in any allocation
