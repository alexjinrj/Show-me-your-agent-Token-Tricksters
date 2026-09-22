# Sales ORDER_BACKLOG diagnosis-to-simulation case

This is the human-readable acceptance case for the sales workstream. It implements the current
snapshot-backed diagnosis-to-simulation phase. Historical state reconstruction remains an explicit
`NOT_IMPLEMENTED` capability and is not silently replaced with the latest snapshot.

## Business question

The current snapshot contains an `ORDER_BACKLOG` exception. If operations adds two warehouse
workers at simulation day 0, does the selected sales fulfilment evidence improve over seven days?

## Current evidence

- Snapshot: the immutable AdventureWorks demonstration snapshot.
- Current sales orders: 500.
- Current open/backlog orders: 100, with a total order amount of SGD 482.80.
- The source stores current imported status and one import event per order. It is not a complete
  historical queue or node-transition series.
- Resource records are synthetic demonstration inputs and must be labelled accordingly.

## Cause hypothesis

`Warehouse processing capacity may contribute to current order backlog.`

This is a candidate hypothesis, not a database fact. A better counterfactual result does not prove
that warehouse capacity caused the observed backlog.

## Parameter intervention

| Field | Value |
|---|---|
| Owner | Operations |
| Event | `warehouse_capacity_increase` |
| Parameter | `warehouse_staff.capacity_delta` |
| Change | `0` to `+2` workers |
| Modification point | simulation day `0` |
| Horizon | `7` days |
| Random seed | `42` |
| Primary metric | `average_waiting_hours` |
| Guardrails | `ending_backlog`, `fulfilment_rate`, `stockout_count` |

The tool creates a no-change baseline, forks an isolated alternative, adds the intervention and
runs both with the same snapshot, process definitions, horizon and seed.

## Deterministic evaluation policy

| Metric | Better direction | Materiality threshold |
|---|---|---:|
| Ending backlog | lower | 1 order |
| Average waiting hours | lower | 0.01 hours |
| Fulfilment rate | higher | 0.0001 |
| Stockout count | lower | 1 event |

The verdict is `improved` when at least one selected metric materially improves and none worsens;
`worsened` when at least one worsens and none improves; `trade_off` when improvements and
worsening coexist; otherwise `no_material_change`.

## Checked expected comparison

For the bundled fixture, the seven-day +2-worker scenario keeps ending backlog and fulfilment
unchanged while materially reducing average waiting hours. Therefore the deterministic verdict is
`improved`. The precise values and run IDs are returned by the tool and persisted simulation runs.

## Expected result shape

The output keeps these fields separate:

1. `facts`: current `actual` snapshot evidence and completeness.
2. `cause_hypothesis`: explicitly `candidate_not_proven`.
3. `intervention`: the operations-owned parameter change.
4. `simulation_comparison`: `simulated` run IDs, per-metric outcomes and overall verdict.

It also returns an `analysis_case_id`, confirms `actual_state_unchanged`, and lists limitations.

## Automated acceptance

- `tests/unit/test_sales_analysis.py` checks parameter contracts, thresholds and trade-off logic.
- `tests/integration/test_sales_agent_tools.py` checks the real snapshot-to-simulation flow,
  persisted matched runs, structured evidence separation and Actual State immutability.
- `tests/unit/test_tool_registry.py` checks consistent tool grouping and access classification.

## Boundaries

- Only warehouse-capacity intervention is supported by this upper-level sales flow.
- The tool evaluates system-level metrics; it does not guarantee that a particular order ships.
- It creates simulation and audit records only. It does not change staffing or Actual State.
- A future historical provider may replace the current `SnapshotSalesEvidenceProvider` without
  changing this analysis contract, after the retrieval contract is agreed and implemented.
