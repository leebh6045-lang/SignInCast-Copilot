"""Deterministic model doubles: offline demo and fast, reproducible tests."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.llm.base import LLMDecision, LLMMessage, TokenUsage, ToolCall

Policy = Callable[[Sequence[LLMMessage], Sequence[dict[str, Any]]], LLMDecision]


class FakeChatModel:
    """A model double driven by a policy function. It never touches the network."""

    name = "fake"

    def __init__(self, policy: Policy) -> None:
        self._policy = policy
        self.calls = 0

    async def decide(
        self, messages: Sequence[LLMMessage], tools: Sequence[dict[str, Any]]
    ) -> LLMDecision:
        self.calls += 1
        decision = self._policy(messages, tools)
        prompt_tokens = max(1, sum(len(item.content) for item in messages) // 4)
        completion_tokens = max(
            1, (len(decision.content) + 40 * len(decision.tool_calls)) // 4
        )
        return replace(
            decision,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )


def _load(content: str) -> dict[str, Any]:
    try:
        loaded = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _call(name: str, arguments: dict[str, Any]) -> LLMDecision:
    return LLMDecision(
        tool_calls=(ToolCall(id=f"demo-{name}", name=name, arguments=arguments),)
    )


def _format_answer(task: dict[str, Any], data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    total = int(summary.get("total") or 0)
    if total == 0:
        return "最近这次签到还没有记录。"
    reasons = summary.get("failure_reasons") or {}
    reason_text = "、".join(f"{name} {count} 人" for name, count in reasons.items()) or "无"
    rate = float(summary.get("attendance_rate") or 0.0)
    title = task.get("title") or "最近一次签到"
    start = task.get("start_time") or ""
    when = f"（{start}）" if start else ""
    return (
        f"{title}{when}：共 {total} 条记录，成功 {summary.get('success')}、"
        f"失败 {summary.get('failure')}，签到率 {rate:.1%}。失败原因：{reason_text}。"
        "如需处理异常，我可以先生成待确认的补签清单。"
    )


def demo_policy() -> Policy:
    """Offline two-stage stand-in for the LLM: locate task, read records, answer."""

    def policy(
        messages: Sequence[LLMMessage], tools: Sequence[dict[str, Any]]
    ) -> LLMDecision:
        available = {item["function"]["name"] for item in tools}
        tool_messages = [item for item in messages if item.role == "tool"]
        user_messages = [item for item in messages if item.role == "user"]
        user_text = user_messages[-1].content if user_messages else ""

        fill_intent = "补签" in user_text
        report_intent = "报告" in user_text

        if tool_messages:
            payload = _load(tool_messages[-1].content)
            if payload.get("ok") is False:
                error = payload.get("error") or {}
                return LLMDecision(
                    content=(
                        f"查询失败：{error.get('message', '未知错误')}。"
                        "请确认账号权限或稍后重试。"
                    )
                )

        if "get_my_classrooms" in available:
            return _student_decision(tool_messages)

        if "list_classrooms" not in available:
            return LLMDecision(
                content="当前角色没有查询考勤数据的权限，请使用教师账号登录。"
            )
        if not tool_messages:
            return _call("list_classrooms", {})

        classrooms = (_load(tool_messages[0].content).get("data") or {}).get(
            "classrooms"
        ) or []
        if len(tool_messages) == 1:
            if not classrooms:
                return LLMDecision(
                    content="这个账号下还没有课堂，请先在 SignInCast 创建课堂。"
                )
            return _call("list_tasks", {"classroom_id": classrooms[0]["id"], "limit": 5})

        tasks = (_load(tool_messages[1].content).get("data") or {}).get("tasks") or []
        if len(tool_messages) == 2:
            if not tasks:
                name = classrooms[0].get("name") or "该课堂"
                return LLMDecision(content=f"{name} 还没有签到任务记录。")
            return _call(
                "get_task_records", {"task_id": tasks[0]["id"], "limit": 200}
            )

        data = _load(tool_messages[2].content).get("data") or {}

        if fill_intent and len(tool_messages) == 3:
            failed = [
                record
                for record in (data.get("records") or [])
                if str(record.get("result") or "").upper() == "FAILURE"
                and record.get("student_id") is not None
            ]
            if not failed:
                return LLMDecision(content="这次签到没有失败记录，不需要补签。")
            student_ids = [str(record["student_id"]) for record in failed[:2]]
            return _call(
                "propose_manual_signin",
                {
                    "task_id": str(data.get("task_id")),
                    "student_ids": student_ids,
                    "reason": "签到失败，课后补签",
                },
            )

        if fill_intent and len(tool_messages) >= 4:
            propose = _load(tool_messages[-1].content).get("data") or {}
            return LLMDecision(
                content=(
                    f"已生成待确认的补签动作（{propose.get('action_id')}）："
                    f"{propose.get('summary')}。"
                    "需要你在界面上确认后系统才会执行。"
                )
            )

        if report_intent and len(tool_messages) == 3:
            classroom = classrooms[0]
            task = tasks[0] if tasks else {}
            if not task:
                return LLMDecision(content="这个课堂还没有任务，暂时无法生成报告。")
            return _call(
                "generate_attendance_report",
                {
                    "classroom_id": classroom["id"],
                    "task_id": task["id"],
                    "format": "markdown",
                },
            )

        if report_intent and len(tool_messages) >= 4:
            report = _load(tool_messages[-1].content).get("data") or {}
            return LLMDecision(
                content=(
                    f"报告已生成：{report.get('path')}"
                    f"（{report.get('rows')} 行数据）。"
                    "Markdown 已写入本地；Excel 版本可以把 format 换成 excel。"
                )
            )

        return LLMDecision(content=_format_answer(tasks[0] if tasks else {}, data))

    return policy

def _student_decision(tool_messages: list[LLMMessage]) -> LLMDecision:
    if not tool_messages:
        return _call("get_my_classrooms", {})
    if len(tool_messages) == 1:
        return _call("get_my_records", {})
    data = _load(tool_messages[-1].content).get("data") or {}
    summary = data.get("summary") or {}
    total = int(summary.get("total") or 0)
    success = int(summary.get("success") or 0)
    failure = int(summary.get("failure") or 0)
    rate = float(summary.get("attendance_rate") or 0.0)
    if total == 0:
        return LLMDecision(content="你目前还没有签到记录。")
    return LLMDecision(
        content=(
            f"你共有 {total} 条签到记录：成功 {success}、失败 {failure}，"
            f"出勤率 {rate:.1%}。可以问我“哪次失败了”，我再按记录逐条说明。"
        )
    )
