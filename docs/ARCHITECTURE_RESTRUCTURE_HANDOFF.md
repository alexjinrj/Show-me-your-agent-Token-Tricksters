# Architecture Restructure Handoff

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
