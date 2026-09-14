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
        "496b1c2cc9141070d6dafce8856000f049ba3c7ad2030c986c9ae86fbad38f9e"
    )
    assert hash_process_definition(first["procure_to_pay"]) == (
        "ce3092229047e55cd638f0310259adde261d10766670c7b366c0604c7772726f"
    )
    assert hash_process_catalog(first) == (
        "c015e0a5df5f910175f1edb6a2cf974868ac7f1233e1de4397d6068b6f6b0bd6"
    )


def test_simulation_runtime_reads_validated_process_structure() -> None:
    runtime = load_runtime_process_catalog(CONFIG_DIRECTORY)

    assert runtime.path_from("order_to_cash", "order_received") == (
        "order_received",
        "credit_review",
        "order_approved",
        "inventory_allocated",
        "pick_and_pack",
        "shipped",
        "invoiced",
        "paid",
    )
    assert runtime.resource("order_to_cash", "pick_and_pack") == "warehouse_staff"
    assert runtime.processing_hours("order_to_cash", "pick_and_pack") == 2
    assert runtime.parameter("procure_to_pay", "supplier_payment_terms_hours") == 336


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
