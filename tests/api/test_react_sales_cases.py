from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


def _call(name: str, arguments: dict[str, Any], number: int) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": f"call-{number}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


class AdaptiveGateway:
    """Protocol fixture: chooses its next action from the latest tool observation."""

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        self.calls = 0

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.calls += 1
        names = {row["function"]["name"] for row in tools}
        assert {
            "get_data_catalog", "query_snapshot_records", "analyze_sales_backlog_intervention"
        } <= names
        latest_user = next(row["content"] for row in reversed(messages) if row["role"] == "user")
        last = messages[-1]
        if "先看看销售" in latest_user:
            if last["role"] == "user":
                return _call("get_data_catalog", {}, self.calls)
            evidence = json.loads(last["content"])
            if evidence["tool_name"] == "get_data_catalog":
                assert "orders" in evidence["data"]["datasets"]
                return _call(
                    "query_snapshot_records",
                    {"dataset": "orders", "group_by": ["status"], "limit": 1},
                    self.calls,
                )
            assert evidence["data"]["total_matching"] == 500
            return {"role": "assistant", "content": "已查到当前销售订单；请确认要测试的干预。"}
        if "增加2名" in latest_user:
            if last["role"] == "user":
                return _call(
                    "analyze_sales_backlog_intervention",
                    {"snapshot_id": self.snapshot_id, "additional_workers": 2,
                     "horizon_days": 7, "random_seed": 42},
                    self.calls,
                )
            evidence = json.loads(last["content"])
            assert evidence["data"]["simulation_comparison"]["verdict"] == "improved"
            return {"role": "assistant", "content": "匹配仿真改善了等待时间，原因仍未证实。"}
        if "SO74695" in latest_user:
            if last["role"] == "user":
                return _call(
                    "query_enterprise_history",
                    {"object_type": "sales_order", "object_id": "SO74695",
                     "as_of": "2026-09-12T23:59:00+08:00"},
                    self.calls,
                )
            evidence = json.loads(last["content"])
            assert evidence["status"] == "ok"
            assert evidence["data"]["reconstruction_status"] == "current_projection"
            return {"role": "assistant", "content": "这是快照时点的当前投影。"}
        if last["role"] == "user":
            return _call(
                "get_metric_history",
                {"snapshot_id": self.snapshot_id, "metric_code": "backlog_count"},
                self.calls,
            )
        evidence = json.loads(last["content"])
        assert evidence["data"]["availability"] == "not_available"
        return {"role": "assistant", "content": "缺少积压指标历史序列，无法判断趋势。"}


def test_ambiguous_react_observe_refine_and_stop_at_missing_history(client: TestClient) -> None:
    runtime = client.app.state.runtime
    runtime.gateway = AdaptiveGateway(client.app.state.context.base_snapshot_id)
    first = client.post(
        "/api/assistant", json={"message": "先看看销售有没有问题，再考虑方案"}
    ).json()
    assert first["status"] == "completed"
    assert [row["tool_name"] for row in first["evidence"]] == [
        "get_data_catalog", "query_snapshot_records"
    ]
    assert "请确认" in first["reply"]

    second = client.post("/api/assistant", json={
        "message": "增加2名仓库员工，7天，seed 42，测试积压等待时间",
        "conversation_id": first["conversation_id"],
    }).json()
    assert second["status"] == "completed"
    assert [row["tool_name"] for row in second["evidence"]] == [
        "analyze_sales_backlog_intervention"
    ]
    assert second["evidence"][0]["data"]["actual_state_unchanged"] is True

    third = client.post("/api/assistant", json={
        "message": "过去几周积压趋势如何？只用历史指标作答",
        "conversation_id": first["conversation_id"],
    }).json()
    assert third["status"] == "completed"
    assert [row["tool_name"] for row in third["evidence"]] == ["get_metric_history"]
    assert "无法判断趋势" in third["reply"]

    fourth = client.post("/api/assistant", json={
        "message": "查询 SO74695 在快照时点的状态",
        "conversation_id": first["conversation_id"],
    }).json()
    assert fourth["status"] == "completed", fourth
    assert [row["tool_name"] for row in fourth["evidence"]] == [
        "query_enterprise_history"
    ]
