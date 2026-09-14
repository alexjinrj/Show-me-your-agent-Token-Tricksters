# MVP Interface Contracts

These contracts are the integration boundary for the foundation, ingestion,
database, and simulation workstreams. Implementations may add internal fields,
but must not change these contracts without updating all downstream branches.

## Dependency Direction

```text
Domain models + process definitions
              |
              v
CSV ingestion -> SQL Actual State -> immutable SnapshotBundle
                                             |
                                             v
                                  SimPy simulation run
```

Simulation code may read a snapshot bundle. It must never update Actual State
tables or reuse mutable SQLAlchemy entities as simulation state.

## Canonical Domain Types

The foundation branch owns versioned, Pydantic-based definitions for:

- `Customer`
- `Supplier`
- `Item`
- `ResourceCapacity`
- `BusinessObject`
- `BusinessEvent`
- `SnapshotManifest`
- `SnapshotRecord`
- `SnapshotBundle`
- `ScenarioEvent`
- `SimulationRunResult`

All identifiers are UUID strings internally. Human-readable customer, supplier,
SKU, order, and purchase-order numbers are stored separately.

Every actual record carries source lineage. Every object or result carries a
`state_type` whose value is either `actual` or `simulated`.

## Ingestion and Database Boundary

The ingestion/database workstream exposes application services equivalent to:

```python
inspect_csv(path) -> SourceInspection
validate_csv(path, source_type, mapping_version) -> ValidationReport
commit_ingestion(validated_run_id, idempotency_key) -> IngestionResult
create_snapshot(as_of_time) -> SnapshotManifest
load_snapshot(snapshot_id) -> SnapshotBundle
```

Only `commit_ingestion` may append Actual State events. A rejected validation
must create no business event. Repeating the same idempotency key must not
duplicate data.

`SnapshotBundle` is canonical JSON-compatible data, not live ORM objects. Its
content hash is calculated after stable key ordering and stable record ordering.

## Simulation Boundary

The simulation workstream consumes only:

```python
run_simulation(
    snapshot: SnapshotBundle,
    scenario_events: list[ScenarioEvent],
    horizon_days: int,
    random_seed: int,
) -> SimulationRunResult
```

The first slice supports these scenario event types:

- `order_arrival`
- `resource_capacity_changed`
- `supplier_delivery_delayed` (a negative day delta represents an expedited delivery)

A simulation run must construct a fresh in-memory state and a fresh SimPy
environment. Its result must contain the snapshot hash, process-definition
version/hash, scenario-event hash, horizon, seed, result hash, summary metrics,
and event trace.

## Compatibility Rules

1. Process YAML is versioned and validated before ingestion or simulation.
2. Times are timezone-aware ISO 8601 values; the demo company timezone is
   `Asia/Singapore`. Source offsets remain in retained files, SQLite storage is
   normalized to UTC, and snapshot outputs restore an explicit UTC offset.
3. Currency values use decimal semantics and the demo currency is SGD.
4. Quantities are never inferred by the LLM.
5. Actual State is append-only except for explicitly materialized projections.
6. A simulation run cannot receive a database session with write permission.
7. Identical snapshot, configuration, events, horizon, and seed must produce an
   identical result hash.
8. Contract changes require coordinated updates to all dependent branches and
   their tests.

## Frontend Boundary

The demo frontend may call `ActualStateService`, `SimulationService`, and the
validated runtime process catalog through an application-facing orchestration
service. It must not query ORM tables directly, write Actual State, duplicate
process definitions, or recalculate values already supplied by
`SimulationRunResult`.
