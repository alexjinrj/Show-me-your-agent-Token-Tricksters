from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from business_coordinator.domain.models import UUIDString


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
    "create_simulation_session": CreateSessionInput,
    "get_simulation_state": SessionInput,
    "fork_simulation_session": ForkSessionInput,
    "add_simulation_event": AddEventInput,
    "run_simulation": RunInput,
    "compare_simulation_runs": CompareInput,
}
