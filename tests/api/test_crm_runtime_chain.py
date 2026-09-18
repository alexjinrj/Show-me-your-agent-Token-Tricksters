from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_runtime.openclaw import OpenClawGateway
from enterprise_state.models import CRMProposalRow, ToolCallAuditRow
from interfaces.api.app import create_app


def test_http_gateway_three_domains_to_crm_review_and_restart(client: TestClient) -> None:
    context = client.app.state.context
    before = context.actual_state.counts()
    snapshot_hash = context.base_manifest().content_hash
    requests: list[dict[str, Any]] = []
    calls = [
        ("get_actual_state_summary", {"snapshot_id": context.base_snapshot_id}),
        (
            "list_inventory_reorder_candidates",
            {"snapshot_id": context.base_snapshot_id, "top_n": 2},
        ),
        ("get_crm_summary", {}),
        ("recommend_resolution", {"complaint_id": "CASE-SO74695"}),
        ("draft_customer_reply", {"complaint_id": "CASE-SO74695", "tone": "empathetic"}),
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            assert self.path == "/v1/chat/completions"
            assert self.headers["Authorization"] == "Bearer test-crm-secret"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            assert len(payload["tools"]) == 23
            assert "SAME canonical snapshot" in payload["messages"][0]["content"]
            if len(requests) == 1:
                reply = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call-{index}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                        for index, (name, arguments) in enumerate(calls)
                    ],
                }
            else:
                tool_messages = [item for item in payload["messages"] if item["role"] == "tool"]
                assert len(tool_messages) == 5
                results = [json.loads(item["content"]) for item in tool_messages]
                assert all(item["status"] == "ok" for item in results)
                assert results[2]["data"]["summary"]["customerCount"] == 486
                assert results[3]["reference_id"] == context.base_snapshot_id
                assert results[3]["data"]["data_scope"]["canonical_snapshot_mapped"] is True
                assert results[4]["data"]["result"]["status"] == "Unsent draft"
                reply = {
                    "role": "assistant",
                    "content": "已生成 CRM 建议和未发送草稿，等待人工审核。",
                }
            encoded = json.dumps({"choices": [{"message": reply}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client.app.state.runtime.gateway = OpenClawGateway(
        f"http://127.0.0.1:{server.server_port}", "test-crm-secret"
    )
    try:
        response = client.post("/api/assistant", json={"message": "分析销售库存和 CASE-SO74695"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert len(run["evidence"]) == 5
    assert context.crm_proposals.list() == []  # The LLM never submits/approves a proposal.
    evidence = run["evidence"][3]
    created = client.post(
        "/api/v1/crm/proposals",
        json={
            "complaintId": "CASE-SO74695",
            "resolutionId": evidence["data"]["result"]["recommendation"]["id"],
            "replyDraft": run["evidence"][4]["data"]["result"]["draft"],
            "sourceAgentRunId": run["agent_run_id"],
            "sourceToolCallId": evidence["tool_call_id"],
        },
    )
    assert created.status_code == 201, created.text
    proposal = created.json()["data"]
    assert proposal["datasetReference"] == evidence["reference_id"]
    assert proposal["sourceAgentRunId"] == run["agent_run_id"]
    assert proposal["evidence"]["source_tool_evidence"] == evidence
    mismatched = client.post(
        "/api/v1/crm/proposals",
        json={
            "complaintId": "CASE-SO74700",
            "resolutionId": "refund",
            "sourceAgentRunId": run["agent_run_id"],
            "sourceToolCallId": evidence["tool_call_id"],
        },
    )
    assert mismatched.status_code == 422
    decision = client.post(
        f"/api/v1/crm/proposals/{proposal['id']}/decision",
        json={
            "decision": "Approved",
            "reviewer": " Human reviewer ",
            "note": "Demo evidence reviewed",
        },
    )
    assert decision.status_code == 200, decision.text
    reviewed = decision.json()["data"]
    assert reviewed["reviewer"] == "Human reviewer"
    assert "No customer contact" in reviewed["effect"]
    with Session(context.engine) as db:
        audits = db.scalars(
            select(ToolCallAuditRow).where(ToolCallAuditRow.agent_case_id == run["agent_run_id"])
        ).all()
        assert {row.id for row in audits} == {item["tool_call_id"] for item in run["evidence"]}
    with TestClient(create_app(client.app.state.settings)) as restarted:
        assert restarted.get(f"/api/assistant/runs/{run['agent_run_id']}").json() == run
        assert restarted.get(f"/api/v1/crm/proposals/{proposal['id']}").json()["data"] == reviewed
    assert context.actual_state.counts() == before
    assert context.base_manifest().content_hash == snapshot_hash


@pytest.mark.parametrize(
    "body",
    [
        {"complaintId": "CASE-SO74701", "resolutionId": "credit"},
        {"complaintId": "CASE-SO74695", "resolutionId": "refund", "sourceAgentRunId": str(uuid4())},
        {
            "complaintId": "CASE-SO74695",
            "resolutionId": "refund",
            "sourceAgentRunId": str(uuid4()),
            "sourceToolCallId": str(uuid4()),
        },
    ],
)
def test_proposal_rejects_infeasible_or_invalid_evidence(client: TestClient, body: Any) -> None:
    assert client.post("/api/v1/crm/proposals", json=body).status_code == 422
    assert client.get("/api/v1/crm/proposals").json()["data"] == []


def test_review_requires_name_and_cannot_overwrite_final_decision(client: TestClient) -> None:
    created = client.post(
        "/api/v1/crm/proposals",
        json={
            "complaintId": "CASE-SO74695",
            "resolutionId": "refund",
        },
    ).json()["data"]
    url = f"/api/v1/crm/proposals/{created['id']}/decision"
    assert client.post(url, json={"decision": "Approved", "reviewer": "  "}).status_code == 422
    accepted = client.post(url, json={"decision": "Rejected", "reviewer": "Reviewer"})
    assert accepted.status_code == 200
    assert client.post(url, json={"decision": "Approved", "reviewer": "Other"}).status_code == 409
    assert (
        client.get(f"/api/v1/crm/proposals/{created['id']}").json()["data"]
        == accepted.json()["data"]
    )
    with Session(client.app.state.context.engine) as db, db.begin():
        row = db.get(CRMProposalRow, created["id"])
        assert row is not None
        row.dataset_reference = str(uuid4())
    assert client.get("/api/v1/crm/proposals").json()["data"] == []
    assert client.get(f"/api/v1/crm/proposals/{created['id']}").status_code == 404
    assert client.post(url, json={"decision": "Approved", "reviewer": "Other"}).status_code == 409


def test_disabled_gateway_keeps_crm_read_and_review_workflow_available(client: TestClient) -> None:
    client.app.state.runtime.gateway = None
    disabled = client.post("/api/assistant", json={"message": "Investigate CASE-SO74695"}).json()
    assert disabled["status"] == "disabled"
    assert disabled["evidence"] == []
    assert client.get("/api/v1/crm/summary").json()["data"]["serviceCaseCount"] == 100
    created = client.post(
        "/api/v1/crm/proposals",
        json={
            "complaintId": "CASE-SO74695",
            "resolutionId": "refund",
        },
    )
    assert created.status_code == 201
    assert created.json()["data"]["sourceAgentRunId"] is None
    assert created.json()["data"]["evidence"]["provenance"]["reference_id"]
