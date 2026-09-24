from tools.inventory.contracts import (
    INVENTORY_TOOL_INPUTS,
    InventoryToolInput,
    InventoryToolResponse,
    ReorderCandidatesInput,
    StrategyAnalysisInput,
)
from tools.inventory.demand import (
    calculate_demand_shortages,
    create_demand_aligned_events,
)
from tools.inventory.recommendation import (
    StrategyRecommendation,
    select_recommended_strategy,
)
from tools.inventory.reorder import (
    ReorderCandidate,
    build_reorder_recommendations,
)
from tools.inventory.snapshot_adapter import (
    InventoryStrategyRows,
    extract_inventory_strategy_rows,
)
from tools.inventory.strategy import (
    InventoryStrategyToolResult,
    run_inventory_strategy_analysis,
)
from tools.inventory.tools import InventoryAgentTools

__all__ = [
    "INVENTORY_TOOL_INPUTS",
    "InventoryAgentTools",
    "InventoryStrategyRows",
    "InventoryStrategyToolResult",
    "InventoryToolInput",
    "InventoryToolResponse",
    "ReorderCandidate",
    "ReorderCandidatesInput",
    "StrategyAnalysisInput",
    "StrategyRecommendation",
    "build_reorder_recommendations",
    "calculate_demand_shortages",
    "create_demand_aligned_events",
    "extract_inventory_strategy_rows",
    "run_inventory_strategy_analysis",
    "select_recommended_strategy",
]