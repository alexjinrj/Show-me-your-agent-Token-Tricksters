from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from agent_runtime.contracts import RuntimeToolResult

ToolAccess = Literal["read", "simulate", "propose", "write"]
ToolHandler = Callable[[dict[str, Any], str], RuntimeToolResult | BaseModel | dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    """One bounded business capability visible to an Agent runtime."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    access: ToolAccess = "read"
    groups: tuple[str, ...] = ()

    def public_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "access": self.access,
            "groups": list(self.groups),
        }


class ToolRegistry:
    """Runtime-neutral catalog that is the only route from an Agent to tools."""

    def __init__(self, tools: Iterable[RegisteredTool] = ()) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: RegisteredTool) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError(f"tool name must be non-empty and unique: {tool.name!r}")
        self._tools[tool.name] = tool

    def names(self, *, group: str | None = None) -> tuple[str, ...]:
        return tuple(
            name for name, tool in self._tools.items() if group is None or group in tool.groups
        )

    def catalog(self, *, group: str | None = None) -> list[dict[str, Any]]:
        return [self._tools[name].public_definition() for name in self.names(group=group)]

    def schemas(self, names: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
        selected = self.names() if names is None else tuple(names)
        return {name: self._require(name).input_schema for name in selected}

    def description(self, name: str) -> str:
        return self._require(name).description

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_case_id: str,
    ) -> RuntimeToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return RuntimeToolResult(
                tool_call_id=str(uuid4()),
                tool_name=name or "unknown",
                status="error",
                error_code="TOOL_NOT_REGISTERED",
                error_message="tool is not registered",
            )
        raw = tool.handler(arguments, agent_case_id)
        if isinstance(raw, RuntimeToolResult):
            return raw
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(mode="json", exclude_none=True)
        return RuntimeToolResult.model_validate(raw)

    def _require(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"tool is not registered: {name}") from exc
