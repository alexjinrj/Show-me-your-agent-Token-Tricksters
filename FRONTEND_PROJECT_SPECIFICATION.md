# Simulation Demo Frontend Project Specification

**Project:** Token Tricksters SME Business State Coordinator  
**Document version:** 1.0  
**Status:** Implementation handoff  
**Target branch:** `codex/demo-frontend`  
**Target worktree:** `Code-worktrees/demo-frontend`  
**Primary implementation language:** Python 3.12  

## 1. Objective

Build a compact, read-only Streamlit demonstration that lets a reviewer inspect
the actual-state snapshot, understand the configured enterprise processes, run
approved simulation scenarios, compare deterministic results, and inspect the
supporting event and accounting traces.

The frontend is a presentation and interaction layer. It must not duplicate
simulation formulas, accounting calculations, process timings, or authoritative
state logic.

## 2. Intended demo journey

The reviewer must be able to complete this sequence without using a terminal:

```text
Open demo
→ inspect source provenance and snapshot time
→ see the current exception and baseline state
→ inspect Order-to-Cash and Procure-to-Pay structures
→ choose or configure one approved scenario
→ run the 30-day simulation
→ compare baseline and alternative outcomes
→ inspect a representative event trace
→ see assumptions, limitations, hashes, and Actual State isolation
```

## 3. Required stack

- Streamlit for the frontend.
- Existing Pydantic domain models for typed values.
- Existing `ActualStateService` and `SimulationService` application services.
- Existing validated process YAML and `RuntimeProcessCatalog`.
- Existing SQLite-compatible persistence for local demonstration.
- No separate JavaScript framework is required for this slice.

The implementation may introduce a small application-facing demo service so
the Streamlit page does not import functions from `scripts/` or duplicate setup
logic.

## 4. Architecture boundary

```text
Streamlit views
      ↓ typed commands and display models
Demo application service
      ├── ActualStateService → immutable SnapshotBundle
      ├── RuntimeProcessCatalog → validated process definitions
      └── SimulationService → stored runs and comparisons
```

The frontend must never:

- write Actual State business entities or events;
- receive writable SQLAlchemy models;
- alter process YAML;
- calculate financial or operational metrics itself;
- call an LLM to create authoritative numeric results;
- hide whether a displayed value is actual or simulated.

## 5. Required views

### 5.1 Overview

Show:

- company and snapshot identifier;
- snapshot as-of time in `Asia/Singapore`, with UTC available as secondary
  detail;
- source dataset and `source` / `derived` / `synthetic` provenance explanation;
- counts of customers, suppliers, SKUs, orders, inventory positions, and events;
- a visible `Actual State` label.

### 5.2 Process explorer

Read both processes from `RuntimeProcessCatalog` and render their configured
node order. Selecting a node should show:

- label and node ID;
- resource type;
- processing time;
- transition target and guard;
- generated events;
- affected metrics;
- financial effect, when present.

Do not hard-code the process structure in the UI.

### 5.3 Scenario controls

Support only these bounded inputs:

1. Baseline with no scenario event.
2. Warehouse capacity increase with a positive integer worker count.
3. Supplier delivery adjustment with an explicit number of days.
4. New sales order with known SKU, positive quantity, day of arrival, and
   optional unit price.

Validate every input through Pydantic before creating a session or event.
Default to the four scenarios used by `scripts/run_simulation_demo.py`.

### 5.4 Scenario comparison

Display baseline and alternative values for:

- ending backlog;
- average waiting hours;
- fulfilment rate;
- stockout count;
- resource utilization;
- ending inventory quantity and value;
- revenue;
- cost of goods sold;
- gross profit;
- accounts receivable and payable;
- ending and minimum cash.

Show absolute differences. Do not label a difference as beneficial or harmful
unless the direction is unambiguous and the underlying value is available.

### 5.5 Trace and audit view

Allow the reviewer to inspect:

- scenario events and their effective simulated day;
- ordered process events with simulated hour and object ID;
- balanced accounting impacts;
- snapshot, process-definition, scenario-event, and result hashes;
- horizon and seed;
- whether Actual State remained unchanged.

## 6. UX requirements

- Optimize for a five-minute hackathon walkthrough on a laptop.
- Use a compact layout and avoid oversized cards or long explanatory blocks.
- Use plain business labels while keeping exact technical IDs available.
- Present actual and simulated values with distinct text labels, not color alone.
- Keep scenario assumptions visible beside the result.
- Include an explicit loading state and a readable error state.
- Do not auto-run expensive work whenever an unrelated widget changes.
- Cache only immutable source/configuration inputs; never cache mutable sessions
  as if they were authoritative.

## 7. Application state

Use Streamlit session state only for UI selections and identifiers. Persisted
simulation sessions and runs remain owned by `SimulationService`.

The baseline and each alternative must have separate session IDs. Changing an
alternative must not mutate the baseline session. Refreshing the browser may
recreate demo data, but one page session must not silently mix results from
different snapshot hashes.

## 8. Error handling

The UI must provide clear messages for:

- missing or invalid demo CSV files;
- process configuration validation failure;
- unknown SKU;
- invalid quantity, capacity, or delivery adjustment;
- snapshot mismatch;
- failed simulation run;
- empty comparison state.

Do not expose a raw stack trace in the default demo view.

## 9. Testing requirements

At minimum, add tests for:

1. Application-service setup from the retained demo CSVs.
2. Process explorer data being derived from YAML rather than duplicated.
3. Scenario input validation.
4. Baseline and alternative session isolation.
5. Comparison display-model accuracy against `SimulationService.compare_runs`.
6. Actual State hash remaining unchanged after frontend-triggered runs.
7. Snapshot time displaying the same instant correctly in Singapore and UTC.
8. A smoke test that imports and renders the main Streamlit entrypoint.

The existing 27 backend tests must continue to pass.

## 10. Acceptance criteria

The frontend slice is complete when:

- `uv run streamlit run app.py` starts the demo locally;
- a reviewer can run baseline plus one alternative without a terminal;
- process nodes and timings come from validated YAML;
- all displayed metrics come from stored `SimulationRunResult` values;
- event and accounting traces are inspectable;
- actual and simulated values are clearly labelled;
- repeating the same inputs produces the same result hash;
- Actual State remains unchanged;
- all existing and new tests, Ruff, and mypy pass;
- the README and this handoff are updated with the final run command and known
  limitations.

## 11. Out of scope

- LangGraph or LLM Agent integration;
- autonomous recommendations;
- authentication and multi-user authorization;
- FastAPI or remote deployment;
- editing Actual State;
- arbitrary process editing;
- production visual design or mobile optimization;
- stochastic forecasting beyond the existing simulation contract.

## 12. Recommended implementation order

1. Extract reusable demo orchestration from the current runner into an
   application service.
2. Build the overview and process explorer.
3. Add baseline execution and stored result presentation.
4. Add one bounded alternative scenario and comparison.
5. Add the remaining approved scenarios.
6. Add trace, accounting, provenance, and reproducibility views.
7. Add tests, documentation, and the final demo walkthrough.
