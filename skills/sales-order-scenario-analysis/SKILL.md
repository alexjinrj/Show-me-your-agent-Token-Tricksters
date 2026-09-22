---
name: sales-order-scenario-analysis
description: Compare warehouse staffing or supplier-delivery scenarios for Order-to-Cash backlog and financial effects.
---

# Sales Order Scenario Analysis

Establish one actual `snapshot_id`. For an `ORDER_BACKLOG` question that proposes changing warehouse capacity, call `analyze_sales_backlog_intervention`. It is the preferred upper-level flow: it reads current evidence, states an unproven capacity hypothesis, runs a no-change baseline, runs the isolated capacity alternative with the same horizon and seed, and returns a deterministic verdict. Do not manually reproduce its arithmetic or replace its verdict.

For another supported scenario, use `create_simulation_session` and `run_simulation` to record a baseline. Fork that session once per alternative with `fork_simulation_session`; use at most three explicit assumptions. The low-level event whitelist is `warehouse_capacity_increase` and `expedite_supplier_delivery` through `add_simulation_event`. Run all alternatives with the same `horizon_days` and `random_seed`, then call `compare_simulation_runs` for each.

Explain ending backlog, average waiting hours, fulfilment, stockouts, gross profit, receivables, payables, ending cash, and minimum cash using the stored comparison. Include baseline and alternative run IDs, snapshot hash, event assumptions, evidence references, and limits. Mark all run results `simulated`; never present them as actual outcomes or calculate replacement figures in the model.

Keep four sections distinct: current `facts`, `cause_hypothesis`, operations-owned `intervention`, and `simulation_comparison`. A verdict of `trade_off` means at least one selected metric improved and another worsened. `no_material_change` means every selected difference was below its deterministic threshold.

For supplier expedites, inspect the tool warning and the target purchase order SKU. If it is not among the backlog SKUs, say the demo provides no evidence that expediting it resolves the affected backlog. A scenario changes only isolated simulation state. Do not propose an Actual State write through these tools.
