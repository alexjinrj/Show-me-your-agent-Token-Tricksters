from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from interfaces.api.context import DemoContext
from interfaces.api.settings import Settings
from tools.crm.scoring import ScoringPolicy, midrank
from tools.crm.service import CRMService
from tools.retrieval.contracts import Compare, Query
from tools.retrieval.tools import RetrievalTools


@pytest.fixture
def crm(tmp_path: Path, demo_path: Path) -> CRMService:
    return DemoContext.bootstrap(
        Settings(
            db_path=tmp_path / "test.db", host="127.0.0.1", host_port=8000, demo_data_dir=demo_path
        )
    ).crm


def test_ties_and_rank_direction() -> None:
    cohort = [Decimal(1), Decimal(1), Decimal(9)]
    assert midrank(Decimal(1), cohort) == pytest.approx(100 / 3)
    assert midrank(Decimal(9), cohort) == pytest.approx(250 / 3)
    assert midrank(Decimal(9), cohort, lower_is_better=True) == pytest.approx(50 / 3)
    assert midrank(Decimal(1), [Decimal(1)]) == 50
    with pytest.raises(ValueError):
        ScoringPolicy(window_days=0)


def test_rfm_hand_calculated_and_window(crm: CRMService) -> None:
    template_customer = next(iter(crm.customers.values()))
    template_order = next(iter(crm.orders.values()))
    crm.customers = {key: deepcopy(template_customer) for key in ["A", "B", "C", "D"]}
    crm.orders = {}
    crm.cases = {}
    now = crm.snapshot.manifest.as_of_time
    # Identical customers must tie at 50, old and future records cannot inflate scores.
    for key, days, amount in [
        ("A", 10, "10"),
        ("B", 10, "10"),
        ("C", 366, "10000"),
        ("D", -1, "10000"),
    ]:
        order = deepcopy(template_order)
        order["details"]["customer_number"] = key
        order["details"]["order_date"] = (now - timedelta(days=days)).isoformat()
        order["amount"] = amount
        crm.orders[key] = order
    rows = {row["id"]: row for row in crm.rate_customers()}
    assert rows["A"]["valueScore"] == rows["B"]["valueScore"] == 50
    assert rows["A"]["scoreDetails"]["cohortSize"] == 2
    assert rows["A"]["scoreDetails"]["recencyDays"] == 10
    assert rows["A"]["scoreDetails"]["monetaryOrderedValue"] == "10.00"
    assert rows["C"]["valueTier"] == rows["D"]["valueTier"] == "Inactive"


def test_exception_share_not_volume(crm: CRMService) -> None:
    template = next(iter(crm.orders.values()))
    customer = next(iter(crm.customers.values()))
    crm.customers = {"A": deepcopy(customer), "B": deepcopy(customer)}
    crm.orders = {}
    crm.cases = {}
    for key, count in [("A", 2), ("B", 10)]:
        for index in range(count):
            row = deepcopy(template)
            row["status"] = "open"
            row["details"]["customer_number"] = key
            crm.orders[f"{key}{index}"] = row
            if index < count // 2:
                crm.cases[f"{key}{index}"] = {"customerId": key, "overdueHours": 1}
    ratings = crm.rate_customers()
    assert [row["riskScore"] for row in ratings] == [50, 50]
    assert ratings[0]["scoreDetails"]["riskSmallSample"] is True
    assert ratings[1]["scoreDetails"]["riskSmallSample"] is False


def test_query_full_aggregate_independent_of_page(crm: CRMService) -> None:
    tools = RetrievalTools(crm)
    before = crm.snapshot.model_dump(mode="json")
    result = tools.query(Query(dataset="orders", limit=1, group_by=["status"]))
    assert result["returned"] == 1
    assert result["total_matching"] == len(crm.orders) == 500
    assert Decimal(result["totals"]["sums"]["amount"]) == sum(
        Decimal(str(row["amount"])) for row in crm.orders.values()
    )
    assert sum(row["row_count"] for row in result["groups"]) == 500
    assert result["next_offset"] == 1
    assert crm.snapshot.model_dump(mode="json") == before


@pytest.mark.parametrize(
    "args",
    [
        {"dataset": "orders", "fields": ["password"]},
        {"dataset": "orders", "sql": "DROP TABLE customers"},
        {"dataset": "orders", "limit": 100000},
        {"dataset": "orders", "filters": [{"field": "amount", "op": "gte", "value": "NaN"}]},
        {"dataset": "orders", "filters": [{"field": "status", "op": "in", "value": "open"}]},
        {"dataset": "inventory", "filters": [{"field": "sku", "op": "gte", "value": "A"}]},
    ],
)
def test_queries_reject_unknown_or_unbounded_requests(crm: CRMService, args: dict) -> None:
    with pytest.raises((ValueError, ValidationError)):
        RetrievalTools(crm).call("query_snapshot_records", args)


