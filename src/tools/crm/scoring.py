"""Transparent demo policy: RFM on observed order value, not paid lifetime value."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScoringPolicy:
    version: str = "crm-rfm-v2"
    window_days: int = 365
    tier_a: int = 75
    tier_b: int = 50
    small_sample_orders: int = 5

    def __post_init__(self) -> None:
        if self.window_days <= 0 or not 0 <= self.tier_b < self.tier_a <= 100:
            raise ValueError("Invalid scoring window or tier thresholds")
        if self.small_sample_orders < 1:
            raise ValueError("Sample warning threshold must be positive")


def midrank(value: Decimal, cohort: list[Decimal], *, lower_is_better: bool = False) -> float:
    """Identical observations get identical scores; an all-tied cohort scores 50."""
    if not cohort:
        raise ValueError("An empty cohort cannot be ranked")
    less = sum(item < value for item in cohort)
    tied = sum(item == value for item in cohort)
    score = 100 * (less + tied / 2) / len(cohort)
    return 100 - score if lower_is_better else score
