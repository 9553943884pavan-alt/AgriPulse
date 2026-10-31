"""AG.5 — LangGraph StateGraph definition.

LangGraph version: 0.2.x
Checkpointer: AsyncSqliteSaver (NOT SqliteSaver — the graph is async)
astream_events version: "v1" (LangGraph 0.2 default; v2 is not stable)

Graph flow:
  START → route
    route ──► merge_patch ──► gather_data          (profile_patch card edit)
    route ──► extract_profile ──► ask_missing      (new_plan, missing fields)
    route ──► extract_profile ──► gather_data      (new_plan, all fields known)
    route ──► answer_from_memory ──► respond       (follow_up / question)

  gather_data ──► recommend_crops ──► predict_yield ──► optimize
    ──► check_feasibility
           ──► explain ──► grounding_check ──► respond ──► save_memory
           ──► relax_constraint ──► optimize           (infeasible loop, max 4)
           ──► respond                                  (still infeasible)
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.agent.nodes import (
    answer_from_memory_node,
    ask_missing_node,
    check_feasibility_node,
    explain_node,
    extract_profile_node,
    gather_data_node,
    grounding_check_node,
    merge_patch_node,
    optimize_node,
    predict_yield_node,
    recommend_crops_node,
    relax_constraint_node,
    respond_node,
    route_node,
    save_memory_node,
)

logger = logging.getLogger(__name__)

# ── State definition ──────────────────────────────────────────────────────────
    # TypedDict defined above — no separate import needed

class AgentState(TypedDict, total=False):
    # Conversation identity
    thread_id: str
    message: str
    language: Literal["mr", "hi", "en"]
    profile_patch: dict | None
    route: Literal["new_plan", "follow_up", "patch", "question"]

    # Profile
    profile: Any          # FarmProfile | None
    missing: list[str]
    question: dict | None  # {text, field, language} — set by ask_missing

    # Data
    location: Any         # Location | None
    weather: dict
    soil: dict
    scenarios: list
    water: list
    prices: dict
    costs: dict
    no_data: bool

    # ML results
    candidates: list
    excluded: list
    scenario_yields: dict
    long_duration_crops: set

    # Optimizer
    strategies: list
    feasibility: str | None   # None | "NEEDS_RELAX" | "INFEASIBLE"
    relaxations: list[str]
    relaxation_count: int

    # Explanation
    explanation_text: str
    explanation_grounded: bool
    explanation_provider: str
    grounding_retry_count: int
    water_saved_pct: float

    # Output
    plan_id: str
    plan_result: Any          # PlanResult | None
    season: Any               # Season | None
    trace: list
    messages: Annotated[list, add_messages]


# ── Edge routing functions ────────────────────────────────────────────────────

def _after_route(state: AgentState) -> str:
    route = state.get("route", "new_plan")
    if route == "patch":
        return "merge_patch"
    if route in ("follow_up", "question"):
        return "answer_from_memory"
    return "extract_profile"


def _after_extract_profile(state: AgentState) -> str:
    if state.get("missing"):
        return "ask_missing"
    return "gather_data"


def _after_gather_data(state: AgentState) -> str:
    if state.get("no_data"):
        return "respond"
    return "recommend_crops"


def _after_check_feasibility(state: AgentState) -> str:
    feasibility = state.get("feasibility")
    if feasibility is None:
        return "explain"
    if feasibility == "INFEASIBLE":
        return "respond"
    return "relax_constraint"


def _after_grounding_check(state: AgentState) -> str:
    if state.get("explanation_grounded"):
        return "respond"
    retry = state.get("grounding_retry_count", 0)
    if retry >= 2:
        return "respond"
    return "explain"


# ── Build and compile ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build the LangGraph StateGraph (uncompiled)."""
    g = StateGraph(AgentState)

    # Register all nodes
    g.add_node("route", route_node)
    g.add_node("merge_patch", merge_patch_node)
    g.add_node("extract_profile", extract_profile_node)
    g.add_node("ask_missing", ask_missing_node)
    g.add_node("gather_data", gather_data_node)
    g.add_node("answer_from_memory", answer_from_memory_node)
    g.add_node("recommend_crops", recommend_crops_node)
    g.add_node("predict_yield", predict_yield_node)
    g.add_node("optimize", optimize_node)
    g.add_node("check_feasibility", check_feasibility_node)
    g.add_node("relax_constraint", relax_constraint_node)
    g.add_node("explain", explain_node)
    g.add_node("grounding_check", grounding_check_node)
    g.add_node("respond", respond_node)
    g.add_node("save_memory", save_memory_node)

    # Entry point
    g.set_entry_point("route")

    # Edges
    g.add_conditional_edges("route", _after_route, {
        "merge_patch": "merge_patch",
        "answer_from_memory": "answer_from_memory",
        "extract_profile": "extract_profile",
    })
    g.add_edge("merge_patch", "gather_data")
    g.add_conditional_edges("extract_profile", _after_extract_profile, {
        "ask_missing": "ask_missing",
        "gather_data": "gather_data",
    })
    g.add_edge("ask_missing", END)   # turn ends; user answers in next message
    g.add_conditional_edges("gather_data", _after_gather_data, {
        "respond": "respond",
        "recommend_crops": "recommend_crops",
    })
    g.add_edge("answer_from_memory", "respond")
    g.add_edge("recommend_crops", "predict_yield")
    g.add_edge("predict_yield", "optimize")
    g.add_edge("optimize", "check_feasibility")
    g.add_conditional_edges("check_feasibility", _after_check_feasibility, {
        "explain": "explain",
        "respond": "respond",
        "relax_constraint": "relax_constraint",
    })
    g.add_edge("relax_constraint", "optimize")
    g.add_edge("explain", "grounding_check")
    g.add_conditional_edges("grounding_check", _after_grounding_check, {
        "respond": "respond",
        "explain": "explain",
    })
    g.add_edge("respond", "save_memory")
    g.add_edge("save_memory", END)

    return g


_compiled_graph = None


async def get_compiled_graph(db_path: str | None = None):
    """Compile the graph once and return the singleton.

    Attach AsyncSqliteSaver as the checkpointer.
    Falls back to no checkpointer if langgraph-checkpoint-sqlite is not installed.
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    from app.agent.memory import get_checkpointer
    checkpointer = await get_checkpointer()

    if checkpointer is not None:
        _compiled_graph = build_graph().compile(checkpointer=checkpointer)
    else:
        logger.warning("No checkpointer — agent will have no memory across turns")
        _compiled_graph = build_graph().compile()

    return _compiled_graph
