"""Human-in-the-loop action model, store protocol and in-memory implementation."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.errors import CopilotError, ErrorCode


class ActionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


@dataclass
class PendingAction:
    action_id: str
    tool_name: str
    args: dict[str, Any]
    summary: str
    status: ActionStatus = ActionStatus.PENDING
    confirm_token: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    executed_at: datetime | None = None
    result: dict[str, Any] | None = None

    def to_dict(self, *, include_token: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "args": self.args,
            "summary": self.summary,
            "status": self.status.value,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "executed_at": (
                self.executed_at.isoformat(timespec="seconds") if self.executed_at else None
            ),
            "result": self.result,
        }
        if include_token:
            payload["confirm_token"] = self.confirm_token
        return payload


class PendingActionStore(Protocol):
    """Persistence boundary: memory for tests, SQLite for the running service."""

    def propose(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        summary: str,
        idempotency_key: str = "",
    ) -> PendingAction: ...

    def get(self, action_id: str) -> PendingAction: ...

    def list_actions(self, status: ActionStatus | None = None) -> list[PendingAction]: ...

    def confirm(self, action_id: str, token: str) -> PendingAction: ...

    def mark_executed(self, action_id: str, result: dict[str, Any]) -> PendingAction: ...

    def audit(self, event: str, action: PendingAction, detail: str = "") -> None: ...

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]: ...


def check_token(action: PendingAction, token: str) -> None:
    if not secrets.compare_digest(action.confirm_token, token or ""):
        raise CopilotError(ErrorCode.ACTION_TOKEN_INVALID, "confirmation token rejected")


class InMemoryPendingActionStore:
    """Used by unit tests and offline demos; the service uses SQLite."""

    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}
        self._by_key: dict[str, str] = {}
        self._audit: list[dict[str, Any]] = []

    def propose(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        summary: str,
        idempotency_key: str = "",
    ) -> PendingAction:
        if idempotency_key and idempotency_key in self._by_key:
            existing = self._actions[self._by_key[idempotency_key]]
            self.audit("proposed_duplicate", existing)
            return existing
        action = PendingAction(
            action_id=f"act_{secrets.token_hex(6)}",
            tool_name=tool_name,
            args=args,
            summary=summary,
            idempotency_key=idempotency_key,
        )
        self._actions[action.action_id] = action
        if idempotency_key:
            self._by_key[idempotency_key] = action.action_id
        self.audit("proposed", action)
        return action

    def get(self, action_id: str) -> PendingAction:
        action = self._actions.get(action_id)
        if action is None:
            raise CopilotError(ErrorCode.ACTION_NOT_FOUND, f"unknown action: {action_id!r}")
        return action

    def list_actions(self, status: ActionStatus | None = None) -> list[PendingAction]:
        actions = list(self._actions.values())
        if status is not None:
            actions = [item for item in actions if item.status is status]
        return sorted(actions, key=lambda item: item.created_at, reverse=True)

    def confirm(self, action_id: str, token: str) -> PendingAction:
        action = self.get(action_id)
        check_token(action, token)
        if action.status is ActionStatus.EXECUTED:
            raise CopilotError(ErrorCode.ACTION_STATE_INVALID, "action already executed")
        if action.status is ActionStatus.CANCELLED:
            raise CopilotError(ErrorCode.ACTION_STATE_INVALID, "action was cancelled")
        if action.status is ActionStatus.CONFIRMED:
            self.audit("confirmed_duplicate", action)
            return action
        action.status = ActionStatus.CONFIRMED
        self.audit("confirmed", action)
        return action

    def mark_executed(self, action_id: str, result: dict[str, Any]) -> PendingAction:
        action = self.get(action_id)
        if action.status is ActionStatus.EXECUTED:
            return action
        if action.status is not ActionStatus.CONFIRMED:
            raise CopilotError(
                ErrorCode.ACTION_STATE_INVALID,
                f"action must be confirmed first (status={action.status.value})",
            )
        action.status = ActionStatus.EXECUTED
        action.executed_at = datetime.now(UTC)
        action.result = result
        self.audit("executed", action)
        return action

    def audit(self, event: str, action: PendingAction, detail: str = "") -> None:
        self._audit.append(
            {
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "event": event,
                "action_id": action.action_id,
                "tool": action.tool_name,
                "summary": action.summary,
                "status": action.status.value,
                "detail": detail,
            }
        )

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self._audit))[:limit]

