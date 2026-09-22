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
from tools.retrieval.contracts import Dataset


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
        "crm_dataset_reference": runtime.context.crm.reference_id,
        "crm_provenance": runtime.context.crm.provenance(),
        "company_id": "SG-SME-001",
        "rules": [
            "Actual State is immutable and authoritative.",
            "Simulation results never modify Actual State.",
            "CRM shares the snapshot; cases are derived order exceptions, not complaints.",
            "CRM drafts and human-review records never execute contact, refunds or shipments.",
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
def analyze_sales_backlog_intervention(
    snapshot_id: str,
    additional_workers: int = 2,
    horizon_days: int = 7,
    random_seed: int = 42,
    primary_metric: Literal[
        "ending_backlog", "average_waiting_hours", "fulfilment_rate", "stockout_count"
    ] = "average_waiting_hours",
    guardrail_metrics: list[
        Literal["ending_backlog", "average_waiting_hours", "fulfilment_rate", "stockout_count"]
    ]
    | None = None,
) -> dict[str, Any]:
    """Run the bounded ORDER_BACKLOG diagnosis-to-capacity-simulation workflow."""

    return _invoke(
        "analyze_sales_backlog_intervention",
        {
            "snapshot_id": snapshot_id,
            "additional_workers": additional_workers,
            "horizon_days": horizon_days,
            "random_seed": random_seed,
            "primary_metric": primary_metric,
            "guardrail_metrics": guardrail_metrics
            if guardrail_metrics is not None
            else ["ending_backlog", "fulfilment_rate", "stockout_count"],
        },
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


@mcp.tool()
def get_crm_summary() -> dict[str, Any]:
    """Read the CRM service-recovery summary and data provenance."""
    return _invoke("get_crm_summary", {})


@mcp.tool()
def list_priority_complaints(limit: int = 10) -> dict[str, Any]:
    """List complaints by deterministic service priority."""
    return _invoke("list_priority_complaints", {"limit": limit})


@mcp.tool()
def get_customer_360(customer_id: str) -> dict[str, Any]:
    """Read customer value, relationship risk and complaint evidence."""
    return _invoke("get_customer_360", {"customer_id": customer_id})


@mcp.tool()
def get_complaint_detail(complaint_id: str) -> dict[str, Any]:
    """Read a derived order-service case, order deadline and priority."""
    return _invoke("get_complaint_detail", {"complaint_id": complaint_id})


@mcp.tool()
def get_order_timeline(complaint_id: str) -> dict[str, Any]:
    """Trace same-snapshot order dates and status for a derived service case."""
    return _invoke("get_order_timeline", {"complaint_id": complaint_id})


@mcp.tool()
def get_inventory_availability(complaint_id: str) -> dict[str, Any]:
    """Read same-snapshot SKU stock and derived pending-order obligations."""
    return _invoke("get_inventory_availability", {"complaint_id": complaint_id})


@mcp.tool()
def estimate_refund_impact(complaint_id: str) -> dict[str, Any]:
    """Read SGD order exposure and standard cost; payment/refund eligibility is unknown."""
    return _invoke("estimate_refund_impact", {"complaint_id": complaint_id})


@mcp.tool()
def compare_resolution_options(complaint_id: str) -> dict[str, Any]:
    """Compare service-recovery options without executing an action."""
    return _invoke("compare_resolution_options", {"complaint_id": complaint_id})


@mcp.tool()
def recommend_resolution(complaint_id: str) -> dict[str, Any]:
    """Investigate a complaint and return one grounded recommendation."""
    return _invoke("recommend_resolution", {"complaint_id": complaint_id})


@mcp.tool()
def draft_customer_reply(
    complaint_id: str,
    tone: Literal["professional", "empathetic"] = "empathetic",
) -> dict[str, Any]:
    """Create an unsent customer reply draft for human review."""
    return _invoke(
        "draft_customer_reply",
        {"complaint_id": complaint_id, "tone": tone},
    )


@mcp.tool()
def get_data_catalog() -> dict[str, Any]:
    """Read available fields and observed record-date coverage before analysis."""
    return _invoke("get_data_catalog", {})


@mcp.tool()
def query_snapshot_records(
    dataset: Dataset,
    filters: list[dict[str, Any]] | None = None,
    fields: list[str] | None = None,
    group_by: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str | None = None,
    sort_direction: Literal["asc", "desc"] = "desc",
    group_limit: int = 100,
    group_offset: int = 0,
) -> dict[str, Any]:
    """Read bounded snapshot records and full filtered totals; never reconstruct past state."""
    return _invoke(
        "query_snapshot_records",
        {
            "dataset": dataset,
            "filters": filters or [],
            "fields": fields or [],
            "group_by": group_by or [],
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "group_limit": group_limit,
            "group_offset": group_offset,
        },
    )


@mcp.tool()
def compare_snapshot_periods(
    query: dict[str, Any],
    date_field: str,
    baseline: dict[str, str],
    comparison: dict[str, str],
) -> dict[str, Any]:
    """Calculate two record-date period totals and differences, not causal conclusions."""
    return _invoke(
        "compare_snapshot_periods",
        {
            "query": query,
            "date_field": date_field,
            "baseline": baseline,
            "comparison": comparison,
        },
    )


@mcp.tool()
def query_enterprise_history(as_of: str) -> dict[str, Any]:
    """Reserved historical state API; explicitly returns NOT_IMPLEMENTED."""
    return _invoke("query_enterprise_history", {"as_of": as_of})


@mcp.tool()
def analyze_order_spikes(
    start: str,
    end: str,
    timezone: str = "Asia/Singapore",
    filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Find daily snapshot order peaks in a bounded local-calendar period."""
    return _invoke(
        "analyze_order_spikes",
        {"start": start, "end": end, "timezone": timezone, "filters": filters or []},
    )


@mcp.tool()
def search_public_events(
    start_date: str, end_date: str, country: str, topic: str = "retail_events", language: str = "zh"
) -> dict[str, Any]:
    """Find public event context; requires separately configured backend search key."""
    return _invoke(
        "search_public_events",
        {
            "start_date": start_date,
            "end_date": end_date,
            "country": country,
            "topic": topic,
            "language": language,
        },
    )


@mcp.tool()
def search_business_documents(
    query: str = "",
    entity_id: str | None = None,
    kind: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Retrieve uploaded source claims, not verified transactions; preserve synthetic labels."""
    return _invoke(
        "search_business_documents",
        {"query": query, "entity_id": entity_id, "kind": kind, "offset": offset, "limit": limit},
    )


@mcp.tool()
def analyze_crm_service_capacity(
    snapshot_id: str,
    complaint_id: str,
    additional_workers: int = 2,
    horizon_days: int = 30,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Test one CRM service-risk capacity intervention; does not prove historical cause."""
    return _invoke(
        "analyze_crm_service_capacity",
        {
            "snapshot_id": snapshot_id,
            "complaint_id": complaint_id,
            "additional_workers": additional_workers,
            "horizon_days": horizon_days,
            "random_seed": random_seed,
        },
    )


if __name__ == "__main__":
    mcp.run()
