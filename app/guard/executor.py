"""Executes a confirmed action; the only component allowed to mutate the system."""

from __future__ import annotations

from typing import Any

from app.business.writer import ActionWriter
from app.errors import CopilotError
from app.guard.hitl import ActionStatus, PendingActionStore


class ActionExecutor:
    def __init__(self, store: PendingActionStore, writer: ActionWriter) -> None:
        self.store = store
        self.writer = writer

    async def execute(self, action_id: str, token: str) -> dict[str, Any]:
        action = self.store.get(action_id)
        if action.status is ActionStatus.EXECUTED:
            return {
                **(action.result or {}),
                "action_id": action.action_id,
                "status": "executed",
                "replayed": True,
            }
        # Validates the token and moves the action to confirmed (idempotent).
        self.store.confirm(action_id, token)
        action = self.store.get(action_id)
        try:
            result = await self.writer.perform(action)
        except CopilotError as exc:
            self.store.audit("execute_failed", action, detail=exc.message)
            raise
        payload = {"action_id": action.action_id, "summary": action.summary, **result}
        if result.get("failed"):
            self.store.audit(
                "execute_partial",
                action,
                detail=f"failed={len(result.get('failed') or [])}",
            )
            return {**payload, "status": "partial"}
        self.store.mark_executed(action_id, payload)
        return {**payload, "status": "executed"}
