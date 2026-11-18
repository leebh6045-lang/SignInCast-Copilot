from pathlib import Path

from app.config import Settings
from app.container import build_container
from app.guard.permissions import can_call, describe_matrix
from app.roles import Role


def test_matrix_matches_registered_specs(tmp_path: Path) -> None:
    container = build_container(
        Settings(
            _env_file=None,
            trace_enabled=False,
            signincast_fixtures_dir=Path("data/fixtures/http-sample"),
            db_path=tmp_path / "permissions.db",
        )
    )
    matrix = describe_matrix(container.registry)
    assert matrix["teacher"] == [
        "aggregate_stats",
        "generate_attendance_report",
        "get_classroom_attendance",
        "get_task_records",
        "list_classrooms",
        "list_students",
        "list_tasks",
        "propose_manual_signin",
        "propose_mark_leave",
        "search_runbook",
    ]
    assert matrix["student"] == [
        "get_my_classrooms",
        "get_my_records",
        "search_runbook",
    ]
    assert matrix["service"] == []


def test_can_call() -> None:
    assert can_call(Role.TEACHER, frozenset({Role.TEACHER})) is True
    assert can_call(Role.STUDENT, frozenset({Role.TEACHER})) is False
