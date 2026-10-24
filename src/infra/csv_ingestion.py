from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "customers": (
        "customer_number",
        "name",
        "active",
        "business_timestamp",
        "data_origin",
        "source_record_id",
    ),
    "suppliers": (
        "supplier_number",
        "name",
        "active",
        "business_timestamp",
        "data_origin",
        "source_record_id",
    ),
    "items": (
        "sku",
        "name",
        "standard_cost",
        "list_price",
        "reorder_point",
        "active",
        "business_timestamp",
        "data_origin",
        "source_record_id",
    ),
    "inventory": (
        "sku",
        "warehouse",
        "quantity",
        "business_timestamp",
        "data_origin",
        "source_record_id",
    ),
    "sales_orders": (
        "order_number",
        "customer_number",
        "sku",
        "quantity",
        "unit_price",
        "order_date",
        "due_date",
        "status",
        "priority",
        "data_origin",
        "source_record_id",
    ),
    "purchase_orders": (
        "order_number",
        "supplier_number",
        "sku",
        "quantity",
        "unit_cost",
        "order_date",
        "due_date",
        "status",
        "priority",
        "data_origin",
        "source_record_id",
    ),
    "resources": (
        "resource_type",
        "process_id",
        "node_id",
        "capacity_units",
        "effective_at",
        "data_origin",
        "source_record_id",
    ),
    "opening_balances": (
        "account_code",
        "amount",
        "currency",
        "business_timestamp",
        "data_origin",
        "source_record_id",
    ),
}

# These fields belong to ingestion lineage rather than the user's business table.
# They may still be supplied, but the importer can generate them deterministically.
GENERATED_FIELDS = {"data_origin", "source_record_id"}
IMPORT_TIME_FIELDS = {
    "customers",
    "suppliers",
    "items",
    "inventory",
    "opening_balances",
}


class ReadModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class SourceInspection(ReadModel):
    path: str
    sha256: str
    columns: tuple[str, ...]
    row_count: int
    probable_source_type: str | None
    sample_rows: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


class ValidationIssue(ReadModel):
    row_number: int
    field: str
    code: str
    message: str


