# Engineering Handoff

## Canonical checkout

The canonical integrated project is the `main` branch in:

```text
/Users/alexjinrj/Library/Mobile Documents/iCloud~md~obsidian/Documents/main/
Show me your agent/Code
```

Start new work from the latest `main`. Do not treat the completed feature
worktrees as newer copies of the product.

## Delivered scope

The first MVP slice is integrated:

1. Immutable Pydantic domain contracts and validated process YAML.
2. AdventureWorks-derived CSV validation, lineage, SQL Actual State, and
   immutable snapshots.
3. Deterministic, isolated SimPy Order-to-Cash and Procure-to-Pay simulation.
4. Scenario sessions for warehouse capacity, supplier delivery timing, and new
   order arrivals.
5. A runnable HTML demo comparing four 30-day scenarios.
6. UTC-safe SQLite timestamp storage while retaining source CSV offsets.
7. FastAPI plus a no-build web dashboard for scenario comparison, trace playback,
   process inspection, and audit evidence.
8. A follow-on object-centric runtime refactor on `codex/object-centric-runtime`:
   unified state records, executable YAML v2, a generic SimPy interpreter, and
   deterministic daily checkpoints.

The refactor branch was created from `codex/demo-frontend`, so it includes that
frontend while PR #3 remains the separate frontend review unit. Rebase the
refactor onto `main` after PR #3 merges, or change its pull-request base if the
frontend history is intentionally retained as a dependency.

GitHub PR #2 integrated the Foundation, Data, and SimPy branches. A later demo
update added the visual runner, validated runtime process catalog, and timezone
correction.

## Important entrypoints

| Purpose | File or interface |
|---|---|
| Product requirements | `PROJECT_SPECIFICATION.md` |
| Frontend requirements | `FRONTEND_PROJECT_SPECIFICATION.md` |
| Shared contracts | `workstreams/INTERFACE_CONTRACTS.md` |
| Process definitions | `config/processes/*.yaml` |
| Validated runtime process catalog | `src/business_coordinator/simulation/process_runtime.py` |
| CSV-to-Actual-State service | `src/business_coordinator/persistence/service.py` |
| Simulation engine | `src/business_coordinator/simulation/engine.py` |
| Object-centric state adapter/store | `src/business_coordinator/simulation/state.py` |
| Persisted simulation sessions | `src/business_coordinator/simulation/service.py` |
| Visual demo | `scripts/run_simulation_demo.py` |
| Web API entrypoint | `src/business_coordinator/api/main.py` |
| Web dashboard | `web/index.html`, `web/app.js`, `web/styles.css` |
| API and UI tests | `tests/api/` |

The supported simulation boundary remains:

```python
run_simulation(
    snapshot: SnapshotBundle,
    scenario_events: list[ScenarioEvent],
    horizon_days: int,
    random_seed: int,
) -> SimulationRunResult
```

Simulation must never receive writable ORM objects or mutate Actual State.

## Run and verify

From `Code/`:

```bash
uv sync --dev
uv run python scripts/run_simulation_demo.py --open
uv run uvicorn business_coordinator.api.main:app --reload
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

The demo rebuilds an in-memory Actual State from the retained CSV fixture,
creates an immutable snapshot, runs four scenarios, and writes
`demo-output/simulation-demo.html`.

## Time and data-quality rule

- Source CSV timestamps retain their recorded `+08:00` offsets.
- Ingestion converts aware timestamps to UTC before SQLite storage.
- Snapshot outputs restore explicit `+00:00` offsets.
- Equivalent instants expressed with different offsets produce the same
  snapshot identity.
- Legacy demo databases created before this rule must be rebuilt from CSV.
  Their naive SQLite values do not contain enough evidence for a safe automatic
  migration.
- Keep `source`, `derived`, and `synthetic` provenance labels intact.

## Process configuration rule

Activity IDs, object bindings, conditions, transitions, resources, durations,
state operations, output events, financial-effect mappings, parameters, and
versions belong in `config/processes/`. The SimPy engine loads them through the
validated `RuntimeProcessCatalog` and interprets only generic primitives. It
must not regain `_order_to_cash` or `_procure_to_pay` workflow functions.

`EnterpriseState.records` is a dictionary keyed by stable `record_id`. Each
`StateRecord` has a lightweight `record_kind`: `object` is a current projection,
`event` is append-only evidence, and `activity_run` records execution state.
Activities move from `waiting` to `running` to `completed`; completion events
then apply the YAML-declared object and financial effects.

Any change to a process YAML file must be accompanied by process-validation and
simulation tests. Do not copy process timing into UI code.

## Current worktree roles

| Worktree | Branch | Role |
|---|---|---|
| `Code/` | `main` | Canonical integrated product and documentation |
| `Code-worktrees/data-csv-sql/` | `codex/data-csv-sql` | Completed data work; use only for an isolated data-layer change |
| `Code-worktrees/mvp-integration/` | `codex/mvp-foundation-data-simpy` | Completed integration history; no longer the canonical checkout |
| `Code-worktrees/demo-frontend/` | `codex/demo-frontend` | FastAPI dashboard MVP; continue visual refinement here |
| `Code-worktrees/object-centric-runtime/` | `codex/object-centric-runtime` | Current object-centric/YAML runtime refactor |

The completed Foundation and SimPy branches remain useful history, but new
product work should not continue on those old branch tips.

## Known MVP limitations

- Waiting time ends at customer invoicing and excludes payment collection time.
- Opening receivables and payables do not automatically schedule collections or
  payments.
- The demo fixture has no open purchase order matching the three embedded
  backlog SKUs, so expediting the next delivery is traceable but does not clear
  that backlog.
- The deterministic engine accepts a seed for the reproducibility contract, but
  the current slice does not yet contain a stochastic distribution.
- The analysis assistant remains a clearly labelled read-only stub.
- Daily checkpoints are returned with a completed run, but live SSE/WebSocket
  transport and checkpoint persistence/retrieval are future API work.
- Agent orchestration, analysis/database-query tools, typed tool calls,
  authentication, and production
  deployment are not implemented yet.

## Rules for the next agent

1. Read this file, both project specifications, and the interface contracts.
2. Work only in the assigned worktree and branch.
3. Use application services; do not query or update Actual State directly from
   the frontend.
4. Label actual and simulated values visibly.
5. Never recalculate authoritative metrics in JavaScript or an LLM.
6. Preserve deterministic hashes, source lineage, and Actual State isolation.
7. Run the complete quality gate before handoff.
