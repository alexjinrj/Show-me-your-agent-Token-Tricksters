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

Implementation should be merged in the same order. The shared boundary between
the workstreams is defined in [`INTERFACE_CONTRACTS.md`](INTERFACE_CONTRACTS.md).

This slice intentionally excludes the Agent, LangGraph, public tool wrappers,
FastAPI, Streamlit, ERPNext submission, and production deployment.
