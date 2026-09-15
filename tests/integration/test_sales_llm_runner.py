from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_runtime.llm_runner import (
    choose_mode,
    render_trace,
    run_sales_agent,
)
from enterprise_state.service import ActualStateService, commit_demo_files
from tools.sales import SalesAgentTools


class FakeClient:
    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        self.requests: list[dict[str, Any]] = []

    def create(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        *,
        tool_choice: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        self.requests.append(
            {"messages": messages, "tools": tool_definitions, "tool_choice": tool_choice}
        )
        if len(self.requests) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_actual_state_summary",
                                        "arguments": json.dumps({"snapshot_id": self.snapshot_id}),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        assert messages[-1]["role"] == "tool"
        assert json.loads(messages[-1]["content"])["data"]["backlog_count"] == 100
        return {
            "choices": [
                {
                    "message": {"content": "当前积压 100 单。", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
        }


class TextOnlyClient:
    def create(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        *,
        tool_choice: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {"content": "I will call a tool.", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ]
        }


def test_llm_tool_loop_uses_real_sales_data_and_records_trace(
    service: ActualStateService, demo_path: Path
) -> None:
    kinds = (
        "customers",
        "suppliers",
        "items",
        "inventory",
        "sales_orders",
        "purchase_orders",
        "resources",
        "opening_balances",
    )
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in kinds))
    snapshot = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    client = FakeClient(snapshot.snapshot_id)
    trace = run_sales_agent(
        tools=SalesAgentTools(service.engine),
        client=client,
        prompt="现在积压多少订单？",
        snapshot_id=snapshot.snapshot_id,
        skill_text="Use actual data.",
        mode="exceptions",
        emit=lambda _: None,
    )
    assert trace["status"] == "complete"
    assert trace["usage"]["total_tokens"] == 42
    assert trace["events"][0]["result"]["data"]["backlog_count"] == 100
    assert len(client.requests) == 2
    assert len(client.requests[0]["tools"]) == 4
    assert "当前积压 100 单" in render_trace(trace)

    diagnostics: list[str] = []
    failed = run_sales_agent(
        tools=SalesAgentTools(service.engine),
        client=TextOnlyClient(),
        prompt="追踪订单",
        snapshot_id=snapshot.snapshot_id,
        skill_text="Use tools.",
        mode="exceptions",
        emit=diagnostics.append,
    )
    assert failed["failure_reason"] == "model_did_not_return_structured_tool_calls"
    assert any("structured tool_calls" in line for line in diagnostics)


def test_mode_and_html_escaping() -> None:
    assert choose_mode("如果仓库增加一名员工，结果如何？", "auto") == "scenario"
    assert choose_mode("订单积压多少？", "auto") == "exceptions"
    page = render_trace(
        {
            "mode": "exceptions",
            "snapshot_id": "id",
            "status": "complete",
            "prompt": "<script>alert(1)</script>",
            "events": [],
            "answer": "done",
            "usage": {},
        }
    )
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