def test_date_boundaries_comparison_and_missing_history(crm: CRMService) -> None:
    tools = RetrievalTools(crm)
    tools.rows["orders"] = [
        {
            "id": str(i),
            "order_date": date,
            "order_month": date[:7],
            "order_day": date[:10],
            "due_date": date,
            "customer_id": "A",
            "sku": "P",
            "status": "open",
            "amount": amount,
            "quantity": "1",
        }
        for i, (date, amount) in enumerate(
            [
                ("2026-06-01T00:00:00Z", "0.10"),
                ("2026-06-30T23:59:59Z", "0.20"),
                ("2026-07-01T00:00:00Z", "0.60"),
                ("2026-08-01T00:00:00Z", "9.99"),
            ]
        )
    ]
    request = {
        "query": {"dataset": "orders", "limit": 1},
        "date_field": "order_date",
        "baseline": {"start": "2026-06-01", "end": "2026-07-01"},
        "comparison": {"start": "2026-07-01", "end": "2026-08-01"},
    }
    result = tools.compare(Compare.model_validate(request))
    assert result["baseline"]["totals"]["sums"]["amount"] == "0.30"
    assert result["comparison"]["total_matching"] == 1
    assert result["deltas"]["amount"] == {"absolute": "0.30", "percent": "100.00"}
    assert result["baseline"]["period_days"] == "30.0"
    request["baseline"] = {"start": "2026-05-01", "end": "2026-06-01"}
    assert tools.compare(Compare.model_validate(request))["deltas"]["amount"]["percent"] is None
    history = tools.call(
        "query_enterprise_history",
        {
            "object_type": "sales_order",
            "object_id": "SO-1",
            "as_of": "2026-06-01",
        },
    )
    assert history.status == "error" and history.error_code == "HISTORY_SOURCE_UNAVAILABLE"
    assert not history.data and history.reference_id is None


def test_general_catalog_covers_purchasing_finance_operations(crm: CRMService) -> None:
    tools = RetrievalTools(crm)
    catalog = tools.catalog()["datasets"]
    assert catalog["purchase_orders"]["record_count"] == 50
    assert catalog["balances"]["record_count"] == 6
    assert catalog["resources"]["record_count"] == 6
    assert catalog["balances"]["data_origins"] == ["synthetic"]
    suppliers = {row["id"] for row in tools.rows["suppliers"]}
    assert all(row["supplier_id"] in suppliers for row in tools.rows["purchase_orders"])
    balances = tools.query(Query(dataset="balances"))
    assert balances["totals"]["sums"] == {}
    assert balances["totals"]["aggregation_warnings"]
    grouped = tools.query(Query(dataset="balances", group_by=["account_code", "currency"]))
    assert all("amount" in group["sums"] for group in grouped["groups"])
    resources = tools.query(Query(dataset="resources"))
    assert resources["totals"]["sums"] == {}


def test_global_ranking_before_pagination(crm: CRMService) -> None:
    tools = RetrievalTools(crm)
    ranked = tools.query(
        Query(dataset="orders", group_by=["customer_id"], sort_by="amount", group_limit=3, limit=1)
    )
    expected = {}
    for order in crm.orders.values():
        key = order["details"]["customer_number"]
        expected[key] = expected.get(key, Decimal(0)) + Decimal(order["amount"])
    top = sorted(expected.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
    assert [
        (group["key"]["customer_id"], Decimal(group["sums"]["amount"]))
        for group in ranked["groups"]
    ] == top
    assert ranked["returned"] == 1 and ranked["total_matching"] == 500
    assert ranked["next_group_offset"] == 3
    next_page = tools.query(
        Query(
            dataset="orders",
            group_by=["customer_id"],
            sort_by="amount",
            group_limit=3,
            group_offset=3,
        )
    )
    assert {g["key"]["customer_id"] for g in ranked["groups"]}.isdisjoint(
        {g["key"]["customer_id"] for g in next_page["groups"]}
    )
    ordered = tools.query(Query(dataset="orders", sort_by="amount", limit=1))
    assert Decimal(ordered["rows"][0]["amount"]) == max(
        Decimal(o["amount"]) for o in crm.orders.values()
    )


def test_nonadditive_period_comparison_reports_omitted_metrics(crm: CRMService) -> None:
    tools = RetrievalTools(crm)
    request = Compare.model_validate(
        {
            "query": {"dataset": "balances"},
            "date_field": "business_timestamp",
            "baseline": {"start": "2026-08-01", "end": "2026-09-01"},
            "comparison": {"start": "2026-09-01", "end": "2026-10-01"},
        }
    )
    result = tools.compare(request)
    assert "amount" not in result["deltas"]
    assert result["omitted_non_additive_metrics"] == ["amount"]
