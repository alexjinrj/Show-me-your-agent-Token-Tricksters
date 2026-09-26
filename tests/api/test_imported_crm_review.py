from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from agent_runtime.service import _requires_crm_action_plan, _runtime_catalog_for
from interfaces.api.app import create_app
from interfaces.api.settings import Settings

CUSTOMERS = (
    "customer_number,name,active,data_origin,source_record_id\n"
    "DEMO-C001,Demo Customer,true,synthetic,demo-customer-001\n"
)
ORDERS = (
    "order_number,customer_number,sku,quantity,unit_price,order_date,due_date,"
    "status,priority,data_origin,source_record_id\n"
    "DEMO-SO-053,DEMO-C001,TT-M928,1,25,2026-08-28T10:00:00+08:00,"
    "2026-09-01T18:00:00+08:00,backlog,1,synthetic,demo-so-053\n"
)
CASE_ID = "CASE-DEMO-SO-053"


def _upload(client: TestClient, source_type: str, csv_text: str) -> None:
    response = client.post(
        "/api/v1/data/uploads/commit",
        json={
            "filename": f"{source_type}.csv",
            "csv_text": csv_text,
            "source_type": source_type,
            "mapping_version": "browser-upload-v1",
            "data_origin": "synthetic",
        },
        headers={"X-Upload-Token": "test-upload-token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["committed"] is True


class RecommendationGateway:
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        available = {tool["function"]["name"] for tool in tools}
        assert "recommend_resolution" in available
        assert "get_data_catalog" not in available
        if not any(message["role"] == "tool" for message in messages):
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "recommend-imported-case",
                        "type": "function",
                        "function": {
                            "name": "recommend_resolution",
                            "arguments": json.dumps({"complaint_id": CASE_ID}),
                        },
                    }
                ],
            }
        assert json.loads(messages[-1]["content"])["status"] == "ok"
        return {"role": "assistant", "content": "Recommendation ready for human review."}


def test_imported_identifiers_support_agent_recommendation_and_human_review(
    settings: Settings,
) -> None:
    app = create_app(replace(settings, upload_token="test-upload-token"))
    with TestClient(app) as client:
        _upload(client, "customers", CUSTOMERS)
        _upload(client, "sales_orders", ORDERS)

        case = client.get(f"/api/v1/crm/complaints/{CASE_ID}")
        assert case.status_code == 200
        assert case.json()["data"]["customerId"] == "DEMO-C001"

        registry = client.app.state.runtime.executor.registry
        customer = registry.call(
            "get_customer_360", {"customer_id": "DEMO-C001"}, agent_case_id="test"
        )
        assert customer.status == "ok"

        client.app.state.runtime.gateway = RecommendationGateway()
        response = client.post(
            "/api/assistant", json={"message": f"Investigate {CASE_ID} and recommend a resolution"}
        )
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["status"] == "completed", run
        evidence = run["evidence"][0]
        assert evidence["tool_name"] == "recommend_resolution"
        assert evidence["data"]["result"]["complaintId"] == CASE_ID

        proposal = client.post(
            "/api/v1/crm/proposals",
            json={
                "complaintId": CASE_ID,
                "resolutionId": evidence["data"]["result"]["recommendation"]["id"],
                "sourceAgentRunId": run["agent_run_id"],
                "sourceToolCallId": evidence["tool_call_id"],
            },
        )
        assert proposal.status_code == 201, proposal.text
        created = proposal.json()["data"]
        assert created["complaintId"] == CASE_ID
        assert created["sourceToolCallId"] == evidence["tool_call_id"]
        reviewed = client.post(
            f"/api/v1/crm/proposals/{created['id']}/decision",
            json={"decision": "Approved", "reviewer": "Demo Reviewer"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["data"]["status"] == "Approved"

        unknown = client.post(
            "/api/v1/crm/proposals",
            json={"complaintId": "CASE-DEMO-SO-999", "resolutionId": "monitor"},
        )
        assert unknown.status_code == 422


def test_imported_case_uses_focused_action_plan_tool_catalog() -> None:
    catalog = [
        {"name": "recommend_resolution", "groups": ["crm"]},
        {"name": "analyze_crm_service_capacity", "groups": ["crm"]},
        {"name": "draft_business_action_plan", "groups": ["investigation"]},
        {"name": "get_data_catalog", "groups": ["retrieval"]},
    ]
    prompt = f"为 {CASE_ID} 制定处理计划"
    assert _requires_crm_action_plan(prompt)
    assert {tool["name"] for tool in _runtime_catalog_for(prompt, catalog)} == {
        "recommend_resolution",
        "analyze_crm_service_capacity",
        "draft_business_action_plan",
    }
    assert not _requires_crm_action_plan("请制定普通处理计划")
