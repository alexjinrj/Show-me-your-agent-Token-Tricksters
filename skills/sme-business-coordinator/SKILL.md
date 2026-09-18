---
name: sme-business-coordinator
description: Analyze auditable SME Actual State and compare isolated sales scenarios through bounded tools.
metadata:
  openclaw:
    requires:
      bins: [uv]
---

# SME Business Coordinator

Use this skill for questions about sales backlog, Order-to-Cash exceptions,
business-object traces, bottlenecks, or warehouse and supplier what-if scenarios.

1. Call `get_business_context` first and use its `base_snapshot_id`.
2. Use only the registered SME tools for business numbers. Never infer a number
   from prose or calculate an authoritative metric yourself.
3. Label snapshot evidence as **actual** and scenario results as **simulated**.
   A simulation never changes Actual State.
4. Cite the returned `tool_call_id` or `reference_id` for every material claim.
5. For what-if analysis, create a baseline session, run it, fork the session,
   add one permitted event, run the alternative with the same horizon and seed,
   and call `compare_simulation_runs`.
6. Report missing history or evidence limits plainly. Do not claim that a
   supplier expedite resolves a backlog when the tool returns a SKU warning.
7. Do not attempt arbitrary SQL, filesystem access, ERP submission, or any
   write to Actual State.
