"""SQLite-backed conversation store (M2: history only, no summarisation yet)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime

from app.llm.base import LLMMessage
from app.memory.session import Session
from app.roles import Role


class SqliteSessionStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._lock = threading.RLock()

    def get_or_create(self, session_id: str, user_id: str, role: Role) -> Session:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is not None:
                return Session(
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    role=Role(row["role"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            now = datetime.now(UTC)
            session = Session(
                session_id=session_id,
                user_id=user_id,
                role=role,
                created_at=now,
                updated_at=now,
            )
            with self._conn:
                self._conn.execute(
                    "INSERT INTO sessions(session_id, user_id, role, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        session_id,
                        user_id,
                        role.value,
                        now.isoformat(timespec="seconds"),
                        now.isoformat(timespec="seconds"),
                    ),
                )
            return session

    def append(self, session_id: str, message: LLMMessage) -> None:
        with self._lock:
            now = datetime.now(UTC)
            with self._conn:
                self._conn.execute(
                    "INSERT INTO session_messages(session_id, role, content, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        session_id,
                        message.role,
                        message.content,
                        now.isoformat(timespec="seconds"),
                    ),
                )
                self._conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (now.isoformat(timespec="seconds"), session_id),
                )

    def messages(self, session_id: str, limit: int = 20) -> list[LLMMessage]:
        rows = self._conn.execute(
            "SELECT role, content FROM session_messages WHERE session_id = ?"
            " ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        messages = [LLMMessage(role=row["role"], content=row["content"]) for row in rows]
        return messages[-limit:]
