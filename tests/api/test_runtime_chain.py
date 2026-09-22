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

from agent_runtime.openclaw import GatewayError, OpenClawGateway
from enterprise_state.models import SimulationResultRow, ToolCallAuditRow
from interfaces.runtime import build_runtime


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


class ScriptedGateway:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.requests: list[list[dict[str, Any]]] = []

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.requests.append(list(messages))
        return next(self.responses)


def test_http_gateway_to_tools_to_persisted_evidence(client: TestClient) -> None:
    context = client.app.state.context
    before = context.actual_state.counts()
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            assert self.path == "/v1/chat/completions"
            assert self.headers["Authorization"] == "Bearer test-secret"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(payload)
            assert payload["model"] == "openclaw/business-coordinator"
            assert {
                "get_data_catalog",
                "query_snapshot_records",
                "compare_snapshot_periods",
                "query_enterprise_history",
            } <= {t["function"]["name"] for t in payload["tools"]}
            assert any(
                tool["function"]["name"] == "recommend_resolution" for tool in payload["tools"]
            )
            if len(received) == 1:
                reply = tool_call(
                    "get_actual_state_summary", {"snapshot_id": context.base_snapshot_id}
                )
            elif len(received) == 2:
                evidence = json.loads(payload["messages"][-1]["content"])
                assert evidence["data"]["sales_order_count"] == 500
                reply = tool_call(
                    "list_inventory_reorder_candidates",
                    {
                        "snapshot_id": context.base_snapshot_id,
                        "top_n": 2,
                    },
                    "call_2",
                )
            else:
                evidence = json.loads(payload["messages"][-1]["content"])
                reply = {"role": "assistant", "content": f"库存依据 {evidence['tool_call_id']}"}
            encoded = json.dumps(
                {
                    "choices": [{"message": reply}],
                    "usage": {"total_tokens": 10},
                }
            ).encode()
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
    runtime = client.app.state.runtime
    runtime.gateway = OpenClawGateway(f"http://127.0.0.1:{server.server_port}", "test-secret")
    try:
        response = client.post("/api/assistant", json={"message": "看看销售和库存"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed", result
    assert len(result["evidence"]) == 2
    assert len(result["events"]) == 2
    assert result["model_usage"] == [{"total_tokens": 10}] * 3
    assert client.get(f"/api/assistant/runs/{result['agent_run_id']}").json() == result
    restored = build_runtime(context)
    assert restored.store.load(result["agent_run_id"]) == result
    with Session(context.engine) as db:
        audit = db.scalars(
            select(ToolCallAuditRow).where(
                ToolCallAuditRow.agent_case_id == result["agent_run_id"],
            )
        ).all()
        assert len(audit) == 2
    assert context.actual_state.counts() == before


def test_inventory_simulation_results_are_retrievable(client: TestClient) -> None:
    runtime = client.app.state.runtime
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    runtime.gateway = ScriptedGateway(
        [
            tool_call(
                "compare_inventory_replenishment_strategies",
                {
                    "snapshot_id": runtime.snapshot_id,
                    "horizon_days": 3,
                    "random_seed": 42,
                },
            ),
            {"role": "assistant", "content": "这是模拟补货建议，未执行真实采购。"},
        ]
    )
    result = client.post("/api/assistant", json={"message": "比较补货方案"}).json()
    assert result["status"] == "completed", result
    evidence = result["evidence"][0]
    assert evidence["state_type"] == "simulated"
    assert len(evidence["data"]["strategy_runs"]) == 4
    with Session(client.app.state.context.engine) as db:
        for run in evidence["data"]["strategy_runs"]:
            persisted = db.scalar(
                select(SimulationResultRow).where(
                    SimulationResultRow.simulation_run_id == run["simulation_run_id"],
                )
            )
            assert persisted is not None
            assert persisted.summary_metrics == run["metrics"]
    assert client.get("/api/snapshot").json()["manifest"]["content_hash"] == before


@pytest.mark.parametrize(
    "name,args",
    [
        ("exec", {}),
        ("get_actual_state_summary", {"snapshot_id": str(uuid4())}),
        ("get_actual_state_summary", {"extra": "sql"}),
        ("get_simulation_state", {"simulation_session_id": str(uuid4())}),
        (
            "compare_simulation_runs",
            {"baseline_run_id": str(uuid4()), "alternative_run_id": str(uuid4())},
        ),
    ],
)
def test_rejected_calls_are_audited(client: TestClient, name: str, args: dict[str, Any]) -> None:
    runtime = client.app.state.runtime
    runtime.gateway = ScriptedGateway(
        [
            tool_call(name, args),
            {"role": "assistant", "content": "缺少有效证据。"},
        ]
    )
    result = client.post("/api/assistant", json={"message": "test"}).json()
    assert result["evidence"][0]["status"] == "error"
    with Session(client.app.state.context.engine) as db:
        assert db.get(ToolCallAuditRow, result["evidence"][0]["tool_call_id"]) is not None


def test_memory_budgets_and_failures(client: TestClient) -> None:
    runtime = client.app.state.runtime
    gateway = ScriptedGateway(
        [
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
    )
    runtime.gateway = gateway
    first = client.post("/api/assistant", json={"message": "hello"}).json()
    second = client.post(
        "/api/assistant",
        json={
            "message": "follow up",
            "conversation_id": first["conversation_id"],
        },
    ).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert {"role": "assistant", "content": "first"} in gateway.requests[1]
    runtime.max_tool_calls = 0
    runtime.gateway = ScriptedGateway(
        [
            tool_call(
                "get_actual_state_summary",
                {
                    "snapshot_id": runtime.snapshot_id,
                },
            )
        ]
    )
    exhausted = client.post("/api/assistant", json={"message": "analyse"}).json()
    assert exhausted["status"] == "failed"
    assert exhausted["evidence"] == []


def test_sales_scenario_full_chain(client: TestClient) -> None:
    runtime = client.app.state.runtime
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]

    class ScenarioGateway:
        def __init__(self) -> None:
            self.step = 0
            self.baseline_session = ""
            self.baseline_run = ""
            self.alternative_session = ""

        def complete(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> dict[str, Any]:
            data = json.loads(messages[-1]["content"])["data"] if self.step else {}
            self.step += 1
            match self.step:
                case 1:
                    name, args = (
                        "create_simulation_session",
                        {
                            "snapshot_id": runtime.snapshot_id,
                            "name": "Runtime baseline",
                        },
                    )
                case 2:
                    self.baseline_session = data["simulation_session_id"]
                    name, args = (
                        "run_simulation",
                        {
                            "simulation_session_id": self.baseline_session,
                            "horizon_days": 3,
                            "random_seed": 42,
                        },
                    )
                case 3:
                    self.baseline_run = data["simulation_run_id"]
                    name, args = (
                        "fork_simulation_session",
                        {
                            "simulation_session_id": self.baseline_session,
                            "name": "Extra warehouse",
                        },
                    )
                case 4:
                    self.alternative_session = data["simulation_session_id"]
                    name, args = (
                        "add_simulation_event",
                        {
                            "simulation_session_id": self.alternative_session,
                            "event_type": "warehouse_capacity_increase",
                            "workers": 2,
                        },
                    )
                case 5:
                    name, args = (
                        "run_simulation",
                        {
                            "simulation_session_id": self.alternative_session,
                            "horizon_days": 3,
                            "random_seed": 42,
                        },
                    )
                case 6:
                    name, args = (
                        "compare_simulation_runs",
                        {
                            "baseline_run_id": self.baseline_run,
                            "alternative_run_id": data["simulation_run_id"],
                        },
                    )
                case _:
                    assert data["random_seed"] == 42
                    return {"role": "assistant", "content": "已比较同一快照的两个模拟方案。"}
            return tool_call(name, args, f"scenario_{self.step}")

    runtime.gateway = ScenarioGateway()
    result = client.post("/api/assistant", json={"message": "比较增加仓库人员的方案"}).json()
    assert result["status"] == "completed", result
    assert len(result["evidence"]) == 6
    assert all(item["status"] == "ok" for item in result["evidence"])
    assert result["evidence"][-1]["tool_name"] == "compare_simulation_runs"
    assert client.get("/api/snapshot").json()["manifest"]["content_hash"] == before


def test_failed_gateway_persists_safe_error(client: TestClient) -> None:
    class FailedGateway:
        def complete(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> dict[str, Any]:
            raise GatewayError("Gateway unavailable")

    client.app.state.runtime.gateway = FailedGateway()
    result = client.post("/api/assistant", json={"message": "test"}).json()
    assert result["status"] == "failed"
    assert client.get(f"/api/assistant/runs/{result['agent_run_id']}").json() == result


def test_gateway_configuration_and_error_sanitization() -> None:
    with pytest.raises(ValueError):
        OpenClawGateway("http://public.example", "secret")
    with pytest.raises(ValueError):
        OpenClawGateway("https://user:secret@public.example", "secret")
    with pytest.raises(GatewayError, match="unavailable"):
        OpenClawGateway("http://127.0.0.1:1", "secret").complete([], [])
