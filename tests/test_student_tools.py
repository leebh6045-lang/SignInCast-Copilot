import asyncio
from pathlib import Path

from app.config import Settings
from app.container import build_container
from app.errors import ErrorCode
from app.roles import Role
from app.tools.base import ToolContext


def _invoke(tool: str, args: dict, role: Role, db_path: Path):
    container = build_container(
        Settings(
            _env_file=None,
            trace_enabled=False,
            signincast_fixtures_dir=Path("data/fixtures/http-sample"),
            db_path=db_path,
        )
    )
    return asyncio.run(
        container.registry.invoke(tool, args, ToolContext(role=role))
    )


def test_student_reads_own_classrooms(tmp_path: Path) -> None:
    result = _invoke("get_my_classrooms", {}, Role.STUDENT, tmp_path / "s.db")
    assert result.ok
    assert result.data["count"] >= 1
    assert result.data["classrooms"][0]["name"]


def test_student_reads_own_records(tmp_path: Path) -> None:
    result = _invoke("get_my_records", {}, Role.STUDENT, tmp_path / "s.db")
    assert result.ok
    assert result.data["total"] >= 1
    assert result.data["summary"]["total"] == result.data["total"]
    assert result.data["records"][0]["result"] in {"SUCCESS", "FAILURE", "MANUAL", "LEAVE"}


def test_teacher_cannot_use_student_tools(tmp_path: Path) -> None:
    result = _invoke("get_my_records", {}, Role.TEACHER, tmp_path / "s.db")
    assert result.ok is False
    assert result.error_code == ErrorCode.TOOL_PERMISSION_DENIED.value


def test_student_cannot_use_teacher_tools(tmp_path: Path) -> None:
    result = _invoke("get_task_records", {"task_id": 103}, Role.STUDENT, tmp_path / "s.db")
    assert result.ok is False
    assert result.error_code == ErrorCode.TOOL_PERMISSION_DENIED.value
