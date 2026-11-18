"""Attendance report rendering: Markdown and Excel, written under report_dir."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from openpyxl import Workbook
from openpyxl.styles import Font

from app.business.models import AttendanceStat, SignInRecord
from app.business.summary import FAILURE_REASON_LABELS, records_summary

ReportFormat = Literal["markdown", "excel"]


@dataclass
class ReportData:
    title: str
    summary: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-")
    return cleaned or "report"


def build_task_report(task_id: int, records: list[SignInRecord]) -> ReportData:
    summary = records_summary(records)
    task_title = records[0].taskTitle if records else ""
    classroom_name = records[0].classroomName if records else ""
    lines = [
        f"任务：{task_title or f'任务 {task_id}'}",
        f"课堂：{classroom_name or '-'}",
        f"记录数：{summary['total']}，成功：{summary['success']}，失败：{summary['failure']}",
        f"签到率：{summary['attendance_rate']:.1%}，位置告警：{summary['warning_count']} 条",
    ]
    if summary["failure_reasons"]:
        reasons = "、".join(
            f"{name} {count} 条" for name, count in summary["failure_reasons"].items()
        )
        lines.append(f"失败原因：{reasons}")
    rows = [
        [
            record.studentName or "-",
            record.result or "-",
            record.signInMethod or "-",
            FAILURE_REASON_LABELS.get(record.failureReason, record.failureReason) or "-",
            record.distance if record.distance is not None else "-",
            "是" if record.hasWarning else "否",
            record.signedInAt or "-",
        ]
        for record in records
    ]
    return ReportData(
        title=f"签到任务报告 - {task_title or task_id}",
        summary=lines,
        headers=["学生", "结果", "方式", "失败原因", "距离(米)", "位置告警", "签到时间"],
        rows=rows,
    )


def build_classroom_report(
    classroom_id: int, classroom_name: str, stats: list[AttendanceStat]
) -> ReportData:
    total_tasks = sum(item.totalTasks for item in stats)
    success = sum(item.successCount for item in stats)
    failure = sum(item.failureCount for item in stats)
    leave = sum(item.leaveCount for item in stats)
    absent = sum(item.absentCount for item in stats)
    lines = [
        f"课堂：{classroom_name}（id={classroom_id}）",
        f"学生数：{len(stats)}，累计任务数：{total_tasks}",
        f"成功：{success}，失败：{failure}，请假：{leave}，缺勤：{absent}",
    ]
    rows = [
        [
            item.studentName or "-",
            item.username or "-",
            item.totalTasks,
            item.successCount,
            item.failureCount,
            item.leaveCount,
            item.absentCount,
        ]
        for item in sorted(
            stats, key=lambda item: (-item.absentCount, -item.failureCount, item.studentName or "")
        )
    ]
    return ReportData(
        title=f"课堂考勤汇总 - {classroom_name}",
        summary=lines,
        headers=["学生", "学号", "任务数", "成功", "失败", "请假", "缺勤"],
        rows=rows,
    )


def write_report(
    data: ReportData,
    *,
    report_dir: Path,
    kind: str,
    identifier: str,
    fmt: ReportFormat,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "md" if fmt == "markdown" else "xlsx"
    filename = f"{_safe_name(kind)}-{_safe_name(identifier)}-{stamp}.{suffix}"
    target = (report_dir / filename).resolve()
    if report_dir.resolve() != target.parent:
        raise ValueError("report path escapes report_dir")
    if fmt == "markdown":
        target.write_text(_render_markdown(data), encoding="utf-8")
    else:
        _render_excel(data, target)
    return {
        "path": str(target),
        "format": fmt,
        "title": data.title,
        "summary": data.summary,
        "rows": len(data.rows),
    }


def _render_markdown(data: ReportData) -> str:
    lines = [f"# {data.title}", ""]
    lines.extend(f"- {line}" for line in data.summary)
    lines.append("")
    lines.append("| " + " | ".join(data.headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(data.headers)) + " |")
    for row in data.rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    lines.append("")
    return "\n".join(lines)


def _render_excel(data: ReportData, target: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "考勤报告"
    sheet.append(data.headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in data.rows:
        sheet.append(row)
    for index, header in enumerate(data.headers, start=1):
        width = max(12, len(str(header)) * 2)
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    workbook.save(target)
