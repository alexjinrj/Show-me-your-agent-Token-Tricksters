from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, cast

import simpy

from business_coordinator.domain.models import (
    AccountingImpact,
    AccountingLine,
    ProcessId,
    ScenarioEvent,
    SimulationCheckpoint,
    SimulationMetrics,
    SimulationRunResult,
    SimulationTraceEvent,
    SnapshotBundle,
    StateRecord,
)
from business_coordinator.domain.processes import (
    ConditionDefinition,
    DurationDefinition,
    EventOutputDefinition,
    FinancialEffectDefinition,
    ProcessDefinition,
    ProcessNodeDefinition,
    StateEffectDefinition,
)
from business_coordinator.simulation.process_runtime import (
    RuntimeProcessCatalog,
    load_runtime_process_catalog,
)
from business_coordinator.simulation.state import SimulationState, snapshot_to_state

MONEY = Decimal("0.01")
NUMBER = Decimal("0.0001")
RUN_NAMESPACE = uuid.UUID("e42e0ab5-d3a3-4d27-a540-4d66d2062d5a")
ASSET_OR_EXPENSE_ACCOUNTS = {
    "CASH",
    "ACCOUNTS_RECEIVABLE",
    "INVENTORY",
    "COST_OF_GOODS_SOLD",
}
ACCOUNT_CODES = {
    "cash": "CASH",
    "accounts_receivable": "ACCOUNTS_RECEIVABLE",
    "accounts_payable": "ACCOUNTS_PAYABLE",
    "inventory": "INVENTORY",
    "revenue": "REVENUE",
    "cost_of_goods_sold": "COST_OF_GOODS_SOLD",
    "goods_received_not_invoiced": "GOODS_RECEIVED_NOT_INVOICED",
}


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


