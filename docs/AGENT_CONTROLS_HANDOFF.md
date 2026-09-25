# Agent controls: human review, guardrails, observability and evaluation

This branch is based on `main@2cd72fe` and is separate from the sales UI branch.

## Runtime flow

After each Agent turn, the runtime checks successful sales simulation evidence for matching
snapshot hashes, separate baseline/alternative runs, identical horizon/seed, typed actual versus
simulated data, and unchanged Actual State. A failed structural check changes the Agent run to
`failed` and blocks its recommendation. These checks cannot verify every free-form sentence in
the LLM answer; they guard machine-verifiable evidence.

The runtime stores a compact observation alongside the full trace: final status, tools used,
tool errors, tool-call rounds and tokens reported by the model provider. No usage is invented
when the provider omits it.

Completed runs with a successful sales, CRM capacity or inventory strategy simulation receive
a pending human-review record. A reviewer can approve or reject the recommendation. The
decision is persisted atomically, linked to the source Tool Call IDs and cannot be overwritten.
Approval records a review decision only; it never changes actual staffing, inventory, payments,
shipments or customer communications.

## API

- `GET /api/assistant/runs/{id}/evaluation`: per-run guardrails, observations and review state.
- `POST /api/assistant/runs/{id}/evaluate-case`: apply explicit required/forbidden Tool criteria
  to a saved run. This is a test assessment, not a claim about unobserved LLM reasoning.
- `GET /api/assistant/runs/{id}/review`: inspect the pending or decided human review.
- `POST /api/assistant/runs/{id}/review`: one human decision, with `decision`, `reviewer`, `note`.
- `GET /api/assistant/evaluation/summary`: aggregate completed, failed, blocked and pending counts.

Example case criteria:

```json
{
  "required_tools": ["analyze_sales_backlog_intervention"],
  "forbidden_tools": ["run_sql"],
  "require_completed": true,
  "require_guardrails_passed": true,
  "require_review_pending": true
}
```

## Scope and follow-up

This is a minimal durable control layer on the existing SQLite AgentRun. It does not create a
general approval engine or perform real business actions. The current structural guardrail
recognizes the versioned sales analysis contract. Other domain contracts can add their own
deterministic checks once their invariants are agreed. The case evaluator checks explicit Tool
paths and run states; real model behavior still needs live Gateway runs and human review of the
answer's wording.
