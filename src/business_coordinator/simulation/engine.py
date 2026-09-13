from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, cast

import simpy
import yaml

from business_coordinator.domain.models import (
    AccountingImpact,
    AccountingLine,
    ScenarioEvent,
    SimulationMetrics,
    SimulationRunResult,
    SimulationTraceEvent,
    SnapshotBundle,
)
from business_coordinator.simulation.state import SimulatedOrder, SimulationState, snapshot_to_state

MONEY = Decimal("0.01")
NUMBER = Decimal("0.0001")
RUN_NAMESPACE = uuid.UUID("e42e0ab5-d3a3-4d27-a540-4d66d2062d5a")


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _number(value: Decimal) -> Decimal:
    return value.quantize(NUMBER, rounding=ROUND_HALF_UP)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class ProcessConfiguration:
    version_label: str
    content_hash: str
    processing_hours: dict[str, Decimal]
    payment_delay_hours: Decimal
    supplier_terms_hours: Decimal


def _load_process_configuration(config_dir: Path | None = None) -> ProcessConfiguration:
    root = config_dir or Path(__file__).parents[3] / "config" / "processes"
    documents: list[dict[str, Any]] = []
    for name in ("order_to_cash.yaml", "procure_to_pay.yaml"):
        with (root / name).open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"invalid process configuration: {name}")
        documents.append(cast(dict[str, Any], loaded))
    processing: dict[str, Decimal] = {}
    for document in documents:
        for node in document["nodes"]:
            processing[str(node["id"])] = _decimal(node["processing_time_hours"])
    versions = ",".join(f"{doc['process_id']}:v{doc['version']}" for doc in documents)
    return ProcessConfiguration(
        version_label=versions,
        content_hash=_hash(documents),
        processing_hours=processing,
        payment_delay_hours=_decimal(documents[0]["parameters"]["customer_payment_delay_hours"]),
        supplier_terms_hours=_decimal(documents[1]["parameters"]["supplier_payment_terms_hours"]),
    )


class CapacityPool:
    def __init__(self, env: simpy.Environment, capacity: int) -> None:
        self.env = env
        self.capacity = capacity
        self.capacity_hours = Decimal("0")
        self.last_change_hour = Decimal("0")
        self.tokens = simpy.Container(env, capacity=10_000, init=capacity)

    def acquire(self) -> simpy.Event:
        return self.tokens.get(1)

    def release(self) -> simpy.Event:
        return self.tokens.put(1)

    def change(self, delta: int) -> Generator[simpy.Event, None, None]:
        if delta > 0:
            yield self.tokens.put(delta)
        elif delta < 0:
            yield self.tokens.get(-delta)
        now = _decimal(self.env.now)
        self.capacity_hours += (now - self.last_change_hour) * self.capacity
        self.last_change_hour = now
        self.capacity += delta

    def available_hours(self, horizon_hours: Decimal) -> Decimal:
        return self.capacity_hours + (horizon_hours - self.last_change_hour) * self.capacity


@dataclass
class RunContext:
    env: simpy.Environment
    state: SimulationState
    config: ProcessConfiguration
    horizon_hours: Decimal
    pools: dict[str, CapacityPool]
    inventory: dict[str, simpy.Container]
    snapshot_time: datetime
    trace: list[SimulationTraceEvent] = field(default_factory=list)
    impacts: list[AccountingImpact] = field(default_factory=list)
    busy_hours: dict[str, Decimal] = field(default_factory=dict)
    order_waiting_hours: list[Decimal] = field(default_factory=list)
    active_sales_orders: int = 0
    fulfilled_sales_orders: int = 0
    stockout_count: int = 0
    revenue: Decimal = Decimal("0")
    cogs: Decimal = Decimal("0")
    cash: Decimal = Decimal("0")
    receivables: Decimal = Decimal("0")
    payables: Decimal = Decimal("0")
    minimum_cash: Decimal = Decimal("0")

    def record(
        self,
        event_type: str,
        order: SimulatedOrder,
        process_id: str,
        **details: object,
    ) -> None:
        self.trace.append(
            SimulationTraceEvent(
                sequence=len(self.trace) + 1,
                simulated_hour=_number(_decimal(self.env.now)),
                event_type=event_type,
                object_id=order.object_id,
                process_id=process_id,
                details={key: str(value) for key, value in sorted(details.items())},
            )
        )

    def record_system(
        self, event_type: str, object_id: str, process_id: str, **details: object
    ) -> None:
        self.trace.append(
            SimulationTraceEvent(
                sequence=len(self.trace) + 1,
                simulated_hour=_number(_decimal(self.env.now)),
                event_type=event_type,
                object_id=object_id,
                process_id=process_id,
                details={key: str(value) for key, value in sorted(details.items())},
            )
        )

    def journal(
        self,
        event_type: str,
        order: SimulatedOrder,
        entries: tuple[tuple[str, Decimal, Decimal], ...],
    ) -> None:
        lines = tuple(
            AccountingLine(account=account, debit=_money(debit), credit=_money(credit))
            for account, debit, credit in entries
        )
        debits = sum((line.debit for line in lines), Decimal("0"))
        credits = sum((line.credit for line in lines), Decimal("0"))
        if debits != credits:
            raise RuntimeError(f"unbalanced accounting impact for {event_type}")
        self.impacts.append(
            AccountingImpact(
                event_type=event_type,
                object_id=order.object_id,
                simulated_hour=_number(_decimal(self.env.now)),
                lines=lines,
            )
        )


