# SME Business State Coordinator

An auditable simulation demo for a simplified SME distributor. CSV source data
is validated into SQL Actual State, copied into immutable snapshots, and run in
an isolated, deterministic SimPy environment. Simulation results never write
back to Actual State.

## What is included

- Deterministic CSV validation and SQLAlchemy/Alembic persistence.
- Source lineage and immutable `SnapshotBundle` values.
- Object-centric `EnterpriseState` records for orders, inventory, balances,
  events, and activity execution state.
- YAML-driven Order-to-Cash and Procure-to-Pay activities.
- Shared inventory and resource constraints across both processes.
- Operational and balanced accounting impacts.
- Scenario comparison for order arrivals, warehouse capacity changes, and
  supplier delivery changes.
- A FastAPI application and browser dashboard for running and inspecting the
  demo.
- Daily simulation checkpoints for future incremental frontend playback.
- Bounded, audited sales, inventory and CRM tools with prompt-driven LLM trajectory testing.
- Transparent RFM customer segmentation and pending-order exception share.
- Field discovery, bounded snapshot filtering/grouping and exact period comparisons.
- CRM derived service-case triage, service-recovery comparison,
  persisted proposals and explicit human approval records.

Arbitrary database-query tools, ERP submission, authentication, and production
deployment are not included yet.

See [General natural-language data questions](docs/DATA_QUESTION_AGENT.md) for the
question-driven tool workflow and supported datasets.

See [CRM scoring and retrieval guide](docs/CRM_SCORING_RETRIEVAL.md) for formulas,
example prompts, data boundaries and the offline verification command.
For “why did orders spike?” with optional web evidence, see
[Order spike investigation](docs/ORDER_SPIKE_INVESTIGATION.md).

## Runtime architecture

```text
external files / APIs
          |
          v
load_data adapters and validation
          |
          v
enterprise_state database -- immutable SnapshotBundle --> core simulation
          ^                                                |
          |                                                v
          +---------------- tools <---- Tool Registry <---- Agent runtime
                                   |
                                   v
                          FastAPI --> frontend
```

The dependency direction is intentional:

- `core` owns enterprise objects, events, process YAML, and the generic SimPy
  interpreter. It does not import databases, Agent code, or interfaces.
- `load_data` adapts heterogeneous sources into validated rows. It does not run
  simulations or contain business recommendations.
- `enterprise_state` owns SQL persistence, Actual State, immutable snapshots,
  simulation records, and audit records.
- `tools` owns business logic and the callable wrappers for sales, inventory,
  CRM, and simulation operations.
- `agent_runtime` selects only registered tools and must not read the database
  or calculate authoritative numbers directly.
- `interfaces` and `frontend` expose the system without duplicating business
  rules.

User CSV ingestion uses `ActualStateService.import_csv(...)`: it performs deterministic field
matching, whole-file validation, lineage generation, and an idempotent SQL commit. Customer and
supplier masters do not need row-level timestamps; transaction dates remain timezone-aware. See
[CSV data import contract](docs/DATA_IMPORT.md).

The two configured processes meet at `inventory_position`. Sales allocation and
shipping decrease its available, reserved, and on-hand quantities; purchasing
receipts increase the same object. Python implements generic execution
primitives, while activity bindings, durations, resources, operations, events,
financial effects, and transitions are defined under `src/core/process_definitions/`.

## Repository layout

```text
src/core/                         Models, process contracts/YAML, SimPy engine
src/load_data/                    Modular source inspection and validation
src/enterprise_state/             SQL models, repositories, Actual State, snapshots
src/tools/                        Business logic and Agent-callable tool wrappers
src/agent_runtime/                Shared LLM tool-calling runtime
src/interfaces/api/               FastAPI transport and response schemas
src/interfaces/reports/           Offline deterministic report renderers
data/load_data/adventureworks_demo/  Versioned demo input and provenance manifest
data/expected/                    Versioned expected demo assertions
runtime_data/                     Generated databases and outputs; Git ignored
frontend/                         English green SPA with seven functional pages
migrations/                       Alembic database migrations
scripts/                          Data build, seeding, and demo entry points
tests/                            Unit, integration, simulation, and API tests
```

See `docs/ARCHITECTURE_RESTRUCTURE_HANDOFF.md` for the move map, interface
alignment status, and the three follow-up workstreams.

## Start from a fresh download (Mac / Windows / Linux)

Download **Code → Download ZIP** from the integrated `main` branch and unzip it,
or clone this private repository using your GitHub account. Open a terminal **inside
the extracted project folder**: it must contain `pyproject.toml`, `uv.lock`, `src/`
and `frontend/`. Do not run these commands from your home directory or inside `frontend/`.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
With Python already installed, `python -m pip install uv` is another option
(on macOS you may need `python3`). Then run:

