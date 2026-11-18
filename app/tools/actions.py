"""Write-intent tools. They never touch the business system: a human confirms first."""

from __future__ import annotations

from pydantic import Field

from app.guard.hitl import PendingActionStore
from app.tools.base import ToolArgs, ToolContext, ToolResult


class ProposeManualSigninArgs(ToolArgs):
    task_id: str = Field(min_length=1, max_length=64)
    student_ids: list[str] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=2, max_length=200)


class ProposeMarkLeaveArgs(ToolArgs):
    task_id: str = Field(min_length=1, max_length=64)
    student_ids: list[str] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=2, max_length=200)


def _propose(
    store: PendingActionStore,
    *,
    tool_name: str,
    args: ToolArgs,
    summary: str,
    idempotency_key: str,
) -> ToolResult:
    action = store.propose(
        tool_name=tool_name,
        args=args.model_dump(),
        summary=summary,
        idempotency_key=idempotency_key,
    )
    return ToolResult(
        ok=True,
        data={
            "action_id": action.action_id,
            "summary": action.summary,
            "status": action.status.value,
            "hint": "需要用户在界面上确认后才会执行；模型无权自行确认。",
        },
        meta={"pending_action_id": action.action_id},
    )


def make_propose_manual_signin(store: PendingActionStore):
    async def handler(
        args: ProposeManualSigninArgs, context: ToolContext
    ) -> ToolResult:
        student_key = ",".join(sorted(args.student_ids))
        return _propose(
            store,
            tool_name="manual_signin",
            args=args,
            summary=f"为 {len(args.student_ids)} 名学生补签（任务 {args.task_id}）",
            idempotency_key=f"manual_signin:{args.task_id}:{student_key}",
        )

    return handler


def make_propose_mark_leave(store: PendingActionStore):
    async def handler(args: ProposeMarkLeaveArgs, context: ToolContext) -> ToolResult:
        student_key = ",".join(sorted(args.student_ids))
        return _propose(
            store,
            tool_name="mark_leave",
            args=args,
            summary=f"为 {len(args.student_ids)} 名学生标记请假（任务 {args.task_id}）",
            idempotency_key=f"mark_leave:{args.task_id}:{student_key}",
        )

    return handler
