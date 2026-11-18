import asyncio
from pathlib import Path

import pytest

from app.business.models import ApiEnvelope
from app.business.signincast import SignInCastClient
from app.business.transport import HttpRequest, HttpResponse, MockTransport
from app.errors import CopilotError, ErrorCode


class FakeTransport:
    is_offline = False

    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[tuple[HttpRequest, dict[str, str]]] = []
        self.login_count = 0

    async def request(self, request: HttpRequest, headers) -> HttpResponse:
        self.requests.append((request, dict(headers)))
        if request.path == "/api/auth/login":
            self.login_count += 1
            if request.json_body is None:
                return HttpResponse(400, {"code": 400, "message": "缺少凭据"})
            return HttpResponse(
                200,
                {
                    "code": 200,
                    "message": "登录成功",
                    "data": {
                        "token": f"token-{self.login_count}",
                        "id": 1,
                        "username": "teacher",
                        "name": "教师",
                        "role": "TEACHER",
                    },
                },
            )
        return self._responses.pop(0)


def _client(transport, max_retries: int = 1, *, username="teacher", password="pw"):
    return SignInCastClient(
        base_url="https://example.test",
        username=username,
        password=password,
        transport=transport,
        max_retries=max_retries,
    )


def _envelope(data):
    return HttpResponse(200, {"code": 200, "message": "success", "data": data})


def test_login_then_get_uses_bearer_token() -> None:
    transport = FakeTransport([_envelope([{"id": 1, "classroomName": "数据结构"}])])
    client = _client(transport)
    data = asyncio.run(client.get("/api/classrooms"))
    assert data == [{"id": 1, "classroomName": "数据结构"}]
    assert transport.login_count == 1
    assert transport.requests[0][0].path == "/api/auth/login"
    assert transport.requests[1][1]["Authorization"] == "Bearer token-1"
    assert client.identity is not None
    assert client.identity.role == "TEACHER"


def test_token_expiry_refreshes_once() -> None:
    transport = FakeTransport(
        [HttpResponse(401), _envelope([{"id": 1, "classroomName": "数据结构"}])]
    )
    client = _client(transport)
    data = asyncio.run(client.get("/api/classrooms"))
    assert data
    assert transport.login_count == 2
    assert transport.requests[-1][1]["Authorization"] == "Bearer token-2"


def test_forbidden_maps_to_auth_failed() -> None:
    transport = FakeTransport([HttpResponse(403)])
    client = _client(transport)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.get("/api/classrooms"))
    assert excinfo.value.code is ErrorCode.AUTH_FAILED


def test_server_error_is_retried_then_fails() -> None:
    transport = FakeTransport([HttpResponse(500), HttpResponse(500)])
    client = _client(transport, max_retries=1)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.get("/api/classrooms"))
    assert excinfo.value.code is ErrorCode.TOOL_ERROR
    assert len([item for item in transport.requests if item[0].path != "/api/auth/login"]) == 2


def test_business_error_code_is_mapped() -> None:
    transport = FakeTransport([HttpResponse(200, {"code": 400, "message": "课堂不存在"})])
    client = _client(transport)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.get("/api/classrooms/999"))
    assert "课堂不存在" in excinfo.value.message


def test_non_json_response_is_mapped() -> None:
    transport = FakeTransport([HttpResponse(200, None)])
    client = _client(transport)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.get("/api/classrooms"))
    assert excinfo.value.code is ErrorCode.TOOL_ERROR


def test_missing_credentials_fail_fast() -> None:
    client = _client(FakeTransport([]), username="", password="")
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.login())
    assert excinfo.value.code is ErrorCode.CONFIG_ERROR


def test_offline_mode_needs_no_network() -> None:
    client = _client(MockTransport(Path("data/fixtures/http")))
    identity = asyncio.run(client.login())
    assert identity.role == "TEACHER"
    assert identity.token == "offline-token"


def test_missing_fixture_is_explicit(tmp_path: Path) -> None:
    client = _client(MockTransport(tmp_path))
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(client.get("/api/classrooms"))
    assert "没有录制响应" in excinfo.value.message


def test_envelope_parsing_ignores_unknown_fields() -> None:
    envelope = ApiEnvelope.model_validate(
        {"code": 200, "message": "ok", "data": [], "timestamp": "x", "extra": 1}
    )
    assert envelope.code == 200
