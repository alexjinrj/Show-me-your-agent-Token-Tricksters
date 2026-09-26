from __future__ import annotations

import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError

from interfaces.api.context import BASE_SNAPSHOT_AS_OF, DemoContext
from interfaces.runtime import build_runtime
from load_data.csv_ingestion import SOURCE_TYPES

router = APIRouter(prefix="/api/v1/data/uploads", tags=["data-upload"])

MAX_UPLOAD_CHARS = 2_000_000
SourceType = Literal[
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
]


class CsvUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=120)
    csv_text: str = Field(min_length=1, max_length=MAX_UPLOAD_CHARS)
    source_type: SourceType | None = None
    mapping_version: str = Field(default="browser-upload-v1", pattern=r"^[A-Za-z0-9._-]{1,64}$")
    data_origin: Literal["source", "synthetic"] = "source"

    @field_validator("filename")
    @classmethod
    def csv_filename_only(cls, value: str) -> str:
        safe = Path(value).name
        if safe != value or not safe.lower().endswith(".csv"):
            raise ValueError("Upload must be a plain .csv filename")
        return safe


def _context(request: Request) -> DemoContext:
    context = request.app.state.context
    if not isinstance(context, DemoContext):  # pragma: no cover - defensive
        raise RuntimeError("demo context is not initialized")
    return context


def _write_temporary(payload: CsvUpload, directory: str) -> Path:
    path = Path(directory) / payload.filename
    path.write_text(payload.csv_text, encoding="utf-8")
    return path


def _authorize(request: Request, supplied: str | None) -> None:
    configured = request.app.state.settings.upload_token
    if configured is None:
        raise HTTPException(
            status_code=503,
            detail="Data import is disabled. Configure BC_UPLOAD_TOKEN on the backend.",
        )
    if supplied is None or not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=403, detail="Invalid upload authorization")


@router.get("/status")
def upload_status(request: Request) -> dict[str, Any]:
    return {
        "schema_version": "data-upload-v1",
        "commit_enabled": request.app.state.settings.upload_token is not None,
        "max_characters": MAX_UPLOAD_CHARS,
        "source_types": list(SOURCE_TYPES),
        "workflow": "inspect_then_commit",
    }


@router.post("/inspect")
def inspect_upload(payload: CsvUpload, request: Request) -> dict[str, Any]:
    with TemporaryDirectory(prefix="business-upload-inspect-") as directory:
        path = _write_temporary(payload, directory)
        inspection = _context(request).actual_state.inspect_csv(path)
    return {
        "schema_version": "data-upload-v1",
        "inspection": inspection.model_dump(mode="json", exclude={"path"}),
        "requested_source_type": payload.source_type,
        "commit_required": True,
    }


@router.post("/commit")
def commit_upload(
    payload: CsvUpload,
    request: Request,
    x_upload_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(request, x_upload_token)
    context = _context(request)
    try:
        with TemporaryDirectory(prefix="business-upload-commit-") as directory:
            path = _write_temporary(payload, directory)
            result = context.actual_state.import_csv(
                path,
                source_type=payload.source_type,
                mapping_version=payload.mapping_version,
                default_data_origin=payload.data_origin,
                default_business_timestamp=BASE_SNAPSHOT_AS_OF,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="The upload conflicts with existing business keys.",
        ) from exc

    if not result["validation"]["valid"]:
        return {
            "schema_version": "data-upload-v1",
            "result": result,
            "snapshot": None,
        }
    if result.get("committed"):
        manifest = context.refresh_base_snapshot()
        request.app.state.runtime = build_runtime(context)
    else:
        manifest = context.base_manifest()
    return {
        "schema_version": "data-upload-v1",
        "result": result,
        "snapshot": manifest.model_dump(mode="json"),
    }
