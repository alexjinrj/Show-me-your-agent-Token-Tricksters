from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from agent_runtime.guardrails import evaluate_run


class SalesGateway:
    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        self.round = 0

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.round += 1
        if self.round == 1:
            assert "analyze_sales_backlog_intervention" in {
                item["function"]["name"] for item in tools
            }
            return {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "sales-1", "type": "function",
                    "function": {
                        "name": "analyze_sales_backlog_intervention",
                        "arguments": json.dumps({"snapshot_id": self.snapshot_id,
                                                 "additional_workers": 2,
                                                 "horizon_days": 7, "random_seed": 42}),
                    },
                }],
            }
        assert json.loads(messages[-1]["content"])["status"] == "ok"
        return {"role": "assistant", "content": "Simulation recommendation for human review."}


def test_guardrail_blocks_inconsistent_sales_evidence() -> None:
    invalid = {
        "evidence": [{
            "tool_name": "analyze_sales_backlog_intervention", "status": "ok",
            "data": {"schema_version": "sales-analysis-result-v1",
                     "facts": {"state_type": "actual"},
                     "analysis_case": {"baseline_run_id": "same", "alternative_run_id": "same"},
                     "simulation_comparison": {"state_type": "simulated",
                                               "baseline_run_id": "same",
                                               "alternative_run_id": "same"}},
        }]
    }
    assert evaluate_run(invalid)["status"] == "blocked"


def test_simulation_review_and_observability_are_persisted(client: TestClient) -> None:
    context = client.app.state.context
    before = context.actual_state.actual_state_hash()
    client.app.state.runtime.gateway = SalesGateway(context.base_snapshot_id)
    response = client.post("/api/assistant", json={"message": "测试增加两名仓库员工"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed", run
    assert run["guardrails"]["status"] == "passed"
    assert run["observability"]["tool_calls"] == 1
    assert run["human_review"]["status"] == "pending"
    assert run["human_review"]["execution_status"] == "not_executed"
    run_id = run["agent_run_id"]
    report = client.get(f"/api/assistant/runs/{run_id}/evaluation")
    assert report.status_code == 200
    assert report.json()["observability"]["tools_used"] == [
        "analyze_sales_backlog_intervention"
    ]
    case_result = client.post(f"/api/assistant/runs/{run_id}/evaluate-case", json={
        "required_tools": ["analyze_sales_backlog_intervention"],
        "forbidden_tools": ["run_sql"],
        "require_guardrails_passed": True,
        "require_review_pending": True,
    }).json()
    assert case_result["passed"] is True
    assert client.get("/api/assistant/evaluation/summary").json()[
        "pending_human_reviews"
    ] == 1
    decision = client.post(f"/api/assistant/runs/{run_id}/review", json={
        "decision": "approved", "reviewer": "Demo Reviewer", "note": "Review only",
    })
    assert decision.status_code == 200
    assert decision.json()["decision"] == "approved"
    assert decision.json()["execution_status"] == "not_executed"
    assert client.post(f"/api/assistant/runs/{run_id}/review", json={
        "decision": "rejected", "reviewer": "Another reviewer",
    }).status_code == 409
    assert client.get(f"/api/assistant/runs/{run_id}").json()["human_review"][
        "status"
    ] == "decided"
    assert context.actual_state.actual_state_hash() == before
