import pytest

from app.errors import CopilotError, ErrorCode
from app.guard.hitl import ActionStatus, InMemoryPendingActionStore


def _store_with_action():
    store = InMemoryPendingActionStore()
    action = store.propose(
        tool_name="manual_signin",
        args={"task_id": "T1", "student_ids": ["1"]},
        summary="补签 1 人",
        idempotency_key="k1",
    )
    return store, action


def test_propose_is_idempotent() -> None:
    store, action = _store_with_action()
    again = store.propose(
        tool_name="manual_signin",
        args={"task_id": "T1", "student_ids": ["1"]},
        summary="补签 1 人",
        idempotency_key="k1",
    )
    assert again.action_id == action.action_id
    assert [item["event"] for item in reversed(store.audit_log())] == [
        "proposed",
        "proposed_duplicate",
    ]


def test_wrong_token_is_rejected() -> None:
    store, action = _store_with_action()
    with pytest.raises(CopilotError) as excinfo:
        store.confirm(action.action_id, "wrong-token")
    assert excinfo.value.code is ErrorCode.ACTION_TOKEN_INVALID


def test_execute_requires_confirmation() -> None:
    store, action = _store_with_action()
    with pytest.raises(CopilotError) as excinfo:
        store.mark_executed(action.action_id, {"ok": True})
    assert excinfo.value.code is ErrorCode.ACTION_STATE_INVALID


def test_confirm_and_execute_flow() -> None:
    store, action = _store_with_action()
    store.confirm(action.action_id, action.confirm_token)
    again = store.confirm(action.action_id, action.confirm_token)
    assert again.status is ActionStatus.CONFIRMED
    executed = store.mark_executed(action.action_id, {"ok": True})
    assert executed.status is ActionStatus.EXECUTED
    assert executed.result == {"ok": True}
    assert [item["event"] for item in reversed(store.audit_log())] == [
        "proposed",
        "confirmed",
        "confirmed_duplicate",
        "executed",
    ]


def test_list_actions_filters_by_status() -> None:
    store, first = _store_with_action()
    second = store.propose(tool_name="mark_leave", args={}, summary="请假")
    store.confirm(first.action_id, first.confirm_token)
    pending = store.list_actions(ActionStatus.PENDING)
    confirmed = store.list_actions(ActionStatus.CONFIRMED)
    assert [item.action_id for item in pending] == [second.action_id]
    assert [item.action_id for item in confirmed] == [first.action_id]
