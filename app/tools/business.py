"""Read-only tools backed by the real SignInCast REST API.

Server endpoints return full lists (no pagination), so every tool applies its own
limit/offset window and returns a compact, model-friendly payload. Numbers that
matter (counts, rates, failure reasons) are computed here in code, never by the
model.
"""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError

from app.business.models import (
    AttendanceStat,
    Classroom,
    SignInRecord,
    SignInTask,
    Student,
)
from app.business.signincast import SignInCastClient
from app.business.summary import records_summary
from app.errors import CopilotError, ErrorCode
from app.tools.base import ToolArgs, ToolContext, ToolResult

T = TypeVar("T", bound=BaseModel)


class ListClassroomsArgs(ToolArgs):
    pass


class ListStudentsArgs(ToolArgs):
    classroom_id: int = Field(gt=0)


class ListTasksArgs(ToolArgs):
    classroom_id: int = Field(gt=0)
    limit: int = Field(default=10, ge=1, le=50)


class GetTaskRecordsArgs(ToolArgs):
    task_id: int = Field(gt=0)
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    result: Literal["ALL", "SUCCESS", "FAILURE"] = "ALL"


class GetClassroomAttendanceArgs(ToolArgs):
    classroom_id: int = Field(gt=0)
    limit: int = Field(default=100, ge=1, le=300)
    offset: int = Field(default=0, ge=0)


def _failure(exc: CopilotError) -> ToolResult:
    return ToolResult(ok=False, error_code=exc.code.value, error_message=exc.message)


def _parse_list(model: type[T], payload: Any, *, what: str) -> list[T]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise CopilotError(ErrorCode.TOOL_ERROR, f"{what}响应结构异常：期望数组")
    try:
        return [model.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise CopilotError(
            ErrorCode.TOOL_ERROR,
            f"{what}响应结构不符合约定：{exc.errors()[:1]}",
        ) from exc


def make_list_classrooms(client: SignInCastClient):
    async def handler(args: ListClassroomsArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get("/api/classrooms")
            classrooms = _parse_list(Classroom, payload, what="课堂列表")
        except CopilotError as exc:
            return _failure(exc)
        items = [
            {
                "id": item.id,
                "name": item.classroomName,
                "class_code": item.classCode,
                "status": item.status,
                "created_at": item.createdAt,
            }
            for item in sorted(classrooms, key=lambda item: item.id)
        ]
        return ToolResult(ok=True, data={"count": len(items), "classrooms": items[:50]})

    return handler


def make_list_students(client: SignInCastClient):
    async def handler(args: ListStudentsArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get(f"/api/classrooms/{args.classroom_id}/students")
            students = _parse_list(Student, payload, what="学生名单")
        except CopilotError as exc:
            return _failure(exc)
        items = [
            {"id": item.id, "username": item.username, "name": item.name}
            for item in sorted(students, key=lambda item: (item.username, item.id))
        ]
        return ToolResult(
            ok=True,
            data={
                "classroom_id": args.classroom_id,
                "count": len(items),
                "students": items[:200],
            },
        )

    return handler


def make_list_tasks(client: SignInCastClient):
    async def handler(args: ListTasksArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get(f"/api/classrooms/{args.classroom_id}/tasks")
            tasks = _parse_list(SignInTask, payload, what="签到任务列表")
        except CopilotError as exc:
            return _failure(exc)
        ordered = sorted(tasks, key=lambda item: (item.startTime or "", item.id), reverse=True)
        items = [
            {
                "id": item.id,
                "title": item.taskTitle,
                "start_time": item.startTime,
                "end_time": item.endTime,
                "status": item.status,
                "sign_in_type": item.signInType,
                "location_required": item.locationRequired,
                "distance_limit": item.distanceLimit,
            }
            for item in ordered[: args.limit]
        ]
        return ToolResult(
            ok=True,
            data={
                "classroom_id": args.classroom_id,
                "count": len(tasks),
                "returned": len(items),
                "tasks": items,
            },
        )

    return handler


def make_get_task_records(client: SignInCastClient):
    async def handler(args: GetTaskRecordsArgs, context: ToolContext) -> ToolResult:
        try:
            payload = await client.get(f"/api/records/task/{args.task_id}")
            records = _parse_list(SignInRecord, payload, what="签到记录")
        except CopilotError as exc:
            return _failure(exc)
        if args.result != "ALL":
            records = [
                record
                for record in records
                if (record.result or "").upper() == args.result
            ]
        summary = records_summary(records)
        ordered = sorted(records, key=lambda item: (item.studentName or "", item.id))
        window = ordered[args.offset : args.offset + args.limit]
        items = [
            {
                "student_id": record.studentId,
                "student_name": record.studentName,
                "result": record.result,
                "method": record.signInMethod,
                "failure_reason": record.failureReason,
                "signed_in_at": record.signedInAt,
                "distance": record.distance,
                "has_warning": record.hasWarning,
            }
            for record in window
        ]
        return ToolResult(
            ok=True,
            data={
                "task_id": args.task_id,
                "total": summary["total"],
                "returned": len(items),
                "offset": args.offset,
                "summary": summary,
                "records": items,
            },
        )

    return handler


def make_get_classroom_attendance(client: SignInCastClient):
    async def handler(
        args: GetClassroomAttendanceArgs, context: ToolContext
    ) -> ToolResult:
        try:
            payload = await client.get(
                f"/api/classrooms/{args.classroom_id}/attendance"
            )
            stats = _parse_list(AttendanceStat, payload, what="课堂考勤统计")
        except CopilotError as exc:
            return _failure(exc)
        ordered = sorted(
            stats,
            key=lambda item: (-item.absentCount, -item.failureCount, item.studentName or ""),
        )
        window = ordered[args.offset : args.offset + args.limit]
        summary = {
            "students": len(stats),
            "total_tasks": sum(item.totalTasks for item in stats),
            "success": sum(item.successCount for item in stats),
            "failure": sum(item.failureCount for item in stats),
            "leave": sum(item.leaveCount for item in stats),
            "absent": sum(item.absentCount for item in stats),
        }
        attention = [
            {
                "student_id": item.studentId,
                "name": item.studentName,
                "absent": item.absentCount,
                "failure": item.failureCount,
            }
            for item in ordered
            if item.absentCount > 0 or item.failureCount > 0
        ][:10]
        students = [
            {
                "student_id": item.studentId,
                "username": item.username,
                "name": item.studentName,
                "total_tasks": item.totalTasks,
                "success": item.successCount,
                "failure": item.failureCount,
                "leave": item.leaveCount,
                "absent": item.absentCount,
            }
            for item in window
        ]
        return ToolResult(
            ok=True,
            data={
                "classroom_id": args.classroom_id,
                "summary": summary,
                "needs_attention": attention,
                "returned": len(students),
                "offset": args.offset,
                "students": students,
            },
        )

    return handler
