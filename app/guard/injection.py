"""Prompt-injection guard for untrusted text (retrieved docs, tool payloads)."""

from __future__ import annotations

import re

_SUSPICIOUS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"忽略(以上|之前|前面|上述)(的)?(所有)?(指令|要求|规则|设定)",
        r"system\s*[:：]",
        r"reveal\s+.*(prompt|instruction)",
        r"你现在是|从现在开始你",
        r"开发者模式|jailbreak",
    )
)


def scan_untrusted(text: str) -> bool:
    """True when untrusted text looks like it tries to issue instructions."""
    return any(pattern.search(text or "") for pattern in _SUSPICIOUS)


def wrap_untrusted(text: str, *, source: str) -> str:
    """Delimit retrieved text so the model treats it as data, not instructions."""
    return f"[资料开始｜{source}]\n{text}\n[资料结束]"
