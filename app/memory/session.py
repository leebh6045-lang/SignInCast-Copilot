"""Conversation memory: session-scoped history (M2 adds compaction/preferences)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.llm.base import LLMMessage
from app.roles import Role


@dataclass
class Session:
    session_id: str
    user_id: str
    role: Role
    messages: list[LLMMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionStore(Protocol):
    def get_or_create(self, session_id: str, user_id: str, role: Role) -> Session: ...

    def append(self, session_id: str, message: LLMMessage) -> None: ...

    def messages(self, session_id: str, limit: int = 20) -> list[LLMMessage]: ...


class InMemorySessionStore:
    """M0 placeholder; M2 swaps in SQLite behind the same protocol."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str, user_id: str, role: Role) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = Session(session_id=session_id, user_id=user_id, role=role)
            self._sessions[session_id] = session
        return session

    def append(self, session_id: str, message: LLMMessage) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        session.messages.append(message)
        session.updated_at = datetime.now(UTC)

    def messages(self, session_id: str, limit: int = 20) -> list[LLMMessage]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return list(session.messages[-limit:])
