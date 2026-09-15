from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from interfaces.api.app import get_context
from interfaces.api.context import DemoContext
from interfaces.api.processes import load_all_processes

router = APIRouter(prefix="/api", tags=["reference"])
ContextDependency = Annotated[DemoContext, Depends(get_context)]


@router.get("/processes")
def get_processes(context: ContextDependency) -> dict[str, Any]:
    return load_all_processes(context.process_catalog)


@router.get("/snapshot")
def get_snapshot(context: ContextDependency) -> dict[str, Any]:
    bundle = context.base_snapshot()
    record_type_counts = Counter(record.record_type for record in bundle.records)
    opening_balances = [
        {
            "account_code": record.data["account_code"],
            "amount": record.data["amount"],
            "currency": record.data["currency"],
        }
        for record in bundle.records
        if record.record_type == "balance"
    ]
    opening_inventory = [
        {
            "item_id": record.data["item_id"],
            "warehouse": record.data["warehouse"],
            "quantity": record.data["quantity"],
        }
        for record in bundle.records
        if record.record_type == "inventory"
    ]
    return {
        "manifest": bundle.manifest.model_dump(mode="python"),
        "counts": context.counts(),
        "record_type_counts": dict(sorted(record_type_counts.items())),
        "opening_balances": opening_balances,
        "opening_inventory": opening_inventory,
        "source_manifest": context.source_manifest,
    }
