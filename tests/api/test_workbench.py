"""Offline integration acceptance; scripted model, no paid inference."""

import json
from typing import Any

from fastapi.testclient import TestClient

from tools.workbench.service import Workbench

DOCUMENT = {
    "title": "Late order complaint",
    "kind": "complaint",
    "text": "My order SO74695 is late. Please investigate delivery before promising a date.",
    "source": "Synthetic acceptance fixture",
    "occurred_at": "2026-09-12T10:00:00+08:00",
    "is_synthetic": True,
    "entity_ids": ["SO74695", "AW00011308", "PK-7098"],
}


class InvestigationGateway:
    def __init__(self) -> None:
        self.step = 0
        self.refs: list[str] = []

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.step += 1
        if self.step > 1:
            result = json.loads(messages[-1]["content"])
            assert result["status"] == "ok", result
            self.refs.append(result["tool_call_id"])
        if self.step == 1:
            name, args = "search_business_documents", {"entity_id": "SO74695"}
        elif self.step == 2:
            assert result["data"]["documents"][0]["is_synthetic"] is True
            name, args = "get_data_catalog", {}
        elif self.step == 3:
            name, args = "query_snapshot_records", {"dataset": "orders", "limit": 1}
        elif self.step == 4:
            name, args = (
                "draft_business_action_plan",
                {
                    "plan_scope": "crm_service_recovery",
                    "case_id": "CASE-SO74695",
                    "title": "Investigate delivery",
                    "findings": "Synthetic complaint was uploaded.",
                    "hypotheses": "Fulfilment delay is unconfirmed.",
                    "missing_evidence": "Actual shipment, policy and reservation details.",
                    "evidence_ids": self.refs,
                    "intervention_evidence": {
                        "status": "not_applicable",
                        "reason": "This draft requests evidence verification only.",
                    },
                    "actions": [
                        {
                            "department": "operations",
                            "task": "Verify delivery state",
                            "success_check": "Record verified delivery status and source",
                        }
                    ],
                },
            )
        else:
            assert result["data"]["draft_only"]
            return {"role": "assistant", "content": "Draft for human review, no shipment executed."}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call-{self.step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        }


def test_investigate_review_follow_up_and_persistence(client: TestClient) -> None:
    context = client.app.state.context
    before = context.base_manifest().content_hash
    assert client.post("/api/workbench/documents", json=DOCUMENT).status_code == 200
    client.app.state.runtime.gateway = InvestigationGateway()
    run = client.post("/api/assistant", json={"message": "Investigate and draft a plan"}).json()
    assert run["status"] == "completed", run
    source = {
        "agent_run_id": run["agent_run_id"],
        "tool_call_id": run["evidence"][-1]["tool_call_id"],
    }
    response = client.post("/api/workbench/plans", json=source)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert client.post("/api/workbench/plans", json=source).json()["id"] == plan["id"]
    endpoint = f"/api/workbench/plans/{plan['id']}/status"
    change = {
        "status": "completed",
        "reviewer": "Demo reviewer",
        "note": "Synthetic test",
        "expected_version": 1,
    }
    assert client.post(endpoint, json=change).status_code == 409
    for version, status in enumerate(["approved", "in_progress", "completed"], start=1):
        response = client.post(
            endpoint, json={**change, "status": status, "expected_version": version}
        )
        assert response.status_code == 200, response.text
    assert client.post(endpoint, json=change).status_code == 409
    # New service instance reads durable data; another snapshot sees no documents or plans.
    saved = Workbench(context.engine, context.base_snapshot_id).list("plan")[0]
    assert saved["status"] == "completed" and len(saved["history"]) == 3
    assert Workbench(context.engine, "other").list("plan") == []
    assert context.base_manifest().content_hash == before


def test_missing_and_forged_evidence_fail_closed(client: TestClient) -> None:
    runtime = client.app.state.runtime
    assert client.get("/api/workbench/documents").json()["total_matching"] == 0
    result = runtime.executor.execute(
        "draft_business_action_plan",
        {
            "plan_scope": "crm_service_recovery",
            "case_id": "CASE-SO74695",
            "title": "Unsupported",
            "findings": "x",
            "hypotheses": "x",
            "missing_evidence": "x",
            "evidence_ids": ["invented"],
            "intervention_evidence": {
                "status": "not_available",
                "reason": "No simulator evidence is available.",
            },
            "actions": [{"department": "crm", "task": "x", "success_check": "x"}],
        },
        snapshot_id=runtime.snapshot_id,
        run_id="missing",
    )
    assert result.status == "error"
    assert (
        client.post(
            "/api/workbench/plans", json={"agent_run_id": "missing", "tool_call_id": "invented"}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/workbench/documents", json={**DOCUMENT, "text": " "}).status_code == 422
    )


def test_search_is_scoped_literal_and_paginated(client: TestClient) -> None:
    client.post("/api/workbench/documents", json=DOCUMENT)
    runtime = client.app.state.runtime
    for query, count in [
        ({"entity_id": "SO74695"}, 1),
        ({"query": "missing"}, 0),
        ({"query": "late delivery"}, 1),
        ({"entity_id": "other"}, 0),
    ]:
        result = runtime.executor.execute(
            "search_business_documents", query, snapshot_id=runtime.snapshot_id, run_id="test"
        )
        assert result.data["total_matching"] == count
