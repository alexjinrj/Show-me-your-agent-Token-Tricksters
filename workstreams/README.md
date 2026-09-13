# MVP Workstreams

This directory separates the first implementation slice into three workstreams.
The Git branches are stacked in dependency order so that downstream work uses
the exact contracts defined upstream.

| Dependency order | Workstream | Git branch | Directory |
|---|---|---|---|
| 1 | Engineering foundation, domain model, and process YAML | `codex/foundation-domain-yaml` | `foundation-domain-yaml/` |
| 2 | CSV ingestion and SQL Actual State | `codex/data-csv-sql` | `data-csv-sql/` |
| 3 | SimPy process simulation | `codex/simpy-process-simulation` | `simpy-process-simulation/` |

The branch dependency chain is:

```text
main
  -> codex/foundation-domain-yaml
      -> codex/data-csv-sql
          -> codex/simpy-process-simulation
```

Each branch is checked out in its own sibling worktree:

```text
Code/                                      # main coordination checkout
Code-worktrees/foundation-domain-yaml/     # codex/foundation-domain-yaml
Code-worktrees/data-csv-sql/               # codex/data-csv-sql
Code-worktrees/simpy-process-simulation/   # codex/simpy-process-simulation
```

Agents must work only in the directory assigned to their branch. They must not
switch branches inside another worktree or edit another workstream's checkout.

Implementation should be merged in the same order. The shared boundary between
the workstreams is defined in [`INTERFACE_CONTRACTS.md`](INTERFACE_CONTRACTS.md).

This slice intentionally excludes the Agent, LangGraph, public tool wrappers,
FastAPI, Streamlit, ERPNext submission, and production deployment.
