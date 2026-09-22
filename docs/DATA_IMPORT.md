# CSV data import contract

`ActualStateService.import_csv(...)` is the single Python entry point for a user CSV:

```text
inspect -> resolve fields -> validate all rows -> stage -> atomic SQL commit
```

The import is rejected as a whole when validation fails. Repeating the same valid upload is
idempotent.

## Time semantics

- Transactions keep their business time in the source: sales and purchase orders require
  timezone-aware `order_date` and `due_date`; resources require `effective_at`.
- Customer and supplier masters do not require a row-level timestamp.
- The SQL lineage column `business_timestamp` is internal metadata, not a customer or supplier
  business attribute. When a snapshot-style upload does not provide it, the importer uses the
  approved batch `default_business_timestamp`; otherwise commit time is used.
- The AdventureWorks demo takes its batch time from `SOURCE_MANIFEST.json/transform/target_as_of`.

## Field matching

Matching is deterministic:

1. Canonical names are normalized for case and punctuation. For example, `Customer Number`
   matches `customer_number`.
2. Semantic aliases are explicit. For example, an upload using `Customer ID` must provide
   `{"customer_number": "Customer ID"}`.
3. `data_origin` defaults to `source`, and `source_record_id` defaults to the one-based data-row
   number when they are not uploaded.
4. Extra columns are not imported and are listed in `ignored_columns`.

The mapping direction is always `canonical_field -> uploaded_column`. An optional LLM mapping
assistant may propose a mapping in the future, but its proposal must still pass the same
deterministic validation before anything reaches Enterprise State.

## Python example

```python
result = actual_state_service.import_csv(
    "customer-upload.csv",
    source_type="customers",
    mapping_version="customer-upload-v1",
    field_mapping={
        "customer_number": "Customer ID",
        "name": "Customer Label",
        "active": "Enabled",
    },
)
```

The result exposes the resolved source type, applied field mapping, ignored columns, validation
report, ingestion run ID, and commit/idempotency status. This is currently a Python service API;
an authenticated HTTP upload endpoint is not part of this change.
