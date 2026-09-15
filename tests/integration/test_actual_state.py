from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from enterprise_state.models import BusinessEventRow, CustomerRow
from enterprise_state.service import ActualStateService, commit_demo_files

ORDER = (
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
)


def seed(service: ActualStateService, demo_path: Path) -> None:
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in ORDER))


def test_rejected_ingestion_creates_no_events(service: ActualStateService, tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "customer_number,name,active,business_timestamp,data_origin,source_record_id\n"
        "C-1,Customer,true,not-a-date,source,1\n",
        encoding="utf-8",
    )
    run_id, report = service.validate_csv(source, "customers", "v1")
    assert not report.valid
    with pytest.raises(ValueError, match="fully validated"):
        service.commit_ingestion(run_id, "bad-file")
    with Session(service.engine) as session:
        assert session.scalar(select(func.count()).select_from(BusinessEventRow)) == 0
        assert session.scalar(select(func.count()).select_from(CustomerRow)) == 0


def test_demo_ingestion_is_lineage_complete_and_idempotent(
    service: ActualStateService, demo_path: Path
) -> None:
    seed(service, demo_path)
    counts = service.counts()
    assert counts == {
        "customers": 486,
        "suppliers": 8,
        "items": 40,
        "resources": 6,
        "inventory": 40,
        "balances": 6,
        "business_events": 596,
        "business_objects": 550,
    }
    path = demo_path / "customers.csv"
    run_id, report = service.validate_csv(path, "customers", "adventureworks-v1")
    assert report.valid
    key = f"demo:customers:{service.inspect_csv(path).sha256}"
    result = service.commit_ingestion(run_id, key)
    assert result["duplicate"] is True
    assert service.counts() == counts
    with Session(service.engine) as session:
        rows = session.scalars(select(CustomerRow)).all()
        assert all(
            row.source_file_id and row.source_record_id and row.ingestion_run_id for row in rows
        )


def test_snapshot_is_canonical_and_detached(service: ActualStateService, demo_path: Path) -> None:
    seed(service, demo_path)
    as_of = datetime.fromisoformat("2026-09-12T23:59:00+08:00")
    first = service.create_snapshot(as_of)
    bundle = service.load_snapshot(first.snapshot_id)
    second = service.create_snapshot(as_of)
    same_instant = service.create_snapshot(datetime.fromisoformat("2026-09-12T15:59:00+00:00"))
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id == same_instant.snapshot_id
    assert first.content_hash == second.content_hash
    assert bundle.manifest.as_of_time == datetime.fromisoformat("2026-09-12T15:59:00+00:00")
    assert bundle.manifest.content_hash == service.actual_state_hash()
    assert len(bundle.records) == 1136
    customer = next(record for record in bundle.records if record.record_type == "customer")
    assert customer.data["business_timestamp"] == "2026-09-12T15:59:00+00:00"
    assert isinstance(bundle.records, tuple)
    with pytest.raises(ValidationError):
        bundle.records[0].data = {}  # type: ignore[misc]
