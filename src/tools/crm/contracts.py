from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CRMToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(CRMToolInput):
    pass


class ComplaintListInput(CRMToolInput):
    limit: int = Field(default=10, ge=1, le=100)


class CustomerInput(CRMToolInput):
    customer_id: str = Field(pattern=r"^AW\d{8}$")


class ComplaintInput(CRMToolInput):
    complaint_id: str = Field(pattern=r"^CASE-SO\d{1,12}$")


class DraftReplyInput(ComplaintInput):
    tone: Literal["professional", "empathetic"] = "empathetic"


CRM_TOOL_INPUTS: dict[str, type[CRMToolInput]] = {
    "get_crm_summary": EmptyInput,
    "list_priority_complaints": ComplaintListInput,
    "get_customer_360": CustomerInput,
    "get_complaint_detail": ComplaintInput,
    "get_order_timeline": ComplaintInput,
    "get_inventory_availability": ComplaintInput,
    "estimate_refund_impact": ComplaintInput,
    "compare_resolution_options": ComplaintInput,
    "recommend_resolution": ComplaintInput,
    "draft_customer_reply": DraftReplyInput,
}
