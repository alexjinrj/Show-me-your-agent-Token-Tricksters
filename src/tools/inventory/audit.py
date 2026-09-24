from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core.serialization import canonical_hash
from enterprise_state.models import ToolCallAuditRow
from tools.inventory.contracts import InventoryToolResponse


def record_inventory_tool_call(
    engine: Engine,
    response: InventoryToolResponse,
    arguments: dict[str, Any],
    *,
    agent_case_id: str,
    duration_ms: int,
) -> None:
    """Persist one Inventory Agent tool invocation."""

    with Session(engine) as database, database.begin():
        database.add(
            ToolCallAuditRow(
                id=response.tool_call_id,
                agent_case_id=agent_case_id,
                tool_name=response.tool_name[:80],
                argument_hash=canonical_hash(arguments),
                result_reference=response.reference_id,
                result_hash=(
                    canonical_hash(response.data)
                    if response.status == "ok"
                    else None
                ),
                status=response.status,
                error_code=response.error_code,
                duration_ms=max(0, duration_ms),
                created_at=datetime.now(UTC),
            )
        )