def _process_id(value: str) -> ProcessId:
    if value not in {"order_to_cash", "procure_to_pay"}:
        raise ValueError(f"unknown process: {value}")
    return cast(ProcessId, value)


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
    config: RuntimeProcessCatalog
    horizon_hours: Decimal
    pools: dict[str, CapacityPool]
    availability: dict[str, simpy.Container]
    snapshot_time: datetime
    trace: list[SimulationTraceEvent] = field(default_factory=list)
    impacts: list[AccountingImpact] = field(default_factory=list)
    checkpoints: list[SimulationCheckpoint] = field(default_factory=list)
    busy_hours: dict[str, Decimal] = field(default_factory=dict)
    cycle_started: dict[str, Decimal] = field(default_factory=dict)
    cycle_elapsed: list[Decimal] = field(default_factory=list)
    cycle_completed: set[str] = field(default_factory=set)
    stockout_count: int = 0
    revenue: Decimal = Decimal("0")
    cogs: Decimal = Decimal("0")
    minimum_cash: Decimal = Decimal("0")

    @property
    def now(self) -> Decimal:
        return _number(_decimal(self.env.now))

    def record_event(
        self,
        output: EventOutputDefinition,
        process_id: str,
        activity_id: str,
        bindings: Mapping[str, StateRecord],
        *,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        subject = bindings["subject"]
        references = tuple(bindings[alias].record_id for alias in output.references)
        details: dict[str, object] = {
            key: subject.data[key]
            for key in ("sku", "quantity", "amount", "object_number")
            if key in subject.data
        }
        details.update(extra or {})
        self.state.append_event(
            output.event_type,
            references,
            self.now,
            data={"process_id": process_id, "activity_id": activity_id, **details},
        )
        self.trace.append(
            SimulationTraceEvent(
                sequence=len(self.trace) + 1,
                simulated_hour=self.now,
                event_type=output.event_type,
                object_id=subject.record_id,
                process_id=process_id,
                node_id=activity_id,
                details={key: str(value) for key, value in sorted(details.items())},
            )
        )

    def record_system(
        self, event_type: str, object_id: str, process_id: str, **details: object
    ) -> None:
        self.state.append_event(
            event_type,
            (object_id,),
            self.now,
            data={"process_id": process_id, **details},
        )
        self.trace.append(
            SimulationTraceEvent(
                sequence=len(self.trace) + 1,
                simulated_hour=self.now,
                event_type=event_type,
                object_id=object_id,
                process_id=process_id,
                details={key: str(value) for key, value in sorted(details.items())},
            )
        )

    def journal(
        self,
        event_type: str,
        object_id: str,
        debit_account: str,
        credit_account: str,
        amount: Decimal,
    ) -> None:
        amount = _money(amount)
        lines = (
            AccountingLine(account=debit_account, debit=amount),
            AccountingLine(account=credit_account, credit=amount),
        )
        self.impacts.append(
            AccountingImpact(
                event_type=event_type,
                object_id=object_id,
                simulated_hour=self.now,
                lines=lines,
            )
        )
        self._post_balance(debit_account, amount, debit=True)
        self._post_balance(credit_account, amount, debit=False)
        if credit_account == "REVENUE":
            self.revenue += amount
        if debit_account == "COST_OF_GOODS_SOLD":
            self.cogs += amount
        self.minimum_cash = min(self.minimum_cash, self.state.balance("CASH"))

    def _post_balance(self, account_code: str, amount: Decimal, *, debit: bool) -> None:
        try:
            balance = self.state.related("balance", "account_code", account_code)
        except ValueError:
            balance = self.state.create_record(
                StateRecord(
                    record_id=f"balance:{account_code}",
                    record_kind="object",
                    record_type="balance",
                    project_id=self.state.project_id,
                    data={
                        "account_code": account_code,
                        "amount": Decimal("0"),
                        "currency": "SGD",
                    },
                )
            )
        current = _decimal(balance.data["amount"])
        normal_debit = account_code in ASSET_OR_EXPENSE_ACCOUNTS
        delta = amount if debit == normal_debit else -amount
        self.state.update(balance.record_id, "amount", _money(current + delta))


def _path_value(bindings: Mapping[str, StateRecord], path: str) -> Any:
    alias, field_name = path.split(".", 1)
    try:
        return bindings[alias].data[field_name]
    except KeyError as exc:
        raise ValueError(f"state path does not exist: {path}") from exc


def _right_value(
    bindings: Mapping[str, StateRecord], value: object | None, value_from: str | None
) -> object:
    return _path_value(bindings, value_from) if value_from is not None else value


def _condition_matches(condition: ConditionDefinition, bindings: Mapping[str, StateRecord]) -> bool:
    left = _path_value(bindings, condition.left)
    right = _right_value(bindings, condition.value, condition.value_from)
    if condition.operator == "equals":
        return bool(left == right)
    if condition.operator == "not_equals":
        return bool(left != right)
    if condition.operator == "greater_than_or_equal":
        return _decimal(left) >= _decimal(right)
    if condition.operator == "in":
        return left in cast(tuple[object, ...], right)
    raise ValueError(f"unsupported condition operator: {condition.operator}")


def _bind_inputs(
    state: SimulationState, activity: ProcessNodeDefinition, subject_id: str
) -> dict[str, StateRecord]:
    subject = state.record(subject_id)
    bindings: dict[str, StateRecord] = {}
    for binding in activity.inputs:
        if binding.source == "subject":
            if subject.record_type != binding.object_type:
                raise ValueError(
                    f"{activity.id} expects {binding.object_type}; got {subject.record_type}"
                )
            bindings[binding.alias] = subject
            continue
        if binding.match_field is None or binding.value_from is None:
            raise ValueError(f"related input is incomplete: {activity.id}.{binding.alias}")
        bindings[binding.alias] = state.related(
            binding.object_type,
            binding.match_field,
            _path_value({"subject": subject}, binding.value_from),
        )
    return bindings


def _effect_value(effect: StateEffectDefinition, bindings: Mapping[str, StateRecord]) -> object:
    return _right_value(bindings, effect.value, effect.value_from)


def _apply_effect(
    context: RunContext,
    effect: StateEffectDefinition,
    bindings: Mapping[str, StateRecord],
) -> Generator[simpy.Event, None, None]:
    alias, field_name = effect.target.split(".", 1)
    record = context.state.record(bindings[alias].record_id)
    value = _effect_value(effect, bindings)
    current = record.data.get(field_name)
    container = (
        context.availability.get(record.record_id) if field_name == "quantity_available" else None
    )
    if effect.operation == "set":
        updated: object = value
    elif effect.operation == "increase":
        updated = _decimal(current or 0) + _decimal(value)
        if container is not None:
            yield container.put(float(_decimal(value)))
    else:
        amount = _decimal(value)
        if container is not None:
            if not effect.wait_if_insufficient and _decimal(container.level) < amount:
                raise ValueError(f"insufficient value for {effect.target}")
            yield container.get(float(amount))
        updated = _decimal(current or 0) - amount
    context.state.update(record.record_id, field_name, updated)


def _reserve_waiting_effects(
    context: RunContext,
    activity: ProcessNodeDefinition,
    bindings: Mapping[str, StateRecord],
) -> Generator[simpy.Event, None, None]:
    for effect in activity.operations:
        if not effect.wait_if_insufficient:
            continue
        alias, field_name = effect.target.split(".", 1)
        record = bindings[alias]
        container = context.availability.get(record.record_id)
        amount = _decimal(_effect_value(effect, bindings))
        if field_name != "quantity_available" or container is None:
            raise ValueError("wait_if_insufficient requires an inventory availability target")
        if _decimal(container.level) < amount:
            context.stockout_count += 1
            context.record_system(
                "stockout_wait_started",
                bindings["subject"].record_id,
                str(bindings["subject"].data["process_id"]),
                activity_id=activity.id,
                required=amount,
                available=container.level,
            )
        yield container.get(float(amount))
        context.state.update(
            record.record_id,
            field_name,
            _decimal(record.data[field_name]) - amount,
        )


def _duration_wait(
    context: RunContext,
    process_id: ProcessId,
    duration: DurationDefinition,
    bindings: Mapping[str, StateRecord],
) -> Generator[simpy.Event, None, None]:
    if duration.kind == "fixed":
        yield context.env.timeout(float(cast(Decimal, duration.hours)))
        return
    if duration.kind == "parameter":
        hours = context.config.parameter(process_id, cast(str, duration.parameter))
        yield context.env.timeout(float(hours))
        return
    target = _path_value(bindings, cast(str, duration.field))
    if isinstance(target, str):
        target = datetime.fromisoformat(target)
    if not isinstance(target, datetime):
        raise ValueError(f"until_field does not contain a datetime: {duration.field}")
    while True:
        subject = context.state.record(bindings["subject"].record_id)
        adjustment = _decimal(subject.data.get("delivery_adjustment_hours", 0))
        target_hour = (
            _decimal((target - context.snapshot_time).total_seconds()) / Decimal("3600")
            + adjustment
        )
        remaining = target_hour - _decimal(context.env.now)
        # SimPy uses floats internally. Treat sub-microhour residue as reached so
        # converting Decimal deadlines cannot schedule an endless zero-time loop.
        if remaining <= Decimal("0.000001"):
            return
        yield context.env.timeout(float(min(remaining, Decimal("24"))))


def _financial_amount(
    context: RunContext, effect: FinancialEffectDefinition, subject: StateRecord
) -> Decimal:
    if effect.amount_basis == "inventory_cost":
        return _money(
            _decimal(subject.data["quantity"]) * context.state.item_costs[str(subject.data["sku"])]
        )
    return _money(_decimal(subject.data["amount"]))


def _apply_financial_effects(
    context: RunContext,
    activity: ProcessNodeDefinition,
    subject: StateRecord,
) -> None:
    for effect in activity.financial_effects:
        context.journal(
            effect.event,
            subject.record_id,
            ACCOUNT_CODES[effect.debit_account],
            ACCOUNT_CODES[effect.credit_account],
            _financial_amount(context, effect, subject),
        )


def _next_activity(
    activity: ProcessNodeDefinition, bindings: Mapping[str, StateRecord]
) -> str | None:
    matches = [
        transition.target
        for transition in activity.next
        if all(_condition_matches(condition, bindings) for condition in transition.conditions)
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple transitions matched after activity {activity.id}")
    if not matches:
        if activity.next:
            raise ValueError(f"no transition matched after activity {activity.id}")
        return None
    return matches[0]


def _run_workflow(
    context: RunContext,
    definition: ProcessDefinition,
    subject_id: str,
    initial_activity_id: str,
) -> Generator[simpy.Event, None, None]:
    if definition.cycle_metrics is not None:
        context.cycle_started[subject_id] = context.now
    activity_id: str | None = initial_activity_id
    while activity_id is not None:
        activity = definition.activity(activity_id)
        bindings = _bind_inputs(context.state, activity, subject_id)
        if not all(_condition_matches(condition, bindings) for condition in activity.enabled_when):
            raise ValueError(f"activity is not enabled: {definition.process_id}.{activity.id}")
        references = tuple(record.record_id for record in bindings.values())
        activity_run_id = context.state.start_activity(
            definition.process_id, activity.id, subject_id, references, context.now
        )
        yield context.env.process(_reserve_waiting_effects(context, activity, bindings))
        resource = activity.resource
        if resource is not None:
            yield context.pools[resource].acquire()
        context.state.mark_activity_running(activity_run_id, context.now)
        if activity.on_start is not None:
            context.record_event(activity.on_start, definition.process_id, activity.id, bindings)
        started = context.now
        yield context.env.process(
            _duration_wait(context, definition.process_id, activity.duration, bindings)
        )
        if resource is not None:
            yield context.pools[resource].release()
            busy_key = f"{definition.process_id}.{activity.id}"
            context.busy_hours[busy_key] = context.busy_hours.get(busy_key, Decimal("0")) + (
                context.now - started
            )
        context.record_event(activity.on_complete, definition.process_id, activity.id, bindings)
        for effect in activity.operations:
            if not effect.wait_if_insufficient:
                yield context.env.process(_apply_effect(context, effect, bindings))
        _apply_financial_effects(
            context, activity, context.state.record(bindings["subject"].record_id)
        )
        context.state.complete_activity(activity_run_id, context.now)
        if (
            definition.cycle_metrics is not None
            and definition.cycle_metrics.completion_activity_id == activity.id
            and subject_id not in context.cycle_completed
        ):
            context.cycle_completed.add(subject_id)
            context.cycle_elapsed.append(context.now - context.cycle_started[subject_id])
        refreshed = _bind_inputs(context.state, activity, subject_id)
        activity_id = _next_activity(activity, refreshed)
        context.state.update(
            subject_id,
            "current_activity_id",
            activity_id or activity.id,
        )


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


def _apply_inventory_replenishment(
    context: RunContext, event: ScenarioEvent
) -> Generator[simpy.Event, None, None]:
    yield context.env.timeout(float(event.effective_day * Decimal("24")))
    sku = str(event.payload["sku"]).strip()
    quantity = _decimal(event.payload["quantity"])
    try:
        inventory = context.state.related("inventory_position", "sku", sku)
    except ValueError as exc:
        raise ValueError(f"unknown inventory replenishment SKU: {sku}") from exc
    container = context.availability[inventory.record_id]
    if _decimal(container.level) + quantity > _decimal(container.capacity):
        raise ValueError(f"inventory capacity exceeded for SKU: {sku}")

    quantity_on_hand = _decimal(inventory.data["quantity_on_hand"]) + quantity
    quantity_available = _decimal(inventory.data["quantity_available"]) + quantity
    unit_cost = context.state.item_costs[sku]
    total_cost = _money(quantity * unit_cost)

    context.state.update(inventory.record_id, "quantity_on_hand", quantity_on_hand)
    context.state.update(inventory.record_id, "quantity_available", quantity_available)
    context.journal(
        "inventory_replenishment",
        inventory.record_id,
        "INVENTORY",
        "CASH",
        total_cost,
    )
    context.record_system(
        "inventory_replenished",
        inventory.record_id,
        "inventory_management",
        sku=sku,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
    )
    yield container.put(float(quantity))


def _apply_delivery_adjustment(
    context: RunContext, event: ScenarioEvent
) -> Generator[simpy.Event, None, None]:
    yield context.env.timeout(float(event.effective_day * Decimal("24")))
    candidates = sorted(
        (
            record
            for record in context.state.records_of_type("purchase_order")
            if record.data.get("status") not in {"received", "invoiced", "paid"}
        ),
        key=lambda record: (str(record.data.get("due_at", "")), record.record_id),
    )
    target_number = event.payload.get("purchase_order_number")
    selected = next(
        (
            record
            for record in candidates
            if target_number is None or record.data.get("object_number") == target_number
        ),
        None,
    )
    if selected is None:
        raise ValueError("supplier delivery event does not identify an open purchase order")
    key = "days_delta" if "days_delta" in event.payload else "delay_days"
    delta = _decimal(event.payload[key]) * Decimal("24")
    current = _decimal(selected.data.get("delivery_adjustment_hours", 0))
    context.state.update(selected.record_id, "delivery_adjustment_hours", current + delta)
    context.record_system(
        "supplier_delivery_adjusted",
        selected.record_id,
        str(selected.data["process_id"]),
        hours_delta=delta,
    )


def _scenario_order_record(
    event: ScenarioEvent,
    sequence: int,
    state: SimulationState,
    snapshot_time: datetime,
) -> StateRecord:
    sku = str(event.payload["sku"])
    if sku not in state.item_prices:
        raise ValueError(f"unknown scenario SKU: {sku}")
    quantity = _decimal(event.payload["quantity"])
    price = _decimal(event.payload.get("unit_price", state.item_prices[sku]))
    amount = _money(quantity * price)
    order_number = str(event.payload.get("order_number", f"SCENARIO-SO-{sequence:04d}"))
    object_id = str(uuid.uuid5(RUN_NAMESPACE, order_number))
    return StateRecord(
        record_id=object_id,
        record_kind="object",
        record_type="sales_order",
        project_id=state.project_id,
        data={
            "id": object_id,
            "object_number": order_number,
            "object_type": "sales_order",
            "process_id": "order_to_cash",
            "current_activity_id": "receive_order",
            "status": "open",
            "amount": amount,
            "quantity": quantity,
            "priority": int(event.payload.get("priority", 0)),
            "sku": sku,
            "due_at": snapshot_time,
            "entered_node_at": snapshot_time,
        },
    )


def _run_scenario_order(
    context: RunContext,
    definition: ProcessDefinition,
    event: ScenarioEvent,
    sequence: int,
) -> Generator[simpy.Event, None, None]:
    yield context.env.timeout(float(event.effective_day * Decimal("24")))
    order = context.state.create_record(
        _scenario_order_record(event, sequence, context.state, context.snapshot_time)
    )
    yield context.env.process(
        _run_workflow(context, definition, order.record_id, definition.initial_activity_id)
    )


def _checkpoint(context: RunContext, day: int) -> None:
    changes, event_ids = context.state.drain_checkpoint_changes()
    context.checkpoints.append(
        SimulationCheckpoint(
            day=day,
            simulated_hour=context.now,
            state_version=context.state.state_version,
            changes=changes,
            new_event_record_ids=event_ids,
            active_activities=context.state.active_activities(),
            state_hash=context.state.state_hash(context.now),
        )
    )


def _result_metrics(context: RunContext) -> SimulationMetrics:
    waiting = (
        sum(context.cycle_elapsed, Decimal("0")) / len(context.cycle_elapsed)
        if context.cycle_elapsed
        else Decimal("0")
    )
    active = len(context.cycle_started)
    fulfilled = len(context.cycle_completed)
    fulfilment = Decimal(fulfilled) / active if active else Decimal("1")
    utilization: dict[str, Decimal] = {}
    for key, hours in sorted(context.busy_hours.items()):
        process_id, activity_id = key.split(".", 1)
        resource = context.config.resource(_process_id(process_id), activity_id)
        if resource is None:
            continue
        denominator = context.pools[resource].available_hours(context.horizon_hours)
        utilization[key] = _number(min(Decimal("1"), hours / denominator))
    inventory = context.state.records_of_type("inventory_position")
    ending_quantity = sum(
        (_decimal(record.data["quantity_on_hand"]) for record in inventory), Decimal("0")
    )
    ending_value = sum(
        (
            _decimal(record.data["quantity_on_hand"])
            * context.state.item_costs[str(record.data["sku"])]
            for record in inventory
        ),
        Decimal("0"),
    )
    return SimulationMetrics(
        ending_backlog=active - fulfilled,
        average_waiting_hours=_number(waiting),
        fulfilment_rate=_number(fulfilment),
        resource_utilization=utilization,
        stockout_count=context.stockout_count,
        ending_inventory_quantity=_number(ending_quantity),
        ending_inventory_value=_money(ending_value),
        revenue=_money(context.revenue),
        cost_of_goods_sold=_money(context.cogs),
        gross_profit=_money(context.revenue - context.cogs),
        accounts_receivable=_money(context.state.balance("ACCOUNTS_RECEIVABLE")),
        accounts_payable=_money(context.state.balance("ACCOUNTS_PAYABLE")),
        ending_cash=_money(context.state.balance("CASH")),
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
    """Interpret validated activity YAML against a detached EnterpriseState."""
    if horizon_days <= 0:
        raise ValueError("horizon_days must be greater than zero")
    state = snapshot_to_state(snapshot)
    config = load_runtime_process_catalog(config_dir)
    events = sorted(
        scenario_events,
        key=lambda item: (item.effective_day, item.event_type, _canonical_json(item.payload)),
    )
    scenario_hash = _hash([event.model_dump(mode="json") for event in events])
    env = simpy.Environment()
    pools = {
        name: CapacityPool(env, capacity) for name, capacity in state.resource_capacities.items()
    }
    availability = {
        record.record_id: simpy.Container(
            env,
            capacity=10**12,
            init=float(_decimal(record.data["quantity_available"])),
        )
        for record in state.records_of_type("inventory_position")
    }
    horizon_hours = Decimal(horizon_days) * Decimal("24")
    context = RunContext(
        env=env,
        state=state,
        config=config,
        horizon_hours=horizon_hours,
        pools=pools,
        availability=availability,
        snapshot_time=snapshot.manifest.as_of_time,
        minimum_cash=state.balance("CASH"),
    )

    for definition in config.definitions.values():
        subjects = [
            record
            for record in state.records_of_type(definition.primary_object_type)
            if str(record.data.get("status")) in definition.active_statuses
        ]
        for subject in subjects:
            start = str(subject.data.get("current_activity_id", definition.initial_activity_id))
            env.process(_run_workflow(context, definition, subject.record_id, start))

    scenario_sequence = 0
    for event in events:
        if event.event_type == "resource_capacity_changed":
            env.process(_apply_capacity_change(context, event))
        elif event.event_type == "inventory_replenishment":
            env.process(_apply_inventory_replenishment(context, event))
        elif event.event_type == "supplier_delivery_delayed":
            env.process(_apply_delivery_adjustment(context, event))
        elif event.event_type == "order_arrival":
            scenario_sequence += 1
            env.process(
                _run_scenario_order(
                    context,
                    config.definition("order_to_cash"),
                    event,
                    scenario_sequence,
                )
            )

    _checkpoint(context, 0)
    for day in range(1, horizon_days + 1):
        target = float(Decimal(day) * Decimal("24"))
        env.run(until=target)
        while env.peek() == target:
            env.step()
        _checkpoint(context, day)

    metrics = _result_metrics(context)
    versions = {
        process_id: definition.version for process_id, definition in config.definitions.items()
    }
    deterministic = {
        "snapshot_hash": snapshot.manifest.content_hash,
        "process_definition_versions": versions,
        "process_definition_hash": config.content_hash,
        "scenario_event_hash": scenario_hash,
        "horizon_days": horizon_days,
        "random_seed": random_seed,
        "summary_metrics": metrics.model_dump(mode="json"),
        "event_trace": [item.model_dump(mode="json") for item in context.trace],
        "accounting_impacts": [item.model_dump(mode="json") for item in context.impacts],
        "checkpoints": [item.model_dump(mode="json") for item in context.checkpoints],
    }
    result_hash = _hash(deterministic)
    run_id = str(uuid.uuid5(RUN_NAMESPACE, result_hash))
    return SimulationRunResult(
        simulation_run_id=run_id,
        snapshot_hash=snapshot.manifest.content_hash,
        process_definition_version=config.version_label,
        process_definition_versions=versions,
        process_definition_hash=config.content_hash,
        scenario_event_hash=scenario_hash,
        horizon_days=horizon_days,
        random_seed=random_seed,
        result_hash=result_hash,
        summary_metrics=metrics,
        event_trace=tuple(context.trace),
        accounting_impacts=tuple(context.impacts),
        checkpoints=tuple(context.checkpoints),
    )
