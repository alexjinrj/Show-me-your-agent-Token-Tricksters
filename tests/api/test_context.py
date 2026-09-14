from __future__ import annotations

from business_coordinator.api.context import DemoContext
from business_coordinator.api.settings import Settings


def test_bootstrap_seeds_expected_counts(settings: Settings) -> None:
    context = DemoContext.bootstrap(settings)
    assert context.counts() == {
        "customers": 486,
        "suppliers": 8,
        "items": 40,
        "resources": 6,
        "inventory": 40,
        "balances": 6,
        "business_events": 596,
        "business_objects": 550,
    }


def test_second_bootstrap_is_idempotent(settings: Settings) -> None:
    first = DemoContext.bootstrap(settings)
    first_counts = first.counts()
    first_hash = first.base_manifest().content_hash
    first.engine.dispose()

    second = DemoContext.bootstrap(settings)
    assert second.counts() == first_counts
    assert second.base_snapshot_id == first.base_snapshot_id
    assert second.base_manifest().content_hash == first_hash
