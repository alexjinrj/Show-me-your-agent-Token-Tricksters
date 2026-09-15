"""Small, auditable Chat Completions loop over the registered sales tools."""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from tools.sales.tools import SalesAgentTools

TOOL_DESCRIPTIONS = {
    "get_actual_state_summary": "Read current sales orders, backlog, and snapshot lineage.",
    "list_exceptions": "List current sales backlog and inventory exceptions.",
    "trace_process_bottleneck": "Inspect current O2C queues and capacity evidence.",
    "trace_business_object": "Trace a sales order by its order number.",
    "get_metric_history": "Check whether an actual historical metric is available.",
    "create_simulation_session": "Create an isolated scenario session from an actual snapshot.",
    "get_simulation_state": "Inspect an isolated simulation session and its events.",
    "fork_simulation_session": "Fork a baseline simulation session for an alternative.",
    "add_simulation_event": "Add a permitted warehouse or supplier scenario event.",
    "run_simulation": "Run an isolated scenario with explicit horizon and seed.",
    "compare_simulation_runs": "Compare compatible baseline and alternative runs.",
}

EXCEPTION_TOOLS = (
    "get_actual_state_summary",
    "list_exceptions",
    "trace_business_object",
    "get_metric_history",
)
SCENARIO_TOOLS = (
    "get_actual_state_summary",
    "list_exceptions",
    "create_simulation_session",
    "get_simulation_state",
    "fork_simulation_session",
    "add_simulation_event",
    "run_simulation",
    "compare_simulation_runs",
)


class CompletionClient(Protocol):
    def create(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        *,
        tool_choice: str,
        max_output_tokens: int,
    ) -> dict[str, Any]: ...


