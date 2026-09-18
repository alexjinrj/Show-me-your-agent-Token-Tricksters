from __future__ import annotations

from fastapi.testclient import TestClient


def module_data(client: TestClient, module: str) -> dict[str, object]:
    response = client.get(f"/api/v1/modules/{module}")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "business-modules-v1"
    assert body["module"] == module
    assert body["provenance"]["state_type"] == "actual"
    return body["data"]


def test_business_modules_are_deterministic_snapshot_reads(client: TestClient) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]

    sales = module_data(client, "sales")
    inventory = module_data(client, "inventory")
    accounting = module_data(client, "accounting")
    operations = module_data(client, "operations")

    after = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    assert before == after
    assert sales["summary"]["order_count"] == 500  # type: ignore[index]
    assert sales["summary"]["backlog_count"] == 100  # type: ignore[index]
    assert sales["summary"]["backlog_value"] == "482.8000"  # type: ignore[index]
    assert inventory["summary"]["sku_count"] == 40  # type: ignore[index]
    assert inventory["summary"]["reorder_candidate_count"] == 6  # type: ignore[index]
    assert accounting["summary"]["cash"] == "85000.0000"  # type: ignore[index]
    assert accounting["summary"]["gross_profit"] == "221000.0000"  # type: ignore[index]
    assert operations["summary"]["business_object_count"] == 550  # type: ignore[index]
    assert operations["summary"]["resource_count"] == 6  # type: ignore[index]


def test_overview_links_all_business_modules(client: TestClient) -> None:
    overview = module_data(client, "overview")
    assert [row["id"] for row in overview["modules"]] == [  # type: ignore[index]
        "sales",
        "inventory",
        "accounting",
        "operations",
        "crm",
    ]
    assert overview["headline"]["service_case_count"] == 100  # type: ignore[index]


def test_crm_and_module_overview_share_the_same_snapshot(client: TestClient) -> None:
    overview = client.get("/api/v1/modules/overview").json()
    crm = client.get("/api/v1/crm/summary").json()
    snapshot = client.get("/api/snapshot").json()["manifest"]
    assert overview["snapshot_reference"] == crm["dataset_reference"] == snapshot["snapshot_id"]
    assert overview["data"]["headline"]["service_case_count"] == crm["data"]["serviceCaseCount"]
    assert overview["data"]["headline"]["overdue_orders"] == crm["data"]["overdueOrders"]
    assert crm["data"]["complaintCount"] is None
