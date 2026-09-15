from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """Recursively convert a value into JSON-safe primitives.

    Every ``Decimal`` is serialized to its exact string form so the API never
    loses determinism to float rounding. Pydantic models are dumped in python
    mode first (keeping ``Decimal`` instances) and then normalized here.
    """
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="python"))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


class DecimalJSONResponse(JSONResponse):
    """JSON response that renders ``Decimal`` as strings (never floats)."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            to_jsonable(content),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
