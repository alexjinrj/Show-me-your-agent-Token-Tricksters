from __future__ import annotations

import uuid
from collections import Counter
from decimal import Decimal
from typing import Any, Literal, Protocol

from core.models import SnapshotBundle
from core.serialization import canonical_hash
from core.simulation import warehouse_capacity_increase
from enterprise_state.service import ActualStateService
from tools.sales.contracts import (
    AnalysisCase,
    AnalyzeBacklogInput,
    CauseHypothesis,
    InterventionSpec,
    MetricAssessment,
    SalesAnalysisResult,
    SalesEvidenceFacts,
    SalesMetricCode,
    SalesSimulationComparison,
)
from tools.simulation.service import SimulationService

ANALYSIS_NAMESPACE = uuid.UUID("14a585c6-58aa-4e3a-b8b1-096f8611ec85")

MetricDirection = Literal["lower", "higher"]
SalesVerdict = Literal["improved", "worsened", "trade_off", "no_material_change"]
METRIC_POLICY: dict[SalesMetricCode, tuple[MetricDirection, Decimal]] = {
    "ending_backlog": ("lower", Decimal("1")),
    "average_waiting_hours": ("lower", Decimal("0.01")),
    "fulfilment_rate": ("higher", Decimal("0.0001")),
    "stockout_count": ("lower", Decimal("1")),
}


class SalesEvidenceProvider(Protocol):
    """Replaceable evidence boundary for current snapshots and future history retrieval."""

    def backlog_facts(self, snapshot_id: str) -> SalesEvidenceFacts: ...


class SnapshotSalesEvidenceProvider:
    """Temporary bounded provider backed by one immutable current-state snapshot."""

    def __init__(self, actual: ActualStateService) -> None:
        self.actual = actual

    def backlog_facts(self, snapshot_id: str) -> SalesEvidenceFacts:
        snapshot = self.actual.load_snapshot(snapshot_id)
        orders = _sales_orders(snapshot)
        backlog = [row for row in orders if row.get("status") in {"open", "backlog"}]
        resources = tuple(
            {
                "node_id": row.data["node_id"],
                "resource_type": row.data["resource_type"],
                "capacity_units": row.data["capacity_units"],
                "data_origin": row.data.get("data_origin"),
            }
            for row in snapshot.records
            if row.record_type == "resource" and row.data.get("process_id") == "order_to_cash"
        )
        return SalesEvidenceFacts(
            snapshot_id=snapshot.manifest.snapshot_id,
            snapshot_hash=snapshot.manifest.content_hash,
            as_of_time=snapshot.manifest.as_of_time,
            sales_order_count=len(orders),
            backlog_count=len(backlog),
            backlog_amount_sgd=sum((Decimal(str(row["amount"])) for row in backlog), Decimal("0")),
            backlog_by_node=dict(
                sorted(Counter(str(row["current_node_id"]) for row in backlog).items())
            ),
            backlog_by_sku=dict(
                sorted(
                    Counter(str(row.get("details", {}).get("sku", "")) for row in backlog).items()
                )
            ),
            resources=resources,
        )


def _sales_orders(snapshot: SnapshotBundle) -> list[dict[str, Any]]:
    return [
        record.data
        for record in snapshot.records
        if record.record_type == "business_object"
        and record.data.get("process_id") == "order_to_cash"
        and record.data.get("object_type") == "sales_order"
    ]


def evaluate_sales_metrics(
    metrics: dict[str, dict[str, Decimal]],
    selected: tuple[SalesMetricCode, ...],
) -> tuple[dict[SalesMetricCode, MetricAssessment], SalesVerdict]:
    assessments: dict[SalesMetricCode, MetricAssessment] = {}
    improved = worsened = 0
    for metric in selected:
        direction, threshold = METRIC_POLICY[metric]
        values = metrics[metric]
        difference = Decimal(str(values["difference"]))
        if abs(difference) < threshold:
            outcome: Literal["improved", "worsened", "unchanged"] = "unchanged"
        elif (direction == "lower" and difference < 0) or (
            direction == "higher" and difference > 0
        ):
            outcome = "improved"
            improved += 1
        else:
            outcome = "worsened"
            worsened += 1
        assessments[metric] = MetricAssessment(
            baseline=Decimal(str(values["baseline"])),
            alternative=Decimal(str(values["alternative"])),
            difference=difference,
            direction=direction,
            materiality_threshold=threshold,
            outcome=outcome,
        )
    verdict: SalesVerdict = (
        "trade_off"
        if improved and worsened
        else "improved"
        if improved
        else "worsened"
        if worsened
        else "no_material_change"
    )
    return assessments, verdict


