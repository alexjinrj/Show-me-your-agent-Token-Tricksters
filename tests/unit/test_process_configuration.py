from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from business_coordinator.config import (
    ProcessConfigurationError,
    hash_process_catalog,
    hash_process_definition,
    load_process_definition,
    load_process_definitions,
)

CONFIG_DIRECTORY = Path(__file__).parents[2] / "config" / "processes"


def test_process_catalog_loads_with_expected_sequences_and_guards() -> None:
    catalog = load_process_definitions(CONFIG_DIRECTORY)

    assert list(catalog) == ["order_to_cash", "procure_to_pay"]
    order_to_cash = catalog["order_to_cash"]
    assert [node.id for node in order_to_cash.nodes] == [
        "order_received",
        "credit_review",
        "order_approved",
        "inventory_allocated",
        "pick_and_pack",
        "shipped",
        "invoiced",
        "paid",
    ]
    assert order_to_cash.transition("order_received", "credit_review").guard == "customer_is_active"
    assert order_to_cash.transition("shipped", "invoiced").guard == "shipment_confirmed"

    procure_to_pay = catalog["procure_to_pay"]
    assert [node.id for node in procure_to_pay.nodes] == [
        "reorder_triggered",
        "purchase_order_placed",
        "supplier_lead_time",
        "goods_received",
        "supplier_invoice_recorded",
        "supplier_paid",
    ]
    assert (
        procure_to_pay.transition("supplier_lead_time", "goods_received").guard
        == "supplier_delivery_received"
    )
    with pytest.raises(ValueError, match="not permitted"):
        order_to_cash.transition("order_received", "paid")


def test_configuration_hashes_are_stable() -> None:
    first = load_process_definitions(CONFIG_DIRECTORY)
    second = load_process_definitions(CONFIG_DIRECTORY)

    assert hash_process_definition(first["order_to_cash"]) == hash_process_definition(
        second["order_to_cash"]
    )
    assert hash_process_catalog(first) == hash_process_catalog(second)
    assert hash_process_definition(first["order_to_cash"]) == (
        "3963e075bb28f686b9e1430d7514c752fef71e149b98c8bc5ec8e3bd53740cbe"
    )
    assert hash_process_definition(first["procure_to_pay"]) == (
        "430f4573b94dde331055cc178e4b57c9800d2b4a13bfe4f550d0ac6dfc137aaf"
    )
    assert hash_process_catalog(first) == (
        "67daa64fe54eb88420924196b94e20e73891ca82f62823e48d4510f86bc58de3"
    )


def _unknown_target(raw: dict[str, Any]) -> None:
    raw["nodes"][0]["next"][0]["target"] = "missing_node"


def _unknown_guard(raw: dict[str, Any]) -> None:
    raw["nodes"][0]["next"][0]["guard"] = "llm_decides"


def _unknown_resource(raw: dict[str, Any]) -> None:
    raw["nodes"][0]["resource"] = "unbounded_workers"


def _wrong_process_guard(raw: dict[str, Any]) -> None:
    raw["nodes"][0]["next"][0]["guard"] = "supplier_payment_due"


def _unsupported_version(raw: dict[str, Any]) -> None:
    raw["version"] = 999


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_unknown_target, "transition targets do not exist"),
        (_unknown_guard, "guard"),
        (_wrong_process_guard, "guards are not valid for order_to_cash"),
        (_unknown_resource, "resource"),
        (_unsupported_version, "unsupported version"),
    ],
)
def test_invalid_process_configuration_fails_clearly(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None], message: str
) -> None:
    source = CONFIG_DIRECTORY / "order_to_cash.yaml"
    raw: dict[str, Any] = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutation(raw)
    path = tmp_path / "order_to_cash.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ProcessConfigurationError, match=message):
        load_process_definition(path)
