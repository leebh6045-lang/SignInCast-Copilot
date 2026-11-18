"""Write operations against SignInCast; only executed after human confirmation.

The server endpoints are upserts (existing record is updated, missing one is
inserted), so retrying a per-student write is safe. This is why partial failures
can be retried by the operator without creating duplicate records.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from app.business.models import SignInRecord
from app.business.signincast import SignInCastClient
from app.errors import CopilotError, ErrorCode
from app.guard.hitl import PendingAction


class ActionWriter(Protocol):
    async def perform(self, action: PendingAction) -> dict[str, Any]: ...


class SignInCastWriter:
    def __init__(self, client: SignInCastClient) -> None:
        self._client = client

    async def manual_signin(self, task_id: int, student_id: int) -> dict[str, Any]:
        payload = await self._client.post(
            f"/api/records/task/{task_id}/manual/{student_id}"
        )
        return self._record(payload)

    async def mark_leave(self, task_id: int, student_id: int) -> dict[str, Any]:
        payload = await self._client.post(
            f"/api/records/task/{task_id}/leave/{student_id}"
        )
        return self._record(payload)

    async def perform(self, action: PendingAction) -> dict[str, Any]:
        if self._client.is_offline:
            raise CopilotError(
                ErrorCode.CONFIG_ERROR,
                (
                    "mock 模式不执行写操作：回放数据里没有写接口响应。"
                    "请用 --live 连接真实系统，并在测试课堂/任务上验证。"
                ),
            )
        handlers = {
            "manual_signin": self.manual_signin,
            "mark_leave": self.mark_leave,
        }
        handler = handlers.get(action.tool_name)
        if handler is None:
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                f"unsupported action tool: {action.tool_name!r}",
            )
        task_id = action.args.get("task_id")
        student_ids = action.args.get("student_ids")
        if task_id in (None, "") or not isinstance(student_ids, list) or not student_ids:
            raise CopilotError(
                ErrorCode.TOOL_INVALID_ARGS,
                "action args missing task_id/student_ids",
            )
        succeeded: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for raw_student_id in student_ids:
            try:
                record = await handler(int(task_id), int(raw_student_id))
                succeeded.append(record)
            except (CopilotError, TypeError, ValueError) as exc:
                failed.append({"student_id": raw_student_id, "error": str(exc)})
        return {"requested": len(student_ids), "succeeded": succeeded, "failed": failed}

    @staticmethod
    def _record(payload: Any) -> dict[str, Any]:
        try:
            record = SignInRecord.model_validate(payload)
        except ValidationError as exc:
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                f"写操作响应结构不符合约定：{exc.errors()[:1]}",
            ) from exc
        return {
            "record_id": record.id,
            "task_id": record.taskId,
            "student_id": record.studentId,
            "result": record.result,
            "method": record.signInMethod,
        }
