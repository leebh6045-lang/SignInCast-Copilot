"""SQLite connection with versioned migrations.

Migrations are append-only: never edit an applied version, add a new one.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                action_id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                confirm_token TEXT NOT NULL,
                idempotency_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                executed_at TEXT,
                result_json TEXT
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_actions_idempotency
            ON pending_actions(idempotency_key) WHERE idempotency_key <> ''
            """,
            """
            CREATE TABLE IF NOT EXISTS action_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event TEXT NOT NULL,
                action_id TEXT NOT NULL,
                tool TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            )
            """,
        ],
    ),
    (
        2,
        [
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_session_messages_session
            ON session_messages(session_id, id)
            """,
        ],
    ),
]


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (and migrate) the local SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    migrate(connection)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        row["version"] for row in connection.execute("SELECT version FROM schema_migrations")
    }
    for version, statements in MIGRATIONS:
        if version in applied:
            continue
        with connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat(timespec="seconds")),
            )


def current_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    return int(row["version"] or 0)
