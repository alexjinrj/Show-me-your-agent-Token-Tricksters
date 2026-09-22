from __future__ import annotations

from fastapi.testclient import TestClient


def test_processes_expose_node_sequences(client: TestClient) -> None:
    response = client.get("/api/processes")
    assert response.status_code == 200
    processes = {item["process_id"]: item for item in response.json()["processes"]}

    otc = processes["order_to_cash"]
    assert [activity["id"] for activity in otc["activities"]] == [
        "receive_order",
        "review_credit",
        "approve_order",
        "allocate_inventory",
        "pick_and_pack",
        "ship_goods",
        "record_customer_invoice",
        "collect_customer_payment",
    ]
    assert [(edge["source"], edge["target"]) for edge in otc["edges"]] == [
        ("receive_order", "review_credit"),
        ("review_credit", "approve_order"),
        ("approve_order", "allocate_inventory"),
        ("allocate_inventory", "pick_and_pack"),
        ("pick_and_pack", "ship_goods"),
        ("ship_goods", "record_customer_invoice"),
        ("record_customer_invoice", "collect_customer_payment"),
    ]
    assert otc["schema_version"] == 2
    assert otc["edges"][0]["conditions"] == []
    assert otc["activities"][3]["inputs"][1]["object_type"] == "inventory_position"
    assert otc["nodes"] == otc["activities"]  # compatibility alias for the existing UI
    assert "warehouse_staff" in otc["resources"]

    ptp = processes["procure_to_pay"]
    assert [activity["id"] for activity in ptp["activities"]] == [
        "evaluate_reorder",
        "place_purchase_order",
        "wait_for_supplier_delivery",
        "receive_goods",
        "record_supplier_invoice",
        "pay_supplier",
    ]
    assert len(response.json()["content_hash"]) == 64


def test_snapshot_manifest_and_openings(client: TestClient) -> None:
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["manifest"]["company_id"] == "SG-SME-001"
    assert len(body["manifest"]["content_hash"]) == 64
    assert body["counts"]["business_objects"] == 550
    assert len(body["opening_balances"]) == 6
    assert len(body["opening_inventory"]) == 40
    # Decimal values serialized as strings, never floats.
    assert isinstance(body["opening_balances"][0]["amount"], str)
    assert body["source_manifest"]["dataset"].startswith("Microsoft AdventureWorks")
    assert body["source_manifest"]["embedded_exception"]["backlog_orders"] == 100


def test_enterprise_state_api_exposes_one_canonical_record_shape(client: TestClient) -> None:
    response = client.get(
        "/api/enterprise-state",
        params={"record_kind": "object", "record_type": "inventory_position"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state_type"] == "actual"
    assert body["as_of_time"] == "2026-09-12T15:59:00Z"
    assert len(body["records"]) == 40
    record_id, record = next(iter(body["records"].items()))
    assert record_id.startswith("inventory_position:")
    assert record["record_kind"] == "object"
    assert record["record_type"] == "inventory_position"
    assert "quantity_on_hand" in record["data"]

    detail = client.get(f"/api/enterprise-state/records/{record_id}")
    assert detail.status_code == 200
    assert detail.json()["record_id"] == record_id

    history = client.get(
        "/api/enterprise-state",
        params={"record_kind": "event"},
    )
    assert history.status_code == 200
    assert len(history.json()["records"]) == 596
