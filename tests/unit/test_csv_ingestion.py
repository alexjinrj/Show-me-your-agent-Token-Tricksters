from pathlib import Path

from load_data.csv_ingestion import inspect_csv, parse_and_validate


def test_inspection_detects_fixed_mapping(demo_path: Path) -> None:
    inspection = inspect_csv(demo_path / "items.csv")
    assert inspection.probable_source_type == "items"
    assert inspection.row_count == 40
    assert len(inspection.sha256) == 64


def test_invalid_row_is_rejected_atomically(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "customer_number,name,active,business_timestamp,data_origin,source_record_id\n"
        "C-1,Customer,true,2026-09-12T00:00:00,source,1\n",
        encoding="utf-8",
    )
    report = parse_and_validate(source, "customers", "v1")
    assert not report.valid
    assert report.valid_row_count == 0
    assert report.issues[0].code == "INVALID_ROW"
