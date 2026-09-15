from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)

DEFAULT_RECOMMENDATION_PATH = Path("data/demo/expected/final_recommendation.json")


def get_inventory_recommendation(
    path: str | Path = DEFAULT_RECOMMENDATION_PATH,
) -> StrategyRecommendation:
    recommendation_path = Path(path)

    if not recommendation_path.exists():
        raise FileNotFoundError(f"Inventory recommendation does not exist: {recommendation_path}")

    try:
        content = recommendation_path.read_text(encoding="utf-8")

        return StrategyRecommendation.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError("Inventory recommendation is invalid") from exc
