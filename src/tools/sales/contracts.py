from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.models import UUIDString


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotInput(ToolInput):
    snapshot_id: UUIDString


class ExceptionsInput(SnapshotInput):
    simulation_run_id: UUIDString | None = None
    top_n: int = Field(default=10, ge=1, le=50)


class BottleneckInput(SnapshotInput):
    simulation_run_id: UUIDString | None = None


class TraceInput(SnapshotInput):
    order_number: str = Field(min_length=1, max_length=80)
    simulation_run_id: UUIDString | None = None
    limit: int = Field(default=50, ge=1, le=100)


class HistoryInput(SnapshotInput):
    metric_code: Literal["backlog_count", "average_waiting_hours", "fulfilment_rate"]


class CreateSessionInput(SnapshotInput):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)


class SessionInput(ToolInput):
    simulation_session_id: UUIDString


class ForkSessionInput(SessionInput):
    name: str = Field(min_length=1, max_length=255)


class AddEventInput(SessionInput):
    event_type: Literal["warehouse_capacity_increase", "expedite_supplier_delivery"]
    workers: int | None = Field(default=None, ge=1, le=20)
    days: int | None = Field(default=None, ge=1, le=30)
    purchase_order_number: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def matching_fields(self) -> AddEventInput:
        if self.event_type == "warehouse_capacity_increase":
            if self.workers is None or self.days is not None or self.purchase_order_number:
                raise ValueError("warehouse event requires only workers")
        elif self.days is None or self.workers is not None:
            raise ValueError("supplier event requires days and optional purchase_order_number")
        return self


class RunInput(SessionInput):
    horizon_days: int = Field(ge=1, le=365)
    random_seed: int


class CompareInput(ToolInput):
    baseline_run_id: UUIDString
    alternative_run_id: UUIDString


SalesMetricCode = Literal[
    "ending_backlog",
    "average_waiting_hours",
    "fulfilment_rate",
    "stockout_count",
]


class AnalyzeBacklogInput(SnapshotInput):
    """One bounded diagnosis-to-simulation flow for the ORDER_BACKLOG exception."""

    additional_workers: int = Field(default=2, ge=1, le=20)
    horizon_days: int = Field(default=7, ge=1, le=365)
    random_seed: int = 42
    primary_metric: SalesMetricCode = "average_waiting_hours"
    guardrail_metrics: tuple[SalesMetricCode, ...] = (
        "ending_backlog",
        "fulfilment_rate",
        "stockout_count",
    )

    @model_validator(mode="after")
    def unique_evaluation_metrics(self) -> AnalyzeBacklogInput:
        if self.primary_metric in self.guardrail_metrics:
            raise ValueError("primary_metric must not also be a guardrail")
        if len(set(self.guardrail_metrics)) != len(self.guardrail_metrics):
            raise ValueError("guardrail_metrics must be unique")
        return self


class AnalysisCase(ToolInput):
    """Stable identifiers and controls for one auditable sales analysis execution."""

    schema_version: Literal["sales-analysis-case-v1"] = "sales-analysis-case-v1"
    analysis_case_id: UUIDString
    analysis_type: Literal["order_backlog_intervention"] = "order_backlog_intervention"
    status: Literal["completed"] = "completed"
    snapshot_id: UUIDString
    snapshot_hash: str = Field(min_length=64, max_length=64)
    baseline_run_id: UUIDString
    alternative_run_id: UUIDString
    horizon_days: int
    random_seed: int


class SalesEvidenceFacts(ToolInput):
    state_type: Literal["actual"] = "actual"
    snapshot_id: UUIDString
    snapshot_hash: str = Field(min_length=64, max_length=64)
    as_of_time: datetime
    sales_order_count: int = Field(ge=0)
    backlog_count: int = Field(ge=0)
    backlog_amount_sgd: Decimal
    backlog_by_node: dict[str, int]
    backlog_by_sku: dict[str, int]
    resources: tuple[dict[str, Any], ...]
    completeness: Literal["current_snapshot_only"] = "current_snapshot_only"


class CauseHypothesis(ToolInput):
    statement: str
    status: Literal["candidate_not_proven"] = "candidate_not_proven"
    basis: tuple[str, ...]


class InterventionSpec(ToolInput):
    owner_domain: Literal["operations"] = "operations"
    event_type: Literal["warehouse_capacity_increase"] = "warehouse_capacity_increase"
    parameter: Literal["warehouse_staff.capacity_delta"] = "warehouse_staff.capacity_delta"
    current_value: str
    proposed_value: str
    modification_point: dict[str, Decimal]


class MetricAssessment(ToolInput):
    baseline: Decimal
    alternative: Decimal
    difference: Decimal
    direction: Literal["lower", "higher"]
    materiality_threshold: Decimal
    outcome: Literal["improved", "worsened", "unchanged"]


class SalesSimulationComparison(ToolInput):
    state_type: Literal["simulated"] = "simulated"
    baseline_run_id: UUIDString
    alternative_run_id: UUIDString
    snapshot_hash: str = Field(min_length=64, max_length=64)
    horizon_days: int
    random_seed: int
    primary_metric: SalesMetricCode
    guardrail_metrics: tuple[SalesMetricCode, ...]
    metrics: dict[SalesMetricCode, MetricAssessment]
    verdict: Literal["improved", "worsened", "trade_off", "no_material_change"]


class SalesAnalysisResult(ToolInput):
    """Facts, hypothesis, intervention and counterfactual evidence kept separate."""

    schema_version: Literal["sales-analysis-result-v1"] = "sales-analysis-result-v1"
    analysis_case: AnalysisCase
    facts: SalesEvidenceFacts
    cause_hypothesis: CauseHypothesis
    intervention: InterventionSpec
    simulation_comparison: SalesSimulationComparison
    actual_state_unchanged: bool
    limitations: tuple[str, ...]


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: UUIDString
    tool_name: str
    status: Literal["ok", "error"]
    state_type: Literal["actual", "simulated"] | None = None
    reference_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


TOOL_INPUTS: dict[str, type[ToolInput]] = {
    "get_actual_state_summary": SnapshotInput,
    "list_exceptions": ExceptionsInput,
    "trace_process_bottleneck": BottleneckInput,
    "trace_business_object": TraceInput,
    "get_metric_history": HistoryInput,
    "analyze_sales_backlog_intervention": AnalyzeBacklogInput,
    "create_simulation_session": CreateSessionInput,
    "get_simulation_state": SessionInput,
    "fork_simulation_session": ForkSessionInput,
    "add_simulation_event": AddEventInput,
    "run_simulation": RunInput,
    "compare_simulation_runs": CompareInput,
}
