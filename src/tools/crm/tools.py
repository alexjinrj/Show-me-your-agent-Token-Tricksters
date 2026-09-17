from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent_runtime.contracts import RuntimeToolResult
from tools.crm.contracts import (
    CRM_TOOL_INPUTS,
    ComplaintInput,
    ComplaintListInput,
    CustomerInput,
    DraftReplyInput,
)
from tools.crm.service import CRMService


class CRMAgentTools:
    def __init__(self, service: CRMService) -> None:
        self.service = service

    @staticmethod
    def schemas() -> dict[str, dict[str, Any]]:
        return {name: model.model_json_schema() for name, model in CRM_TOOL_INPUTS.items()}

    def call(
        self, tool_name: str, arguments: dict[str, Any], *, agent_case_id: str
    ) -> RuntimeToolResult:
        del agent_case_id
        input_model = CRM_TOOL_INPUTS.get(tool_name)
        if input_model is None:
            raise ValueError(f"CRM tool is not registered: {tool_name}")
        parsed = input_model.model_validate(arguments)
        data: dict[str, Any]
        if tool_name == "get_crm_summary":
            data = {"summary": self.service.summary(), "provenance": self.service.provenance()}
        elif tool_name == "list_priority_complaints":
            assert isinstance(parsed, ComplaintListInput)
            rows = self.service.prioritize_complaints()[: parsed.limit]
            data = {"count": len(rows), "complaints": rows, "provenance": self.service.provenance()}
        elif tool_name == "get_customer_360":
            assert isinstance(parsed, CustomerInput)
            data = {
                "customer": self.service.customer(parsed.customer_id),
                "provenance": self.service.provenance(),
            }
        else:
            assert isinstance(parsed, ComplaintInput)
            complaint_id = parsed.complaint_id
            if tool_name == "get_complaint_detail":
                value: Any = self.service.complaint(complaint_id)
            elif tool_name == "get_order_timeline":
                value = self.service.order_timeline(complaint_id)
            elif tool_name == "get_inventory_availability":
                value = self.service.inventory_availability(complaint_id)
            elif tool_name == "estimate_refund_impact":
                value = self.service.financial_impact(complaint_id)
            elif tool_name == "compare_resolution_options":
                value = self.service.resolution_options(complaint_id)
            elif tool_name == "recommend_resolution":
                value = self.service.investigate(complaint_id)
            elif tool_name == "draft_customer_reply":
                assert isinstance(parsed, DraftReplyInput)
                value = self.service.draft_reply(complaint_id, parsed.tone)
            else:  # pragma: no cover - guarded by the registered map
                raise ValueError(f"unsupported CRM tool: {tool_name}")
            data = {"result": value, "provenance": self.service.provenance()}
        return RuntimeToolResult(
            tool_call_id=str(uuid4()),
            tool_name=tool_name,
            status="ok",
            state_type="actual",
            reference_id=self.service.reference_id,
            data=data,
        )
