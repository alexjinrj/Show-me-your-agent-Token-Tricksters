---
name: sales-order-exception-analysis
description: Investigate Order-to-Cash backlog, delayed orders, sales-order status, or fulfilment bottlenecks.
---

# Sales Order Exception Analysis

Use only registered sales tools. Start with a known `snapshot_id`; call `get_actual_state_summary`, then use `list_exceptions` only for the `ORDER_BACKLOG` sales exception. Trace only representative affected orders with `trace_business_object`.

Separate confirmed actual sales facts from candidate explanations. The imported demo stores the current sales-order status and one import event per order, not a complete actual node history. Do not infer actual waiting-time trends, historical node transitions, inventory causes, or operations causes. Use `get_metric_history` when asked for sales history and report its `not_available` result.

Quote numbers from tool output and cite `tool_call_id`, `reference_id`, snapshot hash, and source lineage. Label all current-state values `actual`. Own sales-order counts, statuses, backlog sales value, SKU demand distribution, and order evidence. Route customer profiling to the customer-relationship workstream, stock decisions to inventory, profit and cash reporting to accounting, and capacity or process-root-cause decisions to operations. Never run arbitrary SQL or modify Actual State.
