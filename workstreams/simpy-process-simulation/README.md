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

## Out of Scope

Agent reasoning, LangGraph, tool wrappers, FastAPI, Streamlit, ERPNext, and any
automatic external action.
