# Architecture Restructure Handoff

> 本文主体记录架构重构时的历史基线；最新 Runtime 状态见文末的 2026-09-17 更新及 `AGENT_RUNTIME_HANDOFF.md`。

## Purpose

This restructure separates the simulation core, source loading, persisted
enterprise state, business tools, shared Agent runtime, backend interfaces, and
frontend. It is intentionally a behavior-preserving baseline for three later
workstreams; it does not claim that every cross-layer contract is finished.

## Layer ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| `core` | Enterprise objects/events/activity runs, process YAML validation, generic SimPy execution, checkpoints and result models | File formats, ORM sessions, LLM calls, HTTP routes |
| `load_data` | Source adapters, inspection, mapping, validation and provenance | SQL persistence, simulations, recommendations |
| `enterprise_state` | SQL schema, Actual State, snapshots, simulation persistence and audit persistence | Source-specific parsing, business recommendations, LLM orchestration |
| `tools` | Sales, inventory, CRM and simulation business operations plus callable tool wrappers | Prompt orchestration and frontend rendering |
| `agent_runtime` | Tool selection loop, context control, policies and traces | Direct database access and authoritative calculations |
| `interfaces` | FastAPI request/response transport and reports | Duplicated business rules |
| `frontend` | User interaction and visualization | Authoritative state, scoring, recommendations or a separate Agent runtime |

`core` has no imports from `load_data`, `enterprise_state`, `tools`,
`agent_runtime`, or `interfaces`.

## Main moves

- `business_coordinator/domain` became `core`.
- Generic simulation execution moved to `core/simulation`.
- Persisted simulation-session orchestration moved to `tools/simulation` because
  it combines the core engine with database records.
- `business_coordinator/ingestion` became `load_data`.
- `business_coordinator/persistence` became `enterprise_state`.
- Inventory calculations and the inventory strategy wrapper now live together
  under `tools/inventory`.
- Sales contracts and tools moved to `tools/sales`; the LLM loop moved to
  `agent_runtime`; report rendering moved to `interfaces/reports`.
- FastAPI moved to `interfaces/api` and the existing browser UI moved from
  `web` to `frontend`.
- Process YAML moved into `core/process_definitions`.
- Demo source data moved to `data/load_data/adventureworks_demo`; generated
  databases default to `runtime_data` and remain ignored.

## Interface alignment status

### 1. Load data to simulator

Current stable simulator boundary:

```text
validated source rows -> SQL Actual State -> immutable SnapshotBundle -> core.simulation
```

Aligned now:

- The simulator receives a detached `SnapshotBundle`, never an ORM session.
- `SnapshotBundle` retains object/event provenance and a deterministic content
  hash.

Not aligned yet:

- `load_data` validates one source file at a time; there is no single
  `CanonicalInputBundle` covering a complete import batch.
- The inventory strategy tool still accepts `item_rows`, `inventory_rows`,
  `sales_rows`, and `purchase_rows` separately in addition to a snapshot. This
  creates a second data path outside the canonical snapshot.
- The Olist data in PR #5 has not been mapped into the canonical input and
  Enterprise State contracts.

Owner: `feature/data-alignment`.

### 2. Simulator to Agent

Current stable simulator output is `SimulationRunResult`, including metrics,
events, accounting impacts, daily checkpoints, hashes, horizon, and seed.

Not aligned yet:

- Sales wraps results in `ToolResponse`, while inventory returns
  `InventoryStrategyToolResult`; there is no shared tool-result envelope.
- The current LLM loop is sales-specific and uses static tool lists rather than
  a generic Tool Registry.
- Context-selection rules for large Enterprise State and simulation traces are
  not yet implemented.

Owner: `feature/agent-runtime`.

### 3. Backend to frontend

The existing frontend currently consumes the FastAPI snapshot, process,
session, run, comparison, and checkpoint JSON successfully.

Not aligned yet:

- Backend response envelopes are not versioned and no generated frontend types
  or checked OpenAPI contract exist.
- PR #5 is a standalone CRM full-stack prototype with duplicated data,
  calculations, Agent tools, and local approval state. Only its UI/workflow
  should be adapted into `frontend`; authoritative logic must move to backend
  tools and Enterprise State.
- CRM approval, tool trace, provenance, and incremental playback contracts need
  explicit backend schemas before the frontend integration.

Owner: `feature/front-end`.

## Follow-up branches

All three local branches should start from the committed restructure baseline:

- `feature/data-alignment`: canonical import batch, modular adapters, snapshot-only
  inventory inputs, and Olist mapping/provenance.
- `feature/agent-runtime`: generic Tool Registry, common tool-result envelope,
  context builder, policies, audit integration, and sales/inventory registration.
- `feature/front-end`: simplify and integrate PR #5, remove duplicated backend
  logic, and consume versioned FastAPI contracts.

These are branches only. Create separate worktrees later when an Agent is
assigned to a workstream.

## Verification commands

