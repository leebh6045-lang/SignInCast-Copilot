import json

from app.obs.trace import TraceRecorder


def test_trace_redacts_secrets_and_writes_jsonl(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    recorder = TraceRecorder(path)
    recorder.event(
        "run_started",
        api_key="sk-secret",
        nested={"password": "p", "model": "fake"},
    )
    recorder.event("run_finished", ok=True)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["api_key"] == "***"
    assert first["nested"]["password"] == "***"
    assert first["nested"]["model"] == "fake"
    assert len(recorder.events) == 2


def test_trace_without_path_keeps_memory_only() -> None:
    recorder = TraceRecorder(None)
    recorder.event("x", ok=True)
    assert recorder.path is None
    assert recorder.events[0]["ok"] is True
