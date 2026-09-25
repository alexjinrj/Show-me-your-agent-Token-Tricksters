# AI Coordinator frontend update

## Objective

The AI Coordinator page now uses a focused, single-column conversation layout inspired by modern chat assistants. The page-specific banner and repeated explanatory copy are hidden so the workspace starts directly with the conversation.

## Information retained

- Runtime availability status.
- Actual State, deterministic-tool, simulation and human-review boundaries in a compact About disclosure.
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
- Final Agent answers lead with the conclusion and adapt their depth to the question. They explain complex findings when needed, synthesize key figures and keep raw payloads in the evidence disclosure.

## Safety boundary

The frontend does not parse an LLM response into business records and does not execute recommendations. Existing API requests and CRM human-review behavior are unchanged.
