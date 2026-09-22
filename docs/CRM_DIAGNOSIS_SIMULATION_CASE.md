# CRM diagnosis-to-simulation flow

This is the human-readable acceptance case for the CRM workstream. It implements the immediate
phase of `TEAM_ALIGNMENT_HISTORY_RETRIEVAL_PLAN.md`; it does not implement historical replay.

## Business question

For derived order-service case `CASE-SO74695`, could warehouse capacity contribute to service
risk, and does adding two warehouse workers improve the selected simulation metrics?

## Current evidence

- The case comes from the current immutable AdventureWorks snapshot. It is a derived overdue-order
  exception, not an imported customer complaint.
- The snapshot contains 100 current open/backlog orders. This is current-state evidence, not a
  historical queue series.
- Payment status, actual shipment status, complaint text and complaint SLA are unavailable unless
  separately imported as business documents.

## Cause hypothesis

`Warehouse processing capacity may contribute to the current backlog.`

This remains a hypothesis. A better scenario result does not establish the historical cause.

## Parameter intervention

| Field | Value |
|---|---|
| Event | `warehouse_capacity_increase` |
| Parameter | `warehouse_staff.capacity_delta` |
| Change | `0` to `+2` workers |
| Modification point | simulation day `0` |
| Horizon | `7` days |
| Random seed | `42` |

The baseline and alternative use the same snapshot, process definitions, horizon and seed. The
alternative changes only warehouse capacity. Both runs are persisted with separate run IDs.

## Checked expected comparison

The bundled demonstration fixture currently produces:

| Metric | Baseline | +2 workers | Difference | Interpretation |
|---|---:|---:|---:|---|
| Ending backlog | 43 | 43 | 0 | unchanged |
| Average waiting hours | 72.1184 | 39.3772 | -32.7412 | improved |
| Fulfilment rate | 0.5700 | 0.5700 | 0.0000 | unchanged |

Conclusion: the scenario improves average waiting time in this seven-day simulation, while ending
backlog and fulfilment rate are unchanged. The result supports considering the capacity option; it
does not prove capacity caused the real delay or promise the same operational outcome.

## Runtime sequence

1. `recommend_resolution` reads the current CRM case and its linked snapshot evidence.
2. `analyze_crm_service_capacity` creates and runs the matched baseline and alternative.
3. `draft_business_action_plan` uses the same case ID, cites both evidence calls and binds the
   validated comparison.
4. The AI Coordinator returns the evidence-bound draft and its tool evidence for review in the
   chat trace. The standalone Business Evidence and Action Review pages are intentionally omitted
   from this CRM-focused interface.

If simulation cannot run, the draft must use `not_available`, remains
`unverified_intervention`, and cannot be approved. Evidence collection or communication tasks that
propose no operational parameter change may use `not_applicable` with a reason.

## Automated acceptance

`tests/api/test_crm_intervention_chain.py` checks the complete tool chain, matching run controls,
persisted evidence, immutable Actual State, structured plan output and rejection of an unverified
intervention. `tests/api/test_workbench.py` checks provenance, persistence, review transitions and
snapshot isolation.

## Boundaries

- The only supported CRM counterfactual in this iteration is warehouse staff capacity.
- The simulation evaluates system-level metrics; it does not guarantee the selected order will ship.
- Human review records a decision but does not contact a customer, refund, reserve stock or ship.
- Bounded object-history retrieval is available, but past state is reconstructed only from
  recorded reversible events. Missing change sets remain explicit missing evidence, and the
  current snapshot is never presented as past state.
