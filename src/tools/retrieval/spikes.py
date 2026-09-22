"""Descriptive spike screening, not causal inference or a calibrated forecast."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.retrieval.contracts import SpikeAnalysis


def analyze_days(
    rows: list[dict[str, str]],
    request: SpikeAnalysis,
) -> dict[str, Any]:
    start, end = date.fromisoformat(request.start), date.fromisoformat(request.end)
    if not 1 <= (end - start).days <= 93:
        raise ValueError("Select a period of 1 to 93 days, end exclusive")
    try:
        zone = ZoneInfo(request.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown IANA timezone") from exc
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        timestamp = datetime.fromisoformat(row["order_date"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Source order dates must have a timezone")
        local_day = timestamp.astimezone(zone).date()
        if start <= local_day < end:
            buckets[local_day.isoformat()].append(row)
    typical = Decimal(str(median([len(items) for items in buckets.values()]))) if buckets else None
    total = sum(map(len, buckets.values()))
    days: list[dict[str, Any]] = []
    for offset in range((end - start).days):
        day = (start + timedelta(days=offset)).isoformat()
        items = buckets.get(day, [])
        ratio = Decimal(len(items)) / typical if items and typical else None
        days.append(
            {
                "date": day,
                "snapshot_record_count": len(items),
                "business_order_count": None,  # Unknown complete business count.
                "ordered_amount": str(sum((Decimal(row["amount"]) for row in items), Decimal(0))),
                "ratio_to_observed_day_median": str(ratio.quantize(Decimal("0.01")))
                if ratio
                else None,
                "candidate_spike": len(buckets) >= 7
                and len(items) >= 5
                and ratio is not None
                and ratio >= 3,
            }
        )
    peaks = []
    for peak in sorted(days, key=lambda d: (-int(d["snapshot_record_count"]), str(d["date"])))[:5]:
        if not peak["snapshot_record_count"]:
            continue
        items = buckets[str(peak["date"])]
        sku_counts: dict[str, int] = defaultdict(int)
        for item in items:
            sku_counts[item["sku"]] += 1
        peaks.append(
            {
                **peak,
                "share_of_period_snapshot_orders_pct": str(
                    (Decimal(len(items)) / Decimal(total) * 100).quantize(Decimal("0.01"))
                ),
                "top_skus": [
                    {"sku": sku, "order_count": count}
                    for sku, count in sorted(
                        sku_counts.items(), key=lambda pair: (-pair[1], pair[0])
                    )[:10]
                ],
                "evidence_ids": [row["id"] for row in items[:20]],
                "evidence_ids_truncated": len(items) > 20,
            }
        )
    return {
        "period": {
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "timezone": request.timezone,
            "start_timestamp": datetime.combine(start, time.min, zone).isoformat(),
            "end_timestamp": datetime.combine(end, time.min, zone).isoformat(),
        },
        "total_snapshot_orders": total,
        "observed_days": len(buckets),
        "requested_days": (end - start).days,
        "median_orders_per_observed_day": str(typical) if typical is not None else None,
        "days": days,
        "peak_days": peaks,
        "screening_rule": "Candidate: >=7 observed days, >=5 orders, >=3x observed-day median",
        "coverage": "Snapshot counts only; missing days do not prove zero business orders",
        "interpretation": "Screening only; weekday effects, coverage and causes unverified",
        "missing_attribution_fields": ["sales market", "sales channel", "campaign_id", "discount"],
        "next_step": "Verify market from user context; search public events around detected dates. "
        "Compare event dates, country and channels. A coincident event is not proof.",
    }
