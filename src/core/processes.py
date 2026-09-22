from __future__ import annotations

from collections import Counter, deque
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from core.models import CanonicalModel, ProcessId, ResourceType

OperationalMetric = Literal[
    "object_count",
    "total_quantity",
    "total_monetary_value",
    "backlog_count",
    "average_waiting_time",
    "available_capacity",
    "resource_utilization",
    "exception_count",
    "inventory_quantity",
    "accounts_receivable",
    "accounts_payable",
    "cash",
]
AccountName = Literal[
    "cash",
    "accounts_receivable",
    "accounts_payable",
    "inventory",
    "revenue",
    "cost_of_goods_sold",
    "goods_received_not_invoiced",
]
AmountBasis = Literal["order_amount", "inventory_cost", "supplier_invoice_amount", "payment_amount"]


class ObjectBindingDefinition(CanonicalModel):
    """Bind an activity alias to its subject or a related state object."""

    alias: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: Literal["subject", "related"]
    match_field: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    value_from: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def related_binding_has_join(self) -> ObjectBindingDefinition:
        if self.source == "related" and (self.match_field is None or self.value_from is None):
            raise ValueError("related input requires match_field and value_from")
        if self.source == "subject" and (
            self.match_field is not None or self.value_from is not None
        ):
            raise ValueError("subject input cannot define a related-object join")
        return self


class DurationDefinition(CanonicalModel):
    kind: Literal["fixed", "parameter", "until_field"]
    hours: Decimal | None = Field(default=None, ge=0)
    parameter: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    field: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def exactly_one_duration_source(self) -> DurationDefinition:
        expected = {
            "fixed": self.hours is not None and self.parameter is None and self.field is None,
            "parameter": self.hours is None and self.parameter is not None and self.field is None,
            "until_field": self.hours is None and self.parameter is None and self.field is not None,
        }[self.kind]
        if not expected:
            raise ValueError(f"duration kind {self.kind} has incompatible fields")
        return self


class ConditionDefinition(CanonicalModel):
    left: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    operator: Literal["equals", "not_equals", "greater_than_or_equal", "in"]
    value: str | int | Decimal | bool | tuple[str, ...] | None = None
    value_from: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def has_one_right_hand_side(self) -> ConditionDefinition:
        if (self.value is None) == (self.value_from is None):
            raise ValueError("condition requires exactly one of value or value_from")
        return self


class StateEffectDefinition(CanonicalModel):
    operation: Literal["set", "increase", "decrease"]
    target: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    value: str | int | Decimal | bool | None = None
    value_from: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    wait_if_insufficient: bool = False

    @model_validator(mode="after")
    def has_one_value_source(self) -> StateEffectDefinition:
        if (self.value is None) == (self.value_from is None):
            raise ValueError("state effect requires exactly one of value or value_from")
        if self.wait_if_insufficient and self.operation != "decrease":
            raise ValueError("wait_if_insufficient is valid only for decrease")
        return self


class ExecutionInputDefinition(CanonicalModel):
    """Typed value supplied by an observed transaction or a simulation trigger."""

    type: Literal["string", "decimal", "integer", "boolean", "datetime"]
    required: bool = True


class EventOutputDefinition(CanonicalModel):
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    references: tuple[str, ...] = ()


class TransitionDefinition(CanonicalModel):
    target: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    conditions: tuple[ConditionDefinition, ...] = ()


class CycleMetricDefinition(CanonicalModel):
    completion_activity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


class FinancialEffectDefinition(CanonicalModel):
    event: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    debit_account: AccountName
    credit_account: AccountName
    amount_basis: AmountBasis

    @model_validator(mode="after")
    def accounts_are_distinct(self) -> FinancialEffectDefinition:
        if self.debit_account == self.credit_account:
            raise ValueError("debit_account and credit_account must differ")
        return self


