from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from agent_runtime.contracts import RuntimeToolResult
from agent_runtime.registry import ToolRegistry


class ToolExecutor:
    """Fail-closed business boundary, shared by Gateway handoff and MCP."""

    def __init__(
        self,
        registry: ToolRegistry,
        scope_check: Callable[[dict[str, Any], str], None],
        audit: Callable[[RuntimeToolResult, dict[str, Any], str, int], None] | None = None,
    ) -> None:
        self.registry = registry
        self.scope_check = scope_check
        self.audit = audit

    def execute(
        self, name: str, arguments: dict[str, Any], *, snapshot_id: str, run_id: str
    ) -> RuntimeToolResult:
        started = perf_counter()
        result = self._execute(name, arguments, snapshot_id=snapshot_id, run_id=run_id)
        if self.audit:
            self.audit(result, arguments, run_id, int((perf_counter() - started) * 1000))
        return result

    def _execute(
        self, name: str, arguments: dict[str, Any], *, snapshot_id: str, run_id: str
    ) -> RuntimeToolResult:
        try:
            definition = next((t for t in self.registry.catalog() if t["name"] == name), None)
            if definition is None:
                raise ValueError("TOOL_NOT_REGISTERED")
            if definition["access"] not in {"read", "simulate"}:
                raise ValueError("ACCESS_DENIED")
            self.scope_check(arguments, snapshot_id)
            return self.registry.call(name, arguments, agent_case_id=run_id)
        except ValueError as exc:
            return RuntimeToolResult(
                tool_call_id=str(uuid4()),
                tool_name=name or "unknown",
                status="error",
                error_code="TOOL_REJECTED",
                error_message=str(exc)[:300],
            )
        except Exception:
            # Never send SQL errors, paths or credentials to the model/browser.
            return RuntimeToolResult(
                tool_call_id=str(uuid4()),
                tool_name=name or "unknown",
                status="error",
                error_code="TOOL_FAILED",
                error_message="Business tool execution failed.",
            )