class ValidationReport(ReadModel):
    source_type: str
    mapping_version: str
    valid: bool
    row_count: int
    valid_row_count: int
    issues: tuple[ValidationIssue, ...]
    rows: tuple[dict[str, Any], ...]


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_field(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _required_upload_fields(source_type: str) -> tuple[str, ...]:
    optional = set(GENERATED_FIELDS)
    if source_type in IMPORT_TIME_FIELDS:
        optional.add("business_timestamp")
    return tuple(field for field in SOURCE_TYPES[source_type] if field not in optional)


def resolve_field_mapping(
    columns: tuple[str, ...],
    source_type: str,
    field_mapping: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve canonical field -> uploaded column without fuzzy or LLM guessing."""

    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source_type: {source_type}")
    expected = SOURCE_TYPES[source_type]
    supplied = dict(field_mapping or {})
    unknown_targets = sorted(set(supplied) - set(expected))
    if unknown_targets:
        raise ValueError(f"field mapping has unknown canonical fields: {unknown_targets}")
    unknown_sources = sorted(set(supplied.values()) - set(columns))
    if unknown_sources:
        raise ValueError(f"field mapping references missing uploaded columns: {unknown_sources}")
    if len(set(supplied.values())) != len(supplied):
        raise ValueError("one uploaded column cannot map to multiple canonical fields")

    normalized: dict[str, list[str]] = {}
    for column in columns:
        normalized.setdefault(_normalized_field(column), []).append(column)
    resolved = dict(supplied)
    used_sources = set(resolved.values())
    for target in expected:
        if target in resolved:
            continue
        candidates = [
            column
            for column in normalized.get(_normalized_field(target), [])
            if column not in used_sources
        ]
        if len(candidates) == 1:
            resolved[target] = candidates[0]
            used_sources.add(candidates[0])
    return resolved


def inspect_csv(path: str | Path) -> SourceInspection:
    csv_path = Path(path)
    warnings: list[str] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = list(reader)
    probable = next(
        (
            kind
            for kind in SOURCE_TYPES
            if set(_required_upload_fields(kind))
            <= set(resolve_field_mapping(columns, kind))
        ),
        None,
    )
    if not columns:
        warnings.append("CSV has no header row")
    if not rows:
        warnings.append("CSV has no data rows")
    if probable is None and columns:
        warnings.append("Columns do not exactly match a fixed mapping template")
    return SourceInspection(
        path=str(csv_path),
        sha256=_file_hash(csv_path),
        columns=columns,
        row_count=len(rows),
        probable_source_type=probable,
        sample_rows=tuple(rows[:5]),
        warnings=tuple(warnings),
    )


def _datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone offset is required")
    return result


def _decimal(value: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    result = Decimal(value)
    if positive and result <= 0:
        raise ValueError("must be greater than zero")
    if nonnegative and result < 0:
        raise ValueError("must be zero or greater")
    return result


def _bool(value: str) -> bool:
    values = {"true": True, "false": False, "1": True, "0": False}
    try:
        return values[value.strip().lower()]
    except KeyError as exc:
        raise ValueError("must be true/false or 1/0") from exc


def _validate_row(source_type: str, row: dict[str, str]) -> dict[str, Any]:
    parsed: dict[str, Any] = dict(row)
    for key in ("business_timestamp", "order_date", "due_date", "effective_at"):
        if key in row:
            parsed[key] = _datetime(row[key])
    for key in (
        "standard_cost",
        "list_price",
        "reorder_point",
        "quantity",
        "unit_price",
        "unit_cost",
        "capacity_units",
        "amount",
    ):
        if key in row:
            parsed[key] = _decimal(
                row[key],
                positive=key in {"unit_price", "unit_cost", "capacity_units"},
                nonnegative=key
                in {
                    "standard_cost",
                    "list_price",
                    "reorder_point",
                    "quantity",
                },
            )
    if "active" in row:
        parsed["active"] = _bool(row["active"])
    if "priority" in row:
        parsed["priority"] = int(row["priority"])
        if parsed["priority"] < 0:
            raise ValueError("priority must be zero or greater")
    if row.get("data_origin") not in {"source", "derived", "synthetic"}:
        raise ValueError("data_origin must be source, derived, or synthetic")
    if (
        source_type in {"sales_orders", "purchase_orders"}
        and parsed["due_date"] < parsed["order_date"]
    ):
        raise ValueError("due_date cannot be earlier than order_date")
    if source_type in {"sales_orders", "purchase_orders"} and parsed["quantity"] <= 0:
        raise ValueError("order quantity must be greater than zero")
    if source_type == "opening_balances" and row["currency"] != "SGD":
        raise ValueError("demo balances must use SGD")
    return parsed


def parse_and_validate(
    path: str | Path,
    source_type: str,
    mapping_version: str,
    *,
    field_mapping: dict[str, str] | None = None,
    default_data_origin: str = "source",
    default_business_timestamp: str | None = None,
) -> ValidationReport:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source_type: {source_type}")
    csv_path = Path(path)
    issues: list[ValidationIssue] = []
    parsed_rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        try:
            resolved = resolve_field_mapping(actual, source_type, field_mapping)
        except ValueError as exc:
            resolved = {}
            issues.append(
                ValidationIssue(
                    row_number=1,
                    field="header",
                    code="HEADER_MISMATCH",
                    message=str(exc),
                )
            )
        missing = sorted(set(_required_upload_fields(source_type)) - set(resolved))
        if missing and not issues:
            issues.append(
                ValidationIssue(
                    row_number=1,
                    field="header",
                    code="HEADER_MISMATCH",
                    message=f"missing required canonical fields: {missing}",
                )
            )
        for row_number, row in enumerate(reader, start=2):
            if issues and issues[0].code == "HEADER_MISMATCH":
                continue
            try:
                canonical = {
                    target: row[source]
                    for target, source in resolved.items()
                    if row.get(source) not in {None, ""}
                }
                canonical.setdefault("data_origin", default_data_origin)
                canonical.setdefault("source_record_id", str(row_number - 1))
                if source_type in IMPORT_TIME_FIELDS and default_business_timestamp is not None:
                    canonical.setdefault("business_timestamp", default_business_timestamp)
                missing_values = [
                    field
                    for field in _required_upload_fields(source_type)
                    if canonical.get(field) in {None, ""}
                ]
                if missing_values:
                    raise ValueError(f"required values are empty: {missing_values}")
                parsed_rows.append(_validate_row(source_type, canonical))
            except (ValueError, InvalidOperation) as exc:
                issues.append(
                    ValidationIssue(
                        row_number=row_number,
                        field="row",
                        code="INVALID_ROW",
                        message=str(exc),
                    )
                )
    total = len(parsed_rows) + sum(issue.code == "INVALID_ROW" for issue in issues)
    return ValidationReport(
        source_type=source_type,
        mapping_version=mapping_version,
        valid=not issues and total > 0,
        row_count=total,
        valid_row_count=len(parsed_rows),
        issues=tuple(issues),
        rows=tuple(parsed_rows if not issues else ()),
    )
