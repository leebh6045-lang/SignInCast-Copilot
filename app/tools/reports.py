"""Report generation tool (Markdown / Excel)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from app.business.models import AttendanceStat, Classroom, SignInRecord
from app.business.reports import build_classroom_report, build_task_report, write_report
from app.business.signincast import SignInCastClient
from app.errors import CopilotError, ErrorCode
from app.tools.base import ToolArgs, ToolContext, ToolResult


class GenerateReportArgs(ToolArgs):
    classroom_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    format: Literal["markdown", "excel"] = "markdown"


def _parse_many(model, payload: Any) -> list[Any]:
    return [model.model_validate(item) for item in payload or []]


def make_generate_report(client: SignInCastClient, report_dir: Path):
    async def handler(args: GenerateReportArgs, context: ToolContext) -> ToolResult:
        try:
            if args.task_id is not None:
                records = _parse_many(
                    SignInRecord, await client.get(f"/api/records/task/{args.task_id}")
                )
                data = build_task_report(args.task_id, records)
                written = write_report(
                    data,
                    report_dir=report_dir,
                    kind="task",
                    identifier=str(args.task_id),
                    fmt=args.format,
                )
            else:
                stats = _parse_many(
                    AttendanceStat,
                    await client.get(f"/api/classrooms/{args.classroom_id}/attendance"),
                )
                name = f"课堂 {args.classroom_id}"
                try:
                    classroom = Classroom.model_validate(
                        await client.get(f"/api/classrooms/{args.classroom_id}")
                    )
                    name = classroom.classroomName
                except (CopilotError, ValidationError):
                    pass
                data = build_classroom_report(args.classroom_id, name, stats)
                written = write_report(
                    data,
                    report_dir=report_dir,
                    kind="classroom",
                    identifier=str(args.classroom_id),
                    fmt=args.format,
                )
        except CopilotError as exc:
            return ToolResult(
                ok=False, error_code=exc.code.value, error_message=exc.message
            )
        except (ValidationError, OSError, ValueError) as exc:
            return ToolResult(
                ok=False,
                error_code=ErrorCode.TOOL_ERROR.value,
                error_message=f"报告生成失败：{type(exc).__name__}: {exc}",
            )
        return ToolResult(ok=True, data=written)

    return handler
