from pathlib import Path

from app.guard.hitl import ActionStatus
from app.storage.hitl_store import SqlitePendingActionStore
from app.storage.sqlite import connect, current_version


def _store(db: Path) -> SqlitePendingActionStore:
    return SqlitePendingActionStore(connect(db))


def test_migrations_and_persistence_across_restart(tmp_path: Path) -> None:
    db = tmp_path / "copilot.db"
    connection = connect(db)
    assert current_version(connection) == 2
    store = SqlitePendingActionStore(connection)
    action = store.propose(
        tool_name="manual_signin",
        args={"task_id": "T1", "student_ids": ["1"]},
        summary="补签 1 人",
        idempotency_key="k1",
    )
    reloaded = _store(db).get(action.action_id)
    assert reloaded.args["student_ids"] == ["1"]
    assert reloaded.status is ActionStatus.PENDING


def test_confirm_and_execute_persist(tmp_path: Path) -> None:
    db = tmp_path / "copilot.db"
    store = _store(db)
    action = store.propose(tool_name="manual_signin", args={}, summary="补签")
    store.confirm(action.action_id, action.confirm_token)
    store.mark_executed(action.action_id, {"succeeded": 1})
    reloaded = _store(db).get(action.action_id)
    assert reloaded.status is ActionStatus.EXECUTED
    assert reloaded.executed_at is not None
    assert reloaded.result == {"succeeded": 1}


def test_idempotency_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "copilot.db"
    first = _store(db).propose(
        tool_name="manual_signin", args={}, summary="补签", idempotency_key="same"
    )
    second = _store(db).propose(
        tool_name="manual_signin", args={}, summary="补签", idempotency_key="same"
    )
    assert first.action_id == second.action_id
    assert len(_store(db).list_actions()) == 1


def test_audit_log_is_persisted(tmp_path: Path) -> None:
    db = tmp_path / "copilot.db"
    store = _store(db)
    action = store.propose(tool_name="manual_signin", args={}, summary="补签")
    store.confirm(action.action_id, action.confirm_token)
    store.mark_executed(action.action_id, {"ok": True})
    events = [item["event"] for item in reversed(_store(db).audit_log())]
    assert events == ["proposed", "confirmed", "executed"]
