import asyncio

from app.config import Settings
from app.container import build_container
from app.roles import Role
from app.tools.base import ToolContext


def test_propose_tool_never_leaks_confirm_token(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        trace_enabled=False,
        trace_dir=tmp_path / "traces",
        db_path=tmp_path / "actions.db",
    )
    container = build_container(settings)
    result = asyncio.run(
        container.registry.invoke(
            "propose_manual_signin",
            {"task_id": "T1", "student_ids": ["1", "2"], "reason": "请假未补签"},
            ToolContext(role=Role.TEACHER),
        )
    )
    assert result.ok is True
    assert "confirm_token" not in str(result.data)
    assert result.meta["pending_action_id"] == result.data["action_id"]


def test_student_cannot_propose(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        trace_enabled=False,
        trace_dir=tmp_path / "traces",
        db_path=tmp_path / "actions.db",
    )
    container = build_container(settings)
    result = asyncio.run(
        container.registry.invoke(
            "propose_manual_signin",
            {"task_id": "T1", "student_ids": ["1"], "reason": "请假未补签"},
            ToolContext(role=Role.STUDENT),
        )
    )
    assert result.ok is False
    assert result.error_code == "TOOL_PERMISSION_DENIED"
