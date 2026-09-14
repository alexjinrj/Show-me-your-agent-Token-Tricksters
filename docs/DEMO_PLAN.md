# Business Coordinator Demo Plan (API + Web Dashboard)

## Decisions
- API + web dashboard (FastAPI backend + static vanilla-JS SPA served by the same app; single deployable).
- Dynamic features: scenario what-if comparison AND animated process-trace playback.
- Reserve a chatbot panel + stub endpoint (POST /api/assistant) for a future analysis (LangGraph) agent.
- Persistence: single on-disk SQLite seeded at startup from data/demo/raw; one base snapshot; runs via SimulationService.
- AWS Lightsail: hooks only now (Dockerfile, env-var config, bind 0.0.0.0, /healthz); provisioning deferred.
- API calls application services; simulation never gets a writable session. Small backend corrections are permitted when required to preserve persisted lineage or expose trace node IDs.

## Existing service API surface
- ActualStateService: validate_csv, commit_ingestion, create_snapshot, load_snapshot, counts; commit_demo_files helper.
- SimulationService: create_session, get_session, add_event, fork_session, run_session, compare_runs.
- run_simulation(snapshot, scenario_events, horizon_days, random_seed) -> SimulationRunResult (summary_metrics, event_trace, accounting_impacts, daily state checkpoints; deterministic result_hash).
- Scenario events: order_arrival, resource_capacity_changed, supplier_delivery_delayed. Builders in simulation/scenarios.py.
- Processes: the full validated 8-node Order-to-Cash and 6-node Procure-to-Pay definitions from `RuntimeProcessCatalog`.
- Seeding: scripts/seed_demo_data.py ORDER + snapshot at 2026-09-12T23:59:00+08:00; database.py make_engine/create_schema/sqlite_url.
- Decimal everywhere -> serialize as strings; Asia/Singapore; SGD.

## Tasks (test-first; run ruff/mypy/pytest after each)
1. API deps + app skeleton + GET /healthz + env settings.
2. DemoContext startup seeding + snapshot (idempotent) + Decimal JSON encoder.
3. GET /api/processes, GET /api/snapshot.
4. Session endpoints: create/get/add-event/fork.
5. POST /api/sessions/{id}/run -> metrics+trace+impacts (deterministic).
6. POST /api/compare baseline vs alternative.
7. Static SPA shell + process flow diagrams.
8. Scenario builder + run + comparison panel.
9. Animated trace playback + utilization meters.
10. Chatbot placeholder panel + POST /api/assistant stub.
11. Dockerfile + env config + README (Lightsail hooks only).
12. E2E test + quality gates + docs.

## Review corrections

- Ported Kiro's files from the old SimPy checkout into the dedicated `codex/demo-frontend` worktree based on current `main`.
- Replaced duplicate YAML parsing with the validated runtime catalog.
- Persisted fork lineage correctly by flushing the child session before copied events.
- Isolated baseline and alternative sessions in the browser workflow.
- Added trace node IDs, audit hashes, Actual State isolation evidence, complete comparison metrics, and persisted-lineage tests.
