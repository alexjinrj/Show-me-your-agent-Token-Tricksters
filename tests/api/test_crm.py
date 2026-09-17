from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


def test_crm_versioned_read_contract_and_legacy_compatibility(client: TestClient) -> None:
    summary = client.get("/api/v1/crm/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["schema_version"] == "crm-api-v1"
    assert body["data"]["customerCount"] == 486
    assert body["data"]["salesOrderCount"] == 500
    assert body["data"]["serviceCaseCount"] == 100
    assert body["data"]["complaintCount"] is None
    assert body["provenance"]["dataset_id"] == "adventureworks-unified-snapshot-v1"
    assert body["dataset_reference"] == client.app.state.context.base_snapshot_id
    assert body["provenance"]["boundaries"]["synthetic"] == []

    complaints = client.get("/api/v1/crm/complaints?limit=3").json()["data"]
    assert len(complaints) == 3
    assert complaints == sorted(complaints, key=lambda row: (-row["priorityScore"], row["id"]))
    assert client.get("/api/crm/complaints?limit=3").json() == complaints

    detail = client.get(f"/api/v1/crm/complaints/{complaints[0]['id']}").json()["data"]
    assert detail["investigation"]["recommendation"]["id"] in {"monitor", "reship"}
    assert "canonical AdventureWorks snapshot" in detail["investigation"]["boundary"]
    assert detail["caseKind"] == "derived_order_service_exception"


def test_crm_proposal_and_human_decision_are_persisted(client: TestClient) -> None:
    before_hash = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    created = client.post(
        "/api/v1/crm/proposals",
        json={
            "complaintId": "CASE-SO74695",
            "resolutionId": "refund",
            "replyDraft": "Unsent draft",
            "internalDraft": "Verify before action",
        },
    )
    assert created.status_code == 201, created.text
    proposal = created.json()["data"]
    assert proposal["status"] == "Pending Review"
    assert "No customer contact" in proposal["effect"]

    decision = client.post(
        f"/api/v1/crm/proposals/{proposal['id']}/decision",
        json={"decision": "Approved", "reviewer": "Demo Reviewer", "note": "Evidence checked"},
    )
    assert decision.status_code == 200, decision.text
    reviewed = decision.json()["data"]
    assert reviewed["status"] == "Approved"
    assert reviewed["reviewer"] == "Demo Reviewer"
    assert reviewed["audit"][-1]["actor"] == "Human reviewer"
    assert client.get(f"/api/v1/crm/proposals/{proposal['id']}").json()["data"] == reviewed
    assert client.get("/api/snapshot").json()["manifest"]["content_hash"] == before_hash


def test_crm_tool_runs_through_shared_assistant_runtime(client: TestClient) -> None:
    runtime = client.app.state.runtime

    class CRMGateway:
        step = 0

        def complete(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> dict[str, Any]:
            self.step += 1
            if self.step == 1:
                assert any(item["function"]["name"] == "recommend_resolution" for item in tools)
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "crm-call-1",
                            "type": "function",
                            "function": {
                                "name": "recommend_resolution",
                                "arguments": json.dumps({"complaint_id": "CASE-SO74695"}),
                            },
                        }
                    ],
                }
            evidence = json.loads(messages[-1]["content"])
            assert evidence["reference_id"] == client.app.state.context.base_snapshot_id
            assert evidence["data"]["result"]["boundary"]
            return {
                "role": "assistant",
                "content": "Draft recommendation grounded in CRM evidence.",
            }

    runtime.gateway = CRMGateway()
    response = client.post("/api/assistant", json={"message": "Investigate CASE-SO74695"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["evidence"][0]["tool_name"] == "recommend_resolution"
    assert result["evidence"][0]["state_type"] == "actual"
    assert client.get(f"/api/assistant/runs/{result['agent_run_id']}").json() == result
