import asyncio

import pytest

from app.business.signincast import SignInCastClient
from app.business.transport import HttpResponse
from app.business.writer import SignInCastWriter
from app.errors import CopilotError, ErrorCode
from app.guard.hitl import PendingAction


class FakeTransport:
    is_offline = False

    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)
        self.requests = []

    async def request(self, request, headers):
        self.requests.append(request)
        if request.path == "/api/auth/login":
            return HttpResponse(
                200,
                {
                    "code": 200,
                    "data": {
                        "token": "t",
                        "id": 1,
                        "username": "u",
                        "name": "n",
                        "role": "TEACHER",
                    },
                },
            )
        return self._responses.pop(0)


def _client(responses: list[HttpResponse]):
    transport = FakeTransport(responses)
    client = SignInCastClient(
        base_url="https://x.test",
        username="u",
        password="p",
        transport=transport,
        max_retries=0,
    )
    return client, transport


def _action(tool_name: str = "manual_signin", **args) -> PendingAction:
    return PendingAction(action_id="a1", tool_name=tool_name, args=args, summary="s")


def _record_body(student_id: int) -> dict:
    return {
        "code": 200,
        "message": "补签成功",
        "data": {
            "id": 99,
            "taskId": 7,
            "studentId": student_id,
            "result": "MANUAL",
            "signInMethod": "MANUAL",
        },
    }


def test_manual_signin_calls_real_post_endpoint() -> None:
    client, transport = _client([HttpResponse(200, _record_body(1))])
    writer = SignInCastWriter(client)
    result = asyncio.run(
        writer.perform(_action(task_id="7", student_ids=["1"], reason="补签"))
    )
    assert result["failed"] == []
    assert result["succeeded"][0]["student_id"] == 1
    posts = [
        request
        for request in transport.requests
        if request.method == "POST" and request.path != "/api/auth/login"
    ]
    assert posts[0].path == "/api/records/task/7/manual/1"


def test_mark_leave_uses_leave_endpoint() -> None:
    client, transport = _client([HttpResponse(200, _record_body(2))])
    writer = SignInCastWriter(client)
    asyncio.run(
        writer.perform(
            _action(tool_name="mark_leave", task_id="7", student_ids=["2"])
        )
    )
    paths = [request.path for request in transport.requests]
    assert "/api/records/task/7/leave/2" in paths


def test_partial_failure_is_reported_per_student() -> None:
    client, _ = _client(
        [
            HttpResponse(200, _record_body(1)),
            HttpResponse(400, {"code": 400, "message": "任务不存在"}),
        ]
    )
    writer = SignInCastWriter(client)
    result = asyncio.run(
        writer.perform(_action(task_id="7", student_ids=["1", "2"]))
    )
    assert len(result["succeeded"]) == 1
    assert result["failed"][0]["student_id"] == "2"


def test_unknown_action_tool_is_rejected() -> None:
    client, _ = _client([])
    writer = SignInCastWriter(client)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(writer.perform(_action(tool_name="delete_all", task_id="7")))
    assert excinfo.value.code is ErrorCode.TOOL_ERROR


def test_missing_student_ids_is_rejected() -> None:
    client, _ = _client([])
    writer = SignInCastWriter(client)
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(writer.perform(_action(task_id="7", student_ids=[])))
    assert excinfo.value.code is ErrorCode.TOOL_INVALID_ARGS
