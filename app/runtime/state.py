"""Run checkpoints so a long task can resume instead of restarting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.llm.base import LLMMessage


@dataclass
class RunCheckpoint:
    run_id: str
    step_index: int
    messages: list[LLMMessage]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class StateStore(Protocol):
    def save(self, checkpoint: RunCheckpoint) -> None: ...

    def load(self, run_id: str) -> RunCheckpoint | None: ...

    def drop(self, run_id: str) -> None: ...


class InMemoryStateStore:
    """M0 placeholder; M2 persists checkpoints to SQLite."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, RunCheckpoint] = {}

    def save(self, checkpoint: RunCheckpoint) -> None:
        self._checkpoints[checkpoint.run_id] = checkpoint

    def load(self, run_id: str) -> RunCheckpoint | None:
        return self._checkpoints.get(run_id)

    def drop(self, run_id: str) -> None:
        self._checkpoints.pop(run_id, None)
