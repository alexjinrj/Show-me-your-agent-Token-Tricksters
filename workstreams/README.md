# MVP Workstreams

This directory records completed and planned implementation workstreams. The
first three branches were developed in dependency order and are now integrated
into `main`.

| Dependency order | Workstream | Git branch | Directory |
|---|---|---|---|
| 1 | Engineering foundation, domain model, and process YAML | `codex/foundation-domain-yaml` | `foundation-domain-yaml/` |
| 2 | CSV ingestion and SQL Actual State | `codex/data-csv-sql` | `data-csv-sql/` |
| 3 | SimPy process simulation | `codex/simpy-process-simulation` | `simpy-process-simulation/` |
| 4 | Read-only demo frontend | `codex/demo-frontend` | `demo-frontend/` |
| 5 | Object-centric YAML runtime refactor | `codex/object-centric-runtime` | repository-wide successor workstream |

The completed dependency chain was:

```text
historical main
  -> codex/foundation-domain-yaml
      -> codex/data-csv-sql
          -> codex/simpy-process-simulation
```

Current working-directory roles are:

```text
Code/                                      # canonical integrated main
Code-worktrees/data-csv-sql/               # completed isolated data history
Code-worktrees/mvp-integration/             # completed integration history
Code-worktrees/demo-frontend/              # next frontend implementation
Code-worktrees/object-centric-runtime/     # current state/YAML/SimPy refactor
```

Agents must work only in the directory assigned to their branch. They must not
switch branches inside another worktree or edit another workstream's checkout.

New work must start from the latest `main`. The shared boundary between the
workstreams is defined in [`INTERFACE_CONTRACTS.md`](INTERFACE_CONTRACTS.md),
and current handoff details are in [`../HANDOFF.md`](../HANDOFF.md).

The frontend workstream intentionally excludes the Agent, LangGraph, public
tool wrappers, FastAPI, ERPNext submission, and production deployment.
