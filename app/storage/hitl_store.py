"""SQLite-backed pending action store (persists across restarts)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from app.errors import CopilotError, ErrorCode
from app.guard.hitl import (
    ActionStatus,
    PendingAction,
    check_token,
)


class SqlitePendingActionStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._lock = threading.RLock()

    def propose(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        summary: str,
        idempotency_key: str = "",
    ) -> PendingAction:
        with self._lock:
            if idempotency_key:
                row = self._conn.execute(
                    "SELECT * FROM pending_actions WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    action = self._to_action(row)
                    self.audit("proposed_duplicate", action)
                    return action
            action = PendingAction(
                action_id=f"act_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}",
                tool_name=tool_name,
                args=args,
                summary=summary,
                idempotency_key=idempotency_key,
            )
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO pending_actions(
                        action_id, tool_name, args_json, summary, status,
                        confirm_token, idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action.action_id,
                        action.tool_name,
                        json.dumps(action.args, ensure_ascii=False),
                        action.summary,
                        action.status.value,
                        action.confirm_token,
                        action.idempotency_key,
                        action.created_at.isoformat(timespec="seconds"),
                    ),
                )
            self.audit("proposed", action)
            return action

    def get(self, action_id: str) -> PendingAction:
        row = self._conn.execute(
            "SELECT * FROM pending_actions WHERE action_id = ?", (action_id,)
        ).fetchone()
        if row is None:
            raise CopilotError(ErrorCode.ACTION_NOT_FOUND, f"unknown action: {action_id!r}")
        return self._to_action(row)

    def list_actions(self, status: ActionStatus | None = None) -> list[PendingAction]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM pending_actions ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM pending_actions WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
        return [self._to_action(row) for row in rows]

    def confirm(self, action_id: str, token: str) -> PendingAction:
        with self._lock:
            action = self.get(action_id)
            check_token(action, token)
            if action.status is ActionStatus.EXECUTED:
                raise CopilotError(ErrorCode.ACTION_STATE_INVALID, "action already executed")
            if action.status is ActionStatus.CANCELLED:
                raise CopilotError(ErrorCode.ACTION_STATE_INVALID, "action was cancelled")
            if action.status is ActionStatus.CONFIRMED:
                self.audit("confirmed_duplicate", action)
                return action
            with self._conn:
                self._conn.execute(
                    "UPDATE pending_actions SET status = ? WHERE action_id = ?",
                    (ActionStatus.CONFIRMED.value, action_id),
                )
            action.status = ActionStatus.CONFIRMED
            self.audit("confirmed", action)
            return action

    def mark_executed(self, action_id: str, result: dict[str, Any]) -> PendingAction:
        with self._lock:
            action = self.get(action_id)
            if action.status is ActionStatus.EXECUTED:
                return action
            if action.status is not ActionStatus.CONFIRMED:
                raise CopilotError(
                    ErrorCode.ACTION_STATE_INVALID,
                    f"action must be confirmed first (status={action.status.value})",
                )
            executed_at = datetime.now(UTC)
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE pending_actions
                    SET status = ?, executed_at = ?, result_json = ?
                    WHERE action_id = ?
                    """,
                    (
                        ActionStatus.EXECUTED.value,
                        executed_at.isoformat(timespec="seconds"),
                        json.dumps(result, ensure_ascii=False),
                        action_id,
                    ),
                )
            action.status = ActionStatus.EXECUTED
            action.executed_at = executed_at
            action.result = result
            self.audit("executed", action)
            return action

    def audit(self, event: str, action: PendingAction, detail: str = "") -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO action_audit(ts, event, action_id, tool, summary, status, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(timespec="milliseconds"),
                    event,
                    action.action_id,
                    action.tool_name,
                    action.summary,
                    action.status.value,
                    detail,
                ),
            )

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT ts, event, action_id, tool, summary, status, detail "
            "FROM action_audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _to_action(row: sqlite3.Row) -> PendingAction:
        result_json = row["result_json"]
        executed_at = row["executed_at"]
        return PendingAction(
            action_id=row["action_id"],
            tool_name=row["tool_name"],
            args=json.loads(row["args_json"]),
            summary=row["summary"],
            status=ActionStatus(row["status"]),
            confirm_token=row["confirm_token"],
            idempotency_key=row["idempotency_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
            executed_at=datetime.fromisoformat(executed_at) if executed_at else None,
            result=json.loads(result_json) if result_json else None,
        )
