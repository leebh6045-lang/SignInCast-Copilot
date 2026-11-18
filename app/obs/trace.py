"""Append-only JSONL trace so every decision, call and failure is reproducible."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "confirm_token",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _SENSITIVE_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class TraceRecorder:
    """Writes one JSON object per line; usable without a file for tests."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self.events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path | None:
        return self._path

    def event(self, event: str, **fields: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": event,
            **_redact(fields),
        }
        self.events.append(record)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record
