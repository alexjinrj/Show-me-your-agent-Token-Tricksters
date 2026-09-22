from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


class RetrievalGateway:
    """Offline contract test; deliberately not a claim of real model reasoning."""

    def __init__(self) -> None:
        self.step = 0

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.step += 1
        available = {item["function"]["name"] for item in tools}
        assert "query_snapshot_records" in available
        if self.step == 1:
            name, args = "get_data_catalog", {}
        elif self.step == 2:
            evidence = json.loads(messages[-1]["content"])
            assert "order_date" in evidence["data"]["datasets"]["orders"]["fields"]
            name, args = (
                "query_snapshot_records",
                {"dataset": "orders", "group_by": ["order_month"], "limit": 1},
            )
        elif self.step == 3:
            evidence = json.loads(messages[-1]["content"])
            assert evidence["data"]["total_matching"] == 500
            name, args = (
                "compare_snapshot_periods",
                {
                    "query": {"dataset": "orders", "limit": 1},
                    "date_field": "order_date",
                    "baseline": {"start": "2026-08-01", "end": "2026-09-01"},
                    "comparison": {"start": "2026-09-01", "end": "2026-10-01"},
                },
            )
        else:
            evidence = json.loads(messages[-1]["content"])
            assert evidence["status"] == "ok"
            assert "deltas" in evidence["data"]
            return {
                "role": "assistant",
                "content": f"Snapshot comparison: {evidence['tool_call_id']}",
            }
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{self.step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        }


def test_assistant_discovers_filters_compares_and_persists(client: TestClient) -> None:
    context = client.app.state.context
    before = context.base_manifest().content_hash
    client.app.state.runtime.gateway = RetrievalGateway()
    response = client.post("/api/assistant", json={"message": "Compare monthly order amounts"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert [e["tool_name"] for e in run["evidence"]] == [
        "get_data_catalog",
        "query_snapshot_records",
        "compare_snapshot_periods",
    ]
    assert client.get(f"/api/assistant/runs/{run['agent_run_id']}").json() == run
    assert context.base_manifest().content_hash == before
