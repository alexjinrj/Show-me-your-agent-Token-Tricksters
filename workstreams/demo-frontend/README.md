# Demo Frontend Workstream

Status: ready for implementation.

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

Implement the read-only Streamlit demonstration described by the frontend
specification. Reuse backend application services and validated process
configuration. Do not change Actual State, simulation formulas, or canonical
contracts merely to simplify the UI.

## Starting checks

```bash
git status --short --branch
uv sync --dev
uv run python scripts/run_simulation_demo.py
uv run pytest -q
```

Before changing a backend contract, stop and document the required coordinated
change in this file.
