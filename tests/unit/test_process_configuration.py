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
from business_coordinator.simulation.process_runtime import load_runtime_process_catalog

CONFIG_DIRECTORY = Path(__file__).parents[2] / "config" / "processes"


def test_process_catalog_loads_with_executable_activity_contracts() -> None:
    catalog = load_process_definitions(CONFIG_DIRECTORY)

    assert list(catalog) == ["order_to_cash", "procure_to_pay"]
    order_to_cash = catalog["order_to_cash"]
    assert [node.id for node in order_to_cash.nodes] == [
        "receive_order",
        "review_credit",
        "approve_order",
        "allocate_inventory",
        "pick_and_pack",
        "ship_goods",
        "record_customer_invoice",
        "collect_customer_payment",
    ]
    allocation = order_to_cash.activity("allocate_inventory")
    assert [item.object_type for item in allocation.inputs] == [
        "sales_order",
        "inventory_position",
    ]
    assert allocation.operations[0].target == "inventory.quantity_available"
    assert allocation.operations[0].wait_if_insufficient is True

    procure_to_pay = catalog["procure_to_pay"]
    assert [node.id for node in procure_to_pay.nodes] == [
        "evaluate_reorder",
        "place_purchase_order",
        "wait_for_supplier_delivery",
        "receive_goods",
        "record_supplier_invoice",
        "pay_supplier",
    ]
    receiving = procure_to_pay.activity("receive_goods")
    assert receiving.operations[0].target == "inventory.quantity_on_hand"
    with pytest.raises(ValueError, match="not permitted"):
        order_to_cash.transition("receive_order", "collect_customer_payment")


def test_configuration_hashes_are_stable() -> None:
    first = load_process_definitions(CONFIG_DIRECTORY)
    second = load_process_definitions(CONFIG_DIRECTORY)

    assert hash_process_definition(first["order_to_cash"]) == hash_process_definition(
        second["order_to_cash"]
    )
    assert hash_process_catalog(first) == hash_process_catalog(second)
    assert len(hash_process_definition(first["order_to_cash"])) == 64
    assert len(hash_process_definition(first["procure_to_pay"])) == 64
    assert len(hash_process_catalog(first)) == 64


def test_simulation_runtime_reads_validated_process_structure() -> None:
    runtime = load_runtime_process_catalog(CONFIG_DIRECTORY)

    assert runtime.path_from("order_to_cash", "receive_order") == (
        "receive_order",
        "review_credit",
        "approve_order",
        "allocate_inventory",
        "pick_and_pack",
        "ship_goods",
        "record_customer_invoice",
        "collect_customer_payment",
    )
    assert runtime.resource("order_to_cash", "pick_and_pack") == "warehouse_staff"
    assert runtime.processing_hours("order_to_cash", "pick_and_pack") == 2
    assert runtime.parameter("procure_to_pay", "supplier_payment_terms_hours") == 336


def _unknown_target(raw: dict[str, Any]) -> None:
    raw["activities"][0]["next"][0]["target"] = "missing_node"


def _unknown_input_alias(raw: dict[str, Any]) -> None:
    raw["activities"][0]["operations"][0]["target"] = "missing.status"


def _unknown_resource(raw: dict[str, Any]) -> None:
    raw["activities"][0]["resource"] = "unbounded_workers"


def _unsupported_version(raw: dict[str, Any]) -> None:
    raw["version"] = 999


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_unknown_target, "transition targets do not exist"),
        (_unknown_input_alias, "unknown input alias"),
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