class ProcessNodeDefinition(CanonicalModel):
    """One executable activity in a declarative object-centric flow."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["activity"] = "activity"
    semantic_status: Literal["confirmed", "dummy"] = "confirmed"
    label: str = Field(min_length=1)
    inputs: tuple[ObjectBindingDefinition, ...] = Field(min_length=1)
    execution_inputs: dict[str, ExecutionInputDefinition] = Field(default_factory=dict)
    enabled_when: tuple[ConditionDefinition, ...] = ()
    resource: ResourceType | None = None
    duration: DurationDefinition
    operations: tuple[StateEffectDefinition, ...] = ()
    on_start: EventOutputDefinition | None = None
    on_complete: EventOutputDefinition
    operational_metrics: tuple[OperationalMetric, ...] = ()
    financial_effects: tuple[FinancialEffectDefinition, ...] = ()
    next: tuple[TransitionDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_activity_contract(self) -> ProcessNodeDefinition:
        aliases = [item.alias for item in self.inputs]
        if len(aliases) != len(set(aliases)):
            raise ValueError(f"activity {self.id} has duplicate input aliases")
        if aliases.count("subject") != 1:
            raise ValueError(f"activity {self.id} requires exactly one subject input")
        for path in [
            *(condition.left for condition in self.enabled_when),
            *(condition.value_from for condition in self.enabled_when if condition.value_from),
            *(effect.target for effect in self.operations),
            *(effect.value_from for effect in self.operations if effect.value_from),
        ]:
            path_alias = path.split(".", 1)[0]
            if path_alias == "execution":
                field_name = path.split(".", 1)[1]
                if field_name not in self.execution_inputs:
                    raise ValueError(
                        f"activity {self.id} references unknown execution input: {field_name}"
                    )
                continue
            if path_alias not in aliases:
                raise ValueError(f"activity {self.id} references unknown input alias: {path}")
        event_references = (*self.on_complete.references,)
        if self.on_start is not None:
            event_references += self.on_start.references
        unknown_references = sorted(set(event_references) - set(aliases))
        if unknown_references:
            raise ValueError(
                f"activity {self.id} event references unknown aliases: {unknown_references}"
            )
        if len(self.operational_metrics) != len(set(self.operational_metrics)):
            raise ValueError("operational metrics must be unique")
        effect_events = [effect.event for effect in self.financial_effects]
        if any(event != self.on_complete.event_type for event in effect_events):
            raise ValueError("financial effects must use the activity completion event")
        if len(effect_events) != len(set(effect_events)):
            raise ValueError("financial-effect events must be unique within an activity")
        return self


class ProcessDefinition(CanonicalModel):
    schema_version: Literal[2]
    process_id: ProcessId
    version: int = Field(gt=0)
    label: str = Field(min_length=1)
    primary_object_type: Literal["sales_order", "purchase_order"]
    active_statuses: tuple[str, ...] = Field(min_length=1)
    initial_activity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    terminal_activity_ids: tuple[str, ...] = Field(min_length=1)
    activities: tuple[ProcessNodeDefinition, ...] = Field(min_length=1)
    cycle_metrics: CycleMetricDefinition | None = None
    parameters: dict[str, Decimal] = Field(default_factory=dict)

    @property
    def nodes(self) -> tuple[ProcessNodeDefinition, ...]:
        """Compatibility alias while downstream UI moves from nodes to activities."""
        return self.activities

    @property
    def initial_node_id(self) -> str:
        return self.initial_activity_id

    @property
    def terminal_node_ids(self) -> tuple[str, ...]:
        return self.terminal_activity_ids

    @model_validator(mode="after")
    def validate_graph(self) -> ProcessDefinition:
        expected_object = {
            "order_to_cash": "sales_order",
            "procure_to_pay": "purchase_order",
        }[self.process_id]
        if self.primary_object_type != expected_object:
            raise ValueError(f"{self.process_id} requires primary_object_type {expected_object}")
        activity_ids = [activity.id for activity in self.activities]
        duplicates = sorted(name for name, count in Counter(activity_ids).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate activity IDs: {duplicates}")
        activity_id_set = set(activity_ids)
        if self.initial_activity_id not in activity_id_set:
            raise ValueError(f"initial activity does not exist: {self.initial_activity_id}")
        unknown_terminals = sorted(set(self.terminal_activity_ids) - activity_id_set)
        if unknown_terminals:
            raise ValueError(f"terminal activities do not exist: {unknown_terminals}")

        adjacency: dict[str, tuple[str, ...]] = {}
        targets: list[str] = []
        for activity in self.activities:
            activity_targets = tuple(transition.target for transition in activity.next)
            if len(activity_targets) != len(set(activity_targets)):
                raise ValueError(f"activity {activity.id} has duplicate transition targets")
            if activity.id in activity_targets:
                raise ValueError(f"activity {activity.id} cannot transition to itself")
            if activity.id in self.terminal_activity_ids and activity_targets:
                raise ValueError(f"terminal activity {activity.id} cannot have transitions")
            if activity.id not in self.terminal_activity_ids and not activity_targets:
                raise ValueError(f"non-terminal activity {activity.id} must have a transition")
            adjacency[activity.id] = activity_targets
            targets.extend(activity_targets)
        unknown_targets = sorted(set(targets) - activity_id_set)
        if unknown_targets:
            raise ValueError(f"transition targets do not exist: {unknown_targets}")

        reachable = {self.initial_activity_id}
        pending = deque([self.initial_activity_id])
        while pending:
            for target in adjacency[pending.popleft()]:
                if target not in reachable:
                    reachable.add(target)
                    pending.append(target)
        unreachable = sorted(activity_id_set - reachable)
        if unreachable:
            raise ValueError(f"activities are unreachable from initial activity: {unreachable}")
        if not reachable.intersection(self.terminal_activity_ids):
            raise ValueError("no terminal activity is reachable from the initial activity")
        if (
            self.cycle_metrics is not None
            and self.cycle_metrics.completion_activity_id not in activity_id_set
        ):
            raise ValueError("cycle metric completion activity does not exist")
        return self

    def activity(self, activity_id: str) -> ProcessNodeDefinition:
        for activity in self.activities:
            if activity.id == activity_id:
                return activity
        raise KeyError(f"unknown activity for {self.process_id}: {activity_id}")

    def node(self, node_id: str) -> ProcessNodeDefinition:
        return self.activity(node_id)

    def transition(self, source: str, target: str) -> TransitionDefinition:
        for transition in self.activity(source).next:
            if transition.target == target:
                return transition
        raise ValueError(f"transition is not permitted for {self.process_id}: {source} -> {target}")