class ChatCompletionsClient:
    """HTTP client with no additional Python dependencies."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        token_parameter: str = "max_completion_tokens",
        timeout: int = 60,
    ) -> None:
        if not base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("Use HTTPS for a remote API URL")
        if token_parameter not in {"max_completion_tokens", "max_tokens"}:
            raise ValueError("Unsupported token parameter")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.token_parameter = token_parameter
        self.timeout = timeout

    def create(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        *,
        tool_choice: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tool_definitions,
            "tool_choice": tool_choice,
            self.token_parameter: max_output_tokens,
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM API connection failed: {exc.reason}") from exc
        if len(raw) > 2_000_000:
            raise RuntimeError("LLM API response exceeded 2 MB")
        result = json.loads(raw)
        if not isinstance(result, dict) or not result.get("choices"):
            raise RuntimeError("LLM API returned no choices")
        return result


def choose_mode(prompt: str, requested: str) -> str:
    if requested != "auto":
        return requested
    markers = (
        "如果",
        "假设",
        "模拟",
        "情景",
        "方案",
        "增加人",
        "供应商",
        "对比",
        "what if",
        "scenario",
        "simulate",
        "compare",
    )
    return "scenario" if any(word in prompt.lower() for word in markers) else "exceptions"


def run_sales_agent(
    *,
    tools: SalesAgentTools,
    client: CompletionClient,
    prompt: str,
    snapshot_id: str,
    skill_text: str,
    mode: str,
    max_rounds: int = 8,
    max_tool_calls: int = 12,
    max_output_tokens: int = 600,
    emit: Callable[[str], None] = print,
) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    if max_rounds < 2 or max_tool_calls < 1 or max_output_tokens < 1:
        raise ValueError("Limits must allow at least one tool round and a final answer")
    if mode not in {"exceptions", "scenario"}:
        raise ValueError("Unknown sales mode")
    selected = EXCEPTION_TOOLS if mode == "exceptions" else SCENARIO_TOOLS
    schemas = tools.schemas()
    definitions = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": schemas[name],
            },
        }
        for name in selected
    ]
    system = (
        "You are the sales workstream of one SME Coordinator Agent. Answer in the user's "
        "language. Use only registered tools for data claims. The current snapshot_id is "
        f"{snapshot_id}. Cite tool_call_id or reference_id for material claims. Distinguish "
        "actual state from simulated outcomes. State missing history plainly. Do not invent "
        "numbers or claim a scenario changed actual state. If resource data is synthetic, say "
        "so. Translate reorder point accurately; it is not necessarily safety stock. For the "
        "final answer, use no more than 300 Chinese characters or 220 English words and answer "
        "only what was asked. In exceptions mode, your owned scope is sales orders, statuses, "
        "backlog sales value, and order evidence. Do not make customer-relationship, inventory, "
        "accounting, or operations decisions; identify the responsible workstream when asked.\n\n"
        f"Sales skill:\n{skill_text}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    trace: dict[str, Any] = {
        "prompt": prompt,
        "mode": mode,
        "snapshot_id": snapshot_id,
        "events": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "answer": None,
        "status": "incomplete",
        "finish_reason": None,
        "failure_reason": None,
    }
    call_count = 0
    for round_number in range(1, max_rounds + 1):
        choice_mode = (
            "none"
            if round_number == max_rounds or call_count >= max_tool_calls
            else "required"
            if round_number == 1
            else "auto"
        )
        response = client.create(
            messages,
            definitions,
            tool_choice=choice_mode,
            max_output_tokens=max_output_tokens,
        )
        usage = response.get("usage") or {}
        for field in trace["usage"]:
            trace["usage"][field] += int(usage.get(field) or 0)
        choice = response["choices"][0]
        trace["finish_reason"] = choice.get("finish_reason")
        message = choice["message"]
        content = message.get("content") or ""
        calls = message.get("tool_calls") or []
        legacy_call = message.get("function_call")
        if not calls and isinstance(legacy_call, dict):
            calls = [
                {
                    "id": f"legacy_call_{round_number}",
                    "type": "function",
                    "function": legacy_call,
                }
            ]
        if content:
            trace["events"].append({"kind": "assistant", "round": round_number, "text": content})
            emit(f"[round {round_number}] Agent: {content}")
        if not calls:
            trace["answer"] = content
            if call_count == 0:
                trace["failure_reason"] = "model_did_not_return_structured_tool_calls"
            trace["status"] = (
                "complete"
                if content and call_count > 0 and choice.get("finish_reason") != "length"
                else "incomplete"
            )
            break
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "tool_calls": calls,
        }
        messages.append(assistant_message)
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be an object")
            except (ValueError, TypeError) as exc:
                arguments = {}
                result: dict[str, Any] = {
                    "status": "error",
                    "error_code": "INVALID_JSON",
                    "error_message": str(exc),
                }
            else:
                if name not in selected:
                    result = {"status": "error", "error_code": "TOOL_NOT_ALLOWED"}
                elif "snapshot_id" in arguments and arguments["snapshot_id"] != snapshot_id:
                    result = {"status": "error", "error_code": "SNAPSHOT_MISMATCH"}
                elif call_count >= max_tool_calls:
                    result = {"status": "error", "error_code": "TOOL_BUDGET_EXCEEDED"}
                else:
                    call_count += 1
                    result = tools.call(name, arguments, agent_case_id="sales-llm-demo").model_dump(
                        mode="json", exclude_none=True
                    )
            event = {
                "kind": "tool",
                "round": round_number,
                "name": name,
                "arguments": arguments,
                "result": result,
            }
            trace["events"].append(event)
            emit(f"[round {round_number}] Tool: {name} {json.dumps(arguments, ensure_ascii=False)}")
            emit(f"  -> {json.dumps(result, ensure_ascii=False)}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    emit(f"Usage: {json.dumps(trace['usage'], ensure_ascii=False)}; tool calls: {call_count}")
    if trace["status"] != "complete":
        if trace["finish_reason"] == "length":
            emit(
                "Agent answer was truncated by the output-token limit; increase "
                "--max-output-tokens or request a shorter answer."
            )
        elif trace["failure_reason"] == "model_did_not_return_structured_tool_calls":
            emit(
                "The model returned tool-call prose instead of structured tool_calls. "
                "Select a tool-capable model and verify that the API gateway supports "
                "Chat Completions function calling."
            )
        else:
            emit("Agent did not finish within the configured round/tool limits.")
    return trace


def render_trace(trace: dict[str, Any]) -> str:
    def block(value: Any) -> str:
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))

    cards = []
    for event in trace["events"]:
        if event["kind"] == "assistant":
            cards.append(
                f"<section><h2>Round {event['round']} · Agent</h2>"
                f"<pre>{html.escape(event['text'])}</pre></section>"
            )
        else:
            cards.append(
                f"<section><h2>Round {event['round']} · {html.escape(event['name'])}</h2>"
                f"<details><summary>Arguments</summary><pre>{block(event['arguments'])}</pre></details>"
                f"<details><summary>Tool result</summary>"
                f"<pre>{block(event['result'])}</pre></details></section>"
            )
    return (
        '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Sales LLM Trace</title>'
        "<style>body{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 16px;"
        "background:#f5f7fa;color:#17212b}section{background:white;border:1px solid #dce3e9;"
        "border-radius:10px;padding:16px;margin:14px 0}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;"
        "line-height:1.5}summary{cursor:pointer;padding:8px}small{color:#52606d}</style>"
        "<h1>Sales Agent · LLM Trace</h1>"
        f"<small>Mode: {html.escape(trace['mode'])} · Snapshot: {html.escape(trace['snapshot_id'])}"
        f" · Status: {html.escape(trace['status'])}</small>"
        f"<section><h2>Prompt</h2><pre>{html.escape(trace['prompt'])}</pre></section>"
        + "".join(cards)
        + "<section><h2>Final answer</h2>"
        + f"<pre>{html.escape(trace['answer'] or '(incomplete)')}</pre></section>"
        + f"<small>API token usage: {block(trace['usage'])}</small></html>"
    )
