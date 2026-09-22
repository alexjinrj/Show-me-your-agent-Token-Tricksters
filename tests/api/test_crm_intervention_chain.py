from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


class CRMInterventionGateway:
    """Offline orchestration contract; it does not claim live-model quality."""

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        self.step = 0
        self.evidence_ids: list[str] = []

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        available = {item["function"]["name"] for item in tools}
        assert "analyze_crm_service_capacity" in available
        self.step += 1
        if self.step > 1:
            result = json.loads(messages[-1]["content"])
            assert result["status"] == "ok", result
            self.evidence_ids.append(result["tool_call_id"])
        if self.step == 1:
            name, arguments = "recommend_resolution", {"complaint_id": "CASE-SO74695"}
        elif self.step == 2:
            assert result["state_type"] == "actual"
            name, arguments = (
                "analyze_crm_service_capacity",
                {
                    "snapshot_id": self.snapshot_id,
                    "complaint_id": "CASE-SO74695",
                    "additional_workers": 2,
                    "horizon_days": 7,
                    "random_seed": 42,
                },
            )
        elif self.step == 3:
            comparison = result["data"]["simulation_comparison"]
            assert comparison["baseline_run_id"] != comparison["alternative_run_id"]
            assert comparison["horizon_days"] == 7
            assert comparison["random_seed"] == 42
            name, arguments = (
                "draft_business_action_plan",
                {
                "plan_scope": "crm_service_recovery",
                "case_id": "CASE-SO74695",
                    "title": "Review capacity response for CASE-SO74695",
                    "findings": "The current snapshot contains a derived overdue-order case.",
                    "hypotheses": "Warehouse capacity may contribute; causation is unproven.",
                    "missing_evidence": "Actual shipment status and complaint text are absent.",
                    "evidence_ids": self.evidence_ids,
                    "intervention_evidence": {
                        "status": "tested",
                        "simulation_evidence_id": self.evidence_ids[-1],
                    },
                    "actions": [
                        {
                            "department": "crm",
                            "task": "Ask fulfilment to verify status before customer contact.",
                            "success_check": "A sourced status and next update time are recorded.",
                        }
                    ],
                },
            )
        else:
            assert result["data"]["validation_status"] == "simulation_validated"
            assert result["data"]["simulation_comparison"]["baseline_run_id"]
            return {"role": "assistant", "content": "Tested draft prepared for human review."}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"crm-intervention-{self.step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


def test_crm_diagnosis_intervention_simulation_review_chain(client: TestClient) -> None:
    context = client.app.state.context
    before = context.base_manifest().content_hash
    client.app.state.runtime.gateway = CRMInterventionGateway(context.base_snapshot_id)

    response = client.post(
        "/api/assistant",
        json={"message": "Investigate CASE-SO74695 and test a capacity intervention"},
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed", run
    assert [item["tool_name"] for item in run["evidence"]] == [
        "recommend_resolution",
        "analyze_crm_service_capacity",
        "draft_business_action_plan",
    ]
    simulated = run["evidence"][1]
    assert simulated["state_type"] == "simulated"
    assert simulated["data"]["actual_state_unchanged"] is True
    assert context.base_manifest().content_hash == before

    plan = client.post(
        "/api/workbench/plans",
        json={
            "agent_run_id": run["agent_run_id"],
            "tool_call_id": run["evidence"][-1]["tool_call_id"],
        },
    ).json()
    assert plan["validation_status"] == "simulation_validated"
    assert plan["tested_intervention"]["parameter"] == "warehouse_staff.capacity_delta"
    assert plan["simulation_comparison"]["baseline_run_id"]


def test_unverified_crm_intervention_cannot_be_approved(client: TestClient) -> None:
    context = client.app.state.context

    class UntestedGateway:
        def __init__(self) -> None:
            self.step = 0

        def complete(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> dict[str, Any]:
            self.step += 1
            if self.step == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "actual",
                            "type": "function",
                            "function": {
                                "name": "recommend_resolution",
                                "arguments": json.dumps({"complaint_id": "CASE-SO74695"}),
                            },
                        }
                    ],
                }
            actual = json.loads(messages[-1]["content"])
            if self.step == 2:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "draft",
                            "type": "function",
                            "function": {
                                "name": "draft_business_action_plan",
                                "arguments": json.dumps(
                                    {
                                        "plan_scope": "crm_service_recovery",
                                        "case_id": "CASE-SO74695",
                                        "title": "Untested capacity idea",
                                        "findings": "A derived overdue-order case exists.",
                                        "hypotheses": "Capacity might contribute.",
                                        "missing_evidence": "Simulation was not run.",
                                        "evidence_ids": [actual["tool_call_id"]],
                                        "intervention_evidence": {
                                            "status": "not_available",
                                            "reason": "Simulation was not run.",
                                        },
                                        "actions": [
                                            {
                                                "department": "crm",
                                                "task": "Do not promise the intervention.",
                                                "success_check": "Draft remains unapproved.",
                                            }
                                        ],
                                    }
                                ),
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "Unverified draft only."}

    client.app.state.runtime.gateway = UntestedGateway()
    run = client.post("/api/assistant", json={"message": "Draft without simulation"}).json()
    plan = client.post(
        "/api/workbench/plans",
        json={
            "agent_run_id": run["agent_run_id"],
            "tool_call_id": run["evidence"][-1]["tool_call_id"],
        },
    ).json()
    assert plan["validation_status"] == "unverified_intervention"
    response = client.post(
        f"/api/workbench/plans/{plan['id']}/status",
        json={
            "status": "approved",
            "reviewer": "Demo Reviewer",
            "note": "Should fail",
            "expected_version": 1,
        },
    )
    assert response.status_code == 409
    assert context.base_manifest().content_hash == context.base_snapshot().manifest.content_hash


def test_requested_crm_plan_closes_from_simulation_evidence(client: TestClient) -> None:
    context = client.app.state.context

    class SimulationGateway:
        def __init__(self) -> None:
            self.step = 0

        def complete(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> dict[str, Any]:
            self.step += 1
            assert self.step == 1
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "simulate",
                        "type": "function",
                        "function": {
                            "name": "analyze_crm_service_capacity",
                            "arguments": json.dumps(
                                {
                                    "snapshot_id": context.base_snapshot_id,
                                    "complaint_id": "CASE-SO74695",
                                    "additional_workers": 2,
                                    "horizon_days": 7,
                                    "random_seed": 42,
                                }
                            ),
                        },
                    }
                ],
            }

    gateway = SimulationGateway()
    client.app.state.runtime.gateway = gateway
    run = client.post(
        "/api/assistant",
        json={
            "message": (
                "Investigate CASE-SO74695, test capacity, and draft a CRM "
                "service-recovery action plan."
            )
        },
    ).json()
    assert run["status"] == "completed", run
    assert gateway.step == 1
    assert [item["tool_name"] for item in run["evidence"]] == [
        "analyze_crm_service_capacity",
        "draft_business_action_plan",
    ]
