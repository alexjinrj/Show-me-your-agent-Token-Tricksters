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

