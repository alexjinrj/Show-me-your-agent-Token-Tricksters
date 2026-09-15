---
name: sales-order-scenario-analysis
description: Compare warehouse staffing or supplier-delivery scenarios for Order-to-Cash backlog and financial effects.
---

# Sales Order Scenario Analysis

Establish one actual `snapshot_id`. Use `create_simulation_session` and `run_simulation` to record a baseline. Fork that session once per alternative with `fork_simulation_session`; use at most three explicit assumptions. The sales event whitelist is `warehouse_capacity_increase` and `expedite_supplier_delivery` through `add_simulation_event`. Run all alternatives with the same `horizon_days` and `random_seed`, then call `compare_simulation_runs` for each.

Explain ending backlog, average waiting hours, fulfilment, stockouts, gross profit, receivables, payables, ending cash, and minimum cash using the stored comparison. Include baseline and alternative run IDs, snapshot hash, event assumptions, evidence references, and limits. Mark all run results `simulated`; never present them as actual outcomes or calculate replacement figures in the model.

For supplier expedites, inspect the tool warning and the target purchase order SKU. If it is not among the backlog SKUs, say the demo provides no evidence that expediting it resolves the affected backlog. A scenario changes only isolated simulation state. Do not propose an Actual State write through these tools.
