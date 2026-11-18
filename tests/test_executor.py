import asyncio

import pytest

from app.errors import CopilotError, ErrorCode
from app.guard.executor import ActionExecutor
from app.guard.hitl import ActionStatus, InMemoryPendingActionStore


class FakeWriter:
    def __init__(self, *, failed=None, raise_error=None) -> None:
        self.calls = 0
        self._failed = failed or []
        self._raise = raise_error

    async def perform(self, action):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return {"requested": 1, "succeeded": [{"student_id": "1"}], "failed": self._failed}


def _setup(writer):
    store = InMemoryPendingActionStore()
    action = store.propose(
        tool_name="manual_signin",
        args={"task_id": "T1", "student_ids": ["1"]},
        summary="补签 1 人",
    )
    return store, ActionExecutor(store, writer), action


def test_execute_requires_valid_token() -> None:
    _, executor, action = _setup(FakeWriter())
    with pytest.raises(CopilotError) as excinfo:
        asyncio.run(executor.execute(action.action_id, "wrong"))
    assert excinfo.value.code is ErrorCode.ACTION_TOKEN_INVALID


def test_execute_marks_done_and_is_idempotent() -> None:
    writer = FakeWriter()
    store, executor, action = _setup(writer)
    result = asyncio.run(executor.execute(action.action_id, action.confirm_token))
    assert result["status"] == "executed"
    assert writer.calls == 1
    replay = asyncio.run(executor.execute(action.action_id, action.confirm_token))
    assert replay["replayed"] is True
    assert writer.calls == 1
    assert store.get(action.action_id).status is ActionStatus.EXECUTED


def test_partial_failure_keeps_action_retryable() -> None:
    writer = FakeWriter(failed=[{"student_id": "1", "error": "boom"}])
    store, executor, action = _setup(writer)
    result = asyncio.run(executor.execute(action.action_id, action.confirm_token))
    assert result["status"] == "partial"
    assert store.get(action.action_id).status is ActionStatus.CONFIRMED
    executor.writer = FakeWriter()
    retry = asyncio.run(executor.execute(action.action_id, action.confirm_token))
    assert retry["status"] == "executed"


def test_writer_error_is_audited_and_action_stays_confirmed() -> None:
    writer = FakeWriter(raise_error=CopilotError(ErrorCode.TOOL_ERROR, "接口失败"))
    store, executor, action = _setup(writer)
    with pytest.raises(CopilotError):
        asyncio.run(executor.execute(action.action_id, action.confirm_token))
    assert store.get(action.action_id).status is ActionStatus.CONFIRMED
    assert any(item["event"] == "execute_failed" for item in store.audit_log())
