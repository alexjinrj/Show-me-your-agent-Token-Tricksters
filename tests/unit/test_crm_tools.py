from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from interfaces.api.context import DemoContext
from interfaces.api.settings import Settings
from tools.crm.service import CRMService
from tools.crm.tools import CRMAgentTools


@pytest.fixture
def crm(tmp_path: Path) -> CRMService:
    context = DemoContext.bootstrap(
        Settings(
            db_path=tmp_path / "crm.db",
            host="127.0.0.1",
            host_port=8000,
            demo_data_dir=Path(__file__).parents[2] / "data/load_data/adventureworks_demo",
        )
    )
    return context.crm


def test_crm_scoring_and_priority_are_deterministic_and_labelled(crm: CRMService) -> None:
    first = crm.prioritize_complaints()
    assert first == crm.prioritize_complaints()
    assert len(crm.rate_customers()) == 486
    assert len(first) == 100
    assert all(0 <= row["priorityScore"] <= 100 for row in first)
    assert all(0 <= row["customer"]["valueScore"] <= 100 for row in first)
    assert all(row["caseKind"] == "derived_order_service_exception" for row in first)
    assert all(row["reviewScore"] is None and row["firstResponseAt"] is None for row in first)
    assert "not credit ratings" in crm.provenance()["warning"]
    assert crm.summary()["complaintCount"] is None
    assert crm.provenance()["boundaries"]["synthetic"] == []


def test_crm_tools_use_common_envelope_and_strict_inputs(crm: CRMService) -> None:
    tools = CRMAgentTools(crm)
    result = tools.call("get_customer_360", {"customer_id": "AW00011308"}, agent_case_id="test")
    assert result.status == "ok"
    assert result.state_type == "actual"
    assert result.reference_id == crm.snapshot.manifest.snapshot_id
    assert result.data["customer"]["id"] == "AW00011308"
    assert result.data["data_scope"]["canonical_snapshot_mapped"] is True
    with pytest.raises(ValidationError):
        tools.call(
            "get_complaint_detail",
            {"complaint_id": "CASE-SO74695", "sql": "select *"},
            agent_case_id="test",
        )
    with pytest.raises(ValidationError):
        tools.call("get_customer_360", {"customer_id": "CUS-001"}, agent_case_id="test")


def test_crm_order_inventory_and_money_match_canonical_snapshot(crm: CRMService) -> None:
    case = crm.complaint("CASE-SO74695")
    order = crm.orders[case["orderId"]]
    assert case["customerId"] == order["details"]["customer_number"]
    assert case["orderObjectId"] == order["id"]
    impact = crm.financial_impact(case["id"])
    assert impact["currency"] == "SGD"
    assert Decimal(impact["orderAmount"]) == Decimal(str(order["amount"]))
    assert impact["serviceCreditEstimate"] is None
    assert impact["paymentVerified"] is False
    stock = crm.inventory_availability(case["id"])
    assert Decimal(stock["onHandUnits"]) == sum(
        (Decimal(str(row["quantity"])) for row in stock["warehouses"]), Decimal(0)
    )
    assert Decimal(stock["availableUnits"]) == max(
        Decimal(0), Decimal(stock["onHandUnits"]) - Decimal(stock["pendingOrderUnits"])
    )
    assert Decimal(stock["availableForThisOrder"]) == max(
        Decimal(0),
        Decimal(stock["onHandUnits"])
        - max(Decimal(0), Decimal(stock["pendingOrderUnits"]) - Decimal(case["quantity"])),
    )
    assert all(row["resolutionDays"] is None for row in crm.resolution_options(case["id"]))
    assert crm.snapshot.manifest.content_hash == crm.dataset_fingerprint
