from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from core.serialization import canonical_data, canonical_hash
from core.simulation import (
    expedited_supplier_delivery,
    warehouse_capacity_increase,
)
from enterprise_state.models import (
    BusinessEventRow,
    SimulationResultRow,
    SimulationRunRow,
    ToolCallAuditRow,
)
from enterprise_state.service import ActualStateService
from tools.sales.analysis import SalesAnalysisService
from tools.sales.contracts import (
    TOOL_INPUTS,
    AddEventInput,
    AnalyzeBacklogInput,
    BottleneckInput,
    CompareInput,
    CreateSessionInput,
    ExceptionsInput,
    ForkSessionInput,
    HistoryInput,
    RunInput,
    SessionInput,
    SnapshotInput,
    ToolInput,
    ToolResponse,
    TraceInput,
)
from tools.simulation.service import SimulationService


def _event_time(event: BusinessEventRow) -> datetime:
    """SQLite drops timezone data, so prefer the source payload's timestamp."""
    source_time = event.payload.get("order_date")
    parsed = (
        datetime.fromisoformat(source_time)
        if isinstance(source_time, str)
        else event.business_timestamp
    )
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class SalesAgentTools:
    """A bounded, audited tool surface for the team's single Coordinator Agent."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.actual = ActualStateService(engine)
        self.simulations = SimulationService(engine)
        self.analysis = SalesAnalysisService(self.actual, self.simulations)

    @staticmethod
    def schemas() -> dict[str, dict[str, Any]]:
        return {name: model.model_json_schema() for name, model in TOOL_INPUTS.items()}

    def call(
        self, tool_name: str, arguments: dict[str, Any], *, agent_case_id: str
    ) -> ToolResponse:
        if not agent_case_id or len(agent_case_id) > 80:
            raise ValueError("agent_case_id must contain 1 to 80 characters")
        started = time.perf_counter()
        call_id = str(uuid4())
        response: ToolResponse
        try:
            model = TOOL_INPUTS.get(tool_name)
            if model is None:
                raise ValueError("tool is not registered")
            parsed = model.model_validate(arguments)
            data, state_type, reference = self._dispatch(tool_name, parsed)
            response = ToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="ok",
                state_type=state_type,
                reference_id=reference,
                data=canonical_data(data),
            )
        except (ValueError, ValidationError) as exc:
            response = ToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="error",
                error_code="INVALID_INPUT" if isinstance(exc, ValidationError) else "NOT_AVAILABLE",
                error_message=str(exc),
            )
        except Exception:
            response = ToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="error",
                error_code="INTERNAL_ERROR",
                error_message="Tool execution failed.",
            )
        elapsed = max(0, round((time.perf_counter() - started) * 1000))
        with Session(self.engine) as database, database.begin():
            database.add(
                ToolCallAuditRow(
                    id=call_id,
                    agent_case_id=agent_case_id,
                    tool_name=tool_name[:80],
                    argument_hash=canonical_hash(arguments),
                    result_reference=response.reference_id,
                    result_hash=canonical_hash(response.data) if response.status == "ok" else None,
                    status=response.status,
                    error_code=response.error_code,
                    duration_ms=elapsed,
                    created_at=datetime.now(UTC),
                )
            )
        return response

    def _snapshot(self, snapshot_id: str) -> Any:
        return self.actual.load_snapshot(snapshot_id)

    def _run(self, run_id: str) -> tuple[SimulationRunRow, SimulationResultRow]:
        with Session(self.engine) as database:
            run = database.get(SimulationRunRow, run_id)
            if run is None:
                raise ValueError("simulation run does not exist")
            result = database.scalar(
                select(SimulationResultRow).where(SimulationResultRow.simulation_run_id == run_id)
            )
            if result is None:
                raise ValueError("simulation result does not exist")
            database.expunge(run)
            database.expunge(result)
            return run, result

    def _checked_run(
        self, run_id: str, snapshot_id: str
    ) -> tuple[SimulationRunRow, SimulationResultRow]:
        snapshot = self._snapshot(snapshot_id)
        run, result = self._run(run_id)
        if run.snapshot_hash != snapshot.manifest.content_hash:
            raise ValueError("simulation run belongs to another snapshot")
        return run, result

    def _orders(self, snapshot_id: str) -> list[dict[str, Any]]:
        bundle = self._snapshot(snapshot_id)
        return [
            record.data
            for record in bundle.records
            if record.record_type == "business_object"
            and record.data.get("process_id") == "order_to_cash"
            and record.data.get("object_type") == "sales_order"
        ]

    @staticmethod
    def _backlog(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [order for order in orders if order.get("status") in {"backlog", "open"}]

    def _dispatch(
        self, name: str, args: ToolInput
    ) -> tuple[dict[str, Any], Literal["actual", "simulated"], str]:
        if name == "get_actual_state_summary":
            assert isinstance(args, SnapshotInput)
            bundle = self._snapshot(args.snapshot_id)
            orders = self._orders(args.snapshot_id)
            backlog = self._backlog(orders)
            nodes = dict(sorted(Counter(str(o["current_node_id"]) for o in orders).items()))
            skus = dict(
                sorted(Counter(str(o.get("details", {}).get("sku", "")) for o in backlog).items())
            )
            return (
                {
                    "snapshot_id": args.snapshot_id,
                    "snapshot_hash": bundle.manifest.content_hash,
                    "as_of_time": bundle.manifest.as_of_time,
                    "sales_order_count": len(orders),
                    "backlog_count": len(backlog),
                    "backlog_amount_sgd": sum(
                        (Decimal(str(o["amount"])) for o in backlog), Decimal("0")
                    ),
                    "orders_by_node": nodes,
                    "backlog_by_sku": skus,
                    "data_origin_counts": dict(
                        sorted(
                            Counter(str(o.get("data_origin", "unknown")) for o in orders).items()
                        )
                    ),
                    "history_note": (
                        "Current imported status only; no full actual node-transition history."
                    ),
                },
                "actual",
                args.snapshot_id,
            )
        if name == "list_exceptions":
            assert isinstance(args, ExceptionsInput)
            backlog = self._backlog(self._orders(args.snapshot_id))
            by_sku = Counter(str(o.get("details", {}).get("sku", "")) for o in backlog)
            exceptions: list[dict[str, Any]] = (
                [
                    {
                        "code": "ORDER_BACKLOG",
                        "count": len(backlog),
                        "evidence_order_numbers": sorted(str(o["object_number"]) for o in backlog)[
                            : args.top_n
                        ],
                    }
                ]
                if backlog
                else []
            )
            state_type: Literal["actual", "simulated"] = "actual"
            reference = args.snapshot_id
            if args.simulation_run_id:
                _, result = self._checked_run(args.simulation_run_id, args.snapshot_id)
                metrics = result.summary_metrics
                exceptions = [
                    {"code": "SIMULATED_ENDING_BACKLOG", "count": metrics["ending_backlog"]},
                    {"code": "SIMULATED_STOCKOUT", "count": metrics["stockout_count"]},
                ]
                state_type = "simulated"
                reference = args.simulation_run_id
            return (
                {
                    "exceptions": exceptions[: args.top_n],
                    "backlog_by_sku": dict(sorted(by_sku.items()))
                    if state_type == "actual"
                    else {},
                    "rule": (
                        "Current sales-order backlog only; no inventory cause or historical "
                        "trend inferred."
                    ),
                },
                state_type,
                reference,
            )
        if name == "trace_process_bottleneck":
            assert isinstance(args, BottleneckInput)
            orders = self._orders(args.snapshot_id)
            backlog = self._backlog(orders)
            bundle = self._snapshot(args.snapshot_id)
            resources = [
                r.data
                for r in bundle.records
                if r.record_type == "resource" and r.data.get("process_id") == "order_to_cash"
            ]
            data: dict[str, Any] = {
                "process_id": "order_to_cash",
                "current_backlog_by_node": dict(
                    sorted(Counter(str(o["current_node_id"]) for o in backlog).items())
                ),
                "resources": [
                    {
                        "node_id": r["node_id"],
                        "resource_type": r["resource_type"],
                        "capacity_units": r["capacity_units"],
                        "data_origin": r.get("data_origin"),
                    }
                    for r in resources
                ],
                "actual_waiting_hours": None,
                "actual_waiting_note": "Not available without historical node-transition events.",
            }
            if args.simulation_run_id:
                _, result = self._checked_run(args.simulation_run_id, args.snapshot_id)
                data = {
                    "process_id": "order_to_cash",
                    "resource_utilization": result.summary_metrics["resource_utilization"],
                    "average_waiting_hours": result.summary_metrics["average_waiting_hours"],
                    "ending_backlog": result.summary_metrics["ending_backlog"],
                    "queue_by_node": None,
                    "queue_note": "Simulation result does not store a per-node queue series.",
                }
                return data, "simulated", args.simulation_run_id
            return data, "actual", args.snapshot_id
        if name == "trace_business_object":
            assert isinstance(args, TraceInput)
            bundle = self._snapshot(args.snapshot_id)
            order = next(
                (
                    o
                    for o in self._orders(args.snapshot_id)
                    if o["object_number"] == args.order_number
                ),
                None,
            )
            if order is None:
                raise ValueError("sales order not found in snapshot")
            if args.simulation_run_id:
                _, result = self._checked_run(args.simulation_run_id, args.snapshot_id)
                trace = [
                    event for event in result.event_trace if event.get("object_id") == order["id"]
                ]
                return (
                    {
                        "order_number": args.order_number,
                        "events": trace[: args.limit],
                        "total_events": len(trace),
                    },
                    "simulated",
                    args.simulation_run_id,
                )
            with Session(self.engine) as database:
                events = database.scalars(
                    select(BusinessEventRow)
                    .where(BusinessEventRow.object_id == order["id"])
                    .order_by(BusinessEventRow.business_timestamp, BusinessEventRow.id)
                ).all()
                actual_events = [
                    {
                        "event_id": e.id,
                        "event_type": e.event_type,
                        "business_timestamp": _event_time(e),
                        "source_record_id": e.source_record_id,
                        "data_origin": e.data_origin,
                    }
                    for e in events
                    if _event_time(e) <= bundle.manifest.as_of_time
                ]
            return (
                {
                    "order_number": args.order_number,
                    "current_node_id": order["current_node_id"],
                    "status": order["status"],
                    "events": actual_events[: args.limit],
                    "total_events": len(actual_events),
                    "history_complete": False,
                },
                "actual",
                args.snapshot_id,
            )
        if name == "get_metric_history":
            assert isinstance(args, HistoryInput)
            self._snapshot(args.snapshot_id)
            return (
                {
                    "metric_code": args.metric_code,
                    "availability": "not_available",
                    "reason": (
                        "Only imported current order status is stored; historical node "
                        "transitions and metric series are absent."
                    ),
                },
                "actual",
                args.snapshot_id,
            )
        if name == "analyze_sales_backlog_intervention":
            assert isinstance(args, AnalyzeBacklogInput)
            analysis_result = self.analysis.analyze_order_backlog(args)
            return (
                analysis_result.model_dump(mode="json"),
                "simulated",
                analysis_result.simulation_comparison.alternative_run_id,
            )
        if name == "create_simulation_session":
            assert isinstance(args, CreateSessionInput)
            self._snapshot(args.snapshot_id)
            session = self.simulations.create_session(args.snapshot_id, args.name, args.description)
            return session.model_dump(mode="json"), "simulated", session.simulation_session_id
        if name == "get_simulation_state":
            assert isinstance(args, SessionInput)
            session = self.simulations.get_session(args.simulation_session_id)
            return session.model_dump(mode="json"), "simulated", session.simulation_session_id
        if name == "fork_simulation_session":
            assert isinstance(args, ForkSessionInput)
            session = self.simulations.fork_session(args.simulation_session_id, args.name)
            return session.model_dump(mode="json"), "simulated", session.simulation_session_id
        if name == "add_simulation_event":
            assert isinstance(args, AddEventInput)
            session = self.simulations.get_session(args.simulation_session_id)
            bundle = self._snapshot(session.base_snapshot_id)
            if args.event_type == "warehouse_capacity_increase":
                assert args.workers is not None
                event = warehouse_capacity_increase(workers=args.workers)
                warning = None
            else:
                assert args.days is not None
                open_pos = sorted(
                    (
                        r.data
                        for r in bundle.records
                        if r.record_type == "business_object"
                        and r.data.get("object_type") == "purchase_order"
                        and r.data.get("status") == "open"
                    ),
                    key=lambda p: (
                        str(p.get("details", {}).get("due_date", "")),
                        str(p["object_number"]),
                    ),
                )
                target = next(
                    (
                        p
                        for p in open_pos
                        if args.purchase_order_number is None
                        or p["object_number"] == args.purchase_order_number
                    ),
                    None,
                )
                if target is None:
                    raise ValueError("no matching open purchase order in snapshot")
                event = expedited_supplier_delivery(str(target["object_number"]), days=args.days)
                backlog_skus = {
                    str(o.get("details", {}).get("sku", ""))
                    for o in self._backlog(self._orders(session.base_snapshot_id))
                }
                target_sku = str(target.get("details", {}).get("sku", ""))
                warning = (
                    None
                    if target_sku in backlog_skus
                    else (
                        "Selected purchase order SKU is not among current backlog SKUs; "
                        "do not claim it resolves that backlog."
                    )
                )
            updated = self.simulations.add_event(args.simulation_session_id, event)
            return (
                {
                    "simulation_session_id": updated.simulation_session_id,
                    "event": event.model_dump(mode="json"),
                    "warning": warning,
                },
                "simulated",
                updated.simulation_session_id,
            )
        if name == "run_simulation":
            assert isinstance(args, RunInput)
            session = self.simulations.get_session(args.simulation_session_id)
            bundle = self._snapshot(session.base_snapshot_id)
            simulation_result = self.simulations.run_session(
                args.simulation_session_id,
                bundle,
                horizon_days=args.horizon_days,
                random_seed=args.random_seed,
            )
            return (
                {
                    "simulation_run_id": simulation_result.simulation_run_id,
                    "snapshot_hash": simulation_result.snapshot_hash,
                    "scenario_event_hash": simulation_result.scenario_event_hash,
                    "result_hash": simulation_result.result_hash,
                    "horizon_days": simulation_result.horizon_days,
                    "random_seed": simulation_result.random_seed,
                    "summary_metrics": simulation_result.summary_metrics.model_dump(mode="json"),
                },
                "simulated",
                simulation_result.simulation_run_id,
            )
        if name == "compare_simulation_runs":
            assert isinstance(args, CompareInput)
            baseline, base_result = self._run(args.baseline_run_id)
            alternative, alt_result = self._run(args.alternative_run_id)
            if (
                baseline.snapshot_hash,
                baseline.horizon_days,
                baseline.random_seed,
                baseline.process_definition_hash,
            ) != (
                alternative.snapshot_hash,
                alternative.horizon_days,
                alternative.random_seed,
                alternative.process_definition_hash,
            ):
                raise ValueError("runs must share snapshot, horizon, seed, and process definition")
            comparison = {}
            for key in (
                "ending_backlog",
                "average_waiting_hours",
                "fulfilment_rate",
                "stockout_count",
                "gross_profit",
                "accounts_receivable",
                "accounts_payable",
                "ending_cash",
                "minimum_cash",
            ):
                first = Decimal(str(base_result.summary_metrics[key]))
                second = Decimal(str(alt_result.summary_metrics[key]))
                comparison[key] = {
                    "baseline": first,
                    "alternative": second,
                    "difference": second - first,
                }
            return (
                {
                    "baseline_run_id": baseline.id,
                    "alternative_run_id": alternative.id,
                    "snapshot_hash": baseline.snapshot_hash,
                    "horizon_days": baseline.horizon_days,
                    "random_seed": baseline.random_seed,
                    "metrics": comparison,
                },
                "simulated",
                alternative.id,
            )
        raise ValueError("tool is not registered")
