from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.simulation import inventory_replenishment


def test_creates_inventory_replenishment_event() -> None:
    event = inventory_replenishment(
        "WB-H098",
        Decimal("43"),
        effective_day=Decimal("3"),
    )

    assert event.event_type == "inventory_replenishment"
    assert event.effective_day == Decimal("3")
    assert event.payload == {"sku": "WB-H098", "quantity": "43"}


def test_replenishment_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="must be greater than zero"):
        inventory_replenishment("WB-H098", Decimal("0"))


def test_replenishment_sku_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="SKU cannot be empty"):
        inventory_replenishment("   ", Decimal("1"))
