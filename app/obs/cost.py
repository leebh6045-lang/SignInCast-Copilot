"""Token accounting and approximate cost so runs stay cheap and comparable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.llm.base import TokenUsage


@dataclass
class CostTracker:
    prompt_price_per_mtok: float = 0.5
    completion_price_per_mtok: float = 2.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def record(self, usage: TokenUsage) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost(self) -> float:
        return (
            self.prompt_tokens / 1_000_000 * self.prompt_price_per_mtok
            + self.completion_tokens / 1_000_000 * self.completion_price_per_mtok
        )

    def summary(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
        }
