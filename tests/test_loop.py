import asyncio
from pathlib import Path

from app.config import Settings
from app.container import build_container
from app.errors import ErrorCode
from app.llm.base import LLMDecision, ToolCall
from app.llm.fake import FakeChatModel, demo_policy
from app.roles import Role
from app.runtime.loop import AgentLoop


def _loop(tmp_path, policy, **overrides):
    settings = Settings(
        _env_file=None,
        trace_enabled=False,
        trace_dir=tmp_path / "traces",
        signincast_fixtures_dir=Path("data/fixtures/http-sample"),
        db_path=tmp_path / "loop.db",
        **overrides,
    )
    container = build_container(settings)
    loop = AgentLoop(
        model=FakeChatModel(policy), registry=container.registry, settings=settings
    )
    return loop, container


def test_loop_reaches_answer_through_tools(tmp_path) -> None:
    loop, _ = _loop(tmp_path, demo_policy())
    outcome = asyncio.run(loop.run("刚才那节课的签到情况怎么样？", Role.TEACHER))
    assert outcome.ok
    assert "签到率" in outcome.answer
    assert len(outcome.steps) == 3
    assert [tool.name for tool in outcome.steps[0].tools] == ["list_classrooms"]
    assert [tool.name for tool in outcome.steps[2].tools] == ["get_task_records"]
    assert outcome.usage.total_tokens > 0


def test_permission_denied_is_visible_in_step(tmp_path) -> None:
    def policy(messages, tools):
        if not [item for item in messages if item.role == "tool"]:
            return LLMDecision(
                tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),)
            )
        return LLMDecision(content="没有权限，请使用教师账号。")

    loop, _ = _loop(tmp_path, policy)
    outcome = asyncio.run(loop.run("列出课堂", Role.STUDENT))
    assert outcome.ok
    assert outcome.steps[0].tools[0].error_code == ErrorCode.TOOL_PERMISSION_DENIED.value


def test_step_limit_is_enforced(tmp_path) -> None:
    def policy(messages, tools):
        count = len([item for item in messages if item.role == "tool"])
        return LLMDecision(
            tool_calls=(
                ToolCall(
                    id=f"c{count}",
                    name="search_runbook",
                    arguments={"query": f"签到规则 {count}"},
                ),
            )
        )

    loop, _ = _loop(tmp_path, policy, max_steps=3)
    outcome = asyncio.run(loop.run("查询", Role.TEACHER))
    assert outcome.ok is False
    assert outcome.error_code == ErrorCode.STEP_LIMIT.value


def test_repeated_identical_call_is_stopped(tmp_path) -> None:
    def policy(messages, tools):
        return LLMDecision(
            tool_calls=(
                ToolCall(id="c1", name="search_runbook", arguments={"query": "地理围栏"}),
            )
        )

    loop, _ = _loop(tmp_path, policy)
    outcome = asyncio.run(loop.run("查询", Role.TEACHER))
    assert outcome.error_code == ErrorCode.NO_PROGRESS.value

def test_fabricated_number_is_corrected_then_refused(tmp_path) -> None:
    calls = {"count": 0}

    def policy(messages, tools):
        if not [item for item in messages if item.role == "tool"]:
            return LLMDecision(
                tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),)
            )
        calls["count"] += 1
        return LLMDecision(content="本次共有 999 名学生签到。")

    loop, _ = _loop(tmp_path, policy)
    outcome = asyncio.run(loop.run("有多少学生？", Role.TEACHER))
    assert outcome.ok is False
    assert outcome.error_code == ErrorCode.UNVERIFIED_NUMBER.value
    assert calls["count"] == 2  # 第一次被纠正，第二次仍失败 -> 拒绝输出


def test_derived_percentage_is_accepted(tmp_path) -> None:
    def policy(messages, tools):
        if not [item for item in messages if item.role == "tool"]:
            return LLMDecision(
                tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),)
            )
        return LLMDecision(content="当前有 2 个课堂。")

    loop, _ = _loop(tmp_path, policy)
    outcome = asyncio.run(loop.run("有多少课堂？", Role.TEACHER))
    assert outcome.ok is True

def test_student_demo_flow_uses_only_own_tools(tmp_path) -> None:
    loop, _ = _loop(tmp_path, demo_policy())
    outcome = asyncio.run(loop.run("我这个学期考勤怎么样？", Role.STUDENT))
    assert outcome.ok
    assert "出勤率" in outcome.answer
    tool_names = [tool.name for step in outcome.steps for tool in step.tools]
    assert tool_names == ["get_my_classrooms", "get_my_records"]

def test_numbers_from_user_query_are_allowed(tmp_path) -> None:
    def policy(messages, tools):
        if not [item for item in messages if item.role == "tool"]:
            return LLMDecision(
                tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),)
            )
        return LLMDecision(content="学号 20230104 属于学生账号，我无权补签。")

    loop, _ = _loop(tmp_path, policy)
    outcome = asyncio.run(loop.run("把 20230104 补签一下", Role.STUDENT))
    assert outcome.ok is True
