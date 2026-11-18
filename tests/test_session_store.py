from pathlib import Path

from app.llm.base import LLMMessage
from app.roles import Role
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite import connect, current_version


def test_migration_version_is_two(tmp_path: Path) -> None:
    assert current_version(connect(tmp_path / "s.db")) == 2


def test_history_persists_across_restart(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    store = SqliteSessionStore(connect(db))
    session = store.get_or_create("s1", user_id="demo", role=Role.TEACHER)
    assert session.session_id == "s1"
    store.append("s1", LLMMessage(role="user", content="第一问"))
    store.append("s1", LLMMessage(role="assistant", content="第一答"))

    reloaded = SqliteSessionStore(connect(db))
    messages = reloaded.messages("s1")
    assert [message.content for message in messages] == ["第一问", "第一答"]
    assert reloaded.get_or_create("s1", "demo", Role.TEACHER).role is Role.TEACHER


def test_messages_limit_returns_latest(tmp_path: Path) -> None:
    store = SqliteSessionStore(connect(tmp_path / "s.db"))
    store.get_or_create("s1", "demo", Role.TEACHER)
    for index in range(5):
        store.append("s1", LLMMessage(role="user", content=f"q{index}"))
    messages = store.messages("s1", limit=2)
    assert [message.content for message in messages] == ["q3", "q4"]


def test_unknown_session_returns_empty(tmp_path: Path) -> None:
    store = SqliteSessionStore(connect(tmp_path / "s.db"))
    assert store.messages("missing") == []
