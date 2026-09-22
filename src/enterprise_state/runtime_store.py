from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from agent_runtime.contracts import RuntimeToolResult
from enterprise_state.models import (
    AgentRunRow,
    SimulationRunRow,
    SimulationSessionRow,
    ToolCallAuditRow,
)


class SQLRuntimeStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save(self, run: dict[str, Any]) -> None:
        with Session(self.engine) as db, db.begin():
            row = db.get(AgentRunRow, run["agent_run_id"])
            payload = json.loads(json.dumps(run))
            if row is None:
                db.add(
                    AgentRunRow(
                        id=run["agent_run_id"],
                        conversation_id=run["conversation_id"],
                        created_at=datetime.now(UTC),
                        payload=payload,
                    )
                )
            else:
                row.payload = payload

    def load(self, run_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.get(AgentRunRow, run_id)
            return dict(row.payload) if row else None

    def history(self, conversation_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            rows = db.scalars(
                select(AgentRunRow)
                .where(
                    AgentRunRow.conversation_id == conversation_id,
                )
                .order_by(AgentRunRow.created_at.desc(), AgentRunRow.id)
                .limit(7)
            ).all()
            messages: list[dict[str, Any]] = []
            for row in reversed(rows):
                if row.payload["status"] == "completed":
                    messages.extend(
                        [
                            {"role": "user", "content": row.payload["echo"][:8000]},
                            {"role": "assistant", "content": row.payload["reply"][:8000]},
                        ]
                    )
            return messages

    def check_scope(self, arguments: dict[str, Any], snapshot_id: str) -> None:
        if arguments.get("snapshot_id", snapshot_id) != snapshot_id:
            raise ValueError("Snapshot is outside request scope")
        with Session(self.engine) as db:
            session_id = arguments.get("simulation_session_id")
            if session_id:
                session = db.get(SimulationSessionRow, session_id)
                if session is None or session.base_snapshot_id != snapshot_id:
                    raise ValueError("Simulation session is outside request scope")
            for key in ("simulation_run_id", "baseline_run_id", "alternative_run_id"):
                run_id = arguments.get(key)
                if run_id:
                    run = db.get(SimulationRunRow, run_id)
                    session = (
                        db.get(SimulationSessionRow, run.simulation_session_id) if run else None
                    )
                    if session is None or session.base_snapshot_id != snapshot_id:
                        raise ValueError("Simulation run is outside request scope")
                    if key == "simulation_run_id" and session_id and session.id != session_id:
                        raise ValueError("Simulation run does not belong to the supplied session")

    def audit(
        self, result: RuntimeToolResult, arguments: dict[str, Any], run_id: str, duration: int
    ) -> None:
        def digest(value: Any) -> str:
            return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

        with Session(self.engine) as db, db.begin():
            # Sales already records the same tool_call_id; preserve its authoritative audit.
            if db.get(ToolCallAuditRow, result.tool_call_id) is None:
                db.add(
                    ToolCallAuditRow(
                        id=result.tool_call_id,
                        agent_case_id=run_id,
                        tool_name=result.tool_name[:80],
                        argument_hash=digest(arguments),
                        result_reference=result.reference_id,
                        result_hash=digest(result.model_dump(mode="json")),
                        status=result.status,
                        error_code=result.error_code,
                        duration_ms=duration,
                        created_at=datetime.now(UTC),
                    )
                )
