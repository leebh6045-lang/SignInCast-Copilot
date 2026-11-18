import asyncio
from pathlib import Path

from app.config import Settings
from app.container import build_container
from app.roles import Role
from app.tools.base import ToolContext


def _invoke(tool: str, args: dict, db_path: Path):
    container = build_container(
        Settings(
            _env_file=None,
            trace_enabled=False,
            signincast_fixtures_dir=Path("data/fixtures/http-sample"),
            db_path=db_path,
        )
    )
    return asyncio.run(
        container.registry.invoke(tool, args, ToolContext(role=Role.TEACHER))
    )


def test_list_classrooms(tmp_path: Path) -> None:
    result = _invoke("list_classrooms", {}, tmp_path / "tools.db")
    assert result.ok
    assert result.data["count"] >= 1
    assert result.data["classrooms"][0]["name"]


def test_list_tasks_is_sorted_newest_first(tmp_path: Path) -> None:
    result = _invoke("list_tasks", {"classroom_id": 1, "limit": 5}, tmp_path / "tools.db")
    assert result.ok
    assert result.data["tasks"][0]["id"] == 103


def test_task_records_summary_is_computed_in_code(tmp_path: Path) -> None:
    result = _invoke("get_task_records", {"task_id": 103}, tmp_path / "tools.db")
    assert result.ok
    summary = result.data["summary"]
    assert summary["total"] == 12
    assert summary["success"] == 8
    assert summary["failure"] == 4
    assert summary["attendance_rate"] == round(8 / 12, 4)
    assert summary["failure_reasons"]["超出围栏"] == 2
    assert summary["failure_reasons"]["设备冲突"] == 1
    assert result.data["records"][0]["student_id"] is not None


def test_classroom_attendance_summary(tmp_path: Path) -> None:
    result = _invoke("get_classroom_attendance", {"classroom_id": 1}, tmp_path / "tools.db")
    assert result.ok
    assert result.data["summary"]["students"] == 12
    assert result.data["needs_attention"]


def test_missing_fixture_returns_tool_error(tmp_path: Path) -> None:
    result = _invoke("list_tasks", {"classroom_id": 999}, tmp_path / "tools.db")
    assert result.ok is False
    assert result.error_code == "TOOL_ERROR"
    assert "没有录制响应" in result.error_message
