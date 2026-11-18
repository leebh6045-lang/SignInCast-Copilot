"""HTTP transport abstraction: live calls, recorded replay, and record-on-live.

The agent code never talks to httpx directly. Swapping transports lets tests and
offline demos run without credentials or network, which is also what makes the
contract tests deterministic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.errors import CopilotError, ErrorCode


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    params: Mapping[str, Any] = field(default_factory=dict)
    json_body: dict[str, Any] | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, Any] | None = None
    text: str = ""


class Transport(Protocol):
    """is_offline=True means credentials are not required (mock)."""

    is_offline: bool

    async def request(
        self, request: HttpRequest, headers: Mapping[str, str]
    ) -> HttpResponse: ...


def fixture_key(request: HttpRequest) -> str:
    """Stable key for a request; used as the recorded fixture file name."""
    query = "&".join(f"{key}={request.params[key]}" for key in sorted(request.params))
    raw = f"{request.method.upper()} {request.path}?{query}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class LiveTransport:
    """Real HTTP calls against SignInCast."""

    is_offline = False

    def __init__(self, base_url: str, timeout_s: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def request(
        self, request: HttpRequest, headers: Mapping[str, str]
    ) -> HttpResponse:
        url = f"{self._base_url}{request.path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.request(
                    request.method,
                    url,
                    params=dict(request.params),
                    headers=dict(headers),
                    json=request.json_body,
                )
        except httpx.TimeoutException as exc:
            raise CopilotError(
                ErrorCode.TOOL_TIMEOUT,
                f"SignInCast 请求超时：{request.method} {request.path}",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                f"SignInCast 网络错误：{type(exc).__name__}",
                retryable=True,
            ) from exc
        body: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None
        return HttpResponse(status=response.status_code, body=body, text=response.text[:2000])


class MockTransport:
    """Replays recorded fixtures; a missing fixture is an explicit error."""

    is_offline = True

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir

    async def request(
        self, request: HttpRequest, headers: Mapping[str, str]
    ) -> HttpResponse:
        path = self._fixtures_dir / f"{fixture_key(request)}.json"
        if not path.is_file():
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                (
                    f"没有录制响应：{request.method} {request.path}。"
                    "请用 --record 模式联网录制，或先跑 M1 的录制流程。"
                ),
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = payload.get("response") or {}
        return HttpResponse(
            status=int(response.get("status", 200)),
            body=response.get("body"),
            text=str(response.get("text", ""))[:2000],
        )


class RecordingTransport:
    """Calls the live API and persists each response for offline replay.

    The login request is deliberately not recorded: its response contains a
    bearer token, and the mock mode never needs real authentication.
    """

    is_offline = False

    def __init__(self, inner: Transport, fixtures_dir: Path) -> None:
        self._inner = inner
        self._fixtures_dir = fixtures_dir

    async def request(
        self, request: HttpRequest, headers: Mapping[str, str]
    ) -> HttpResponse:
        response = await self._inner.request(request, headers)
        if request.path == "/api/auth/login":
            return response
        self._fixtures_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "request": {
                "method": request.method,
                "path": request.path,
                "params": dict(request.params),
            },
            "response": {"status": response.status, "body": response.body},
            "meta": {
                "source": "live",
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        }
        target = self._fixtures_dir / f"{fixture_key(request)}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return response
