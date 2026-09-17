# CRM runtime integration

## Implemented chain

```text
Olist demo fixture -> deterministic CRMService
                   -> versioned FastAPI CRM endpoints -> team frontend
                   -> CRMAgentTools -> shared Tool Registry -> OpenClaw/MCP
                   -> common evidence envelope -> persisted AgentRun/tool audit

Resolution draft -> POST proposal -> SQL crm_proposals -> human decision
                                      (review record only; no business execution)
```

The CRM frontend no longer calculates customer scores or complaint priority.
Those values come from backend Python tools. The unified Agent calls the same
tools through the existing `ToolExecutor`; it does not run a separate CRM model
or use browser-local data as an authoritative source.

## Data boundary

The bundled dataset is a 30-customer/24-complaint demonstration derived from
the Brazilian E-Commerce Public Dataset by Olist. Each response retains a
dataset fingerprint and separates:

- **source**: anonymized customer geography, orders, payments, delivery dates,
  review scores and comments;
- **derived**: customer value, relationship risk, complaint priority and next
  action;
- **synthetic**: complaint workflow/SLA replay, replacement inventory and
  resolution-cost assumptions.

Customer value and relationship risk are service-management signals, not credit
ratings. The Olist fixture is not yet mapped into the canonical AdventureWorks
`SnapshotBundle`; that remains a data-alignment workstream.

## HTTP contracts

Versioned reads and review workflow:

- `GET /api/v1/crm/provenance`
- `GET /api/v1/crm/summary`
- `GET /api/v1/crm/customers`
- `GET /api/v1/crm/customers/{customer_id}`
- `GET /api/v1/crm/complaints?limit=24`
- `GET /api/v1/crm/complaints/{complaint_id}`
- `GET|POST /api/v1/crm/proposals`
- `GET /api/v1/crm/proposals/{proposal_id}`
- `POST /api/v1/crm/proposals/{proposal_id}/decision`

All versioned responses use `crm-api-v1` and include `dataset_reference`,
`data`, and `provenance`. Temporary `/api/crm/*` read/proposal aliases keep the
original green frontend working during migration.

## Agent tools

The shared runtime registers ten read-only CRM tools: summary, priority queue,
customer 360, complaint detail, order timeline, replacement availability,
financial-impact estimate, resolution comparison, resolution recommendation,
and unsent reply draft.

The Agent cannot approve or execute a resolution. Proposal creation and the
approval/rejection decision require explicit API/UI actions and are stored in
`crm_proposals` with an audit trail. Approval records a human decision only.

## Run

```bash
uv sync --all-groups
uv run uvicorn interfaces.api.main:app --reload
```

Open `http://127.0.0.1:8000` and use the green **CRM Service Recovery** panel.
Without OpenClaw configuration the CRM dashboard, tools, proposals and approval
workflow still work; only natural-language Agent answers are disabled.

## Validate

```bash
uv run pytest tests/unit/test_crm_tools.py tests/api/test_crm.py -q
uv run ruff check .
uv run mypy src
node --test tests/frontend/assistant.test.cjs
```
