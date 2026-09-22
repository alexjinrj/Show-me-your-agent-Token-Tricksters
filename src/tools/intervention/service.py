from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import SnapshotBundle
from core.simulation import warehouse_capacity_increase
from enterprise_state.service import ActualStateService
from tools.crm.service import CRMService
from tools.simulation.service import SimulationService


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CapacityInput(StrictInput):
    snapshot_id: str = Field(min_length=1, max_length=80)
    additional_workers: int = Field(default=2, ge=1, le=20)
    horizon_days: int = Field(default=30, ge=1, le=365)
    random_seed: int = 42


class CRMServiceCapacityInput(CapacityInput):
    complaint_id: str = Field(min_length=1, max_length=100)


class CRMInterventionTools:
    """Run reproducible capacity counterfactuals from one immutable snapshot.

    The current snapshot supports a bottleneck hypothesis, not a historical causal
    conclusion. Both tools persist baseline and alternative runs for later audit.
    """

    def __init__(self, actual: ActualStateService, simulations: SimulationService, crm: CRMService):
        self.actual = actual
        self.simulations = simulations
        self.crm = crm

    @staticmethod
    def schemas() -> dict[str, dict[str, Any]]:
        return {
            "analyze_crm_service_capacity": CRMServiceCapacityInput.model_json_schema(),
        }

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "analyze_crm_service_capacity":
            parsed = CRMServiceCapacityInput.model_validate(arguments)
            if parsed.snapshot_id != self.crm.reference_id:
                raise ValueError("CRM case and requested snapshot do not match")
            return self._run(parsed, self.crm.investigate(parsed.complaint_id))
        raise ValueError("intervention tool is not registered")

    def _run(
        self,
        request: CapacityInput,
        crm_case: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self.actual.load_snapshot(request.snapshot_id)
        facts = self._facts(snapshot)
        if facts["backlog_count"] == 0:
            raise ValueError("No current backlog exists to support this intervention test")

        baseline_session = self.simulations.create_session(
            request.snapshot_id,
            f"CRM {crm_case['complaintId']}: baseline",
            "No intervention; comparison control.",
        )
        alternative_session = self.simulations.fork_session(
            baseline_session.simulation_session_id,
            f"CRM {crm_case['complaintId']}: warehouse +{request.additional_workers}",
        )
        event = warehouse_capacity_increase(workers=request.additional_workers)
        self.simulations.add_event(alternative_session.simulation_session_id, event)
        baseline = self.simulations.run_session(
            baseline_session.simulation_session_id,
            snapshot,
            horizon_days=request.horizon_days,
            random_seed=request.random_seed,
        )
        alternative = self.simulations.run_session(
            alternative_session.simulation_session_id,
            snapshot,
            horizon_days=request.horizon_days,
            random_seed=request.random_seed,
        )
        metrics = self.simulations.compare_runs(baseline, alternative)
        evaluation = self._evaluate(metrics)
        result: dict[str, Any] = {
            "analysis_flow": "crm_service_capacity",
            "facts": facts,
            "cause_hypothesis": {
                "statement": "Warehouse processing capacity may contribute to current backlog.",
                "status": "candidate_not_proven",
                "basis": [
                    "Current snapshot contains backlog orders.",
                    "The counterfactual changes warehouse staff capacity only.",
                ],
            },
            "intervention": {
                "event_type": "warehouse_capacity_increase",
                "parameter": "warehouse_staff.capacity_delta",
                "current_value": "0 additional workers",
                "proposed_value": f"{request.additional_workers} additional workers",
                "modification_point": {"effective_day": "0"},
            },
            "simulation_comparison": {
                "baseline_run_id": baseline.simulation_run_id,
                "alternative_run_id": alternative.simulation_run_id,
                "snapshot_hash": baseline.snapshot_hash,
                "horizon_days": baseline.horizon_days,
                "random_seed": baseline.random_seed,
                "metrics": metrics,
                "evaluation": evaluation,
            },
            "actual_state_unchanged": True,
            "limitations": [
                "Current snapshot evidence does not prove historical causation.",
                "The scenario changes warehouse staff only and holds model assumptions fixed.",
                "Simulated improvement is counterfactual evidence, not a promised outcome.",
            ],
        }
        result["crm_case"] = crm_case
        result["limitations"].append(
            "The CRM case is a derived order-service exception, not an imported complaint."
        )
        return result

    @staticmethod
    def _facts(snapshot: SnapshotBundle) -> dict[str, Any]:
        orders = [
            record.data
            for record in snapshot.records
            if record.record_type == "business_object"
            and record.data.get("object_type") == "sales_order"
        ]
        backlog = [row for row in orders if row.get("status") in {"open", "backlog"}]
        resources = [
            record.data
            for record in snapshot.records
            if record.record_type == "resource" and record.data.get("process_id") == "order_to_cash"
        ]
        return {
            "snapshot_id": snapshot.manifest.snapshot_id,
            "snapshot_hash": snapshot.manifest.content_hash,
            "as_of": snapshot.manifest.as_of_time,
            "sales_order_count": len(orders),
            "backlog_count": len(backlog),
            "backlog_amount": sum((Decimal(str(row["amount"])) for row in backlog), Decimal("0")),
            "backlog_by_node": dict(
                sorted(Counter(str(row["current_node_id"]) for row in backlog).items())
            ),
            "resources": [
                {
                    "node_id": row["node_id"],
                    "resource_type": row["resource_type"],
                    "capacity_units": row["capacity_units"],
                    "data_origin": row.get("data_origin"),
                }
                for row in resources
            ],
            "scope": "Current immutable snapshot; no complete historical transition series.",
        }

    @staticmethod
    def _evaluate(metrics: dict[str, dict[str, Decimal]]) -> dict[str, Any]:
        directions: dict[str, Literal["lower", "higher"]] = {
            "ending_backlog": "lower",
            "average_waiting_hours": "lower",
            "fulfilment_rate": "higher",
        }
        outcomes: dict[str, str] = {}
        improved = worsened = 0
        for metric, direction in directions.items():
            difference = metrics[metric]["difference"]
            if difference == 0:
                outcome = "unchanged"
            elif (direction == "lower" and difference < 0) or (
                direction == "higher" and difference > 0
            ):
                outcome = "improved"
                improved += 1
            else:
                outcome = "worsened"
                worsened += 1
            outcomes[metric] = outcome
        overall = (
            "improved"
            if improved and not worsened
            else "worsened"
            if worsened and not improved
            else "mixed"
            if improved or worsened
            else "no_material_change"
        )
        return {"overall": overall, "metric_outcomes": outcomes}