def _use_resource(
    context: RunContext, resource_type: str, node_id: str
) -> Generator[simpy.Event, None, None]:
    duration = context.config.processing_hours[node_id]
    pool = context.pools[resource_type]
    yield pool.acquire()
    yield context.env.timeout(float(duration))
    yield pool.release()
    context.busy_hours[node_id] = context.busy_hours.get(node_id, Decimal("0")) + duration


def _order_to_cash(
    context: RunContext, order: SimulatedOrder, *, arrival_hour: Decimal = Decimal("0")
) -> Generator[simpy.Event, None, None]:
    if arrival_hour > _decimal(context.env.now):
        yield context.env.timeout(float(arrival_hour - _decimal(context.env.now)))
    started = _decimal(context.env.now)
    context.active_sales_orders += 1
    context.record("order_entered_simulation", order, "order_to_cash", sku=order.sku)
    if order.current_node_id == "order_received":
        yield context.env.process(_use_resource(context, "sales_staff", "credit_review"))
        context.record("order_approved", order, "order_to_cash")

    inventory = context.inventory[order.sku]
    if _decimal(inventory.level) < order.quantity:
        context.stockout_count += 1
        context.record(
            "stockout_wait_started",
            order,
            "order_to_cash",
            required=order.quantity,
            available=inventory.level,
        )
    yield inventory.get(float(order.quantity))
    context.record("inventory_allocated", order, "order_to_cash", quantity=order.quantity)
    yield context.env.process(_use_resource(context, "warehouse_staff", "pick_and_pack"))
    cost = _money(context.state.item_costs[order.sku] * order.quantity)
    context.cogs += cost
    context.journal(
        "goods_shipped",
        order,
        (("COST_OF_GOODS_SOLD", cost, Decimal("0")), ("INVENTORY", Decimal("0"), cost)),
    )
    context.record("goods_shipped", order, "order_to_cash", cost=cost)
    yield context.env.process(_use_resource(context, "finance_staff", "invoiced"))
    amount = _money(order.amount)
    context.revenue += amount
    context.receivables += amount
    context.journal(
        "customer_invoiced",
        order,
        (("ACCOUNTS_RECEIVABLE", amount, Decimal("0")), ("REVENUE", Decimal("0"), amount)),
    )
    context.fulfilled_sales_orders += 1
    context.order_waiting_hours.append(_decimal(context.env.now) - started)
    context.record("customer_invoiced", order, "order_to_cash", amount=amount)
    yield context.env.timeout(float(context.config.payment_delay_hours))
    context.receivables -= amount
    context.cash += amount
    context.minimum_cash = min(context.minimum_cash, context.cash)
    context.journal(
        "customer_payment_received",
        order,
        (("CASH", amount, Decimal("0")), ("ACCOUNTS_RECEIVABLE", Decimal("0"), amount)),
    )
    context.record("customer_payment_received", order, "order_to_cash", amount=amount)


def _delivery_adjustments(
    orders: list[SimulatedOrder], events: list[ScenarioEvent]
) -> dict[str, Decimal]:
    open_orders = sorted(
        (
            order
            for order in orders
            if order.object_type == "purchase_order" and order.status == "open"
        ),
        key=lambda order: (order.due_at, order.object_number),
    )
    adjustments: dict[str, Decimal] = {}
    for event in events:
        if event.event_type != "supplier_delivery_delayed":
            continue
        target = event.payload.get("purchase_order_number")
        selected = next(
            (order for order in open_orders if target is None or order.object_number == target),
            None,
        )
        if selected is None:
            raise ValueError("supplier delivery event does not identify an open purchase order")
        adjustments[selected.object_id] = adjustments.get(selected.object_id, Decimal("0")) + (
            _decimal(event.payload["days_delta"]) * Decimal("24")
        )
    return adjustments


