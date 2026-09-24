from __future__ import annotations

from typing import Any


def summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    """Derive compact, persisted metrics from the full audited trace."""
    evidence = run.get("evidence", [])
    events = run.get("events", [])
    usage = run.get("model_usage", [])
    return {
        "schema_version": "agent-observability-v1",
        "run_status": run["status"],
        "tool_calls": len(evidence),
        "tool_errors": sum(item.get("status") == "error" for item in evidence),
        "rounds_with_tool_calls": len({item.get("round") for item in events}),
        "tools_used": [item.get("tool_name") for item in evidence],
        "reported_tokens": sum(
            value.get("total_tokens", 0)
            for value in usage
            if isinstance(value, dict) and isinstance(value.get("total_tokens"), int)
        ),
        "snapshot_id": run.get("snapshot_id"),
    }
