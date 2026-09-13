# Engineering Foundation, Domain Model, and Process YAML

Git branch: `codex/foundation-domain-yaml`

## Objective

Create the common Python project skeleton and the versioned business contracts
used by both persistence and simulation.

## Deliverables

- Python 3.12 `uv` project with `src/` layout.
- Pydantic domain models listed in `../INTERFACE_CONTRACTS.md`.
- Configuration loader and deterministic configuration hashing.
- `config/processes/order_to_cash.yaml`.
- `config/processes/procure_to_pay.yaml`.
- Unit tests for schemas, process transitions, guards, and configuration hashes.
- Ruff and mypy configuration.

## Completion Criteria

- Both process files load and validate.
- Invalid nodes, transitions, guards, resource types, or versions fail clearly.
- Canonical objects serialize deterministically.
- No database, SimPy, API, UI, Agent, or external-service implementation is
  introduced in this branch.

## Output to the Next Workstream

The canonical model package and validated process definitions are the only
business-contract inputs used by CSV ingestion and SQL persistence.
