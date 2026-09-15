from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from core.models import (
    ScenarioEvent,
    ScenarioEventType,
    SimulationRunResult,
    SimulationSession,
    SnapshotBundle,
)
from core.simulation.engine import run_simulation
from enterprise_state.models import (
    AccountingImpactRow,
    SimulationEventRow,
    SimulationResultRow,
    SimulationRunRow,
    SimulationSessionRow,
    StateSnapshotRow,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SimulationService:
    """Persist scenario metadata while keeping execution detached from ORM state."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_session(
        self, base_snapshot_id: str, name: str, description: str = ""
    ) -> SimulationSession:
        with Session(self.engine) as database, database.begin():
            if database.get(StateSnapshotRow, base_snapshot_id) is None:
                raise ValueError("base snapshot does not exist")
            session_id = str(uuid.uuid4())
            database.add(
                SimulationSessionRow(
                    id=session_id,
                    base_snapshot_id=base_snapshot_id,
                    name=name,
                    description=description,
                    parent_session_id=None,
                    created_at=_utcnow(),
                    state_type="simulated",
                )
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SimulationSession:
        with Session(self.engine) as database:
            row = database.get(SimulationSessionRow, session_id)
            if row is None:
                raise ValueError("simulation session does not exist")
            events = database.scalars(
                select(SimulationEventRow)
                .where(SimulationEventRow.simulation_session_id == session_id)
                .order_by(SimulationEventRow.created_at, SimulationEventRow.id)
            ).all()
            return SimulationSession(
                simulation_session_id=row.id,
                base_snapshot_id=row.base_snapshot_id,
                name=row.name,
                description=row.description,
                parent_session_id=row.parent_session_id,
                scenario_events=tuple(
                    ScenarioEvent(
                        event_type=cast(ScenarioEventType, event.event_type),
                        effective_day=event.effective_day,
                        payload=dict(event.payload),
                    )
                    for event in events
                ),
            )

    def add_event(self, session_id: str, event: ScenarioEvent) -> SimulationSession:
        with Session(self.engine) as database, database.begin():
            if database.get(SimulationSessionRow, session_id) is None:
                raise ValueError("simulation session does not exist")
            database.add(
                SimulationEventRow(
                    id=str(uuid.uuid4()),
                    simulation_session_id=session_id,
                    event_type=event.event_type,
                    effective_day=event.effective_day,
                    payload=event.model_dump(mode="json")["payload"],
                    created_at=_utcnow(),
                )
            )
        return self.get_session(session_id)

    def fork_session(self, session_id: str, name: str) -> SimulationSession:
        parent = self.get_session(session_id)
        child_id = str(uuid.uuid4())
        now = _utcnow()
        with Session(self.engine) as database, database.begin():
            database.add(
                SimulationSessionRow(
                    id=child_id,
                    base_snapshot_id=parent.base_snapshot_id,
                    name=name,
                    description=parent.description,
                    parent_session_id=parent.simulation_session_id,
                    created_at=now,
                    state_type="simulated",
                )
            )
            # Persist the child before copying events that reference it. This
            # makes foreign-key ordering explicit on SQLite and preserves the
            # fork lineage in the database rather than only in an API response.
            database.flush()
            for index, event in enumerate(parent.scenario_events):
                database.add(
                    SimulationEventRow(
                        id=str(uuid.uuid4()),
                        simulation_session_id=child_id,
                        event_type=event.event_type,
                        effective_day=event.effective_day,
                        payload=event.model_dump(mode="json")["payload"],
                        created_at=now.replace(microsecond=min(now.microsecond + index, 999999)),
                    )
                )
        return self.get_session(child_id)

    def run_session(
        self,
        session_id: str,
        snapshot: SnapshotBundle,
        *,
        horizon_days: int,
        random_seed: int,
    ) -> SimulationRunResult:
        configured = self.get_session(session_id)
        if configured.base_snapshot_id != snapshot.manifest.snapshot_id:
            raise ValueError("snapshot does not match the simulation session")
        result = run_simulation(
            snapshot,
            list(configured.scenario_events),
            horizon_days,
            random_seed,
        )
        persisted_run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{result.result_hash}"))
        result = result.model_copy(update={"simulation_run_id": persisted_run_id})
        with Session(self.engine) as database, database.begin():
            existing = database.get(SimulationRunRow, persisted_run_id)
            if existing is None:
                database.add(
                    SimulationRunRow(
                        id=result.simulation_run_id,
                        simulation_session_id=session_id,
                        snapshot_hash=result.snapshot_hash,
                        process_definition_version=result.process_definition_version,
                        process_definition_hash=result.process_definition_hash,
                        scenario_event_hash=result.scenario_event_hash,
                        horizon_days=result.horizon_days,
                        random_seed=result.random_seed,
                        result_hash=result.result_hash,
                        status=result.status,
                        created_at=_utcnow(),
                    )
                )
                database.flush()
                database.add(
                    SimulationResultRow(
                        id=str(uuid.uuid4()),
                        simulation_run_id=result.simulation_run_id,
                        summary_metrics=result.summary_metrics.model_dump(mode="json"),
                        event_trace=[event.model_dump(mode="json") for event in result.event_trace],
                    )
                )
                for impact in result.accounting_impacts:
                    database.add(
                        AccountingImpactRow(
                            id=str(uuid.uuid4()),
                            simulation_run_id=result.simulation_run_id,
                            event_type=impact.event_type,
                            object_id=impact.object_id,
                            simulated_hour=impact.simulated_hour,
                            lines=[line.model_dump(mode="json") for line in impact.lines],
                        )
                    )
        return result

    def compare_runs(
        self, baseline: SimulationRunResult, alternative: SimulationRunResult
    ) -> dict[str, dict[str, Decimal]]:
        keys = (
            "ending_backlog",
            "average_waiting_hours",
            "fulfilment_rate",
            "stockout_count",
            "ending_inventory_quantity",
            "ending_inventory_value",
            "revenue",
            "cost_of_goods_sold",
            "gross_profit",
            "accounts_receivable",
            "accounts_payable",
            "ending_cash",
            "minimum_cash",
        )
        first = baseline.summary_metrics.model_dump(mode="python")
        second = alternative.summary_metrics.model_dump(mode="python")
        comparison: dict[str, dict[str, Decimal]] = {}
        for key in keys:
            baseline_value = Decimal(str(first[key]))
            alternative_value = Decimal(str(second[key]))
            comparison[key] = {
                "baseline": baseline_value,
                "alternative": alternative_value,
                "difference": alternative_value - baseline_value,
            }
        baseline_utilization = first["resource_utilization"]
        alternative_utilization = second["resource_utilization"]
        for resource in sorted(set(baseline_utilization) | set(alternative_utilization)):
            baseline_value = Decimal(str(baseline_utilization.get(resource, 0)))
            alternative_value = Decimal(str(alternative_utilization.get(resource, 0)))
            comparison[f"resource_utilization.{resource}"] = {
                "baseline": baseline_value,
                "alternative": alternative_value,
                "difference": alternative_value - baseline_value,
            }
        return comparison
