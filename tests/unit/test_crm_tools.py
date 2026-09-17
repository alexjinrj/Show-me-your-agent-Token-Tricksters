from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.crm.service import CRMService
from tools.crm.tools import CRMAgentTools

CRM_FIXTURE = Path(__file__).parents[2] / "data/load_data/olist_crm_demo/olist-snapshot.json"


def test_crm_scoring_and_priority_are_deterministic_and_labelled() -> None:
    service = CRMService(CRM_FIXTURE)
    first = service.prioritize_complaints()
    second = service.prioritize_complaints()
    assert first == second
    assert len(service.rate_customers()) == 30
    assert len(first) == 24
    assert all(0 <= row["priorityScore"] <= 100 for row in first)
    assert all(0 <= row["customer"]["valueScore"] <= 100 for row in first)
    assert "not credit ratings" in service.provenance()["warning"]


def test_crm_tools_use_common_envelope_and_strict_inputs() -> None:
    tools = CRMAgentTools(CRMService(CRM_FIXTURE))
    result = tools.call("get_customer_360", {"customer_id": "CUS-001"}, agent_case_id="test")
    assert result.status == "ok"
    assert result.state_type == "actual"
    assert result.reference_id and result.reference_id.startswith("olist-crm-demo:")
    assert result.data["customer"]["id"] == "CUS-001"
    with pytest.raises(ValidationError):
        tools.call(
            "get_complaint_detail",
            {"complaint_id": "TKT-001", "sql": "select *"},
            agent_case_id="test",
        )
