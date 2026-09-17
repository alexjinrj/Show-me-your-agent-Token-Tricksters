# Unified agent runtime: implementation and acceptance

## Implemented paths

```text
Browser -> POST /api/assistant -> RuntimeService -> OpenClaw Gateway
                           <- client function calls --+
                           -> ToolExecutor -> sales / inventory tools
                                          -> snapshots / persisted simulations
                           -> tool results -> Gateway -> final answer + evidence

Standalone OpenClaw MCP -> interfaces.mcp.server -> same ToolExecutor
```

The web path uses the official Gateway client-function handoff contract, not a
second Python model. This lets the backend enforce each request's snapshot scope
and retain the complete business-tool evidence. Do not attach the standalone MCP
server to the dedicated web agent: that would introduce a second, differently
scoped route to the same capabilities.

23 business tools are registered: 11 sales tools, 2 snapshot-backed inventory
tools and 10 CRM service-recovery tools. CRM uses the bundled Olist demo fixture
with explicit source/derived/synthetic provenance. It supports deterministic
customer scoring, complaint triage, resolution comparison and reply drafts.
Proposal creation and approval remain explicit HTTP actions outside the LLM tool
surface and persist review-only records; they execute no customer contact,
refund, shipment or Actual State write.

## Setup

1. Install Python 3.12, uv, and a current OpenClaw version with Gateway client
   function support. Check OpenClaw's Node requirements before installation.
2. Configure a working model/provider in OpenClaw using its normal onboarding.
3. Merge `integrations/openclaw/gateway.json.example` into your existing Gateway
   configuration, preserving auth/model settings. It creates a dedicated
   `business-coordinator` agent and disables its internal tools. Validate against
   the installed version's `openclaw config schema`; older versions may have
   different agent configuration keys. This example targets current
   `agents.entries`, not the retired `agents.list` structure.
4. Keep authenticated Gateway access on loopback/private infrastructure. Start
   the Gateway normally. Do not expose its operator credential to the browser.
5. In the repository root, PowerShell:

```powershell
uv sync --all-groups
$env:BC_OPENCLAW_URL = 'http://127.0.0.1:18789'
$env:BC_OPENCLAW_TOKEN = Read-Host 'Gateway token'
$env:BC_OPENCLAW_AGENT_ID = 'business-coordinator'
uv run uvicorn interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

`.env.example` documents variables; the application does not automatically load
`.env`. Export them in the process environment. Missing URL/token disables the
agent without pretending to perform analysis. `enabled` means configured, not
that Gateway connectivity/model health has been verified.

The API bootstrap creates missing tables on an existing demo DB. Managed
deployments should apply Alembic revision `0004_agent_runs` to their configured
database using the project's existing migration configuration.

## API and trace

- `GET /api/assistant/status`: configured state, schemas and budgets.
- `POST /api/assistant`: message, optional conversation_id, simulation session_id,
  simulation run_id. IDs are UUIDs; simulation references must match the base
  snapshot, and supplied session/run context must be consistent.
- Response: status (`disabled`, `completed`, `failed`), reply, agent_run_id,
  conversation_id, snapshot_id, events, common-envelope evidence and Gateway
  reported per-round model_usage (absent provider usage is not estimated).
- `GET /api/assistant/runs/{agent_run_id}`: persisted reply and full tool trace.
- Pass the returned conversation_id for follow-ups. The app replays recent
  completed user/assistant messages, bounded to six turns; tool evidence remains
  in the run trace. The model must re-query tools for new numerical claims.

Every dispatched or rejected business call records `tool_call_audit`; sales'
existing audit is preserved rather than duplicated. Runtime traces persist
after each tool completion, so Gateway failure does not hide completed work.
Inventory comparison now persists four simulation sessions/runs/results; its
returned simulation_run_ids resolve to real stored evidence.

## Limits and trust boundary

Only read/simulate tools are callable. Strict business input models reject
unknown fields and validate ranges. Snapshot/session/run scope is checked before
dispatch. Default budgets are 8 Gateway rounds, 16 calls, 60 seconds per Gateway
request and a 240-second cooperative turn deadline. The deadline is checked
between operations; it does not preempt an already-running Python simulation.
Gateway errors are sanitized, response sizes bounded, HTTP redirects prohibited,
and non-loopback cleartext Gateway URLs rejected.
Conversation/tool message context is limited to 300,000 serialized characters;
oversized individual model-visible tool results ask for a narrower query, while
the full business evidence remains persisted.

This is a trusted, single-company, single-process demo API, not a multi-tenant
service. There is no user authentication, tenant ownership, distributed lock,
automatic recovery/resume, or streaming/job queue. Keep the API private too.
Turns are serialized and concurrent requests get 409; run records survive
restart, but interrupted running turns are not automatically resumed. Business
evidence is authoritative; natural-language grounding is instructed, not a
formal verification of every model-written claim. No real inventory/purchase
writes are exposed, so approval/execution of actual transactions is out of scope.

## Acceptance

```powershell
uv run pytest tests/api/test_runtime_chain.py tests/integration/test_openclaw_mcp.py -q
node --test tests/frontend/assistant.test.cjs
uv run python scripts/smoke_agent_runtime.py
```

Automated tests use a fake HTTP Gateway with the official request/response
contract plus real backend tools/SQLite, and real MCP stdio transport. They test
sales/inventory reads, persisted four-strategy inventory comparison, the full
sales baseline/fork/event/run/compare chain, scope rejection/audit, conversation
history, budgets and Gateway failure. They do not substitute for real OpenClaw
model/provider acceptance. The smoke command requires a running configured API
and makes real analysis requests, saving only simulation/audit/runtime records.

Official references:

- [Gateway client-function contract](https://docs.openclaw.ai/gateway/openai-http-api)
- [Per-agent entries](https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent)
- [Tool policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)
