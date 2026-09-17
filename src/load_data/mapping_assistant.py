from __future__ import annotations

from typing import Protocol

from pydantic import Field

from core.models import CanonicalModel
from core.object_schema import ObjectSchemaRegistry
from core.simulation.process_runtime import RuntimeProcessCatalog


class SourceProfile(CanonicalModel):
    source_name: str = Field(min_length=1)
    columns: tuple[str, ...]
    sample_rows: tuple[dict[str, str], ...] = ()
    row_count: int = Field(ge=0)


class MappingProposal(CanonicalModel):
    status: str = Field(min_length=1)
    proposed_mapping: dict[str, object] | None = None
    warnings: tuple[str, ...] = ()


class MappingAssistant(Protocol):
    """Optional proposal-only extension point; assistants never write Enterprise State."""

    def propose_mapping(
        self,
        source_profile: SourceProfile,
        object_schemas: ObjectSchemaRegistry,
        process_catalog: RuntimeProcessCatalog,
    ) -> MappingProposal: ...


class NoOpMappingAssistant:
    def propose_mapping(
        self,
        source_profile: SourceProfile,
        object_schemas: ObjectSchemaRegistry,
        process_catalog: RuntimeProcessCatalog,
    ) -> MappingProposal:
        del source_profile, object_schemas, process_catalog
        return MappingProposal(
            status="manual_mapping_required",
            warnings=("No mapping assistant is configured; provide an approved mapping spec.",),
        )
