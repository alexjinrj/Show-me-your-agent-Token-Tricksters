from __future__ import annotations

from fastapi.testclient import TestClient


def test_processes_expose_node_sequences(client: TestClient) -> None:
    response = client.get("/api/processes")
    assert response.status_code == 200
    processes = {item["process_id"]: item for item in response.json()["processes"]}

    otc = processes["order_to_cash"]
    assert [node["id"] for node in otc["nodes"]] == [
        "order_received",
        "credit_review",
        "order_approved",
        "inventory_allocated",
        "pick_and_pack",
        "shipped",
        "invoiced",
        "paid",
    ]
    assert [(edge["source"], edge["target"]) for edge in otc["edges"]] == [
        ("order_received", "credit_review"),
        ("credit_review", "order_approved"),
        ("order_approved", "inventory_allocated"),
        ("inventory_allocated", "pick_and_pack"),
        ("pick_and_pack", "shipped"),
        ("shipped", "invoiced"),
        ("invoiced", "paid"),
    ]
    assert otc["edges"][0]["guard"] == "customer_is_active"
    assert "warehouse_staff" in otc["resources"]

    ptp = processes["procure_to_pay"]
    assert [node["id"] for node in ptp["nodes"]] == [
        "reorder_triggered",
        "purchase_order_placed",
        "supplier_lead_time",
        "goods_received",
        "supplier_invoice_recorded",
        "supplier_paid",
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
