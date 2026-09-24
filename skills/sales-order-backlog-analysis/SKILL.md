---
name: sales-order-backlog-analysis
description: Diagnose current ORDER_BACKLOG evidence and test a warehouse-capacity intervention with matched simulations.
---

# Sales Order Backlog Analysis

Use this flow when the user asks whether warehouse capacity could contribute to current sales-order backlog or whether adding warehouse workers improves the simulated outcome. For an open-ended diagnosis, first use `get_actual_state_summary`, `list_exceptions` and `trace_process_bottleneck`. For record-level questions use `get_data_catalog` and `query_snapshot_records`; for order-record period comparison use `compare_snapshot_periods` and disclose coverage. For one object's past state use `query_enterprise_history`; `reconstructed` is limited to recorded reversible events, while `unavailable` is a valid result. This is not a historical backlog metric series; `get_metric_history` still reports that series unavailable.

Call `analyze_sales_backlog_intervention` with the trusted `snapshot_id`, an explicit positive worker change, horizon, seed, primary metric and non-duplicated guardrails. Treat `facts` as current snapshot evidence only. Treat `cause_hypothesis` as unproven. The intervention belongs to operations, not sales. Treat `simulation_comparison` as counterfactual evidence and quote its deterministic verdict without recalculating it.

Report the analysis case ID, baseline and alternative run IDs, selected metric outcomes, Actual State immutability result and limitations. Stop if there is no current backlog or if the tool fails. Do not substitute the latest snapshot for missing history, and do not claim that simulated improvement proves the historical cause or guarantees a real outcome.