```bash
uv python install 3.12
uv sync --locked --all-groups
uv run uvicorn interfaces.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser. Keep this terminal open; use Ctrl+C
to stop. If port 8000 is busy, use `--port 8020` and open http://127.0.0.1:8020.
Use the same start command next time from the same project folder.

No Node/npm install, MySQL server, separate frontend server, Olist download,
API key or OpenClaw deployment is needed for the local business demo.
FastAPI serves the English green interface and its API together on one port.
The first launch seeds the included AdventureWorks demo into
`runtime_data/enterprise_state.db`; subsequent launches reuse that local database.
Each teammate gets their own database; cloning the repository does not share saved proposals.
The `.venv/` and `runtime_data/` directories are generated locally and must not be uploaded.

### What to try

Use the left navigation to open **Executive Overview, Sales, Inventory, Accounting,
Operations, Customer Relationships, AI Coordinator**.

- Overview and the four operational modules read the same Actual State snapshot.
- Operations: create a session → run a baseline → pin it → add an alternative
  event → run again → compare. Simulation does not overwrite Actual State.
- CRM: select a derived order-service case → inspect customer rating, order,
  inventory and available options → submit a proposal → approve or reject it.
  Decisions are persisted, but do not send messages, issue refunds or ship goods.
- AI Coordinator: without Gateway configuration it explicitly reports
  **not configured / disabled**. Business pages, deterministic simulations and
  manual CRM review still work. See the OpenClaw section below to enable real AI.

All CRM customer/order/SKU references now come from the same AdventureWorks snapshot.
Service cases are **derived order exceptions**, not real customer complaints.
Actual complaint counts, response SLAs and reviews are unavailable, not zero.
Older Olist demo files, if present in the repository, are not loaded by this app.

### Verify the download

In a second terminal in the project root:

```bash
uv run python scripts/smoke_local.py
uv run pytest -q
uv run ruff check src tests scripts migrations
uv run mypy src
```

The smoke check starts its own server with a temporary empty database, checks every
module and shared CRM snapshot, then stops it. It does not use LLM credentials or
modify your existing database. Developers with Node installed can additionally run
`node --test tests/frontend/*.test.cjs`.

### Updating an existing installation

A fresh download needs no manual migration. If reusing an older database, stop the
server and back up the file identified by `BC_DB_PATH` (default:
`runtime_data/enterprise_state.db`). Preview, then apply the migration:

```bash
uv sync --locked --all-groups
uv run python scripts/migrate_runtime.py
uv run python scripts/migrate_runtime.py --apply
```

Start the server again using the command above. Do not delete an existing database
as a startup workaround. The migration preserves historical proposals and adds
Runtime evidence fields. `.env.example` is a configuration reference; the server
does **not** automatically read `.env`. Set optional Gateway variables in the server
terminal, as described in `docs/AGENT_RUNTIME_HANDOFF.md`.

## Run the standalone demo

```bash
uv run python scripts/run_simulation_demo.py --open
```

The command generates `demo-output/simulation-demo.html` with a deterministic
30-day scenario comparison and checks that the baseline is reproducible and
Actual State remains unchanged.

To build a persistent demo database separately:

```bash
uv run python scripts/seed_demo_data.py --database actual_state.db
```

## Run the sales Agent demo

The deterministic sales path can generate an offline report without an LLM:

```bash
uv run python scripts/seed_demo_data.py --database sales_demo.db
uv run python scripts/demo_sales_agent.py --database sales_demo.db --report-dir sales_report
```

For prompt-driven testing, configure a tool-capable Chat Completions endpoint
using `.env.example`, then run:

```bash
uv run python scripts/chat_sales_agent.py --database sales_demo.db --mode exceptions --prompt "How many sales orders are backlogged?"
```

The terminal shows every tool call. `sales_report/llm_trace.html` and
`sales_report/llm_trace.json` record the trajectory and API-reported token use.
See `docs/NSCC_SALES_TEST.md` and `docs/SALES_LLM_EVAL_CASES.md` for cluster and
sales-only validation steps.

## Run with OpenClaw

The web assistant now runs the complete Gateway handoff chain: request context,
OpenClaw reasoning, 23 bounded sales/inventory/CRM tools, persisted simulation
evidence, audit, and final response. Configure `BC_OPENCLAW_URL`,
`BC_OPENCLAW_TOKEN` and `BC_OPENCLAW_AGENT_ID` in the backend environment.
Without configuration, the assistant reports `disabled` and executes no tools.

See [runtime setup and handoff](docs/AGENT_RUNTIME_HANDOFF.md) for the dedicated
Gateway agent configuration, API contracts, live smoke test and deployment limits.

See [CRM runtime integration](docs/CRM_RUNTIME_INTEGRATION.md) for the unified
snapshot projection, derived order-service cases, shared tools and human-review workflow.

接入已有 AWS Lightsail OpenClaw 实例的中文步骤见
[Lightsail 接入说明](docs/AWS_LIGHTSAIL_OPENCLAW_接入说明.md)，包括本地 SSH 联调、
同实例部署、凭证轮换与验收。

The same tools remain available through a standalone local MCP server:

```bash
uv run python -m interfaces.mcp.server
```

See `docs/OPENCLAW_INTEGRATION.md` for OpenClaw registration, probing, skill
loading, and the security boundary. OpenClaw is a runtime client; authoritative
calculations remain in deterministic Python tools.

## Demo data provenance

The fixture is based on Microsoft AdventureWorks OLTP CSV data. Singapore/SGD
rebasing, process statuses, resource capacity, opening balances, and embedded
exceptions are explicitly labelled `derived` or `synthetic`. Source URLs,
transformations, row counts, and hashes are retained in
`data/load_data/adventureworks_demo/SOURCE_MANIFEST.json`.

The current fixture contains 500 sales orders, 50 purchase orders, 40 SKUs, 486
customers, 8 suppliers, inventory positions, resource capacity, and opening
financial balances.

## Core invariants

1. Actual State is authoritative and is never mutated by simulation.
2. Every simulation starts from a detached immutable snapshot.
3. Money uses decimal semantics and timestamps are timezone-aware.
4. Process YAML is validated before execution.
5. Identical snapshot, configuration, scenario events, horizon, and seed produce
   an identical result hash.
6. Calculations are performed by deterministic Python code, not by an LLM or
   browser JavaScript.

The CRM workstream's checked diagnosis → intervention → simulation → comparison case is in
[CRM diagnosis-to-simulation flow](docs/CRM_DIAGNOSIS_SIMULATION_CASE.md).