class SalesAnalysisService:
    """Deterministic ORDER_BACKLOG diagnosis-to-simulation orchestration."""

    def __init__(
        self,
        actual: ActualStateService,
        simulations: SimulationService,
        evidence: SalesEvidenceProvider | None = None,
    ) -> None:
        self.actual = actual
        self.simulations = simulations
        self.evidence = evidence or SnapshotSalesEvidenceProvider(actual)

    def analyze_order_backlog(self, request: AnalyzeBacklogInput) -> SalesAnalysisResult:
        actual_hash_before = self.actual.actual_state_hash()
        facts = self.evidence.backlog_facts(request.snapshot_id)
        if facts.backlog_count == 0:
            raise ValueError("No current ORDER_BACKLOG evidence exists in the requested snapshot")
        snapshot = self.actual.load_snapshot(request.snapshot_id)

        baseline_session = self.simulations.create_session(
            request.snapshot_id,
            "Sales ORDER_BACKLOG baseline",
            "No intervention; comparison control.",
        )
        alternative_session = self.simulations.fork_session(
            baseline_session.simulation_session_id,
            f"Sales ORDER_BACKLOG: warehouse +{request.additional_workers}",
        )
        self.simulations.add_event(
            alternative_session.simulation_session_id,
            warehouse_capacity_increase(workers=request.additional_workers),
        )
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
        raw_metrics = self.simulations.compare_runs(baseline, alternative)
        selected = (request.primary_metric, *request.guardrail_metrics)
        assessments, verdict = evaluate_sales_metrics(raw_metrics, selected)

        actual_unchanged = self.actual.actual_state_hash() == actual_hash_before
        if not actual_unchanged:
            raise RuntimeError("Simulation mutated Actual State")
        case_payload = {
            "snapshot_id": request.snapshot_id,
            "baseline_run_id": baseline.simulation_run_id,
            "alternative_run_id": alternative.simulation_run_id,
            "horizon_days": request.horizon_days,
            "random_seed": request.random_seed,
            "primary_metric": request.primary_metric,
            "guardrail_metrics": request.guardrail_metrics,
        }
        case_id = str(uuid.uuid5(ANALYSIS_NAMESPACE, canonical_hash(case_payload)))
        return SalesAnalysisResult(
            analysis_case=AnalysisCase(
                analysis_case_id=case_id,
                snapshot_id=request.snapshot_id,
                snapshot_hash=facts.snapshot_hash,
                baseline_run_id=baseline.simulation_run_id,
                alternative_run_id=alternative.simulation_run_id,
                horizon_days=request.horizon_days,
                random_seed=request.random_seed,
            ),
            facts=facts,
            cause_hypothesis=CauseHypothesis(
                statement="Warehouse processing capacity may contribute to current order backlog.",
                basis=(
                    "The current immutable snapshot contains ORDER_BACKLOG evidence.",
                    "The counterfactual changes warehouse staff capacity only.",
                ),
            ),
            intervention=InterventionSpec(
                current_value="0 additional workers",
                proposed_value=f"{request.additional_workers} additional workers",
                modification_point={"effective_day": Decimal("0")},
            ),
            simulation_comparison=SalesSimulationComparison(
                baseline_run_id=baseline.simulation_run_id,
                alternative_run_id=alternative.simulation_run_id,
                snapshot_hash=baseline.snapshot_hash,
                horizon_days=baseline.horizon_days,
                random_seed=baseline.random_seed,
                primary_metric=request.primary_metric,
                guardrail_metrics=request.guardrail_metrics,
                metrics=assessments,
                verdict=verdict,
            ),
            actual_state_unchanged=actual_unchanged,
            limitations=(
                "Current snapshot evidence does not prove historical causation.",
                "Historical state reconstruction remains unavailable.",
                "The scenario changes warehouse staff only and holds model assumptions fixed.",
                "A simulated improvement is counterfactual evidence, not a promised outcome.",
            ),
        )
