"""Mask personal fields in recorded fixtures so they can be committed safely.

Only personal identifiers are changed; IDs, timestamps, results and classroom
names stay intact so the recorded data still exercises the real code paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MASK = "****"


def _mask_username(value: Any) -> str:
    text = str(value or "")
    if len(text) >= 6:
        return f"{text[:2]}{MASK}{text[-2:]}"
    return MASK


def _student_label(student_id: Any) -> str:
    return f"学生{student_id}" if student_id is not None else "学生"


def _desensitize_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "studentName" in result:
        result["studentName"] = _student_label(result.get("studentId"))
    if "username" in result:
        result["username"] = _mask_username(result["username"])
        if result.get("name"):
            result["name"] = _student_label(result.get("id"))
    if "teacherName" in result:
        result["teacherName"] = "教师"
    if "joinCode" in result:
        result["joinCode"] = MASK
    if "studentAvatar" in result:
        result["studentAvatar"] = None
    return result


def desensitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied payload with personal fields masked (idempotent)."""
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    body = result.get("response", {}).get("body") or {}
    data = body.get("data")
    if isinstance(data, list):
        body["data"] = [
            _desensitize_row(row) if isinstance(row, dict) else row for row in data
        ]
    meta = result.setdefault("meta", {})
    meta["desensitized"] = True
    return result


def desensitize_dir(directory: Path) -> int:
    """Mask every JSON fixture in a directory; returns the number processed."""
    changed = 0
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(
            json.dumps(desensitize_payload(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        changed += 1
    return changed
