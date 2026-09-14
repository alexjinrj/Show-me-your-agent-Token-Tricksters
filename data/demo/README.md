# Demo data provenance

The canonical CSVs in `raw/` are a deterministic, compact extract derived from
Microsoft's fictitious AdventureWorks OLTP install-script CSV files. The
upstream repository is MIT licensed.

- Dataset: <https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works>
- Source CSV directory: <https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/oltp-install-script>
- License: <https://github.com/microsoft/sql-server-samples/blob/master/license.txt>
- Rebuild: `uv run python scripts/build_demo_data.py`
- Seed: `uv run python scripts/seed_demo_data.py --database actual_state.db`

`SOURCE_MANIFEST.json` records each downloaded file's SHA-256 digest, row
counts, date rebasing, and the `source` / `derived` / `synthetic` boundary.
AdventureWorks is not represented as Singapore business evidence. It supplies
fictitious, relationally coherent records which are adapted for this MVP.

## Timestamp handling

Source CSVs retain their original demo offset (`+08:00`) so the supplied local
time remains auditable. During ingestion, timestamps are normalized to UTC
before SQLite storage; snapshot records restore explicit `+00:00` offsets.
This preserves the instant represented by the source value and avoids SQLite's
loss of timezone offsets. Existing demo databases created before this rule
must be rebuilt from the retained CSVs rather than migrated heuristically,
because a legacy naive SQLite timestamp does not contain enough information to
prove its original offset.
