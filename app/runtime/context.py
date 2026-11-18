"""Context budgeting: keep prompts small while preserving state that matters."""

from __future__ import annotations

from collections.abc import Sequence

from app.llm.base import LLMMessage

_CJK_RANGE = range(0x4E00, 0x9FFF + 1)


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: about one token per CJK char, four ASCII chars per token."""
    if not text:
        return 0
    cjk = sum(1 for char in text if ord(char) in _CJK_RANGE)
    other = len(text) - cjk
    return cjk + (other + 3) // 4


class ContextBuilder:
    """Drops redundant history first, then compresses, then trims tool payloads."""

    def __init__(
        self,
        token_budget: int = 8000,
        max_tool_result_chars: int = 1200,
        keep_last: int = 6,
    ) -> None:
        self._token_budget = token_budget
        self._max_tool_result_chars = max_tool_result_chars
        self._keep_last = keep_last

    def tokens(self, messages: Sequence[LLMMessage]) -> int:
        return sum(estimate_tokens(message.content) for message in messages)

    def compact(self, messages: Sequence[LLMMessage]) -> list[LLMMessage]:
        if not messages:
            return []
        if self.tokens(messages) <= self._token_budget:
            return [self._normalize_one(message) for message in messages]

        head = [self._normalize_one(message) for message in messages[:2]]
        tail_start = max(2, len(messages) - self._keep_last)
        middle = list(messages[2:tail_start])
        tail = [self._normalize_one(message) for message in messages[tail_start:]]

        compacted = list(head)
        if middle:
            lines: list[str] = []
            for message in middle:
                if message.role == "tool":
                    excerpt = message.content[:160].replace("\n", " ")
                    lines.append(f"- 工具 {message.name or '?'}：{excerpt}")
                elif message.tool_calls:
                    names = "、".join(call.name for call in message.tool_calls)
                    lines.append(f"- 请求工具：{names}")
                elif message.content:
                    lines.append(f"- {message.role}：{message.content[:160]}")
            if lines:
                compacted.append(
                    LLMMessage(
                        role="system",
                        content="[历史步骤摘要，原始内容已压缩]\n" + "\n".join(lines),
                    )
                )
        compacted.extend(tail)

        # Extreme case degrades to system+user; documented in limitations.md.
        while self.tokens(compacted) > self._token_budget and len(compacted) > 2:
            compacted.pop(2)
        return compacted

    def _normalize_one(self, message: LLMMessage) -> LLMMessage:
        content = message.content
        if message.role == "tool" and len(content) > self._max_tool_result_chars:
            content = content[: self._max_tool_result_chars] + "... [trimmed]"
        return LLMMessage(
            role=message.role,
            content=content,
            tool_call_id=message.tool_call_id,
            name=message.name,
            tool_calls=message.tool_calls,
            reasoning_content=message.reasoning_content,
        )
