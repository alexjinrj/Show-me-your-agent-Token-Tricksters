from __future__ import annotations

from typing import Any

from agent_runtime.executor import ToolExecutor
from agent_runtime.registry import RegisteredTool, ToolRegistry


def test_write_policy_is_enforced_before_handler() -> None:
    invoked: list[bool] = []

    def handler(arguments: dict[str, Any], case_id: str) -> dict[str, Any]:
        invoked.append(True)
        raise AssertionError("Write handler must never execute")

    registry = ToolRegistry(
        [
            RegisteredTool(
                name="write_inventory",
                description="forbidden",
                input_schema={},
                handler=handler,
                access="write",
            )
        ]
    )
    executor = ToolExecutor(registry, lambda arguments, snapshot: None)
    result = executor.execute("write_inventory", {}, snapshot_id="snapshot", run_id="run")
    assert result.status == "error"
    assert result.error_message == "ACCESS_DENIED"
    assert invoked == []
