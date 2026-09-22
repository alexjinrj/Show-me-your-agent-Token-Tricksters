from pathlib import Path

from load_data.csv_ingestion import inspect_csv, parse_and_validate, resolve_field_mapping


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


def test_customer_master_needs_no_row_timestamp_or_lineage_columns(tmp_path: Path) -> None:
    source = tmp_path / "customers.csv"
    source.write_text(
        "Customer Number,Name,Active\n"
        "C-1,Customer One,true\n",
        encoding="utf-8",
    )

    inspection = inspect_csv(source)
    report = parse_and_validate(source, "customers", "upload-v1")

    assert inspection.probable_source_type == "customers"
    assert report.valid
    assert report.rows[0] == {
        "customer_number": "C-1",
        "name": "Customer One",
        "active": True,
        "data_origin": "source",
        "source_record_id": "1",
    }


def test_explicit_mapping_resolves_noncanonical_upload_headers() -> None:
    mapping = resolve_field_mapping(
        ("Customer ID", "Customer Label", "Enabled"),
        "customers",
        {
            "customer_number": "Customer ID",
            "name": "Customer Label",
            "active": "Enabled",
        },
    )

    assert mapping == {
        "customer_number": "Customer ID",
        "name": "Customer Label",
        "active": "Enabled",
    }