def _procure_to_pay(
    context: RunContext, order: SimulatedOrder, delivery_adjustment: Decimal
) -> Generator[simpy.Event, None, None]:
    context.record("purchase_order_entered_simulation", order, "procure_to_pay", sku=order.sku)
    if delivery_adjustment:
        context.record(
            "supplier_delivery_adjusted",
            order,
            "procure_to_pay",
            hours_delta=delivery_adjustment,
        )
    yield context.env.process(_use_resource(context, "purchasing_staff", "purchase_order_placed"))
    due_hours = max(
        Decimal("0"),
        _decimal((order.due_at - context.snapshot_time).total_seconds()) / Decimal("3600")
        + delivery_adjustment,
    )
    remaining = due_hours - _decimal(context.env.now)
    if remaining > 0:
        yield context.env.timeout(float(remaining))
    yield context.env.process(_use_resource(context, "warehouse_staff", "goods_received"))
    yield context.inventory[order.sku].put(float(order.quantity))
    amount = _money(order.amount)
    context.journal(
        "goods_received",
        order,
        (
            ("INVENTORY", amount, Decimal("0")),
            ("GOODS_RECEIVED_NOT_INVOICED", Decimal("0"), amount),
        ),
    )
    context.record("goods_received", order, "procure_to_pay", quantity=order.quantity)
    yield context.env.process(_use_resource(context, "finance_staff", "supplier_invoice_recorded"))
    context.payables += amount
    context.journal(
        "supplier_invoice_recorded",
        order,
        (
            ("GOODS_RECEIVED_NOT_INVOICED", amount, Decimal("0")),
            ("ACCOUNTS_PAYABLE", Decimal("0"), amount),
        ),
    )
    context.record("supplier_invoice_recorded", order, "procure_to_pay", amount=amount)
    yield context.env.timeout(float(context.config.supplier_terms_hours))
    context.payables -= amount
    context.cash -= amount
    context.minimum_cash = min(context.minimum_cash, context.cash)
    context.journal(
        "supplier_paid",
        order,
        (("ACCOUNTS_PAYABLE", amount, Decimal("0")), ("CASH", Decimal("0"), amount)),
    )
    context.record("supplier_paid", order, "procure_to_pay", amount=amount)


def _apply_capacity_change(
    context: RunContext, event: ScenarioEvent
) -> Generator[simpy.Event, None, None]:
    yield context.env.timeout(float(event.effective_day * Decimal("24")))
    resource_type = str(event.payload["resource_type"])
    delta = int(event.payload["capacity_delta"])
    if resource_type not in context.pools:
        raise ValueError(f"unknown resource type: {resource_type}")
    if context.pools[resource_type].capacity + delta < 1:
        raise ValueError("resource capacity cannot fall below one")
    yield context.env.process(context.pools[resource_type].change(delta))
    context.record_system(
        "resource_capacity_changed",
        resource_type,
        "resource_management",
        capacity_delta=delta,
        new_capacity=context.pools[resource_type].capacity,
    )


def _scenario_order(
    event: ScenarioEvent,
    sequence: int,
    state: SimulationState,
    snapshot_time: datetime,
) -> SimulatedOrder:
    sku = str(event.payload["sku"])
    if sku not in state.item_prices:
        raise ValueError(f"unknown scenario SKU: {sku}")
    quantity = _decimal(event.payload["quantity"])
    if quantity <= 0:
        raise ValueError("scenario order quantity must be greater than zero")
    amount = _money(quantity * _decimal(event.payload.get("unit_price", state.item_prices[sku])))
    order_number = str(event.payload.get("order_number", f"SCENARIO-SO-{sequence:04d}"))
    return SimulatedOrder(
        object_id=str(uuid.uuid5(RUN_NAMESPACE, order_number)),
        object_number=order_number,
        object_type="sales_order",
        current_node_id="order_received",
        status="open",
        amount=amount,
        quantity=quantity,
        priority=int(event.payload.get("priority", 0)),
        sku=sku,
        due_at=snapshot_time,
    )


