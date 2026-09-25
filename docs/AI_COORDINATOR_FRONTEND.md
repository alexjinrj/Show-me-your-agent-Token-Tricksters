# AI Coordinator frontend update

## Objective

The AI Coordinator page now uses a focused, single-column conversation layout inspired by modern chat assistants. The redesign reduces explanatory clutter while preserving the information needed to judge an Agent response.

## Information retained

- Runtime availability status.
- Actual State evidence boundary.
- Deterministic tool boundary.
- Separation of simulation from Actual State.
- Human-review requirement.
- Optional public-event search limitation.
- Conversation history and response status.
- Tool-call count, Agent run ID and raw evidence.
- Safe external evidence links.
- CRM recommendation review link when returned by the Agent.

## Interaction changes

- Four suggested investigation prompts fill the composer without automatically sending data.
- Enter sends a message; Shift+Enter keeps a new line.
- The send action is disabled while the Agent is working.
- Evidence stays collapsed until the user asks to inspect it.
- The empty welcome state disappears after the first message.
- The composer remains visually anchored below the conversation.
- The layout collapses to one column on small screens.

## Safety boundary

The frontend does not parse an LLM response into business records and does not execute recommendations. Existing API requests and CRM human-review behavior are unchanged.
