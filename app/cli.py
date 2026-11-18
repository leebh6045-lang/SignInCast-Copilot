"""Command line entry point: local demo, live smoke checks and trace inspection."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.business.models import Classroom, SignInTask, Student
from app.config import Settings, get_settings
from app.container import build_container
from app.errors import CopilotError
from app.guard.hitl import ActionStatus
from app.llm.base import LLMMessage
from app.logging import configure_logging
from app.obs.trace_viewer import load_events, render_html, render_text
from app.roles import Role


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signincast-copilot",
        description="SignInCast Copilot 命令行入口（默认 mock 模式，离线可跑）",
    )
    parser.add_argument(
        "query", nargs="?", default="刚才三年级2班那节课的签到情况怎么样？"
    )
    parser.add_argument(
        "--role", default=Role.TEACHER.value, choices=[role.value for role in Role]
    )
    parser.add_argument("--list-tools", action="store_true", help="打印当前可调用工具")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="只读本地录制响应（默认）")
    mode.add_argument("--live", action="store_true", help="调用真实 SignInCast")
    mode.add_argument(
        "--record", action="store_true", help="调用真实接口并录制响应到 data/fixtures/http"
    )
    parser.add_argument(
        "--smoke", action="store_true", help="真实登录 + 拉取课堂/任务/名单，验证契约"
    )
    parser.add_argument(
        "--actions", action="store_true", help="列出待确认的写操作动作"
    )
    parser.add_argument("--confirm", metavar="ACTION_ID", help="确认一个待确认动作")
    parser.add_argument("--execute", metavar="ACTION_ID", help="执行一个已确认动作")
    parser.add_argument(
        "--sample-fixtures", action="store_true", help="使用合成样例数据（离线演示 HITL）"
    )
    parser.add_argument(
        "--session", metavar="SESSION_ID", help="继续一个持久化会话（SQLite）"
    )
    parser.add_argument("--show-trace", metavar="FILE", help="打印 trace 摘要")
    parser.add_argument(
        "--trace-html", nargs=2, metavar=("FILE", "OUT"), help="把 trace 导出为 HTML"
    )
    return parser


def _resolve_settings(args: argparse.Namespace) -> Settings:
    settings = get_settings()
    mode = (
        "live"
        if args.live
        else "record"
        if args.record
        else "mock"
        if args.mock
        else None
    )
    if args.sample_fixtures:
        return settings.model_copy(
            update={
                "signincast_mode": "mock",
                "signincast_fixtures_dir": Path("data/fixtures/http-sample"),
            }
        )
    if mode is None:
        return settings
    return settings.model_copy(update={"signincast_mode": mode})


def _print_tools(registry) -> None:
    for item in registry.describe():
        roles = ",".join(item["roles"])
        print(f"- {item['name']} [{roles}] {item['description']}")


def _print_outcome(outcome) -> None:
    print(f"\nrun_id: {outcome.run_id}")
    for step in outcome.steps:
        names = ", ".join(item.name for item in step.tools) or "-"
        print(f"  step {step.index}: {names}")
    if outcome.error_code:
        print(f"错误: {outcome.error_code} - {outcome.error_message}")
    print(f"\n回答:\n{outcome.answer or '(无)'}")
    print(f"\ntokens: {outcome.usage.total_tokens} | 估算成本: ${outcome.cost_usd:.6f}")
    if outcome.trace_path:
        print(f"trace: {outcome.trace_path}")
    if outcome.pending_action_ids:
        print(f"待确认动作: {', '.join(outcome.pending_action_ids)}")


async def _smoke(container) -> int:
    client = container.client
    started = time.monotonic()
    identity = await client.login()
    print(f"登录成功：role={identity.role} name={identity.name} id={identity.id}")
    classrooms_payload = await client.get("/api/classrooms")
    classrooms = [Classroom.model_validate(item) for item in classrooms_payload or []]
    print(f"课堂：{len(classrooms)} 个")
    for classroom in classrooms[:5]:
        print(f"  - {classroom.id} {classroom.classroomName} [{classroom.status}]")
    if not classrooms:
        print("没有课堂，跳过任务/名单检查")
        return 0
    for classroom in classrooms:
        tasks_payload = await client.get(f"/api/classrooms/{classroom.id}/tasks")
        tasks = [SignInTask.model_validate(item) for item in tasks_payload or []]
        students_payload = await client.get(f"/api/classrooms/{classroom.id}/students")
        students = [Student.model_validate(item) for item in students_payload or []]
        attendance_payload = await client.get(
            f"/api/classrooms/{classroom.id}/attendance"
        )
        attendance = attendance_payload or []
        latest_note = ""
        if tasks:
            latest = max(tasks, key=lambda item: item.startTime or "")
            records = await client.get(f"/api/records/task/{latest.id}")
            latest_note = (
                f"，最近任务「{latest.taskTitle}」记录 {len(records or [])} 条"
            )
        print(
            f"课堂「{classroom.classroomName}」：任务 {len(tasks)} 个、"
            f"学生 {len(students)} 人、学期统计 {len(attendance)} 行{latest_note}"
        )
    print(f"耗时 {round((time.monotonic() - started) * 1000)} ms；契约校验通过")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = _resolve_settings(args)
    configure_logging(settings.log_level)
    try:
        if args.show_trace:
            events = load_events(Path(args.show_trace))
            print(render_text(events))
            return 0
        if args.trace_html:
            source, target = args.trace_html
            events = load_events(Path(source))
            Path(target).write_text(
                render_html(events, title=f"Agent trace - {source}"), encoding="utf-8"
            )
            print(f"HTML trace 已写入 {target}")
            return 0
        container = build_container(settings)
        if args.actions:
            actions = container.pending_store.list_actions(ActionStatus.PENDING)
            if not actions:
                print("没有待确认动作")
            for action in actions:
                print(
                    f"- {action.action_id}  {action.created_at:%H:%M:%S}  "
                    f"{action.summary}  (tool={action.tool_name})"
                )
            return 0
        if args.confirm:
            action = container.pending_store.get(args.confirm)
            confirmed = container.pending_store.confirm(
                args.confirm, action.confirm_token
            )
            print(f"已确认：{confirmed.action_id}  {confirmed.summary}")
            return 0
        if args.execute:
            action = container.pending_store.get(args.execute)
            result = asyncio.run(
                container.action_executor.execute(
                    args.execute, action.confirm_token
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("status") != "failed" else 2
        if args.list_tools:
            _print_tools(container.registry)
            return 0
        if args.smoke:
            return asyncio.run(_smoke(container))
        role = Role.parse(args.role)
        history = []
        if args.session:
            container.session_store.get_or_create(
                args.session, user_id=role.value, role=role
            )
            history = container.session_store.messages(args.session)
        outcome = asyncio.run(
            container.loop.run(args.query, role, history=history)
        )
        if args.session:
            container.session_store.append(
                args.session, LLMMessage(role="user", content=args.query)
            )
            container.session_store.append(
                args.session,
                LLMMessage(
                    role="assistant",
                    content=outcome.answer or outcome.error_message or "",
                ),
            )
        _print_outcome(outcome)
        return 0 if outcome.ok else 2
    except CopilotError as exc:
        print(f"错误：{exc}")
        return 2
    except ValidationError as exc:
        print(f"契约校验失败（线上返回结构变化）：{exc.errors()[:2]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