def _result_metrics(context: RunContext) -> SimulationMetrics:
    waiting = (
        sum(context.order_waiting_hours, Decimal("0")) / len(context.order_waiting_hours)
        if context.order_waiting_hours
        else Decimal("0")
    )
    fulfilment = (
        Decimal(context.fulfilled_sales_orders) / context.active_sales_orders
        if context.active_sales_orders
        else Decimal("1")
    )
    utilization: dict[str, Decimal] = {}
    for node, hours in sorted(context.busy_hours.items()):
        resource_type = {
            "credit_review": "sales_staff",
            "pick_and_pack": "warehouse_staff",
            "invoiced": "finance_staff",
            "purchase_order_placed": "purchasing_staff",
            "goods_received": "warehouse_staff",
            "supplier_invoice_recorded": "finance_staff",
        }[node]
        denominator = context.pools[resource_type].available_hours(context.horizon_hours)
        utilization[node] = _number(min(Decimal("1"), hours / denominator))
    ending_quantity = sum(
        (_decimal(container.level) for container in context.inventory.values()), Decimal("0")
    )
    ending_value = sum(
        (
            _decimal(container.level) * context.state.item_costs[sku]
            for sku, container in context.inventory.items()
        ),
        Decimal("0"),
    )
    return SimulationMetrics(
        ending_backlog=context.active_sales_orders - context.fulfilled_sales_orders,
        average_waiting_hours=_number(waiting),
        fulfilment_rate=_number(fulfilment),
        resource_utilization=utilization,
        stockout_count=context.stockout_count,
        ending_inventory_quantity=_number(ending_quantity),
        ending_inventory_value=_money(ending_value),
        revenue=_money(context.revenue),
        cost_of_goods_sold=_money(context.cogs),
        gross_profit=_money(context.revenue - context.cogs),
        accounts_receivable=_money(context.receivables),
        accounts_payable=_money(context.payables),
        ending_cash=_money(context.cash),
        minimum_cash=_money(context.minimum_cash),
    )


def run_simulation(
    snapshot: SnapshotBundle,
    scenario_events: list[ScenarioEvent],
    horizon_days: int,
    random_seed: int,
    *,
    config_dir: Path | None = None,
) -> SimulationRunResult:
    """Run a deterministic simulation using only a detached snapshot bundle."""
    if horizon_days <= 0:
        raise ValueError("horizon_days must be greater than zero")
    state = snapshot_to_state(snapshot)
    config = _load_process_configuration(config_dir)
    events = sorted(
        scenario_events,
        key=lambda item: (item.effective_day, item.event_type, _canonical_json(item.payload)),
    )
    scenario_hash = _hash([event.model_dump(mode="json") for event in events])
    env = simpy.Environment()
    pools = {
        name: CapacityPool(env, capacity) for name, capacity in state.resource_capacities.items()
    }
    inventory = {
        sku: simpy.Container(
            env,
            capacity=10**12,
            init=float(state.inventory.get(sku, Decimal("0"))),
        )
        for sku in state.item_costs
    }
    horizon_hours = Decimal(horizon_days) * Decimal("24")
    context = RunContext(
        env=env,
        state=state,
        config=config,
        horizon_hours=horizon_hours,
        pools=pools,
        inventory=inventory,
        snapshot_time=snapshot.manifest.as_of_time,
        cash=state.balances["CASH"],
        receivables=state.balances["ACCOUNTS_RECEIVABLE"],
        payables=state.balances["ACCOUNTS_PAYABLE"],
        minimum_cash=state.balances["CASH"],
    )
    adjustments = _delivery_adjustments(state.orders, events)
    for order in state.orders:
        if order.object_type == "sales_order" and order.status in {"open", "backlog"}:
            env.process(_order_to_cash(context, order))
        elif order.object_type == "purchase_order" and order.status == "open":
            adjustment = adjustments.get(order.object_id, Decimal("0"))
            env.process(_procure_to_pay(context, order, adjustment))
    scenario_sequence = 0
    for event in events:
        if event.event_type == "resource_capacity_changed":
            env.process(_apply_capacity_change(context, event))
        elif event.event_type == "order_arrival":
            scenario_sequence += 1
            order = _scenario_order(
                event,
                scenario_sequence,
                state,
                snapshot.manifest.as_of_time,
            )
            arrival_hour = event.effective_day * Decimal("24")
            env.process(_order_to_cash(context, order, arrival_hour=arrival_hour))
    env.run(until=float(horizon_hours))
    metrics = _result_metrics(context)
    deterministic = {
        "snapshot_hash": snapshot.manifest.content_hash,
        "process_definition_version": config.version_label,
        "process_definition_hash": config.content_hash,
        "scenario_event_hash": scenario_hash,
        "horizon_days": horizon_days,
        "random_seed": random_seed,
        "summary_metrics": metrics.model_dump(mode="json"),
        "event_trace": [item.model_dump(mode="json") for item in context.trace],
        "accounting_impacts": [item.model_dump(mode="json") for item in context.impacts],
    }
    result_hash = _hash(deterministic)
    run_id = str(uuid.uuid5(RUN_NAMESPACE, result_hash))
    return SimulationRunResult(
        simulation_run_id=run_id,
        snapshot_hash=snapshot.manifest.content_hash,
        process_definition_version=config.version_label,
        process_definition_hash=config.content_hash,
        scenario_event_hash=scenario_hash,
        horizon_days=horizon_days,
        random_seed=random_seed,
        result_hash=result_hash,
        summary_metrics=metrics,
        event_trace=tuple(context.trace),
        accounting_impacts=tuple(context.impacts),
    )
