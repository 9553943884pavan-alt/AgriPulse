"""All 25 Pydantic v2 models that form the API contract (backend/SPECS.md §5.1).

These are the single source of truth for:
  - the REST API (FastAPI generates OpenAPI from these)
  - the ML interface (backend/app/ml/ stubs use these types)
  - the frontend TypeScript types (generated from the OpenAPI file)

Rule: every farmer-visible number is a SourcedValue. Plain int/float only for
ids, counts, duration_ms, version numbers. No mock status — assumption is the
lowest level for a declared modelling constant.

C.1 task: reviewed by all three owners; no type used anywhere without being
defined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# 1. SourcedValue  — every number the farmer sees
# ─────────────────────────────────────────────────────────────────────────────

SourcedStatus = Literal[
    "live",
    "cached",
    "official_dataset",
    "model",
    "computed",
    "farmer_input",
    "assumption",
]


class SourcedValue(BaseModel):
    """A single numeric value with full provenance."""

    value: float | int | str          # str allowed for category values (e.g. "Over-exploited")
    unit: str
    source: str
    source_url: str = ""
    as_of: str                        # ISO date string or dataset year e.g. "2022-23"
    status: SourcedStatus

    # Optional extras used by specific fields
    history_years: int | None = None  # seasonal_ratio: years of price history used
    note: str | None = None           # seasonal_ratio: explains 1.0 fallback


class UncertaintyBand(BaseModel):
    """A declared, bounded uncertainty range for one optimizer input/output.

    Bounds are deliberately optional at the field level (``CropOption``) because
    the currently shipped yield and price datasets cannot support a defensible
    interval for every crop.  A missing band means *unknown*, not zero risk.
    """

    lower: float
    expected: float
    upper: float
    unit: str
    basis: str
    status: SourcedStatus

    @model_validator(mode="after")
    def _ordered_bounds(self) -> "UncertaintyBand":
        if self.lower > self.expected or self.expected > self.upper:
            raise ValueError("uncertainty bounds must satisfy lower <= expected <= upper")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 2. FarmProfile  — what the agent understood from the farmer
# ─────────────────────────────────────────────────────────────────────────────

WaterSource = Literal["rainfed", "borewell", "canal", "both"]
IrrigationMethod = Literal["flood", "sprinkler", "drip"]
RiskAppetite = Literal["safe", "balanced", "max_profit"]
Language = Literal["mr", "hi", "en"]
MissingField = Literal["location_text", "land_acres", "budget_rs"]


class SoilTest(BaseModel):
    n: float
    p: float
    k: float
    ph: float


class DefaultUsed(BaseModel):
    field: str
    value: str | float | int
    basis: str


class FarmProfile(BaseModel):
    location_text: str
    land_acres: float
    budget_rs: float
    water_source: WaterSource | None = None   # null treated as rainfed
    borewell_count: int | None = None
    borewell_yield_lph: float | None = None   # litres per hour
    pump_hours_per_day: float | None = None
    canal_access: bool = False
    irrigation_method: IrrigationMethod | None = None
    risk_appetite: RiskAppetite = "balanced"
    soil_test: SoilTest | None = None
    language: Language = "en"
    missing: list[MissingField] = Field(default_factory=list)
    defaults_used: list[DefaultUsed] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Location
# ─────────────────────────────────────────────────────────────────────────────

class Location(BaseModel):
    input: str
    resolved_name: str
    district: str
    state: str
    latitude: float
    longitude: float


# ─────────────────────────────────────────────────────────────────────────────
# 4. Season
# ─────────────────────────────────────────────────────────────────────────────

class SowingWindow(BaseModel):
    start: str   # ISO date
    end: str     # ISO date


class Season(BaseModel):
    name: str                        # Kharif | Rabi | Summer | Whole Year
    sowing_window: SowingWindow
    status: SourcedStatus = "official_dataset"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Scenario  — one analogue year (drought / normal / excess)
# ─────────────────────────────────────────────────────────────────────────────

class Scenario(BaseModel):
    id: Literal["drought", "normal", "excess"]
    label: str
    season_rain_mm: SourcedValue
    probability: float = Field(ge=0.0, le=1.0)  # assumption, not a forecast
    analogue_year: int               # real calendar year at P10/P50/P90
    all_year_samples: list[SourcedValue] = Field(default_factory=list)

    # All weather features for this analogue year (used by ML for prediction)
    rainfall_mm: float | None = None
    et0_mm: float | None = None
    rainy_days: int | None = None
    max_dry_spell_days: int | None = None
    mean_temp_c: float | None = None
    max_temp_c: float | None = None
    heat_stress_days: int | None = None
    mean_humidity_pct: float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Candidate  — a crop that passed the filter (ML.1), before scoring
# ─────────────────────────────────────────────────────────────────────────────

class Candidate(BaseModel):
    crop_id: str
    names: dict[str, str]            # {"en": "Chickpea", "mr": "हरभरा", "hi": "चना"}
    season: str
    duration_days: int
    water_need_m3_per_acre: SourcedValue
    opens_on: str | None = None      # ISO date if sowing window opens within 21 days


# ─────────────────────────────────────────────────────────────────────────────
# 7. ExcludedCrop
# ─────────────────────────────────────────────────────────────────────────────

ExcludedReasonCode = Literal[
    "NO_REAL_PRICE",
    "NO_YIELD_DATA",
    "DATA_UNAVAILABLE",
    "NOT_SOWABLE_NOW",
    "NOT_GROWN_IN_DISTRICT",
    "WATER_INFEASIBLE",
    "OVER_BUDGET",
]


class ExcludedCrop(BaseModel):
    crop_id: str
    reason_code: ExcludedReasonCode
    params: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Suitability
# ─────────────────────────────────────────────────────────────────────────────

SuitabilityLabel = Literal["good", "average", "poor"]

# Fixed feature codes — the frontend owns one i18n sentence per code
SuitabilityFeature = Literal[
    "season_rainfall_mm",
    "rainfall_departure_pct",
    "rainy_days",
    "max_dry_spell_days",
    "mean_temp_c",
    "max_temp_c",
    "heat_stress_days",
    "et0_total_mm",
    "mean_humidity_pct",
    "soil_n_kg_ha",
    "soil_p_kg_ha",
    "soil_k_kg_ha",
    "soil_ph",
    "organic_carbon_pct",
    "irrigated_pct",
    "fertilizer_use_kg_per_ha",
]


class SuitabilityFactor(BaseModel):
    feature: SuitabilityFeature
    value: float
    unit: str
    effect_quintal_per_acre: float
    direction: Literal["up", "down"]


class Suitability(BaseModel):
    score: float                     # predicted_yield / district_normal_yield
    label: SuitabilityLabel          # good>=1.05 | average 0.9-1.05 | poor<0.9
    top_factors: list[SuitabilityFactor]
    fallback_used: bool = False      # True when model weak; uses district historical avg


# ─────────────────────────────────────────────────────────────────────────────
# 9. YieldPrediction  — raw output from the yield model (ML.4)
# ─────────────────────────────────────────────────────────────────────────────

class YieldPrediction(BaseModel):
    t_per_ha: SourcedValue           # status = "model"
    clipped: bool = False            # True when clipped to district historical max
    out_of_training_range: bool = False
    uncertainty: UncertaintyBand | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 10. WaterNeed  — per crop per scenario (output of ML.7)
# ─────────────────────────────────────────────────────────────────────────────

class WaterNeed(BaseModel):
    drought: SourcedValue            # m3 per acre
    normal: SourcedValue
    excess: SourcedValue


# ─────────────────────────────────────────────────────────────────────────────
# 11. WaterBudget  — one per scenario (PlanResult carries list[WaterBudget] x3)
# ─────────────────────────────────────────────────────────────────────────────

class WaterAvailable(BaseModel):
    rain: SourcedValue
    groundwater: SourcedValue
    canal: SourcedValue
    total: SourcedValue


class WaterBasis(BaseModel):
    groundwater_category: SourcedValue
    category_cap: SourcedValue       # status = assumption until CGWB citation added
    effective_rain_factor: SourcedValue  # 0.75, status = assumption
    reservoir_storage_pct: SourcedValue
    rain_so_far_mm: SourcedValue


class WaterNeedSummary(BaseModel):
    traditional_plan: SourcedValue
    recommended_plan: SourcedValue


class WaterBudget(BaseModel):
    scenario: Literal["drought", "normal", "excess"]
    analogue_year: int
    available_m3: WaterAvailable
    basis: WaterBasis
    irrigation_method: str           # flood | sprinkler | drip
    efficiency_pct: SourcedValue
    need_m3: WaterNeedSummary


# ─────────────────────────────────────────────────────────────────────────────
# 12. FertilizerPlan  — RDF dose, product bags, cost (ML.8)
# ─────────────────────────────────────────────────────────────────────────────

class FertilizerPlan(BaseModel):
    n_kg_per_acre: float
    p2o5_kg_per_acre: float
    k2o_kg_per_acre: float
    urea_bags: float                 # converted from N requirement
    dap_bags: float                  # covers P2O5 (and part of N)
    mop_bags: float                  # covers K2O
    cost_rs: SourcedValue            # status = computed (dose × MRP)
    basis: str = "university recommended dose (RDF)"


# ─────────────────────────────────────────────────────────────────────────────
# 13. CostBreakdown  — itemized cost per acre for one crop
# ─────────────────────────────────────────────────────────────────────────────

class SupersededLines(BaseModel):
    """DES 2022-23 lines that were replaced by live sources."""
    seed_des: float | None = None
    fertilizer_des: float | None = None


class CostBreakdown(BaseModel):
    total_rs: float
    seed: float                      # from seed.csv (overrides DES)
    fertilizer: float                # RDF × MRP (overrides DES)
    manure: float
    labour: float
    machine: float
    irrigation: float
    pesticide: float
    interest: float
    superseded: SupersededLines = Field(default_factory=SupersededLines)
    reference_year: str              # e.g. "2022-23"
    source: str
    status: SourcedStatus = "official_dataset"


# ─────────────────────────────────────────────────────────────────────────────
# 14. CropOption  — one candidate crop with all farmer-visible numbers
# ─────────────────────────────────────────────────────────────────────────────

class YieldByScenario(BaseModel):
    drought: float
    normal: float
    excess: float


class ProfitByScenario(BaseModel):
    drought: float
    normal: float
    excess: float


class RevenueByScenario(BaseModel):
    """Gross revenue before the per-acre cost breakdown is deducted."""

    drought: float
    normal: float
    excess: float


class CropOption(BaseModel):
    crop_id: str
    names: dict[str, str]
    season: str
    suitability: Suitability
    yield_quintal_per_acre: YieldByScenario
    price: SourcedValue                      # today's Agmarknet quote
    expected_harvest_price: SourcedValue     # today × seasonal_ratio, floored at MSP
    seasonal_ratio: SourcedValue             # ratio with history_years and note
    duration_days: int
    harvest_month: str                       # "2027-02"
    opens_on: str | None = None              # ISO date if sowing window opens soon
    msp: SourcedValue | None = None
    cost_per_acre: CostBreakdown
    fertilizer: FertilizerPlan
    water_need_m3_per_acre: WaterNeed
    profit_rs_per_acre: ProfitByScenario
    # Optional until the source pipeline can estimate defensible intervals.
    # Absence must be presented as unknown uncertainty, never as a zero-risk input.
    revenue_rs_per_acre: RevenueByScenario | None = None
    yield_uncertainty: UncertaintyBand | None = None
    price_uncertainty: UncertaintyBand | None = None
    risk_note: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 15. Allocation  — one crop's slice in a StrategyResult
# ─────────────────────────────────────────────────────────────────────────────

class Allocation(BaseModel):
    crop_id: str
    acres: float
    share_pct: float
    cost_rs: float
    water_m3: float
    profit_rs: ProfitByScenario
    revenue_rs: RevenueByScenario | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 16. OptimizerInputs  — everything the optimizer needs in one bundle
# ─────────────────────────────────────────────────────────────────────────────

class OptimizerInputs(BaseModel):
    profile: FarmProfile
    location: Location
    season: Season
    candidates: list[CropOption]
    water_budgets: list[WaterBudget]   # one per scenario
    scenario_weights: list[float]      # [0.2, 0.6, 0.2]
    price_history_years: dict[str, int]  # crop_id → number of years available

    @model_validator(mode="after")
    def _validate_optimizer_contract(self) -> "OptimizerInputs":
        """Reject ambiguous input bundles before a solver receives them.

        The optimizer maps weights and water budgets by the three fixed scenario
        ids.  Accepting a partial or unnormalised bundle silently changes the
        objective, so it is a validation error rather than a solver fallback.
        """
        scenario_ids = {budget.scenario for budget in self.water_budgets}
        required_ids = {"drought", "normal", "excess"}
        if scenario_ids != required_ids or len(self.water_budgets) != 3:
            raise ValueError("water_budgets must contain exactly drought, normal, and excess")
        if len(self.scenario_weights) != 3:
            raise ValueError("scenario_weights must contain drought, normal, and excess weights")
        if any(weight < 0 for weight in self.scenario_weights):
            raise ValueError("scenario_weights must be non-negative")
        if abs(sum(self.scenario_weights) - 1.0) > 1e-6:
            raise ValueError("scenario_weights must sum to 1")
        crop_ids = [candidate.crop_id for candidate in self.candidates]
        if len(crop_ids) != len(set(crop_ids)):
            raise ValueError("candidates must not contain duplicate crop_id values")
        if any(years < 0 for years in self.price_history_years.values()):
            raise ValueError("price_history_years cannot be negative")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 17. StrategyResult  — one plan from one strategy
# ─────────────────────────────────────────────────────────────────────────────

StrategyKind = Literal["traditional", "lp", "qp"]
StrategyId = Literal["traditional", "lp_max_profit", "qp_balanced", "qp_drought_safe"]


class StrategyTotals(BaseModel):
    land_used_acres: float
    budget_used_rs: float
    fertilizer_kg: dict[str, float]  # {"n": ..., "p2o5": ..., "k2o": ...}
    water_m3: float


class FinanceSummary(BaseModel):
    """Computed portfolio finance for the strategy's scenario-weighted plan.

    Values are emitted only from the same crop yield, harvest-price and cost
    inputs used in the objective; this prevents a dashboard total from using a
    different financial definition than the optimizer.
    """

    investment_rs: SourcedValue
    expected_yield_quintal: SourcedValue
    expected_revenue_rs: SourcedValue
    expected_profit_rs: SourcedValue
    roi_pct: SourcedValue | None = None
    break_even_price_rs_per_quintal: SourcedValue | None = None


class RelaxationApplied(BaseModel):
    step: Literal[
        "CAP_TO_1",
        "REDUCE_AREA",
        "DROP_WATER_HUNGRY_CROP",
        "USE_NORMAL_SCENARIO_WATER",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class SolverInfo(BaseModel):
    name: str
    status: str
    ms: int


class StrategyResult(BaseModel):
    id: StrategyId
    label: str
    kind: StrategyKind
    risk_lambda: float
    safety_scenario: Literal["drought", "normal", "excess"]
    allocations: list[Allocation]
    totals: StrategyTotals
    finance: FinanceSummary | None = None
    profit_by_scenario_rs: ProfitByScenario
    expected_profit_rs: float
    worst_case_profit_rs: float
    feasible: bool
    binding_constraints: list[str]
    relaxations_applied: list[RelaxationApplied] = Field(default_factory=list)
    solver: SolverInfo | None = None
    infeasibility: Any | None = None        # Infeasibility | None (forward ref)
    traditional_exceeds: list[str] = Field(default_factory=list)  # limits the traditional mix breaks


# ─────────────────────────────────────────────────────────────────────────────
# 18. Infeasibility  — when no feasible plan exists after the relaxation ladder
# ─────────────────────────────────────────────────────────────────────────────

class ConstraintDetail(BaseModel):
    constraint: str
    required_rs: float | None = None
    available_rs: float | None = None
    shortfall_rs: float | None = None
    required_m3: float | None = None
    available_m3: float | None = None
    shortfall_m3: float | None = None


class RelaxationTried(BaseModel):
    step: str
    result: str


class Infeasibility(BaseModel):
    binding: list[str]
    violated: list[str]
    detail: list[ConstraintDetail]
    relaxations_tried: list[RelaxationTried]
    suggestion_code: str | None = None
    suggestion_params: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 19. Impact  — comparison vs Traditional plan
# ─────────────────────────────────────────────────────────────────────────────

class Impact(BaseModel):
    water_saved_pct: SourcedValue
    fertilizer_saved_pct: SourcedValue       # vs Traditional (same denominator as water)
    fertilizer_vs_district_use_pct: SourcedValue | None = None  # null when district use already below RDF
    drought_profit_gain_rs: SourcedValue
    versus: Literal["traditional"] = "traditional"
    traditional_exceeds: list[str]           # e.g. ["water"]


# ─────────────────────────────────────────────────────────────────────────────
# 20. PlanResult  — the full answer from run_plan()
# ─────────────────────────────────────────────────────────────────────────────

WarningCode = Literal[
    "CACHED_PRICES",
    "CACHED_WEATHER",
    "ASSUMED_IRRIGATION",
    "ASSUMED_BOREWELL",
    "CANAL_NOT_CREDITED",
    "DISTRICT_AVERAGE_SOIL",
    "OLD_COST_YEAR",
    "PRICE_NOT_ADJUSTED",
    "SINGLE_CROP_ELIGIBLE",
    "SINGLE_SEASON_COMPARISON",
]

KeyPointIcon = Literal[
    "wheat",
    "droplets",
    "cloud-rain",
    "sun",
    "coins",
    "trending-up",
    "trending-down",
    "map-pin",
    "alert-triangle",
    "badge-check",
]


class Warning(BaseModel):
    code: WarningCode
    params: dict[str, Any] = Field(default_factory=dict)


class KeyPoint(BaseModel):
    icon: KeyPointIcon
    text: str   # free text — written by the LLM in the farmer's language


class Explanation(BaseModel):
    language: Language
    text: str                         # LLM output in farmer's language (only free text in response)
    key_points: list[KeyPoint]
    grounded: bool
    provider: str                     # Sarvam model id used, or "template"


class DataStatus(BaseModel):
    live: int
    cached: int
    official_dataset: int


class PlanResult(BaseModel):
    plan_id: str
    thread_id: str
    version: int
    previous_version: int | None = None   # null on first version or direct E2 call
    created_at: datetime
    profile: FarmProfile
    location: Location
    season: Season
    scenarios: list[Scenario]             # always 3: drought, normal, excess
    crops: list[CropOption]
    excluded_crops: list[ExcludedCrop]
    water: list[WaterBudget]              # one WaterBudget per scenario (3 items)
    strategies: list[StrategyResult]      # up to 4
    recommended_strategy: StrategyId | None = None
    impact: Impact | None = None
    infeasibility: Infeasibility | None = None
    explanation: Explanation
    warnings: list[Warning]
    data_status: DataStatus


# ─────────────────────────────────────────────────────────────────────────────
# 21. TraceEvent  — one step of the agent, streamed as SSE
# ─────────────────────────────────────────────────────────────────────────────

TraceStatus = Literal["running", "ok", "cached", "failed", "skipped"]


class TraceSource(BaseModel):
    name: str
    url: str
    status: str


class TraceEvent(BaseModel):
    id: str
    node: str
    step: str
    status: TraceStatus
    started_at: datetime
    duration_ms: int
    summary: str
    source: TraceSource | None = None
    fallback_used: str | None = None
    # Additive, all optional: older clients ignore them.
    run_id: str | None = None          # one id per chat request
    sequence: int | None = None        # 1..n across the whole turn, set when emitted
    tool_name: str | None = None       # internal tool id, e.g. crop_recommender
    display_name: str | None = None    # friendly English name for the UI
    completed_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 22. ChatMessage  — one message in the conversation thread
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["farmer", "agent"]
    text: str
    language: Language
    at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# 23. Message  — farmer-facing text as {code, params} (i18n keys)
# ─────────────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    """All farmer-facing strings except explanation.text use this shape.
    The frontend resolves code → i18n sentence and fills in params.
    """
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 24. Error  — every non-2xx response body
# ─────────────────────────────────────────────────────────────────────────────

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "LOCATION_NOT_FOUND",
    "DISTRICT_NOT_AGRICULTURAL",
    "PLAN_NOT_FOUND",
    "AUDIO_TOO_LARGE",
    "STT_FAILED",
    "UPSTREAM_UNAVAILABLE",
    "RATE_LIMITED",
    "INTERNAL",
]


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    user_message: dict[str, str]   # {"mr": "...", "hi": "...", "en": "..."}
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """The 25th Pydantic type. API-facing response schema for all non-2xx replies.
    Named ErrorResponse to avoid shadowing Python's built-in Error.
    """
    error: ErrorDetail


# ─────────────────────────────────────────────────────────────────────────────
# SSE event envelope types (exposed via GET /api/schemas/sse-events — C.4)
# ─────────────────────────────────────────────────────────────────────────────

class SSEThread(BaseModel):
    thread_id: str


class SSEProfile(FarmProfile):
    pass


class SSEQuestion(BaseModel):
    text: str
    field: str
    language: Language


class SSEMessage(BaseModel):
    text: str
    language: Language
    provider: str


class SSEDone(BaseModel):
    ms: int


class SSEEventExamples(BaseModel):
    """Returned by GET /api/schemas/sse-events so OpenAPI includes every SSE
    payload and the frontend can generate TypeScript types for all of them."""
    thread: SSEThread
    profile: SSEProfile
    question: SSEQuestion
    trace: TraceEvent
    plan: PlanResult
    message: SSEMessage
    done: SSEDone
