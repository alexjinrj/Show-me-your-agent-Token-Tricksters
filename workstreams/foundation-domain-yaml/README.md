# Engineering Foundation, Domain Model, and Process YAML

Status: completed and integrated into `main` through PR #2.

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

## Public Foundation API

Canonical contracts are exported from `business_coordinator.domain`. They are
immutable Pydantic v2 models with forbidden extra fields, UUID-string internal
identifiers, timezone-aware timestamps, decimal monetary values, and explicit
`actual` or `simulated` state labels.

Process configuration is loaded through:

```python
from business_coordinator.config import (
    hash_process_catalog,
    hash_process_definition,
    load_process_definition,
    load_process_definitions,
)
```

Hashes are lowercase SHA-256 digests of canonical JSON. They depend on validated
configuration semantics, not YAML key order, whitespace, or comments. Catalogs
are ordered by process ID, and snapshot records are ordered by record type and
record key.

## Verification

From the repository root, run:

```text
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

This workstream has no persistence, SimPy, API, UI, Agent, LangGraph, or
external-service dependency.
