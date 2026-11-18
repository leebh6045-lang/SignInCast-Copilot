from pathlib import Path

from fastapi.testclient import TestClient


class FakeWriter:
    def __init__(self) -> None:
        self.calls = 0

    async def perform(self, action):
        self.calls += 1
        return {"requested": 1, "succeeded": [{"student_id": "1"}], "failed": []}


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("COPILOT_TRACE_ENABLED", "false")
    monkeypatch.setenv("COPILOT_SIGNINCAST_FIXTURES_DIR", "data/fixtures/http-sample")
    monkeypatch.setenv("COPILOT_DB_PATH", str(tmp_path / "api.db"))
    from app.config import reset_settings_cache
    from app.container import reset_container

    reset_settings_cache()
    reset_container()
    from app.main import app

    return TestClient(app)


def test_ui_is_served(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    index = client.get("/")
    assert index.status_code == 200
    assert "SignInCast Copilot" in index.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_session_history_is_persisted(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    first = client.post(
        "/api/run",
        json={"query": "刚才那节课签到情况怎么样？", "role": "teacher", "session_id": "s1"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/run",
        json={"query": "再总结一下", "role": "teacher", "session_id": "s1"},
    )
    assert second.status_code == 200
    from app.container import get_container

    messages = get_container().session_store.messages("s1")
    assert len(messages) == 4


def test_health(monkeypatch, tmp_path: Path) -> None:
    response = _client(monkeypatch, tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_run_endpoint_with_fake_model(monkeypatch, tmp_path: Path) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/run", json={"query": "刚才那节课签到情况怎么样？", "role": "teacher"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "签到率" in payload["answer"]


def test_action_confirmation_flow_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    from app.container import get_container

    container = get_container()
    action = container.pending_store.propose(
        tool_name="manual_signin",
        args={"task_id": "7", "student_ids": ["1"]},
        summary="补签 1 人",
    )
    detail = client.get(f"/api/actions/{action.action_id}")
    assert detail.status_code == 200
    token = detail.json()["confirm_token"]

    writer = FakeWriter()
    container.action_executor.writer = writer
    executed = client.post(
        f"/api/actions/{action.action_id}/execute", json={"confirm_token": token}
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "executed"
    assert writer.calls == 1

    replay = client.post(
        f"/api/actions/{action.action_id}/execute", json={"confirm_token": token}
    )
    assert replay.json()["replayed"] is True
    assert writer.calls == 1


def test_actions_list_and_pending_filter(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    from app.container import get_container

    get_container().pending_store.propose(
        tool_name="manual_signin", args={"task_id": "7"}, summary="补签"
    )
    response = client.get("/api/actions", params={"status": "pending"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["actions"][0]["status"] == "pending"


def test_execute_with_wrong_token_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    from app.container import get_container

    action = get_container().pending_store.propose(
        tool_name="manual_signin", args={"task_id": "7", "student_ids": ["1"]}, summary="补签"
    )
    response = client.post(
        f"/api/actions/{action.action_id}/execute",
        json={"confirm_token": "wrong-token"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ACTION_TOKEN_INVALID"
