"""Deterministic aggregation shared by tools and reports."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.business.models import SignInRecord

FAILURE_REASON_LABELS = {
    "GESTURE_WRONG": "手势错误",
    "DISTANCE_TOO_FAR": "超出围栏",
    "LOCATION_DENIED": "未授权定位",
    "DEVICE_CONFLICT": "设备冲突",
}


def records_summary(records: list[SignInRecord]) -> dict[str, Any]:
    total = len(records)
    results = Counter((record.result or "UNKNOWN").upper() for record in records)
    success = results.get("SUCCESS", 0)
    failure = results.get("FAILURE", 0)
    reasons = Counter(
        FAILURE_REASON_LABELS.get(record.failureReason, record.failureReason)
        for record in records
        if (record.result or "").upper() == "FAILURE" and record.failureReason
    )
    methods = Counter(record.signInMethod for record in records if record.signInMethod)
    return {
        "total": total,
        "success": success,
        "failure": failure,
        "attendance_rate": round(success / total, 4) if total else 0.0,
        "warning_count": sum(1 for record in records if record.hasWarning),
        "failure_reasons": dict(sorted(reasons.items())),
        "methods": dict(sorted(methods.items())),
    }
