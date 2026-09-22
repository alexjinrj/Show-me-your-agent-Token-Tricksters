# Inventory Replenishment Analysis Case

## Business question

Which inventory items require replenishment, and which simulated replenishment
strategy should be preferred?

## Current evidence

The analysis uses the bounded Actual State snapshot created from
`data/load_data/adventureworks_demo/`.

The checked snapshot contains:

- 6 reorder candidates;
- 3 critical candidates;
- 647 total recommended replenishment units;
- demand shortages of 5 units for `PK-7098` and 38 units for `WB-H098`.

These are actual snapshot facts returned by inventory tools.

## Hypothesis

Replenishing selected inventory items may reduce shortages and improve order
fulfilment compared with taking no replenishment action.

This is a hypothesis, not proof of the historical cause of the current stock.

## Simulation intervention

Call `compare_inventory_replenishment_strategies` using:

- horizon: 30 days;
- random seed: 42;
- effective day: 3.

Compare `baseline`, `critical_only`, `demand_aligned`, and `full`.

## Expected result

The result must:

- be labelled `simulated`;
- include all four strategy runs;
- include baseline and recommended run IDs;
- recommend one of the tested strategies;
- report `actual_state_unchanged` as `true`;
- preserve the Actual State hash.

The Agent must separate actual facts, the hypothesis, simulated interventions,
comparison results, and limitations.

## Limitations

The current snapshot does not establish historical cause. Simulation does not
create purchase orders, receive stock, or change Actual State. Historical
questions must report retrieval as unavailable until
`query_enterprise_history` is implemented.

## Automated test

The linked automated test is
`tests/integration/test_inventory_agent_tools_integration.py`.

## Future history retrieval integration

The current Inventory implementation performs bounded reads from the selected
Actual State snapshot through `ActualStateService` and
`extract_inventory_strategy_rows`.

When the shared `query_enterprise_history` capability is implemented,
historical inventory evidence should be obtained through that shared tool.

The inventory reorder calculation and simulation logic should remain
unchanged. This document does not define the request or response contract of
the shared history tool because that contract is owned by the shared retrieval
workstream.