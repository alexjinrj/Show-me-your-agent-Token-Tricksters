from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal
from uuid import uuid4

from mcp.server import MCPServer

from agent_runtime import ToolRegistry
from agent_runtime.service import RuntimeService
from interfaces.api.context import DemoContext
from interfaces.api.settings import load_settings
from interfaces.runtime import build_runtime


@dataclass(frozen=True)
class CoordinatorRuntime:
    context: DemoContext
    registry: ToolRegistry
    service: RuntimeService


@lru_cache(maxsize=1)
def get_runtime() -> CoordinatorRuntime:
    """Build the composition root lazily so MCP tool discovery stays side-effect light."""

    context = DemoContext.bootstrap(load_settings())
    service = build_runtime(context, use_gateway=False)
    return CoordinatorRuntime(context=context, registry=service.executor.registry, service=service)


def _invoke(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return (
        get_runtime()
        .service.executor.execute(
            name,
            arguments,
            snapshot_id=get_runtime().context.base_snapshot_id,
            run_id=str(uuid4()),
        )
        .model_dump(mode="json", exclude_none=True)
    )


mcp = MCPServer(
    "SME Business Coordinator",
    instructions=(
        "Use get_business_context first. Treat Actual State as immutable, distinguish actual "
        "facts from simulated outcomes, and cite tool_call_id or reference_id for material claims."
    ),
)


@mcp.tool()
def get_business_context() -> dict[str, Any]:
    """Get the authoritative base snapshot and the bounded business-tool catalog."""

    runtime = get_runtime()
    return {
        "base_snapshot_id": runtime.context.base_snapshot_id,
        "company_id": "SG-SME-001",
        "rules": [
            "Actual State is immutable and authoritative.",
            "Simulation results never modify Actual State.",
            "Cite tool_call_id or reference_id for material claims.",
        ],
        "tools": [
            {
                "name": item["name"],
                "description": item["description"],
                "access": item["access"],
                "groups": item["groups"],
            }
            for item in runtime.registry.catalog()
        ],
    }


@mcp.tool()
def get_actual_state_summary(snapshot_id: str) -> dict[str, Any]:
    """Read sales-order counts, backlog value, and lineage for an immutable snapshot."""

    return _invoke("get_actual_state_summary", {"snapshot_id": snapshot_id})


@mcp.tool()
def list_exceptions(
    snapshot_id: str,
    simulation_run_id: str | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """List bounded sales and inventory exceptions with evidence references."""

    return _invoke(
        "list_exceptions",
        {
            "snapshot_id": snapshot_id,
            "simulation_run_id": simulation_run_id,
            "top_n": top_n,
        },
    )


@mcp.tool()
def trace_process_bottleneck(
    snapshot_id: str,
    simulation_run_id: str | None = None,
) -> dict[str, Any]:
    """Inspect Order-to-Cash queues and resource-capacity evidence."""

    return _invoke(
        "trace_process_bottleneck",
        {"snapshot_id": snapshot_id, "simulation_run_id": simulation_run_id},
    )


@mcp.tool()
def trace_business_object(
    snapshot_id: str,
    order_number: str,
    simulation_run_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Trace one sales order without exposing arbitrary database access."""

    return _invoke(
        "trace_business_object",
        {
            "snapshot_id": snapshot_id,
            "order_number": order_number,
            "simulation_run_id": simulation_run_id,
            "limit": limit,
        },
    )


@mcp.tool()
def get_metric_history(
    snapshot_id: str,
    metric_code: Literal["backlog_count", "average_waiting_hours", "fulfilment_rate"],
) -> dict[str, Any]:
    """Check whether an actual historical sales metric is available."""

    return _invoke(
        "get_metric_history",
        {"snapshot_id": snapshot_id, "metric_code": metric_code},
    )


@mcp.tool()
def create_simulation_session(
    snapshot_id: str,
    name: str,
    description: str = "",
) -> dict[str, Any]:
    """Create an isolated simulation session from an immutable snapshot."""

    return _invoke(
        "create_simulation_session",
        {"snapshot_id": snapshot_id, "name": name, "description": description},
    )


@mcp.tool()
def get_simulation_state(simulation_session_id: str) -> dict[str, Any]:
    """Inspect one isolated simulation session and its scenario events."""

    return _invoke(
        "get_simulation_state",
        {"simulation_session_id": simulation_session_id},
    )


@mcp.tool()
def fork_simulation_session(simulation_session_id: str, name: str) -> dict[str, Any]:
    """Fork a simulation session so alternatives do not mutate their baseline."""

    return _invoke(
        "fork_simulation_session",
        {"simulation_session_id": simulation_session_id, "name": name},
    )


@mcp.tool()
def add_simulation_event(
    simulation_session_id: str,
    event_type: Literal["warehouse_capacity_increase", "expedite_supplier_delivery"],
    workers: int | None = None,
    days: int | None = None,
    purchase_order_number: str | None = None,
) -> dict[str, Any]:
    """Add one permitted warehouse-capacity or supplier-expedite scenario event."""

    return _invoke(
        "add_simulation_event",
        {
            "simulation_session_id": simulation_session_id,
            "event_type": event_type,
            "workers": workers,
            "days": days,
            "purchase_order_number": purchase_order_number,
        },
    )


@mcp.tool()
def run_simulation(
    simulation_session_id: str,
    horizon_days: int,
    random_seed: int,
) -> dict[str, Any]:
    """Run an isolated deterministic scenario; it cannot modify Actual State."""

    return _invoke(
        "run_simulation",
        {
            "simulation_session_id": simulation_session_id,
            "horizon_days": horizon_days,
            "random_seed": random_seed,
        },
    )


@mcp.tool()
def compare_simulation_runs(
    baseline_run_id: str,
    alternative_run_id: str,
) -> dict[str, Any]:
    """Compare compatible baseline and alternative simulation runs."""

    return _invoke(
        "compare_simulation_runs",
        {
            "baseline_run_id": baseline_run_id,
            "alternative_run_id": alternative_run_id,
        },
    )


@mcp.tool()
def list_inventory_reorder_candidates(
    snapshot_id: str,
    risk_level: Literal["all", "critical", "high", "medium", "low"] = "all",
    top_n: int = 10,
) -> dict[str, Any]:
    """List actual inventory reorder candidates from the scoped snapshot."""
    return _invoke(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": snapshot_id,
            "risk_level": risk_level,
            "top_n": top_n,
        },
    )


@mcp.tool()
def compare_inventory_replenishment_strategies(
    snapshot_id: str,
    horizon_days: int = 30,
    random_seed: int = 42,
    effective_day: float = 3,
) -> dict[str, Any]:
    """Compare four deterministic inventory strategies and persist their evidence."""
    return _invoke(
        "compare_inventory_replenishment_strategies",
        {
            "snapshot_id": snapshot_id,
            "horizon_days": horizon_days,
            "random_seed": random_seed,
            "effective_day": effective_day,
        },
    )


if __name__ == "__main__":
    mcp.run()
