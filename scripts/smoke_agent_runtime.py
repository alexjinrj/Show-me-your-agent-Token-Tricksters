"""Live acceptance against an already-running API; no fabricated model fallback."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    def call(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = Request(
            args.api_url.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=310) as response:
            return dict(json.load(response))

    if not call("/api/assistant/status")["enabled"]:
        raise SystemExit("OpenClaw is not configured; live acceptance was not performed.")
    before = call("/api/snapshot")["manifest"]["content_hash"]
    conversation_id = None
    for prompt, expected in (
        (
            "请调用销售汇总和库存补货候选工具，给出当前风险并引用工具证据。",
            {"get_actual_state_summary", "list_inventory_reorder_candidates"},
        ),
        (
            "请调用库存策略比较工具，比较未来3天补货策略，种子42，说明结果是模拟而非实际采购。",
            {"compare_inventory_replenishment_strategies"},
        ),
        (
            "请调用 get_crm_summary、recommend_resolution 分析 CASE-SO74695，并调用 "
            "draft_customer_reply 起草回复。引用统一快照证据，标明订单服务异常是派生而非真实投诉；"
            "不要发送回复、创建审批、退款或发货。",
            {"get_crm_summary", "recommend_resolution", "draft_customer_reply"},
        ),
    ):
        run = call("/api/assistant", {"message": prompt, "conversation_id": conversation_id})
        if run["status"] != "completed" or not run["evidence"]:
            raise SystemExit(f"Live acceptance failed: {run['status']}: {run['reply']}")
        if any(item["status"] != "ok" for item in run["evidence"]):
            raise SystemExit("Live acceptance returned tool errors; inspect the run trace.")
        if not expected <= {item["tool_name"] for item in run["evidence"]}:
            raise SystemExit("Agent did not execute the requested acceptance tools.")
        if call(f"/api/assistant/runs/{run['agent_run_id']}") != run:
            raise SystemExit("Persisted runtime evidence does not match the response.")
        conversation_id = run["conversation_id"]
        print(f"PASS {run['agent_run_id']} ({len(run['evidence'])} business calls)")
    if call("/api/snapshot")["manifest"]["content_hash"] != before:
        raise SystemExit("Actual snapshot changed during analysis.")
    print("PASS live OpenClaw chain and immutable snapshot")


if __name__ == "__main__":
    main()
