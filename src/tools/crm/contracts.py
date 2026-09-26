from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CASE_ID_PATTERN = r"^CASE-[A-Za-z0-9][A-Za-z0-9_-]*$"
CUSTOMER_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"


class CRMToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(CRMToolInput):
    pass


class ComplaintListInput(CRMToolInput):
    limit: int = Field(default=10, ge=1, le=100)


class CustomerInput(CRMToolInput):
    customer_id: str = Field(min_length=1, max_length=80, pattern=CUSTOMER_ID_PATTERN)


class ComplaintInput(CRMToolInput):
    complaint_id: str = Field(min_length=6, max_length=100, pattern=CASE_ID_PATTERN)


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
