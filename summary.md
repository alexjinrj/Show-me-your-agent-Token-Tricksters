# Summary

**Name:** SME Business State Coordinator

## Tech Stack

- Python 3.12 with FastAPI, Pydantic, and MCP.
- SQLAlchemy 2, Alembic, and SimPy for persistence and deterministic simulation.
- HTML/CSS/JavaScript browser dashboard with UV-managed tooling.

## Main Components

1. **Data & Enterprise State** — Validates CSV inputs and stores auditable actual states, immutable snapshots, and lineage in SQL.
2. **Simulation Core** — Runs isolated, deterministic Order-to-Cash and Procure-to-Pay processes using YAML-defined activities and shared resource constraints.
3. **Agent Tooling & Interface** — Provides bounded business tools, prompt-injection checks, a FastAPI backend, and a dashboard for running and inspecting scenarios.
