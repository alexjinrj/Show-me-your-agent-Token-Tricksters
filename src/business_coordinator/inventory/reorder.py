from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

DATA_DIR = Path("data/demo/raw")
OUTPUT_PATH = Path("data/demo/expected/reorder_recommendations.csv")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def build_reorder_recommendations(
    items: list[dict[str, str]],
    inventory: list[dict[str, str]],
) -> list[dict[str, str]]:
    inventory_by_sku: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for row in inventory:
        inventory_by_sku[row["sku"]] += Decimal(row["quantity"])

    results: list[dict[str, str]] = []

    for item in items:
        sku = item["sku"]
        current_stock = inventory_by_sku[sku]
        reorder_point = Decimal(item["reorder_point"])

        needs_reorder = current_stock <= reorder_point
        target_stock = reorder_point * Decimal("2")

        recommended_quantity = max(
            Decimal("0"),
            target_stock - current_stock,
        )

        if current_stock <= 0:
            risk_level = "critical"
        elif current_stock <= reorder_point / Decimal("2"):
            risk_level = "high"
        elif current_stock <= reorder_point:
            risk_level = "medium"
        else:
            risk_level = "low"

        results.append(
            {
                "sku": sku,
                "name": item["name"],
                "current_stock": decimal_text(current_stock),
                "reorder_point": decimal_text(reorder_point),
                "target_stock": decimal_text(target_stock),
                "needs_reorder": str(needs_reorder).lower(),
                "risk_level": risk_level,
                "recommended_quantity": decimal_text(recommended_quantity),
            }
        )

    return results


def write_recommendations(
    results: list[dict[str, str]],
    output_path: Path,
) -> None:
    fieldnames = [
        "sku",
        "name",
        "current_stock",
        "reorder_point",
        "target_stock",
        "needs_reorder",
        "risk_level",
        "recommended_quantity",
    ]

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        mode="w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    items = read_csv(DATA_DIR / "items.csv")
    inventory = read_csv(DATA_DIR / "inventory.csv")

    results = build_reorder_recommendations(
        items,
        inventory,
    )

    write_recommendations(
        results,
        OUTPUT_PATH,
    )

    reorder_rows = [row for row in results if row["needs_reorder"] == "true"]

    print(f"Analysed SKUs: {len(results)}")
    print(f"SKUs requiring reorder: {len(reorder_rows)}")
    print()

    for row in reorder_rows:
        print(
            f"{row['sku']} | "
            f"stock={row['current_stock']} | "
            f"reorder_point={row['reorder_point']} | "
            f"risk={row['risk_level']} | "
            f"recommended={row['recommended_quantity']}"
        )

    print()
    print(f"Report saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
