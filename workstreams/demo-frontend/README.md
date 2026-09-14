# Demo Frontend Workstream

Status: MVP implementation available; further visual refinement is expected.

- Branch: `codex/demo-frontend`
- Worktree: `Code-worktrees/demo-frontend`
- Base: latest `main`
- Specification: `FRONTEND_PROJECT_SPECIFICATION.md`
- Backend handoff: `HANDOFF.md`
- Shared contracts: `workstreams/INTERFACE_CONTRACTS.md`

## Ownership

One Agent owns this worktree. Other Agents must not edit or switch its branch
while that Agent is active.

## Scope

Implement the read-only FastAPI web demonstration described by the frontend
specification. Reuse backend application services and validated process
configuration. Do not change Actual State, simulation formulas, or canonical
contracts merely to simplify the UI.

## Run and verify

```bash
git status --short --branch
uv sync --dev
uv run uvicorn business_coordinator.api.main:app --reload
uv run pytest -q
```

Before changing a backend contract, stop and document the required coordinated
change in this file.
