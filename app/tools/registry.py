"""Tool registry: one place that validates, authorizes, times out and retries."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import ValidationError

from app.config import Settings
from app.errors import CopilotError, ErrorCode
from app.logging import get_logger
from app.roles import Role
from app.tools.base import ToolContext, ToolResult, ToolSpec

logger = get_logger(__name__)


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(item) for item in error.get("loc", ())) or "<args>"
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return "invalid arguments: " + "; ".join(parts)


class ToolRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool registration: {spec.name!r}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        spec = self._tools.get(name)
        if spec is None:
            raise CopilotError(ErrorCode.TOOL_NOT_FOUND, f"unknown tool: {name!r}")
        return spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "read_only": spec.read_only,
                "roles": sorted(role.value for role in spec.allowed_roles),
            }
            for spec in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def schemas_for_role(self, role: Role) -> list[dict[str, Any]]:
        allowed = [spec for spec in self._tools.values() if role in spec.allowed_roles]
        return [spec.schema() for spec in sorted(allowed, key=lambda item: item.name)]

    async def invoke(
        self, name: str, raw_args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        try:
            spec = self.get(name)
        except CopilotError as exc:
            return ToolResult(ok=False, error_code=exc.code.value, error_message=exc.message)
        if context.role not in spec.allowed_roles:
            exc = CopilotError.permission_denied(name, context.role.value)
            return ToolResult(ok=False, error_code=exc.code.value, error_message=exc.message)
        try:
            args = spec.args_model.model_validate(raw_args or {})
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                error_code=ErrorCode.TOOL_INVALID_ARGS.value,
                error_message=_validation_message(exc),
            )
        return await self._run(spec, args, context)

    async def _run(self, spec: ToolSpec, args: Any, context: ToolContext) -> ToolResult:
        attempts = spec.max_retries + 1 if spec.read_only else 1
        last: ToolResult | None = None
        for attempt in range(attempts):
            started = time.monotonic()
            retry = False
            try:
                result = await asyncio.wait_for(
                    spec.handler(args, context), timeout=spec.timeout_s
                )
                if isinstance(result, ToolResult):
                    return result
                return ToolResult(ok=True, data=result)
            except TimeoutError:
                last = ToolResult(
                    ok=False,
                    error_code=ErrorCode.TOOL_TIMEOUT.value,
                    error_message=(
                        f"tool {spec.name!r} timed out after {spec.timeout_s:.1f}s"
                    ),
                )
                retry = spec.read_only and attempt < attempts - 1
            except CopilotError as exc:
                last = ToolResult(
                    ok=False, error_code=exc.code.value, error_message=exc.message
                )
                retry = exc.retryable and spec.read_only and attempt < attempts - 1
            except Exception as exc:  # noqa: BLE001 - tool boundary: normalize every failure
                logger.exception("tool %s raised", spec.name)
                last = ToolResult(
                    ok=False,
                    error_code=ErrorCode.TOOL_ERROR.value,
                    error_message=f"{type(exc).__name__}: {exc}"[:300],
                )
            finally:
                logger.debug(
                    "tool=%s attempt=%d duration_ms=%.1f",
                    spec.name,
                    attempt + 1,
                    (time.monotonic() - started) * 1000,
                )
            if not retry:
                return last
            await asyncio.sleep(min(0.2 * (2**attempt), 2.0))
        return last or ToolResult(
            ok=False,
            error_code=ErrorCode.TOOL_ERROR.value,
            error_message=f"tool {spec.name!r} failed",
        )
