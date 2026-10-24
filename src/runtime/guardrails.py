from __future__ import annotations

from typing import Any


def evaluate_run(run: dict[str, Any]) -> dict[str, Any]:
    """Check machine-verifiable runtime and sales-simulation invariants."""
    checks: list[dict[str, str]] = []
    prompt_security = run.get("prompt_security") or {}
    if prompt_security:
        checks.append(
            {
                "name": "prompt_injection",
                "status": "blocked" if prompt_security.get("status") == "blocked" else "passed",
            }
        )
    if run.get("security_events"):
        checks.append({"name": "indirect_prompt_injection", "status": "passed"})
    for evidence in run.get("evidence", []):
        if evidence.get("tool_name") != "analyze_sales_backlog_intervention":
            continue
        if evidence.get("status") != "ok":
            checks.append({"name": "sales_analysis_tool", "status": "not_evaluated"})
            continue
        data = evidence.get("data") or {}
        facts = data.get("facts") or {}
        case = data.get("analysis_case") or {}
        comparison = data.get("simulation_comparison") or {}
        valid = (
            data.get("schema_version") == "sales-analysis-result-v1"
            and facts.get("state_type") == "actual"
            and comparison.get("state_type") == "simulated"
            and data.get("actual_state_unchanged") is True
            and case.get("baseline_run_id") == comparison.get("baseline_run_id")
            and case.get("alternative_run_id") == comparison.get("alternative_run_id")
            and case.get("baseline_run_id") != case.get("alternative_run_id")
            and case.get("snapshot_hash") == facts.get("snapshot_hash")
            and facts.get("snapshot_hash") == comparison.get("snapshot_hash")
            and case.get("horizon_days") == comparison.get("horizon_days")
            and case.get("random_seed") == comparison.get("random_seed")
            and comparison.get("primary_metric") in (comparison.get("metrics") or {})
        )
        checks.append({
            "name": "sales_matched_simulation",
            "status": "passed" if valid else "blocked",
        })
    if any(check["status"] == "blocked" for check in checks):
        status = "blocked"
    elif any(check["status"] == "passed" for check in checks):
        status = "passed"
    else:
        status = "not_evaluated"
    return {"schema_version": "agent-guardrails-v1", "status": status, "checks": checks}
