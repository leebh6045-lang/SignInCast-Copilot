"""Answer verification: no fabricated numbers, no internal payload leakage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_SMALL_NUMBER = 5.0
_RATIO_TOLERANCE = 0.003


@dataclass
class VerificationResult:
    ok: bool
    problems: list[str] = field(default_factory=list)


def collect_numbers(texts: list[str] | tuple[str, ...]) -> set[float]:
    numbers: set[float] = set()
    for text in texts:
        for match in _NUMBER.findall(text or ""):
            try:
                numbers.add(round(float(match), 4))
            except ValueError:
                continue
    return numbers


def _percent_is_supported(value: float, numbers: set[float]) -> bool:
    ratio = round(value / 100, 4)
    if ratio in numbers or round(value, 4) in numbers:
        return True
    values = sorted(numbers)
    for numerator in values:
        for denominator in values:
            if denominator == 0 or numerator == denominator:
                continue
            if abs(numerator / denominator - ratio) <= _RATIO_TOLERANCE:
                return True
    return False


def _percent_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in _PERCENT.finditer(text)]


def verify_answer(
    answer: str, *, tool_numbers: set[float] | None = None
) -> VerificationResult:
    """Check structure always; check number provenance when tool_numbers is given."""
    text = (answer or "").strip()
    if not text:
        return VerificationResult(False, ["回答为空"])
    if text.startswith("{") and '"ok"' in text:
        return VerificationResult(False, ["回答中泄漏了工具原始 JSON"])
    if tool_numbers is None:
        return VerificationResult(True)

    problems: list[str] = []
    spans = _percent_spans(text)
    for match in _PERCENT.finditer(text):
        value = float(match.group(1))
        if not _percent_is_supported(value, tool_numbers):
            problems.append(f"百分比 {match.group(0)} 无法由工具结果推出")
    for match in _NUMBER.finditer(text):
        start = match.start()
        if any(span_start <= start < span_end for span_start, span_end in spans):
            continue
        value = float(match.group(0))
        if abs(value) < _SMALL_NUMBER:
            continue
        if round(value, 4) not in tool_numbers:
            problems.append(f"数字 {match.group(0)} 未出现在工具结果中")
    return VerificationResult(not problems, problems)
