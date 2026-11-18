"""Human-readable views of an agent trace: terminal text and standalone HTML."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

_INTERESTING_KEYS = (
    "role",
    "model",
    "input",
    "step",
    "tool",
    "tool_calls",
    "ok",
    "error_code",
    "error_message",
    "content_chars",
    "duration_ms",
    "total_tokens",
    "estimated_cost",
    "steps",
)


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            events.append(json.loads(stripped))
    return events


def render_text(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for event in events:
        stamp = str(event.get("ts", ""))[11:23]
        details = [f"{key}={event[key]}" for key in _INTERESTING_KEYS if key in event]
        lines.append(f"{stamp} {event.get('event', '?'):<16} " + " ".join(details))
    return "\n".join(lines)


def render_html(events: list[dict[str, Any]], *, title: str = "Agent trace") -> str:
    rows: list[str] = []
    for event in events:
        stamp = html.escape(str(event.get("ts", "")))
        name = html.escape(str(event.get("event", "")))
        details = {
            key: event[key] for key in _INTERESTING_KEYS if key in event
        }
        payload = html.escape(json.dumps(details, ensure_ascii=False, default=str))
        rows.append(
            f"<tr><td class='ts'>{stamp}</td><td class='ev'>{name}</td>"
            f"<td class='payload'>{payload}</td></tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", sans-serif;
       margin: 24px; background: #0f172a; color: #e2e8f0; }}
h1 {{ font-size: 18px; font-weight: 600; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border-bottom: 1px solid #1e293b; padding: 6px 8px;
         text-align: left; vertical-align: top; }}
th {{ color: #94a3b8; font-weight: 500; }}
td.ts {{ color: #64748b; white-space: nowrap; }}
td.ev {{ color: #38bdf8; white-space: nowrap; }}
td.payload {{ color: #cbd5e1; word-break: break-all; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<table>
<thead><tr><th>时间</th><th>事件</th><th>详情</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
