from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_coordinator.domain.models import (
    ScenarioEvent,
)


def test_valid_inventory_replenishment_event() -> None:
    event = ScenarioEvent(
        event_type="inventory_replenishment",
        effective_day=Decimal("3"),
        payload={
            "sku": "WB-H098",
            "quantity": "5",
            "unit_cost": "1.8663",
        },
    )

    assert event.event_type == "inventory_replenishment"
    assert event.effective_day == Decimal("3")
    assert event.payload["sku"] == "WB-H098"
    assert event.payload["quantity"] == "5"


def test_replenishment_quantity_must_be_positive() -> None:
    with pytest.raises(
        ValidationError,
        match="replenishment quantity must be",
    ):
        ScenarioEvent(
            event_type="inventory_replenishment",
            effective_day=Decimal("3"),
            payload={
                "sku": "WB-H098",
                "quantity": "0",
            },
        )
