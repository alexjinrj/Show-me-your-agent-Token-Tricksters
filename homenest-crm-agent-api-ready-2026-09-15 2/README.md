# HomeNest CRM Service Recovery Agent

An English-language, Git-ready CRM Agent prototype for NUS-ISS Show Me Your Agent Hackathon challenge 28, Business Performance Monitoring.

The application turns customer experience signals into a controlled service recovery workflow:

```text
Olist facts + labelled CRM replay
→ customer value and relationship risk
→ deterministic complaint priority
→ cross-functional investigation
→ resolution option comparison
→ human approval
→ local audit trail
```

## Product capabilities

- Customer value scoring based on payment percentile (50%), order frequency (30%) and recency (20%).
- Relationship risk scoring using low reviews, delivery delays and labelled CRM workflow signals.
- Complaint priority using SLA severity, first response, review severity, delivery delay, risk and value.
- Customer 360 with source-backed reasons and linked complaints.
- Cross-functional order, fulfilment, inventory and finance investigation.
- Comparison of refund, replacement, service credit and monitor options.
- A deterministic recommendation with estimated cost, resolution time and relationship recovery.
- Human approval state machine: Pending Review → Approved → In Progress → Completed, or Rejected.
- Local audit trail for proposals and reviewer decisions.
- Ten strict Agent tools with an optional OpenAI Responses API tool-calling loop.

## Evidence boundary

The project intentionally separates three evidence classes:

1. **Olist facts:** anonymous customer IDs, city/state, orders, payment totals, purchase/delivery/estimated-delivery timestamps, review scores and review text.
2. **CRM replay:** display IDs, complaint IDs, workflow status, 48-hour SLA and first-response timestamps.
3. **Demo assumptions:** replacement inventory, replenishment time, refund exposure, replacement cost and service-credit estimates.

Customer value and relationship risk are operational prioritisation signals, not credit ratings. No proposed resolution is executed automatically.

## Run locally

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Open the local URL printed by the development server.

## Optional LLM configuration

Without an API key, the application uses the same deterministic tools through a stable demo router. To let an LLM choose tools and compose the final response:

```bash
cp .env.example .env.local
```

Add your API key to `.env.local`, then restart the app. Never commit `.env.local` or an API key.

All scores, dates and costs continue to come from deterministic tools. The LLM only selects tools and explains their outputs.

## Team FastAPI integration

The frontend exposes stable CRM endpoints and can run before the team backend is ready:

```text
GET  /api/integration/status
GET  /api/crm/summary
GET  /api/crm/customers
GET  /api/crm/customers/{customer_id}
GET  /api/crm/complaints
GET  /api/crm/complaints/{complaint_id}
POST /api/crm/proposals
POST /api/agent
```

Without configuration, read endpoints use the bundled Olist snapshot and return
`X-CRM-Data-Source: local-demo`. To use the team FastAPI service, set this in
`.env.local` and restart the frontend:

```env
TEAM_API_BASE_URL=http://127.0.0.1:8028
TEAM_API_TIMEOUT_MS=3000
```

The gateway forwards CRM reads to the existing FastAPI `/api/crm/*` routes.
In LLM mode, Agent tools prefer the team backend for customer and complaint
evidence and fall back to the labelled local demo if it is unavailable. `POST
/api/crm/proposals` is reserved for durable approval storage and returns a safe
error until the team backend implements that endpoint.

The browser never receives `OPENAI_API_KEY` or the team backend address.

## Agent tools

```text
list_priority_complaints
get_customer_360
get_complaint_detail
get_order_timeline
get_inventory_availability
estimate_refund_impact
compare_resolution_options
recommend_resolution
draft_customer_reply
create_followup_proposal
```

## Suggested demo

1. Open **Today** and show the priority queue and value-risk matrix.
2. Open `TKT-004` and explain the Olist facts versus CRM replay fields.
3. Send the complaint to **Resolution Lab**.
4. Compare refund, replacement, credit and monitor options.
5. Submit the recommended option for human approval.
6. Approve it and move it through In Progress to Completed, showing the audit trail.
7. Ask the Agent: `Investigate TKT-004 and recommend the best action` and expand the tool trace.

## Project structure

```text
app/page.tsx                 English CRM workspace and approval workflow
app/api/agent/route.ts       Optional Responses API tool-calling loop
components/crm-agent.tsx     Agent chat and visible tool trace
data/olist-snapshot.json     Traceable Olist facts plus labelled CRM replay
lib/crm.ts                   Customer scores, complaint priority and approval state
lib/crm-client.ts            Typed frontend client for the stable CRM API
lib/resolution.ts            Cross-functional investigation and option comparison
lib/agent.ts                 Ten strict tools and deterministic demo routing
tests/crm.test.mjs           Source, scoring, decision and safety tests
```

## Verify

```bash
npm test
npm run typecheck
npm run lint
npm run build
```
