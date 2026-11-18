"""Student-only read tools: own classrooms and own attendance records."""

from __future__ import annotations

from pydantic import Field, ValidationError

from app.business.models import Classroom, SignInRecord
from app.business.signincast import SignInCastClient
from app.business.summary import FAILURE_REASON_LABELS, records_summary
from app.errors import CopilotError, ErrorCode
from app.tools.base import ToolArgs, ToolContext, ToolResult


class GetMyClassroomsArgs(ToolArgs):
    limit: int = Field(default=10, ge=1, le=50)


class GetMyRecordsArgs(ToolArgs):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


def _failure(exc: CopilotError) -> ToolResult:
    return ToolResult(ok=False, error_code=exc.code.value, error_message=exc.message)


def make_get_my_classrooms(client: SignInCastClient):
    async def handler(args: GetMyClassroomsArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get("/api/classrooms/my")
            classrooms = [Classroom.model_validate(item) for item in payload or []]
        except CopilotError as exc:
            return _failure(exc)
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                error_code=ErrorCode.TOOL_ERROR.value,
                error_message=f"课堂响应结构不符合约定：{exc.errors()[:1]}",
            )
        items = [
            {
                "id": item.id,
                "name": item.classroomName,
                "class_code": item.classCode,
                "status": item.status,
                "teacher_name": item.teacherName,
            }
            for item in sorted(classrooms, key=lambda item: item.id)
        ][: args.limit]
        return ToolResult(ok=True, data={"count": len(items), "classrooms": items})

    return handler


def make_get_my_records(client: SignInCastClient):
    async def handler(args: GetMyRecordsArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get("/api/records/my")
            records = [SignInRecord.model_validate(item) for item in payload or []]
        except CopilotError as exc:
            return _failure(exc)
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                error_code=ErrorCode.TOOL_ERROR.value,
                error_message=f"记录响应结构不符合约定：{exc.errors()[:1]}",
            )
        summary = records_summary(records)
        ordered = sorted(records, key=lambda item: (item.signedInAt or "", item.id), reverse=True)
        window = ordered[args.offset : args.offset + args.limit]
        items = [
            {
                "task_title": record.taskTitle,
                "classroom_name": record.classroomName,
                "result": record.result,
                "method": record.signInMethod,
                "failure_reason": FAILURE_REASON_LABELS.get(
                    record.failureReason, record.failureReason
                ),
                "signed_in_at": record.signedInAt,
                "has_warning": record.hasWarning,
            }
            for record in window
        ]
        return ToolResult(
            ok=True,
            data={
                "total": len(records),
                "returned": len(items),
                "offset": args.offset,
                "summary": summary,
                "records": items,
            },
        )

    return handler
