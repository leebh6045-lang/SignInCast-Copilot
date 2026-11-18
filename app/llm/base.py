"""Model abstraction shared by every backend (fake, OpenAI-compatible, local Ollama)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

RoleName = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMMessage:
    role: RoleName
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    reasoning_content: str | None = None


@dataclass(frozen=True)
class LLMDecision:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    reasoning_content: str | None = None


class ChatModel(Protocol):
    """A model must be able to pick tools or answer, and report its token usage."""

    name: str

    async def decide(
        self, messages: Sequence[LLMMessage], tools: Sequence[dict[str, Any]]
    ) -> LLMDecision: ...


def to_openai_messages(messages: Sequence[LLMMessage]) -> list[dict[str, Any]]:
    """Convert internal messages into the OpenAI chat-completions shape."""
    payload: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.role == "tool":
            item["tool_call_id"] = message.tool_call_id or ""
            if message.name:
                item["name"] = message.name
        elif message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.role == "assistant" and message.reasoning_content:
            item["reasoning_content"] = message.reasoning_content
        payload.append(item)
    return payload
