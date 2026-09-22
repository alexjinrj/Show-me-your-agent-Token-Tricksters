from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class GatewayError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise GatewayError("Gateway redirects are not permitted")


class OpenClawGateway:
    """Official OpenAI-compatible client-function handoff; no local LLM fallback."""

    def __init__(
        self,
        url: str,
        token: str,
        agent_id: str = "business-coordinator",
        timeout_seconds: float = 180,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Invalid OpenClaw Gateway URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Gateway URL must not contain credentials or query parameters")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-loopback Gateway requires HTTPS")
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("Gateway timeout must be between 1 and 300 seconds")
        self.url = url.rstrip("/") + "/v1/chat/completions"
        self.token = token
        self.agent_id = agent_id
        self.timeout_seconds = timeout_seconds

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload = {
            "model": f"openclaw/{self.agent_id}",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_completion_tokens": 2048,
        }
        request = Request(
            self.url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            # Deliberately stateless Gateway requests: the application owns conversation memory.
            with build_opener(NoRedirect).open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise GatewayError("Gateway response exceeded size limit")
            decoded = json.loads(raw)
            message = decoded["choices"][0]["message"]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise GatewayError("Invalid Gateway assistant message")
            return {**message, "_usage": decoded.get("usage", {})}
        except HTTPError as exc:
            raise GatewayError(f"OpenClaw Gateway returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise GatewayError("OpenClaw Gateway unavailable or timed out") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise GatewayError("Invalid OpenClaw Gateway response") from exc
