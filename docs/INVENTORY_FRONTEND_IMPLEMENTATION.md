# Inventory frontend integration report

## Outcome

The Inventory page now exposes the existing deterministic Inventory Agent tools through a browser-safe REST adapter. It keeps the previous overview and adds interactive Actual State filtering plus a four-strategy what-if comparison. The page does not calculate replenishment rules, mutate inventory, create purchase orders, or parse natural-language Agent replies.

## REST contract

### Reorder candidates

```http
GET /api/v1/modules/inventory/reorder-candidates?risk_level=all&top_n=10
```

The server supplies the current snapshot ID and calls `list_inventory_reorder_candidates`. The response keeps the Inventory tool envelope. The frontend requires `status: ok` and reads the structured `data` object.

### Strategy comparison

```http
POST /api/v1/modules/inventory/strategy-comparison
Content-Type: application/json

{
  "horizon_days": 30,
  "random_seed": 42,
  "effective_day": "3"
}
```

The server supplies the current snapshot ID and calls `compare_inventory_replenishment_strategies`. The tool persists one isolated simulation run for each of `baseline`, `critical_only`, `demand_aligned`, and `full`. It returns the backend-selected recommendation, metrics, shortages, run IDs, hashes, assumptions, limitations, and Actual State boundary.

## Page changes

- Actual snapshot candidate filters for risk and result limit.
- Candidate summary and Target stock column.
- Horizon, effective-day, and seed controls.
- Loading, validation, tool, network, empty, stale, and duplicate-submit states.
- Backend-selected recommendation card.
- Four-strategy comparison with expandable secondary metrics and hashes.
- Demand-shortage table or explicit empty state.
- Expandable assumptions, limitations, snapshot evidence, run IDs, and result hashes.
- Visible statement that simulation did not modify Actual State and did not create a purchase order.
- Responsive single-column layouts for smaller screens.

## Files changed

- `src/interfaces/api/routes_modules.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `tests/api/test_inventory_module_analysis.py`
- `tests/frontend/assistant.test.cjs`

The teammate Inventory backend commit is included on this integration branch because it was previously reverted from `main`. No file under `src/tools/sales/` was changed.

## Verification

- `ruff check .`: passed.
- `mypy`: passed with no issues in 88 source files.
- `pytest -q`: 180 passed.
- `node --test tests/frontend/assistant.test.cjs`: 6 passed.
- `git diff --check`: passed.
- `git diff -- src/tools/sales`: no output.
- Manual browser check: candidate data loaded from the Actual State; strategy comparison displayed exactly four rows, highlighted the backend recommendation, exposed shortages and run evidence, and showed the non-mutation boundary.

## Remaining boundary

CSV download remains a CLI capability. A future browser download needs a dedicated backend download endpoint. Full audit records remain backend-only and should be exposed only through a separate access-controlled admin surface if required.
