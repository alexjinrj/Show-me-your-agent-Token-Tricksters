# SME Business State Coordinator

Team repository for the NUS ISS **Show Me Your Agent** Hackathon.

The project builds an auditable, deterministic model of a simplified Singapore
SME distributor. Structured source data is normalized into authoritative Actual
State, copied into immutable snapshots, and evaluated safely in isolated SimPy
scenarios. Simulation results never write back to Actual State.

## Documentation

- [Project specification](PROJECT_SPECIFICATION.md) — source of truth for scope,
  architecture, invariants, and acceptance criteria.
- [MVP workstreams](workstreams/README.md) — branch ownership and dependency
  order.
- [Interface contracts](workstreams/INTERFACE_CONTRACTS.md) — canonical types
  and the hand-off between domain, persistence, and simulation.

## Current MVP Status

Three implementation workstreams have been completed on isolated Git branches:

| Workstream | Branch | Delivered |
|---|---|---|
| Foundation | `codex/foundation-domain-yaml` | Python project, immutable Pydantic domain contracts, canonical serialization, process configuration loader, and versioned Order-to-Cash and Procure-to-Pay YAML |
| Data and Actual State | `codex/data-csv-sql` | Deterministic CSV mappings and validation, source lineage, SQLAlchemy/Alembic persistence, idempotent ingestion, materialized Actual State, immutable snapshot bundles, and demo data |
| Simulation | `codex/simpy-process-simulation` | Isolated SimPy runs, shared inventory/resources, O2C and P2P processing, financial state, scenario events, reproducible result hashes, persistence, comparison, and invariant tests |

The intended integration order is:

```text
foundation domain + process definitions
                    ↓
CSV ingestion → SQL Actual State → immutable SnapshotBundle
                                             ↓
                                  isolated SimPy simulation
```

An integration branch combines the three workstreams before they are merged
into `main`. Until that pull request is merged, `main` remains the coordination
and documentation branch.

## Architectural Rules

1. Actual State is authoritative and event-backed.
2. Simulations start from immutable, detached `SnapshotBundle` values.
3. Simulation code must never mutate Actual State or accept writable ORM state.
4. Money uses decimal semantics; timestamps are timezone-aware; internal IDs
   are UUID strings.
5. Identical snapshot, configuration, scenario events, horizon, and seed must
   produce identical result hashes.
6. Operational and financial values are calculated by deterministic Python
   code, not by an LLM.

## Demo Data

The data workstream uses Microsoft AdventureWorks OLTP CSV data as its source
base. Singapore/SGD rebasing, process status, resource capacity, opening
balances, and the embedded exception are explicitly labelled as `derived` or
`synthetic`. Source URLs, transformations, row counts, and hashes are recorded
in `data/demo/raw/SOURCE_MANIFEST.json` on the implementation branches.

The deterministic fixture currently contains:

- 500 sales orders and 50 purchase orders;
- 40 SKUs, 486 customers, and 8 suppliers;
- inventory, resource capacity, and opening financial balances;
- an embedded backlog, capacity, inventory, collection, and cash-pressure
  exception.

## Development and Verification

After checking out the integration branch or an implementation worktree:

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Build the deterministic Actual State database and snapshot with:

```bash
uv run python scripts/seed_demo_data.py --database actual_state.db
```

Run the end-to-end visual simulation demo with:

```bash
uv run python scripts/run_simulation_demo.py --open
```

This creates `demo-output/simulation-demo.html` with a 30-day comparison of
the baseline, one additional warehouse worker, an expedited supplier delivery,
and a new customer order arriving on day one. The report also shows the
configured process nodes, representative event journeys, reproducibility, and
Actual State isolation checks.

Generated databases, virtual environments, download caches, and test/type-check
caches are ignored by Git.

## Picking Up the Work

Before changing a workstream:

1. Read `PROJECT_SPECIFICATION.md` and
   `workstreams/INTERFACE_CONTRACTS.md` completely.
2. Read the workstream-specific README under `workstreams/`.
3. Use a dedicated Git worktree for one branch; do not switch another agent's
   worktree to a different branch.
4. Rebase or merge the latest upstream dependency before changing a public
   contract.
5. Update dependent tests whenever a canonical type, snapshot field, process
   definition, or simulation event changes.
6. Run Ruff, mypy, and pytest before committing.

The next product layers remain out of scope for this slice: typed Agent tools,
FastAPI, LangGraph/LLM coordination, Streamlit, ERPNext submission, and
production deployment.

## Known Demo Limitation

The current fixture has no open purchase order for the three embedded backlog
SKUs. Expediting the next open supplier delivery is therefore visible in the
simulation trace and inventory timing, but does not improve that specific
backlog. Treat this as an evidence-limited fixture result rather than a general
causal conclusion.
