#!/usr/bin/env python3
"""Ask the sales tools a question through a configurable LLM API and save its trace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_coordinator.persistence.database import make_engine, sqlite_url
from business_coordinator.persistence.models import StateSnapshotRow
from business_coordinator.sales_agent import SalesAgentTools
from business_coordinator.sales_agent.llm_runner import (
    ChatCompletionsClient,
    choose_mode,
    render_trace,
    run_sales_agent,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="sales_demo.db")
    parser.add_argument("--prompt", help="Question; if omitted, read one prompt from the terminal")
    parser.add_argument("--mode", choices=("auto", "exceptions", "scenario"), default="auto")
    parser.add_argument("--model", default=os.environ.get("SALES_LLM_MODEL"))
    parser.add_argument(
        "--base-url", default=os.environ.get("SALES_LLM_BASE_URL", "https://api.openai.com/v1")
    )
    parser.add_argument(
        "--token-param",
        choices=("max_completion_tokens", "max_tokens"),
        default="max_completion_tokens",
    )
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--max-tool-calls", type=int, default=12)
    parser.add_argument("--max-output-tokens", type=int, default=600)
    parser.add_argument("--trace-dir", type=Path, default=Path("sales_report"))
    args = parser.parse_args()

    prompt = args.prompt if args.prompt is not None else input("Sales question> ")
    if not prompt.strip():
        parser.error("prompt cannot be empty")
    if not args.model:
        parser.error("set SALES_LLM_MODEL or pass --model")
    api_key = os.environ.get("SALES_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        parser.error("set SALES_LLM_API_KEY or OPENAI_API_KEY")
    if not Path(args.database).is_file():
        parser.error(f"database not found: {args.database}")

    engine = make_engine(sqlite_url(args.database))
    with Session(engine) as database:
        snapshot = database.scalar(
            select(StateSnapshotRow).order_by(StateSnapshotRow.as_of_time.desc())
        )
        if snapshot is None:
            parser.error("no snapshot found; run scripts/seed_demo_data.py first")
        snapshot_id = snapshot.id

    mode = choose_mode(prompt, args.mode)
    repo_root = Path(__file__).resolve().parents[1]
    skill_path = (
        repo_root
        / "skills"
        / f"sales-order-{('scenario' if mode == 'scenario' else 'exception')}-analysis"
        / "SKILL.md"
    )
    skill_text = skill_path.read_text(encoding="utf-8")
    client = ChatCompletionsClient(
        base_url=args.base_url,
        api_key=api_key,
        model=args.model,
        token_parameter=args.token_param,
    )
    print(f"Model: {args.model} | mode: {mode} | snapshot: {snapshot_id}", flush=True)
    trace = run_sales_agent(
        tools=SalesAgentTools(engine),
        client=client,
        prompt=prompt,
        snapshot_id=snapshot_id,
        skill_text=skill_text,
        mode=mode,
        max_rounds=args.max_rounds,
        max_tool_calls=args.max_tool_calls,
        max_output_tokens=args.max_output_tokens,
        emit=lambda line: print(line, flush=True),
    )
    trace["model"] = args.model
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    trace_json = args.trace_dir / "llm_trace.json"
    trace_html = args.trace_dir / "llm_trace.html"
    trace_json.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    trace_html.write_text(render_trace(trace), encoding="utf-8")
    print(f"Trace: {trace_html} | JSON: {trace_json}")
    if trace["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
