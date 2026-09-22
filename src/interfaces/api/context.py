from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine

from core.models import EnterpriseState, SnapshotBundle, SnapshotManifest
from core.simulation.process_runtime import (
    RuntimeProcessCatalog,
    load_runtime_process_catalog,
)
from enterprise_state.crm_proposals import CRMProposalStore
from enterprise_state.database import create_schema, make_engine, sqlite_url
from enterprise_state.service import ActualStateService, commit_demo_files
from interfaces.api.settings import Settings
from tools.crm.service import CRMService
from tools.simulation.service import SimulationService

# CSV source ingestion order, mirroring scripts/seed_demo_data.py exactly so the
# base snapshot content_hash stays identical across the CLI seeder and the API.
ORDER = (
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
)

# The single base snapshot as-of time defined by scripts/seed_demo_data.py.
BASE_SNAPSHOT_AS_OF = "2026-09-12T23:59:00+08:00"
COMPANY_ID = "SG-SME-001"


class DemoContext:
    """Owns the on-disk SQLite engine and the seeded base snapshot.

    Seeding is idempotent: ingestion is keyed on file content and snapshot
    creation is keyed on content_hash, so restarting the app against a
    persistent database never duplicates rows or snapshots.
    """

    def __init__(
        self,
        engine: Engine,
        base_snapshot_id: str,
        process_catalog: RuntimeProcessCatalog,
        source_manifest: dict[str, object],
        crm: CRMService,
    ) -> None:
        self.engine = engine
        self.base_snapshot_id = base_snapshot_id
        self.actual_state = ActualStateService(
            engine, source_system="microsoft-adventureworks-demo"
        )
        self.simulations = SimulationService(engine)
        self.process_catalog = process_catalog
        self.source_manifest = source_manifest
        self.crm = crm
        self.crm_proposals = CRMProposalStore(engine, crm)

    @classmethod
    def bootstrap(cls, settings: Settings) -> DemoContext:
        engine = make_engine(sqlite_url(settings.db_path))
        create_schema(engine)
        service = ActualStateService(engine, source_system="microsoft-adventureworks-demo")
        root = Path(settings.demo_data_dir)
        commit_demo_files(service, ((name, root / f"{name}.csv") for name in ORDER))
        manifest = service.create_snapshot(
            datetime.fromisoformat(BASE_SNAPSHOT_AS_OF), company_id=COMPANY_ID
        )
        return cls(
            engine,
            manifest.snapshot_id,
            load_runtime_process_catalog(settings.config_dir),
            json.loads((root / "SOURCE_MANIFEST.json").read_text(encoding="utf-8")),
            CRMService(service.load_snapshot(manifest.snapshot_id)),
        )

    def base_snapshot(self) -> SnapshotBundle:
        """Return a fresh detached snapshot bundle for the simulation.

        The bundle is immutable (frozen pydantic models) and carries no ORM
        session, guaranteeing the simulator never receives a writable handle.
        """
        return self.actual_state.load_snapshot(self.base_snapshot_id)

    def base_manifest(self) -> SnapshotManifest:
        return self.base_snapshot().manifest

    def enterprise_state(self) -> EnterpriseState:
        """Return the canonical actual state document used by tools and APIs."""

        return self.actual_state.get_enterprise_state(
            datetime.fromisoformat(BASE_SNAPSHOT_AS_OF), company_id=COMPANY_ID
        )

    def counts(self) -> dict[str, int]:
        return self.actual_state.counts()
