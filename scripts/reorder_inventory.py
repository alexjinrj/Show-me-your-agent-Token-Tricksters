from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from tools.inventory.reorder import (
    ReorderCandidate,
    build_reorder_recommendations,
)

DATA_DIR = Path(
    "data/load_data/adventureworks_demo"
)

OUTPUT_PATH = Path(
    "data/expected/reorder_recommendations.csv"
)


def read_csv(
    path: Path,
) -> list[dict[str, str]]:
    """Read one CSV file for the standalone report."""

    with path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def csv_row(
    candidate: ReorderCandidate,
) -> dict[str, Any]:
    """
    Convert the typed model to the legacy CSV format.

    The CSV continues to store true/false as text,
    while Python code uses real booleans.
    """

    row = candidate.model_dump(
        mode="json"
    )

    row["needs_reorder"] = str(
        candidate.needs_reorder
    ).lower()

    return row


def write_recommendations(
    results: list[ReorderCandidate],
    output_path: Path,
) -> None:
    """Write recommendations to a CSV report."""

    fieldnames = list(
        ReorderCandidate.model_fields
    )

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

        writer.writerows(
            csv_row(row)
            for row in results
        )


def main() -> None:
    items = read_csv(
        DATA_DIR / "items.csv"
    )

    inventory = read_csv(
        DATA_DIR / "inventory.csv"
    )

    results = build_reorder_recommendations(
        items,
        inventory,
    )

    write_recommendations(
        results,
        OUTPUT_PATH,
    )

    reorder_rows = [
        row
        for row in results
        if row.needs_reorder
    ]

    print(
        f"Analysed SKUs: {len(results)}"
    )

    print(
        "SKUs requiring reorder: "
        f"{len(reorder_rows)}"
    )

    print()

    for row in reorder_rows:
        print(
            f"{row.sku} | "
            f"stock={row.current_stock} | "
            f"reorder_point={row.reorder_point} | "
            f"risk={row.risk_level} | "
            f"recommended="
            f"{row.recommended_quantity}"
        )

    print()

    print(
        f"Report saved to: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()