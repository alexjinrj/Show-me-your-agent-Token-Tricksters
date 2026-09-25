---
name: sales-order-exception-analysis
description: Investigate Order-to-Cash backlog, delayed orders, sales-order status, or fulfilment bottlenecks.
---

# Sales Order Exception Analysis

Use only registered tools. Start with the trusted `snapshot_id`. For current backlog call `get_actual_state_summary`, then `list_exceptions` for `ORDER_BACKLOG`; trace representative orders with `trace_business_object`. For open-ended sales questions first call `get_data_catalog`, then use allowed fields, filters, rankings and grouping through `query_snapshot_records`. Its totals cover all matches, not just the returned page. Use `compare_snapshot_periods` for explicit order-record date windows and report coverage; current status is not historical status.

Use `trace_process_bottleneck` for bounded current resource evidence. If the user explicitly asks whether additional warehouse capacity would improve `ORDER_BACKLOG`, transition to `analyze_sales_backlog_intervention`; do not stop at an untested staffing recommendation.

Separate confirmed actual sales facts from candidate explanations. The imported demo stores the current sales-order status and one import event per order, not a complete actual node history. For one object's past state call `query_enterprise_history` with object type, ID and `as_of`; `reconstructed` is complete only for recorded reversible events, and `unavailable` must be reported. For backlog or waiting-time series call `get_metric_history` and report `not_available`. Object replay cannot establish an aggregate trend. Do not infer actual waiting-time trends, inventory causes, or operations causes.

Quote numbers from tool output and cite `tool_call_id`, `reference_id`, snapshot hash, and source lineage. Label all current-state values `actual`. Own sales-order counts, statuses, backlog sales value, SKU demand distribution, and order evidence. Route customer profiling to the customer-relationship workstream, stock decisions to inventory, profit and cash reporting to accounting, and capacity or process-root-cause decisions to operations. Never run arbitrary SQL or modify Actual State.
