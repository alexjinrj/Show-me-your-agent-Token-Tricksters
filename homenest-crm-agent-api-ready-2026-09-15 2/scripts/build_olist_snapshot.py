#!/usr/bin/env python3
"""Build the small, source-traceable Olist snapshot used by the CRM demo."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def parse(value: str):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None


def iso(value: datetime | None):
    return value.isoformat() if value else None


def main(raw_dir: Path, output: Path):
    customers = {row["customer_id"]: row for row in rows(raw_dir / "olist_customers_dataset.csv")}

    payments = defaultdict(float)
    payment_rows = 0
    for row in rows(raw_dir / "olist_order_payments_dataset.csv"):
        payments[row["order_id"]] += float(row["payment_value"])
        payment_rows += 1

    reviews = {}
    review_rows = 0
    for row in rows(raw_dir / "olist_order_reviews_dataset.csv"):
        review_rows += 1
        current = reviews.get(row["order_id"])
        if current is None or int(row["review_score"]) < int(current["review_score"]):
            reviews[row["order_id"]] = row

    orders_by_customer = defaultdict(list)
    all_orders = []
    for row in rows(raw_dir / "olist_orders_dataset.csv"):
        customer = customers.get(row["customer_id"])
        if not customer:
            continue
        delivered = parse(row["order_delivered_customer_date"])
        estimated = parse(row["order_estimated_delivery_date"])
        review = reviews.get(row["order_id"])
        late_days = max(0, (delivered - estimated).days) if delivered and estimated else 0
        record = {
            **row,
            "customer_unique_id": customer["customer_unique_id"],
            "customer_city": customer["customer_city"],
            "customer_state": customer["customer_state"],
            "payment_value": round(payments.get(row["order_id"], 0), 2),
            "review_score": int(review["review_score"]) if review else None,
            "review_comment": (review.get("review_comment_message") or "").strip() if review else "",
            "late_days": late_days,
        }
        all_orders.append(record)
        orders_by_customer[customer["customer_unique_id"]].append(record)

    def complaint_strength(order):
        score = order["review_score"]
        return (3 - score) * 20 + min(20, order["late_days"] * 2) if score is not None and score <= 2 else min(20, order["late_days"] * 2)

    complaint_orders = [
        order for order in all_orders
        if (order["review_score"] is not None and order["review_score"] <= 2) or order["late_days"] >= 5
    ]
    complaint_orders.sort(key=lambda order: (complaint_strength(order), order["payment_value"]), reverse=True)

    selected_unique_ids = []
    chosen_complaints = []
    for order in complaint_orders:
        unique_id = order["customer_unique_id"]
        if unique_id in selected_unique_ids:
            continue
        selected_unique_ids.append(unique_id)
        chosen_complaints.append(order)
        if len(chosen_complaints) == 24:
            break

    remaining = [
        (unique_id, sum(order["payment_value"] for order in customer_orders))
        for unique_id, customer_orders in orders_by_customer.items()
        if unique_id not in selected_unique_ids
    ]
    remaining.sort(key=lambda item: (len(orders_by_customer[item[0]]), item[1]), reverse=True)
    selected_unique_ids.extend(unique_id for unique_id, _ in remaining[:6])

    id_map = {unique_id: f"CUS-{index:03d}" for index, unique_id in enumerate(selected_unique_ids, 1)}
    output_customers = []
    for unique_id in selected_unique_ids:
        customer_orders = orders_by_customer[unique_id]
        dated_orders = [parse(order["order_purchase_timestamp"]) for order in customer_orders]
        review_scores = [order["review_score"] for order in customer_orders if order["review_score"] is not None]
        first = customer_orders[0]
        output_customers.append({
            "id": id_map[unique_id],
            "name": f"Olist 匿名客户 {id_map[unique_id][-3:]}",
            "type": "匿名",
            "orderCount": len(customer_orders),
            "spend": round(sum(order["payment_value"] for order in customer_orders), 2),
            "onboarding": "数据未提供",
            "paymentTerms": "数据未提供",
            "sourceCustomerId": unique_id,
            "city": first["customer_city"],
            "state": first["customer_state"],
            "lastOrderAt": iso(max(value for value in dated_orders if value)),
            "averageReviewScore": round(sum(review_scores) / len(review_scores), 2) if review_scores else None,
            "lateDeliveryCount": sum(1 for order in customer_orders if order["late_days"] > 0),
        })

    singapore = timezone(timedelta(hours=8))
    replay_base = datetime(2026, 9, 7, 8, 30, tzinfo=singapore)
    output_complaints = []
    for index, order in enumerate(chosen_complaints, 1):
        opened = replay_base + timedelta(hours=index * 4)
        due = opened + timedelta(hours=48)
        first_response = None if index in {4, 9, 14, 19} else opened + timedelta(hours=1)
        review_score = order["review_score"]
        late_days = order["late_days"]
        if review_score is not None and review_score <= 2 and late_days:
            issue = f"客户评分 {review_score}/5；实际配送比预计晚 {late_days} 天"
        elif review_score is not None and review_score <= 2:
            issue = f"客户评分 {review_score}/5，需要核实不满意原因"
        else:
            issue = f"实际配送比预计晚 {late_days} 天，需要主动关怀"
        status = "WAITING_WAREHOUSE" if late_days >= 5 else "READY"
        output_complaints.append({
            "id": f"TKT-{index:03d}",
            "customerId": id_map[order["customer_unique_id"]],
            "orderId": f"ORD-{order['order_id'][:8].upper()}",
            "sourceOrderId": order["order_id"],
            "status": status,
            "issue": issue,
            "openedAt": opened.isoformat(),
            "dueAt": due.isoformat(),
            "firstResponseAt": first_response.isoformat() if first_response else None,
            "reviewScore": review_score,
            "reviewText": order["review_comment"][:300] or None,
            "lateDays": late_days,
            "sourcePurchaseAt": order["order_purchase_timestamp"],
            "sourceDeliveredAt": order["order_delivered_customer_date"] or None,
            "sourceEstimatedDeliveryAt": order["order_estimated_delivery_date"] or None,
        })

    payload = {
        "meta": {
            "dataset": "Brazilian E-Commerce Public Dataset by Olist",
            "sourceUrl": "https://www.kaggle.com/olistbr/brazilian-ecommerce",
            "licenseNote": "Public, anonymized commercial dataset; verify the Kaggle data card for current terms.",
            "sourcePeriod": "2016-09-04 to 2018-10-17",
            "replayAsOf": "2026-09-11T23:59:59+08:00",
            "sourceRows": {
                "customers": len(customers),
                "orders": len(all_orders),
                "payments": payment_rows,
                "reviews": review_rows,
            },
            "selectedCustomers": len(output_customers),
            "derivedOpenComplaints": len(output_complaints),
            "realFields": [
                "anonymized customer id", "city/state", "orders", "payment totals", "purchase/delivery timestamps",
                "estimated delivery date", "review score", "review comment",
            ],
            "simulatedFields": [
                "display customer id/name", "complaint id", "complaint workflow status", "SLA due time", "first response time",
            ],
        },
        "customers": output_customers,
        "complaints": output_complaints,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_olist_snapshot.py RAW_DATA_DIR OUTPUT_JSON")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
