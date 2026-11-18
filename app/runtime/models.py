"""Run state and result objects returned by the agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.base import LLMDecision, TokenUsage


@dataclass
class ToolRecord:
    call_id: str
    name: str
    arguments: dict[str, Any]
    ok: bool
    error_code: str | None
    content_chars: int
    duration_ms: float


@dataclass
class StepRecord:
    index: int
    decision: LLMDecision
    tools: list[ToolRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "content": self.decision.content[:500],
            "tool_calls": [call.name for call in self.decision.tool_calls],
            "tools": [
                {
                    "name": item.name,
                    "ok": item.ok,
                    "error_code": item.error_code,
                    "content_chars": item.content_chars,
                    "duration_ms": item.duration_ms,
                }
                for item in self.tools
            ],
        }


@dataclass
class RunOutcome:
    run_id: str
    answer: str = ""
    error_code: str | None = None
    error_message: str = ""
    steps: list[StepRecord] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    pending_action_ids: list[str] = field(default_factory=list)
    trace_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and bool(self.answer.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ok": self.ok,
            "answer": self.answer,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "usage": self.usage.to_dict(),
            "cost_usd": round(self.cost_usd, 6),
            "pending_action_ids": list(self.pending_action_ids),
            "trace_path": self.trace_path,
            "steps": [step.to_dict() for step in self.steps],
        }
