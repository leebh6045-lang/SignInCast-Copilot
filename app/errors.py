"""Domain errors with a stable taxonomy so every failure stays diagnosable."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable error codes used in traces, eval reports and API responses."""

    MODEL_ERROR = "MODEL_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_PERMISSION_DENIED = "TOOL_PERMISSION_DENIED"
    TOOL_INVALID_ARGS = "TOOL_INVALID_ARGS"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    ACTION_NOT_FOUND = "ACTION_NOT_FOUND"
    ACTION_TOKEN_INVALID = "ACTION_TOKEN_INVALID"
    ACTION_STATE_INVALID = "ACTION_STATE_INVALID"
    NO_PROGRESS = "NO_PROGRESS"
    STEP_LIMIT = "STEP_LIMIT"
    UNVERIFIED_NUMBER = "UNVERIFIED_NUMBER"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RUN_TIMEOUT = "RUN_TIMEOUT"
    AUTH_FAILED = "AUTH_FAILED"
    CONFIG_ERROR = "CONFIG_ERROR"
    INTERNAL = "INTERNAL"


class CopilotError(Exception):
    """Base error for anticipated failures."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.detail = detail or {}

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "detail": self.detail,
        }

    @classmethod
    def permission_denied(cls, tool_name: str, role: str) -> CopilotError:
        return cls(
            ErrorCode.TOOL_PERMISSION_DENIED,
            f"role {role!r} may not call tool {tool_name!r}",
        )
