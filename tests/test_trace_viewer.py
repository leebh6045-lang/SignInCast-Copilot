import json
from pathlib import Path

from app.obs.trace_viewer import load_events, render_html, render_text


def _write_trace(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    events = [
        {
            "ts": "2026-11-17T20:00:00.000",
            "event": "run_started",
            "role": "teacher",
            "model": "fake",
        },
        {
            "ts": "2026-11-17T20:00:01.000",
            "event": "tool_result",
            "tool": "list_classrooms",
            "ok": True,
        },
    ]
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in events),
        encoding="utf-8",
    )
    return path


def test_render_text_contains_events(tmp_path: Path) -> None:
    text = render_text(load_events(_write_trace(tmp_path)))
    assert "run_started" in text
    assert "list_classrooms" in text


def test_render_html_escapes_event_names() -> None:
    html = render_html([{"ts": "t", "event": "<script>", "ok": True}], title="trace")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
