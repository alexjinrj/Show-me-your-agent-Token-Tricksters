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
- Bounded, audited sales-order tools with prompt-driven LLM trajectory testing.

Arbitrary database-query tools, ERP submission, authentication, and production
deployment are not included yet.

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
frontend/                         Browser UI; PR #5 is to be reduced into this boundary
migrations/                       Alembic database migrations
scripts/                          Data build, seeding, and demo entry points
tests/                            Unit, integration, simulation, and API tests
```

See `docs/ARCHITECTURE_RESTRUCTURE_HANDOFF.md` for the move map, interface
alignment status, and the three follow-up workstreams.

## Setup and verification

Python 3.12 and `uv` are required.

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

If editable imports do not resolve from a path containing spaces, prefix the
commands with `PYTHONPATH=src`.

## Run the browser dashboard

```bash
uv run uvicorn interfaces.api.main:app --reload
```

Open <http://127.0.0.1:8000>.

The application seeds an idempotent local SQLite database, loads the validated
process catalog, and runs baseline and alternative simulations without changing
Actual State.

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
