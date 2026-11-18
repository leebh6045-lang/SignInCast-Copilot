"""Tool contracts: schema, permission and normalized execution results."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.roles import Role


class ToolArgs(BaseModel):
    """Base class for tool arguments; unknown fields are rejected."""

    model_config = {"extra": "forbid"}


@dataclass(frozen=True)
class ToolResult:
    """Normalized tool outcome so the loop never sees raw exceptions."""

    ok: bool
    data: Any = None
    error_code: str | None = None
    error_message: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_content(self, max_chars: int = 4000) -> str:
        if self.ok:
            payload: dict[str, Any] = {"ok": True, "data": self.data}
        else:
            payload = {
                "ok": False,
                "error": {"code": self.error_code, "message": self.error_message},
            }
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) <= max_chars:
            return text
        # TODO(M2): trim structured payloads (lists/page info) instead of raw chars.
        return text[:max_chars] + f"\n... [truncated {len(text) - max_chars} chars]"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "meta": self.meta,
        }


@dataclass(frozen=True)
class ToolContext:
    """Per-call context available to tool handlers."""

    role: Role
    run_id: str = ""
    user_id: str = ""


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    """Everything the registry needs to validate, authorize and execute a tool."""

    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    allowed_roles: frozenset[Role]
    read_only: bool = True
    timeout_s: float = 8.0
    max_retries: int = 2
    max_content_chars: int = 4000

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }
