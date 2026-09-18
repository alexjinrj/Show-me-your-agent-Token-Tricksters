# Unified agent runtime: implementation and acceptance

## Implemented paths

```text
Browser -> POST /api/assistant -> RuntimeService -> OpenClaw Gateway
                           <- client function calls --+
                           -> ToolExecutor -> sales / inventory / CRM tools
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
tools and 10 CRM service-recovery tools. CRM now uses the SAME immutable
AdventureWorks snapshot as Sales/Inventory, not the separate Olist fixture.
It supports derived customer scoring, order-service exception triage,
resolution comparison and reply drafts, preserving upstream lineage.
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
deployments should apply migrations through `0006_crm_runtime_evidence` to the
same database used by the API. `scripts/migrate_runtime.py` previews the target
from `BC_DB_PATH`; after stopping the API and backing up that database, rerun
with `--apply`. Do not blindly use the default database URL in `alembic.ini`.

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

### CRM 人工审核闭环

队员代码来源为 `main@ac9d327` 的 `repo-overlay/`；本地集成已将其接入正式项目目录，
不是让应用从 overlay 运行。统一数据版完整链路发布在 `feature/agent-runtime`，尚未合并到 `main`。

1. 在统一聊天中请求分析 `CASE-SO74695`（来源订单 `SO74695`）。模型调用 CRM 建议与未发送草稿工具。
2. 聊天证据中的 **Review CRM recommendation** 按钮打开 CRM 案件审核表单，并关联
   `sourceAgentRunId` 和 `sourceToolCallId`。模型不会自动提交或审批提案。
3. 人工选择可行方案、修改草稿并提交。后端校验 AgentRun 已完成，证据成功、属于
   `recommend_resolution`、案件及数据集指纹匹配；提交时保存调查、选定方案、来源证据与来源标签。
4. 人工填写审核人后批准或拒绝。审批使用待审核状态的原子比较更新；已审核记录不允许覆盖。
5. AgentRun、提案、证据及审批审计都保存在 SQLite，重启后可通过相应 GET 接口读取。

从 CRM 面板手动提交也可不传 Runtime 来源，但后端仍保存提交时的调查和数据集引用。
来源字段必须同时提供，非法来源及当前不可行的演示方案返回 422；重复审批返回 409。
升级前的历史提案没有新增证据，其字段保持为空，不伪造历史溯源。

CRM 使用 `DemoContext` 已创建的规范快照；工具 `reference_id`、API `dataset_reference`
与 Runtime 的 `snapshot_id` 相同，币种为 SGD，客户号直接沿用 `AW...`。
现有统一数据的 486 个客户、500 个销售订单、商品和库存均不重复导入。
100 个 backlog 订单形成 `CASE-SO...` 服务异常投影，不是客户提交的真实投诉。
客户价值使用订单金额而非已支付消费；逾期依据订单截止日期而非投诉 SLA。
库存来自同一快照，待履约义务由 pending 订单计算，不能声称已做仓库预留。
退款敞口是条件性估计；支付/退款资格、补偿政策、物流费和解决 ETA 缺失，不补造数据。
工具保留 `state_type=actual` 表示快照读取，同时在 `data_scope`、
`provenance` 和 `caseKind` 标明派生计算，不把评分或案件当成原始事实。
旧快照或旧 Olist 审核记录不删除，但不会进入当前快照的审核列表，也不能跨快照审批。
`BC_CRM_DATA_PATH` 配置已移除，启动时不读取 Olist 文件。

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

统一数据版本全量 Python 回归通过 121 项，前端通过 3 项。
快照/金额/库存一致性、迁移 CLI、Gateway 禁用场景和审核证据链专项验证通过；
Ruff、mypy、JS 语法检查通过。本地默认数据库已备份后迁移至 0006，
实际 API 启动与 CRM/提案读取通过，迁移及启动前后的 Actual State 哈希保持一致。

Automated tests use a fake HTTP Gateway with the official request/response
contract plus real backend tools/SQLite, and real MCP stdio transport. They test
sales/inventory reads, persisted four-strategy inventory comparison, the full
sales baseline/fork/event/run/compare chain, scope rejection/audit, conversation
history, budgets and Gateway failure. They do not substitute for real OpenClaw
model/provider acceptance. CRM tests additionally cover HTTP Gateway calls across
all three tool domains, runtime-audit linkage, explicit proposal review, persisted
evidence after restart, mismatched evidence rejection, migration of legacy review
records, infeasible demo resolutions and duplicate/blank-reviewer rejection.
The smoke command includes CRM reads/recommendations/unsent drafts, requires a running configured API
and makes real analysis requests, saving only simulation/audit/runtime records.

Official references:

- [Gateway client-function contract](https://docs.openclaw.ai/gateway/openai-http-api)
- [Per-agent entries](https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent)
- [Tool policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)
