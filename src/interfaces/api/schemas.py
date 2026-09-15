from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import ScenarioEvent


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreateRequest(ApiModel):
    base_snapshot_id: str | None = Field(
        default=None,
        description="Defaults to the seeded base snapshot when omitted.",
    )
    name: str = Field(min_length=1)
    description: str = ""


class ForkRequest(ApiModel):
    name: str = Field(min_length=1)


class OrderArrivalEvent(ApiModel):
    event_type: Literal["order_arrival"]
    effective_day: Decimal = Field(default=Decimal("0"), ge=0)
    sku: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, gt=0)
    priority: int = Field(default=0, ge=0)

    def to_scenario_event(self) -> ScenarioEvent:
        payload: dict[str, Any] = {
            "sku": self.sku,
            "quantity": str(self.quantity),
            "priority": self.priority,
        }
        if self.unit_price is not None:
            payload["unit_price"] = str(self.unit_price)
        return ScenarioEvent(
            event_type="order_arrival", effective_day=self.effective_day, payload=payload
        )


class ResourceCapacityChangedEvent(ApiModel):
    event_type: Literal["resource_capacity_changed"]
    effective_day: Decimal = Field(default=Decimal("0"), ge=0)
    resource_type: str = Field(min_length=1)
    capacity_delta: int = Field(description="Non-zero integer change in worker count.")

    def to_scenario_event(self) -> ScenarioEvent:
        if self.capacity_delta == 0:
            raise ValueError("capacity_delta must be a non-zero integer")
        return ScenarioEvent(
            event_type="resource_capacity_changed",
            effective_day=self.effective_day,
            payload={
                "resource_type": self.resource_type,
                "capacity_delta": self.capacity_delta,
            },
        )


class SupplierDeliveryDelayedEvent(ApiModel):
    event_type: Literal["supplier_delivery_delayed"]
    effective_day: Decimal = Field(default=Decimal("0"), ge=0)
    days_delta: Decimal = Field(description="Non-zero shift in delivery days (negative expedites).")
    purchase_order_number: str | None = None

    def to_scenario_event(self) -> ScenarioEvent:
        if self.days_delta == 0:
            raise ValueError("days_delta must be a non-zero finite number")
        payload: dict[str, Any] = {"days_delta": str(self.days_delta)}
        if self.purchase_order_number is not None:
            payload["purchase_order_number"] = self.purchase_order_number
        return ScenarioEvent(
            event_type="supplier_delivery_delayed",
            effective_day=self.effective_day,
            payload=payload,
        )


EventRequest = Annotated[
    OrderArrivalEvent | ResourceCapacityChangedEvent | SupplierDeliveryDelayedEvent,
    Field(discriminator="event_type"),
]


class PresetRequest(ApiModel):
    """Optional convenience wrappers around simulation/scenarios.py builders."""

    preset: Literal["warehouse_capacity_increase", "expedited_supplier_delivery"]
    workers: int = Field(default=1, gt=0)
    days: int = Field(default=5, gt=0)
    purchase_order_number: str | None = None


class RunRequest(ApiModel):
    horizon_days: int = Field(default=30, gt=0, le=3650)
    random_seed: int = Field(default=42, ge=0)


class RunSpec(ApiModel):
    """One side of a comparison: run a session with a horizon/seed."""

    session_id: str = Field(min_length=1)
    horizon_days: int = Field(default=30, gt=0, le=3650)
    random_seed: int = Field(default=42, ge=0)


class CompareRequest(ApiModel):
    baseline: RunSpec
    alternative: RunSpec
