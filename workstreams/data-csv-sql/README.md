# CSV Ingestion and SQL Actual State

Status: completed and integrated into `main` through PR #2.

Git branch: `codex/data-csv-sql`

Depends on: `codex/foundation-domain-yaml`

## Objective

Load deterministic CSV demo sources into a normalized, lineage-preserving SQL
Actual State and create immutable snapshots for simulation.

## Deliverables

- CSV inspection, fixed mapping templates, deterministic validation, and batch
  commit services.
- Demo customer, supplier, item, inventory, sales-order, purchase-order,
  resource-capacity, and opening-balance CSV files.
- SQLAlchemy 2 models and Alembic migrations for source files, ingestion runs,
  normalized masters, business events, materialized business objects,
  snapshots, and snapshot records.
- SQLite configuration with PostgreSQL-compatible model types.
- Idempotent ingestion and canonical snapshot hashing.
- Unit and integration tests from CSV through `SnapshotBundle`.

## Completion Criteria

- Invalid input produces no business events.
- Recommitting a batch with the same idempotency key creates no duplicates.
- Every normalized record retains source lineage.
- A snapshot can be loaded without returning mutable ORM instances.
- Snapshot content is immutable and deterministically hashed.

## Output to the Next Workstream

`load_snapshot(snapshot_id) -> SnapshotBundle` is the only Actual State input to
the SimPy workstream. Simulation must not write back through this interface.

## Implemented data source

The demo extract uses Microsoft's fictitious AdventureWorks OLTP install-script
CSVs under the repository's MIT license. It is rebuilt deterministically by
`scripts/build_demo_data.py`; `data/demo/raw/SOURCE_MANIFEST.json` records the
upstream URLs, hashes, transformations, row counts, and provenance boundary.

The source provides customer, vendor, product, inventory, sales-order, and
purchase-order relationships. Singapore/SGD rebasing, process status, resource
capacity, opening balances, and the required exception are explicitly labelled
`derived` or `synthetic`, never as source facts.

Run the slice with:

```bash
uv sync --dev
uv run pytest
uv run python scripts/seed_demo_data.py --database actual_state.db
```

## Out of Scope

XLSX/JSON parsing, AI-assisted mapping, fuzzy entity matching, public APIs, UI,
Agent orchestration, and ERPNext integration.
