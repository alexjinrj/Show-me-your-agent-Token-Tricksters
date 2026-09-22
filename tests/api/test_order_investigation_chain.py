from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.runtime import build_runtime


class InvestigationGateway:
    """Scripted protocol check, not a real model evaluation."""

    def __init__(self) -> None:
        self.step = 0
        self.peak = ""

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.step += 1
        if self.step == 1:
            name, args = "get_data_catalog", {}
        elif self.step == 2:
            name, args = (
                "analyze_order_spikes",
                {"start": "2026-09-01", "end": "2026-10-01", "timezone": "Asia/Singapore"},
            )
        elif self.step == 3:
            evidence = json.loads(messages[-1]["content"])
            assert evidence["status"] == "ok"
            self.peak = evidence["data"]["peak_days"][0]["date"]
            name, args = (
                "search_public_events",
                {"start_date": self.peak, "end_date": self.peak, "country": "China"},
            )
        else:
            evidence = json.loads(messages[-1]["content"])
            if evidence["status"] == "error":
                return {
                    "role": "assistant",
                    "content": "Internal drill-down completed; web search not configured.",
                }
            assert (
                evidence["data"]["evidence_kind"] == "external_public_context_not_enterprise_fact"
            )
            url = evidence["data"]["sources"][0]["url"]
            return {"role": "assistant", "content": f"Candidate explanation only. Source: {url}"}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call{self.step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        }


@pytest.mark.parametrize("search_enabled", [False, True])
def test_runtime_internal_then_external_audited_chain(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, search_enabled: bool
) -> None:
    queries = []

    class FakeProvider:
        def search(self, query):
            queries.append(query)
            return {
                "results": [
                    {
                        "title": "Synthetic event context",
                        "url": "https://example.com/event",
                        "content": "Test source only, not a live event assertion.",
                    }
                ]
            }

    monkeypatch.setenv("BC_ENABLE_WEB_SEARCH", "1" if search_enabled else "0")
    monkeypatch.setenv("TAVILY_API_KEY", "test-placeholder-never-sent")
    monkeypatch.setattr("interfaces.runtime.TavilySearch", lambda key: FakeProvider())
    context = client.app.state.context
    fingerprint = context.base_manifest().content_hash
    runtime = build_runtime(context, use_gateway=False)
    runtime.gateway = InvestigationGateway()
    client.app.state.runtime = runtime
    response = client.post(
        "/api/assistant",
        json={"message": "Investigate September 2026 orders; assume China market for this test."},
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert [row["tool_name"] for row in run["evidence"]] == [
        "get_data_catalog",
        "analyze_order_spikes",
        "search_public_events",
    ]
    if search_enabled:
        assert runtime.gateway.peak in queries[0]
        assert "AW" not in queries[0] and "SO" not in queries[0]
        assert "Candidate explanation only" in run["reply"]
    else:
        assert not queries
        assert run["evidence"][-1]["error_code"] == "WEB_SEARCH_NOT_CONFIGURED"
    assert client.get(f"/api/assistant/runs/{run['agent_run_id']}").json() == run
    assert context.base_manifest().content_hash == fingerprint
