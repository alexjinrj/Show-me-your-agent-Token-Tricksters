from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filter(StrictInput):
    field: str = Field(min_length=1, max_length=40)
    op: Literal["eq", "in", "gte", "lt"] = "eq"
    value: str | list[str]


Dataset = Literal[
    "orders",
    "customers",
    "cases",
    "inventory",
    "purchase_orders",
    "suppliers",
    "balances",
    "resources",
]


class Query(StrictInput):
    dataset: Dataset
    filters: list[Filter] = Field(default_factory=list, max_length=8)
    fields: list[str] = Field(default_factory=list, max_length=12)
    group_by: list[str] = Field(default_factory=list, max_length=2)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
    sort_by: str | None = Field(
        default=None, max_length=40, description="Row field, or numeric sum/row_count for groups"
    )
    sort_direction: Literal["asc", "desc"] = "desc"
    group_limit: int = Field(default=100, ge=1, le=100)
    group_offset: int = Field(default=0, ge=0, le=10000)


class Period(StrictInput):
    start: str
    end: str


class Compare(StrictInput):
    query: Query
    date_field: str
    baseline: Period
    comparison: Period


class History(StrictInput):
    object_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)
    object_id: str = Field(min_length=1, max_length=160)
    as_of: str
    fields: list[str] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class SpikeAnalysis(StrictInput):
    start: str = Field(description="Inclusive local calendar date YYYY-MM-DD")
    end: str = Field(description="Exclusive local calendar date YYYY-MM-DD, at most 93 days later")
    timezone: str = Field(default="Asia/Singapore", description="IANA timezone for calendar days")
    filters: list[Filter] = Field(default_factory=list, max_length=8)
