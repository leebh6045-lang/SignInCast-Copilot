"""Deterministic attendance statistics; numbers are computed, never guessed."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import Field

from app.tools.base import ToolArgs, ToolContext, ToolResult

RecordStatus = Literal["SUCCESS", "FAIL", "LEAVE", "MAKEUP"]


class RecordIn(ToolArgs):
    student_id: str = Field(min_length=1, max_length=64)
    status: RecordStatus
    method: str | None = None
    failure_reason: str | None = None


class AggregateStatsArgs(ToolArgs):
    records: list[RecordIn] = Field(default_factory=list, max_length=500)
    expected_count: int | None = Field(default=None, ge=0)


def compute_attendance_stats(
    records: list[RecordIn] | list[dict[str, Any]],
    expected_count: int | None = None,
) -> dict[str, Any]:
    parsed = [
        item if isinstance(item, RecordIn) else RecordIn.model_validate(item)
        for item in records
    ]
    expected = expected_count if expected_count is not None else len(parsed)
    statuses = Counter(item.status for item in parsed)
    signed = statuses.get("SUCCESS", 0) + statuses.get("MAKEUP", 0)
    leave = statuses.get("LEAVE", 0)
    failed = statuses.get("FAIL", 0)
    absent = max(expected - signed - leave, 0)
    denominator = expected - leave
    rate = round(signed / denominator, 4) if denominator > 0 else 0.0
    reasons = Counter(
        item.failure_reason
        for item in parsed
        if item.status == "FAIL" and item.failure_reason
    )
    return {
        "expected": expected,
        "recorded": len(parsed),
        "signed": signed,
        "leave": leave,
        "failed": failed,
        "absent": absent,
        "attendance_rate": rate,
        "failure_reasons": dict(sorted(reasons.items())),
        "data_inconsistent": expected < len(parsed),
    }


def make_aggregate_stats():
    async def handler(args: AggregateStatsArgs, context: ToolContext) -> ToolResult:
        stats = compute_attendance_stats(args.records, args.expected_count)
        return ToolResult(ok=True, data=stats)

    return handler
