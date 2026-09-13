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


def inspect_csv(path: str | Path) -> SourceInspection:
    csv_path = Path(path)
    warnings: list[str] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = list(reader)
    probable = next(
        (kind for kind, fields in SOURCE_TYPES.items() if set(fields) <= set(columns)), None
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
    path: str | Path, source_type: str, mapping_version: str
) -> ValidationReport:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source_type: {source_type}")
    csv_path = Path(path)
    issues: list[ValidationIssue] = []
    parsed_rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        expected = SOURCE_TYPES[source_type]
        if actual != expected:
            issues.append(
                ValidationIssue(
                    row_number=1,
                    field="header",
                    code="HEADER_MISMATCH",
                    message=f"expected {expected!r}, got {actual!r}",
                )
            )
        for row_number, row in enumerate(reader, start=2):
            if issues and issues[0].code == "HEADER_MISMATCH":
                continue
            try:
                if any(value is None or value == "" for value in row.values()):
                    raise ValueError("all mapped values are required")
                parsed_rows.append(_validate_row(source_type, row))
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
