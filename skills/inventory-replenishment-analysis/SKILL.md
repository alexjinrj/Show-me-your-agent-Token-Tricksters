---
name: inventory-replenishment-analysis
description: Analyze current inventory reorder candidates and compare isolated replenishment strategies.
---

# Inventory Replenishment Analysis

Use this skill for questions about current stock, reorder candidates,
inventory risk, recommended replenishment, demand shortages, or inventory
strategy comparison.

1. Call `get_business_context` first and use its `base_snapshot_id`.

2. For current inventory questions, call
   `list_inventory_reorder_candidates`.

3. Treat returned snapshot values as actual evidence. Use tool values and
   totals verbatim. Do not calculate authoritative inventory metrics in the
   model.

4. Separate confirmed inventory facts, cause hypotheses, proposed parameter
   interventions, simulated comparisons, and evidence limitations.

5. A current snapshot does not establish a historical cause. For questions
   about changes over time, call `query_enterprise_history` when available.
   If history retrieval is unavailable or not implemented, disclose the
   limitation and do not substitute the latest snapshot or invent a cause.

6. For replenishment recommendations, interventions, or what-if questions,
   call `compare_inventory_replenishment_strategies`.

7. Compare only the strategies and metrics returned by the simulation tool.
   Do not invent or recalculate authoritative simulation results.

8. Treat every strategy result as simulated. Simulation does not modify
   Actual State.

9. Cite `tool_call_id`, `reference_id`, snapshot hash, and simulation run IDs
   for material claims when available.

10. Never claim that a purchase order, receipt, inventory write, or other
    Actual State transaction was performed.

11. Stop and explain the limitation when required evidence or simulation is
    unavailable.