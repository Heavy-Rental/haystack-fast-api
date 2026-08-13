"""LangGraph multi-agent orchestration (Stage 1 + S3 + S6 + S7.0–S7.6)."""

from app.agents.fleet_tools import (
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
)
from app.agents.graph import build_project_knowledge_graph, run_project_knowledge_agents
from app.agents.recommend_graph import build_recommend_graph, run_recommend_graph
from app.agents.recommend_synthesis import (
    SynthesisSchemaError,
    synthesize_recommendation,
    validate_recommendation_shape,
)
from app.agents.indexing_gate import (
    build_indexing_gate_graph,
    run_indexing_gate,
)
from app.agents.recommend_state import (
    ROLE_COORDINATOR,
    ROLE_DELEGATOR,
    ROLE_FLEET_WORKER,
    ROLE_PRICING_WORKER,
    ROLE_PROJECT_WORKER,
    RecommendAgentState,
    StateTransitionError,
    apply_partition_write,
    empty_recommend_state,
    validate_state_transition,
)
from app.agents.tool_factory import (
    build_recommend_tool_catalog,
    get_recommend_tool,
)
from app.agents.tools import (
    TOOL_PREDICT_ASSET_PRICE,
    TOOL_RUN_INDEXING,
    predict_asset_price,
    run_indexing_from_request,
)

__all__ = [
    "ROLE_COORDINATOR",
    "ROLE_DELEGATOR",
    "ROLE_FLEET_WORKER",
    "ROLE_PRICING_WORKER",
    "ROLE_PROJECT_WORKER",
    "RecommendAgentState",
    "StateTransitionError",
    "TOOL_CHECK_BOOKING_AVAILABILITY",
    "TOOL_DECOMPOSE_PROJECT_NEEDS",
    "TOOL_FILTER_FLEET_CANDIDATES",
    "TOOL_PREDICT_ASSET_PRICE",
    "TOOL_RETRIEVE_FLEET_ASSETS",
    "TOOL_RUN_INDEXING",
    "apply_partition_write",
    "SynthesisSchemaError",
    "build_indexing_gate_graph",
    "build_project_knowledge_graph",
    "build_recommend_graph",
    "build_recommend_tool_catalog",
    "empty_recommend_state",
    "get_recommend_tool",
    "predict_asset_price",
    "run_indexing_from_request",
    "run_indexing_gate",
    "run_project_knowledge_agents",
    "run_recommend_graph",
    "synthesize_recommendation",
    "validate_recommendation_shape",
    "validate_state_transition",
]
