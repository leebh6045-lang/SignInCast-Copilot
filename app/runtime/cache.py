"""In-run cache for read-only tool results (latency and repeated-work reduction)."""

from __future__ import annotations

import json
from typing import Any

from app.tools.base import ToolResult


class ToolResultCache:
    def __init__(self) -> None:
        self._items: dict[str, ToolResult] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(name: str, arguments: dict[str, Any]) -> str:
        return name + ":" + json.dumps(
            arguments, sort_keys=True, ensure_ascii=False, default=str
        )

    def get(self, name: str, arguments: dict[str, Any]) -> ToolResult | None:
        cached = self._items.get(self.key(name, arguments))
        if cached is None:
            self.misses += 1
            return None
        self.hits += 1
        return cached

    def put(self, name: str, arguments: dict[str, Any], result: ToolResult) -> None:
        self._items[self.key(name, arguments)] = result

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._items)}