```bash
PYTHONPATH=src uv run ruff format --check .
PYTHONPATH=src uv run ruff check .
PYTHONPATH=src uv run mypy src
PYTHONPATH=src uv run pytest -q
```

Verified on the restructure branch:

- Ruff check passed.
- Ruff format check passed for 87 files.
- Strict mypy passed for 45 source files.
- Pytest passed: 78 tests, with two existing dependency deprecation warnings.
- The standalone simulation demo reported `Actual State unchanged: True` and
  `Baseline reproducible: True`.
- The seeded deterministic Sales Agent demo generated its JSON and offline HTML
  report successfully.

## Invariants for every follow-up Agent

1. Actual State is authoritative; simulation never writes back to it.
2. The core simulator accepts immutable snapshots, not writable repositories.
3. Business numbers are calculated by deterministic tools, not the LLM or
   frontend.
4. Process behavior belongs in validated YAML; Python contains only generic
   execution primitives.
5. Preserve `source`, `derived`, and `synthetic` provenance.
6. Keep daily checkpoints and compatibility aliases until the frontend contract
   is deliberately versioned.

## CRM interface integration update — 2026-09-17

The CRM interface work is now implemented on top of `feature/agent-runtime`:

- 10 deterministic CRM tools are registered in the shared Tool Registry and
  therefore use the same Web/MCP executor, evidence envelope and audit path.
- Versioned `/api/v1/crm/*` contracts expose summary, customer, complaint,
  provenance and proposal-review records.
- The team frontend consumes those contracts and contains no scoring or
  complaint-priority calculations.
- Proposals and human approval/rejection are persisted in Enterprise State;
  they record review state only and perform no real customer contact, refund,
  shipment or Actual State write.
- The original green frontend has temporary `/api/crm/*` compatibility routes.

The Olist demonstration fixture remains explicitly separate from the canonical
AdventureWorks `SnapshotBundle`. Mapping Olist into canonical Enterprise State
is still owned by data alignment. See `CRM_RUNTIME_INTEGRATION.md`.

## Agent Runtime integration update — 2026-09-17

发布分支：`feature/agent-runtime`，尚未合并到 `main`。本节更新 Runtime 工作流状态，不将上述历史基线中的待办自动视为全部完成。

### 已构建的 Sales / Inventory 链路

```text
frontend -> FastAPI /api/assistant -> RuntimeService
         -> OpenClaw Gateway /v1/chat/completions
         -> function tool calls -> shared ToolExecutor
         -> sales / inventory tools -> snapshots / persisted simulations
         -> tool evidence -> Gateway final reply -> persisted AgentRun -> frontend
```

- `interfaces/runtime.py` 是装配入口，注册 11 个 Sales 工具和 2 个 Inventory 工具；Web 与 MCP 共享执行器。MCP 是独立工具入口，不是 Web 请求的重复执行路径。
- Runtime 通过注入的 Gateway、存储和作用域检查接口工作，不直接访问数据库或模拟器；权威业务计算仍在工具层。
- 统一结果封装包含工具调用标识、快照/模拟运行引用和 Actual/Simulated 区分。Inventory 策略模拟现在通过 SimulationService 持久化。
- AgentRun、工具轨迹及证据由 Enterprise State 持久化；新增 `0004_agent_runs` 迁移。会话历史由应用维护，后续事实仍需重新调用工具查询。
- 执行器仅允许 read/simulate，校验快照及会话/模拟运行作用域，保留审计；Runtime 限制工具轮数、调用次数及上下文大小。
- 浏览器展示真实回复、证据和运行标识，禁止并发重复提交；未配置 Gateway 时明确返回 disabled，不伪装成已完成业务回答。

### 验证与未完成边界

- 完整 Python 测试曾通过 107 项；最近的 Runtime/API/MCP/策略/迁移专项复核通过 15 项，前端测试通过 2 项。Ruff、mypy 和前端语法检查通过。
- Gateway 合同测试使用模拟 HTTP 服务；MCP、业务工具和数据库测试实际执行。尚未完成真实 Lightsail OpenClaw / 模型端到端验收；配置状态接口不等于 Gateway 健康证明。
- CRM interface follow-up has now registered 10 read-only tools, added backend
  proposal/review persistence and replaced frontend-local scoring. Olist-to-canonical
  SnapshotBundle mapping remains unfinished and is still a separate data-alignment task.
- 数据对齐分支的后续工作需另行审查合并。本次 Runtime 上传不代表 Olist 映射、全部导入契约或其他分支已合并。
- 当前面向私有、单企业、单进程演示；尚无用户鉴权、多租户隔离、分布式作业、断点恢复或真实业务写入审批链路。

详细构建、接口、工具及限制见 [Agent Runtime handoff](AGENT_RUNTIME_HANDOFF.md)；部署步骤见 [AWS Lightsail OpenClaw 接入说明](AWS_LIGHTSAIL_OPENCLAW_接入说明.md)。
