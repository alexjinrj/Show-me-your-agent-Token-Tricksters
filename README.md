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

Agent analysis tools, database-query tools, ERP submission, authentication,
and production deployment are not included yet.

## Runtime architecture

```text
CSV files
   ↓
SQL Actual State
   ↓ immutable snapshot
EnterpriseState
   ↓ validated activity YAML
Generic SimPy interpreter
   ↓
metrics + events + accounting impacts + daily checkpoints
   ↓
FastAPI dashboard
```

The two configured processes meet at `inventory_position`. Sales allocation and
shipping decrease its available, reserved, and on-hand quantities; purchasing
receipts increase the same object. Python implements generic execution
primitives, while activity bindings, durations, resources, operations, events,
financial effects, and transitions are defined under `config/processes/`.

## Repository layout

```text
config/processes/                 Executable process YAML
data/demo/raw/                    Deterministic demo CSV fixture and source manifest
migrations/                       Alembic database migrations
scripts/                          Data build, seeding, and visual demo commands
src/business_coordinator/domain/  Pydantic state and process contracts
src/business_coordinator/         Ingestion, persistence, simulation, and API code
tests/                            Unit, persistence, simulation, and API tests
web/                              No-build browser dashboard
```

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
uv run uvicorn business_coordinator.api.main:app --reload
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

## Demo data provenance

The fixture is based on Microsoft AdventureWorks OLTP CSV data. Singapore/SGD
rebasing, process statuses, resource capacity, opening balances, and embedded
exceptions are explicitly labelled `derived` or `synthetic`. Source URLs,
transformations, row counts, and hashes are retained in
`data/demo/raw/SOURCE_MANIFEST.json`.

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
