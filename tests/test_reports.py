import asyncio
from pathlib import Path

from openpyxl import load_workbook

from app.config import Settings
from app.container import build_container
from app.errors import ErrorCode
from app.roles import Role
from app.tools.base import ToolContext


def _invoke(tool: str, args: dict, role: Role, root: Path):
    settings = Settings(
        _env_file=None,
        trace_enabled=False,
        signincast_fixtures_dir=Path("data/fixtures/http-sample"),
        db_path=root / "reports.db",
        report_dir=root / "reports",
    )
    container = build_container(settings)
    result = asyncio.run(
        container.registry.invoke(tool, args, ToolContext(role=role))
    )
    return result, settings


def test_task_markdown_report(tmp_path: Path) -> None:
    result, settings = _invoke(
        "generate_attendance_report",
        {"classroom_id": 1, "task_id": 103, "format": "markdown"},
        Role.TEACHER,
        tmp_path,
    )
    assert result.ok, result.error_message
    path = Path(result.data["path"])
    assert path.is_file()
    assert path.parent == settings.report_dir.resolve()
    content = path.read_text(encoding="utf-8")
    assert "签到任务报告" in content
    assert "签到率" in content
    assert "| 学生 |" in content


def test_task_excel_report(tmp_path: Path) -> None:
    result, _ = _invoke(
        "generate_attendance_report",
        {"classroom_id": 1, "task_id": 103, "format": "excel"},
        Role.TEACHER,
        tmp_path,
    )
    assert result.ok, result.error_message
    workbook = load_workbook(result.data["path"])
    sheet = workbook.active
    assert sheet.max_row == 13
    assert sheet.cell(row=1, column=1).value == "学生"


def test_classroom_report(tmp_path: Path) -> None:
    result, _ = _invoke(
        "generate_attendance_report",
        {"classroom_id": 1, "format": "markdown"},
        Role.TEACHER,
        tmp_path,
    )
    assert result.ok, result.error_message
    content = Path(result.data["path"]).read_text(encoding="utf-8")
    assert "课堂考勤汇总" in content


def test_student_cannot_generate_report(tmp_path: Path) -> None:
    result, _ = _invoke(
        "generate_attendance_report",
        {"classroom_id": 1, "format": "markdown"},
        Role.STUDENT,
        tmp_path,
    )
    assert result.ok is False
    assert result.error_code == ErrorCode.TOOL_PERMISSION_DENIED.value


def test_missing_task_returns_error(tmp_path: Path) -> None:
    result, _ = _invoke(
        "generate_attendance_report",
        {"classroom_id": 1, "task_id": 999, "format": "markdown"},
        Role.TEACHER,
        tmp_path,
    )
    assert result.ok is False
    assert result.error_code == ErrorCode.TOOL_ERROR.value
