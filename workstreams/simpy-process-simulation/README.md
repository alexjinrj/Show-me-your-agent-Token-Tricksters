# SimPy Process Simulation

Git branch: `codex/simpy-process-simulation`

Depends on: `codex/data-csv-sql`, which itself depends on
`codex/foundation-domain-yaml`.

## Objective

Reconstruct an isolated SME state from an immutable snapshot and run a
deterministic 30-day Order-to-Cash and Procure-to-Pay simulation.

## Deliverables

- Snapshot-to-simulation-state adapter that deep-copies canonical data.
- Fresh SimPy environment and resources for every run.
- Order-to-Cash and Procure-to-Pay processes driven by the versioned YAML.
- Shared inventory, warehouse capacity, receivables, payables, and cash state.
- Baseline plus warehouse-worker and expedited-delivery scenarios.
- Operational and financial metrics, event trace, and deterministic result hash.
- Persistence of simulation sessions, events, runs, results, and accounting
  impacts without changing Actual State.
- Reproducibility, isolation, accounting-balance, and end-to-end tests.

## Completion Criteria

- The demo CSV data can be ingested, snapshotted, and simulated end to end.
- Identical inputs and seeds return identical result hashes.
- Running or forking a scenario does not change Actual State or its parent.
- Baseline and both alternatives produce a deterministic comparison covering
  backlog, wait time, fulfilment, utilization, stockouts, inventory, revenue,
  COGS, gross profit, receivables, payables, and cash.

## Implemented Boundary

`business_coordinator.simulation.run_simulation` is the deterministic public
entry point. It accepts only a frozen `SnapshotBundle`, scenario events, a
horizon, and a seed. It creates and disposes a new SimPy environment, shared
resource pools, inventory containers, and mutable financial state for every
call. No database session or ORM object is accepted by the engine.

The snapshot contains detached order details needed to reconstruct pending
obligations. `SimulationService` persists simulation sessions, independent
forks, scenario events, run metadata, result summaries, traces, and balanced
accounting impacts. Persistence occurs after the detached run and never writes
`business_events` or materialized Actual State.

Process timing is versioned in:

- `config/processes/order_to_cash.yaml`
- `config/processes/procure_to_pay.yaml`

The simulation loads these files through the validated
`RuntimeProcessCatalog` in
`src/business_coordinator/simulation/process_runtime.py`. Node definitions,
transitions, resources, processing times, process parameters, versions, and
the process hash therefore remain outside the SimPy engine. Operational
effects such as allocating inventory and posting balanced accounting entries
remain deterministic Python behavior.

Supported first-slice events are `order_arrival`,
`resource_capacity_changed`, and `supplier_delivery_delayed`; negative delivery
day deltas represent expedited delivery. Convenience constructors provide the
required warehouse-worker and next-supplier-delivery alternatives.

The supplied demo data has no open purchase order for the three embedded
backlog SKUs. Consequently, expediting its next open delivery is visible in the
trace and inventory timing but does not improve that backlog. This is an
evidence-limited result of the fixture, not a simulated causal claim.

## Verification

Run from the repository root:

```text
uv run ruff check .
uv run mypy src
uv run pytest -q
```

The test suite covers deep-copy isolation, reproducibility, Actual State hash
immutability, session forking, shared capacity and inventory, scenario traces,
balanced journal impacts, result persistence, comparison, and the complete
CSV-to-snapshot-to-simulation path.

## Out of Scope

Agent reasoning, LangGraph, tool wrappers, FastAPI, Streamlit, ERPNext, and any
automatic external action.
