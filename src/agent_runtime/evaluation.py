from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseCriteria(BaseModel):
    """Explicit, deterministic acceptance criteria for one Agent run."""

    model_config = ConfigDict(extra="forbid")

    required_tools: tuple[str, ...] = Field(default=(), max_length=16)
    forbidden_tools: tuple[str, ...] = Field(default=(), max_length=16)
    require_completed: bool = True
    require_guardrails_passed: bool = False
    require_review_pending: bool = False


def evaluate_case(run: dict[str, Any], criteria: CaseCriteria) -> dict[str, Any]:
    successful = [
        item.get("tool_name") for item in run.get("evidence", [])
        if item.get("status") == "ok"
    ]
    all_tools = [item.get("tool_name") for item in run.get("evidence", [])]
    checks = {
        "completed": not criteria.require_completed or run.get("status") == "completed",
        "required_tools": all(name in successful for name in criteria.required_tools),
        "forbidden_tools": not any(name in all_tools for name in criteria.forbidden_tools),
        "guardrails": not criteria.require_guardrails_passed
        or (run.get("guardrails") or {}).get("status") == "passed",
        "human_review": not criteria.require_review_pending
        or (run.get("human_review") or {}).get("status") == "pending",
    }
    return {
        "schema_version": "agent-case-evaluation-v1",
        "agent_run_id": run.get("agent_run_id"),
        "passed": all(checks.values()),
        "checks": checks,
        "observed_tools": all_tools,
    }
