"""Composition root: the only place that wires concrete implementations together."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.business.signincast import SignInCastClient
from app.business.transport import (
    LiveTransport,
    MockTransport,
    RecordingTransport,
    Transport,
)
from app.business.writer import SignInCastWriter
from app.config import Settings, get_settings
from app.errors import CopilotError, ErrorCode
from app.guard.executor import ActionExecutor
from app.guard.hitl import PendingActionStore
from app.llm.base import ChatModel
from app.llm.fake import FakeChatModel, demo_policy
from app.llm.openai_compat import OpenAICompatibleModel
from app.rag.retriever import HybridRetriever
from app.roles import Role
from app.runtime.loop import AgentLoop
from app.storage.hitl_store import SqlitePendingActionStore
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite import connect
from app.tools.actions import (
    ProposeManualSigninArgs,
    ProposeMarkLeaveArgs,
    make_propose_manual_signin,
    make_propose_mark_leave,
)
from app.tools.base import ToolSpec
from app.tools.business import (
    GetClassroomAttendanceArgs,
    GetTaskRecordsArgs,
    ListClassroomsArgs,
    ListStudentsArgs,
    ListTasksArgs,
    make_get_classroom_attendance,
    make_get_task_records,
    make_list_classrooms,
    make_list_students,
    make_list_tasks,
)
from app.tools.knowledge import SearchRunbookArgs, make_search_runbook
from app.tools.registry import ToolRegistry
from app.tools.reports import GenerateReportArgs, make_generate_report
from app.tools.stats import AggregateStatsArgs, make_aggregate_stats
from app.tools.student import (
    GetMyClassroomsArgs,
    GetMyRecordsArgs,
    make_get_my_classrooms,
    make_get_my_records,
)


@dataclass
class Container:
    settings: Settings
    registry: ToolRegistry
    model: ChatModel
    pending_store: PendingActionStore
    action_executor: ActionExecutor
    session_store: SqliteSessionStore
    retriever: HybridRetriever
    client: SignInCastClient
    loop: AgentLoop


def build_model(settings: Settings) -> ChatModel:
    if settings.llm_provider == "fake":
        return FakeChatModel(demo_policy())
    if settings.llm_provider == "openai_compat":
        if not settings.llm_api_key.get_secret_value():
            raise CopilotError(
                ErrorCode.CONFIG_ERROR,
                "COPILOT_LLM_API_KEY 未配置：请写入 .env，或把 provider 切回 fake",
            )
        return OpenAICompatibleModel(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
        )
    raise CopilotError(
        ErrorCode.CONFIG_ERROR, f"unsupported llm provider: {settings.llm_provider!r}"
    )


def build_transport(settings: Settings) -> Transport:
    if settings.signincast_mode == "mock":
        return MockTransport(settings.signincast_fixtures_dir)
    live = LiveTransport(settings.signincast_base_url, settings.signincast_timeout_s)
    if settings.signincast_mode == "record":
        return RecordingTransport(live, settings.signincast_fixtures_dir)
    return live


def build_client(settings: Settings) -> SignInCastClient:
    if settings.signincast_mode != "mock" and (
        not settings.signincast_username
        or not settings.signincast_password.get_secret_value()
    ):
        raise CopilotError(
            ErrorCode.CONFIG_ERROR,
            (
                "SignInCast 凭据未配置：请在 .env 填写 "
                "COPILOT_SIGNINCAST_USERNAME / COPILOT_SIGNINCAST_PASSWORD，"
                "或使用 mock 模式离线运行。"
            ),
        )
    return SignInCastClient(
        base_url=settings.signincast_base_url,
        username=settings.signincast_username,
        password=settings.signincast_password.get_secret_value(),
        transport=build_transport(settings),
        max_retries=settings.signincast_max_retries,
    )


def build_registry(
    settings: Settings,
    client: SignInCastClient,
    pending_store: PendingActionStore,
    retriever: HybridRetriever,
) -> ToolRegistry:
    registry = ToolRegistry(settings)

    registry.register(
        ToolSpec(
            name="list_classrooms",
            description="列出当前教师名下的课堂（id、名称、课号、状态）。查考勤前先用它定位课堂。",
            args_model=ListClassroomsArgs,
            handler=make_list_classrooms(client),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="list_students",
            description="列出某个课堂的学生名单（学号与姓名）。用于核对名单或解读学生相关结果。",
            args_model=ListStudentsArgs,
            handler=make_list_students(client),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="list_tasks",
            description=(
                "列出某个课堂的签到任务（按开始时间倒序）。"
                "需要 task_id 时先用本工具；不要凭猜测填 task_id。"
            ),
            args_model=ListTasksArgs,
            handler=make_list_tasks(client),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="get_task_records",
            description=(
                "查询某次签到任务的全部记录，并在服务端本地完成统计"
                "（成功/失败/签到率/失败原因/告警数）。"
                "回答任何考勤数字前必须调用本工具，直接引用 summary。"
            ),
            args_model=GetTaskRecordsArgs,
            handler=make_get_task_records(client),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="get_classroom_attendance",
            description=(
                "查询整个课堂的学期考勤统计（每个学生的总任务数、成功/失败/请假/缺勤）。"
                "用于跨任务汇总与“谁需要关注”类问题。"
            ),
            args_model=GetClassroomAttendanceArgs,
            handler=make_get_classroom_attendance(client),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="aggregate_stats",
            description=(
                "对一小段签到记录做确定性统计。仅当 get_task_records 的 summary 不够用时使用。"
            ),
            args_model=AggregateStatsArgs,
            handler=make_aggregate_stats(),
            allowed_roles=frozenset({Role.TEACHER}),
        )
    )
    registry.register(
        ToolSpec(
            name="search_runbook",
            description=(
                "检索考勤规则、常见问题与操作手册，返回带来源的知识片段。"
                "用于回答“为什么签到失败”“怎么补签”“地理围栏规则是什么”等问题。"
            ),
            args_model=SearchRunbookArgs,
            handler=make_search_runbook(retriever, settings.rag_top_k),
            allowed_roles=frozenset({Role.TEACHER, Role.STUDENT}),
        )
    )
    registry.register(
        ToolSpec(
            name="propose_manual_signin",
            description=(
                "生成待人工确认的补签动作，不会立即执行。"
                "仅在用户明确要求补签时调用；返回 action_id 与摘要，"
                "由用户在界面确认后系统才执行。"
            ),
            args_model=ProposeManualSigninArgs,
            handler=make_propose_manual_signin(pending_store),
            allowed_roles=frozenset({Role.TEACHER}),
            read_only=False,
        )
    )
    registry.register(
        ToolSpec(
            name="propose_mark_leave",
            description=(
                "生成待人工确认的请假标记动作，不会立即执行。"
                "仅在用户明确要求标记请假时调用；由用户确认后系统才执行。"
            ),
            args_model=ProposeMarkLeaveArgs,
            handler=make_propose_mark_leave(pending_store),
            allowed_roles=frozenset({Role.TEACHER}),
            read_only=False,
        )
    )
    registry.register(
        ToolSpec(
            name="get_my_classrooms",
            description="学生查询自己加入的课堂。仅学生角色可用，只返回本人数据。",
            args_model=GetMyClassroomsArgs,
            handler=make_get_my_classrooms(client),
            allowed_roles=frozenset({Role.STUDENT}),
        )
    )
    registry.register(
        ToolSpec(
            name="get_my_records",
            description=(
                "学生查询自己的签到记录与个人统计。仅学生角色可用，只返回本人数据；"
                "不要用它查询他人的考勤。"
            ),
            args_model=GetMyRecordsArgs,
            handler=make_get_my_records(client),
            allowed_roles=frozenset({Role.STUDENT}),
        )
    )
    registry.register(
        ToolSpec(
            name="generate_attendance_report",
            description=(
                "把一次签到任务或整个课堂的考勤导出为报告文件（Markdown 或 Excel）。"
                "需要给 classroom_id；给 task_id 则导出单次任务报告。"
                "返回文件路径与摘要，文件写入 data/reports/。"
            ),
            args_model=GenerateReportArgs,
            handler=make_generate_report(client, settings.report_dir),
            allowed_roles=frozenset({Role.TEACHER}),
            read_only=False,
        )
    )
    return registry


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    retriever = HybridRetriever.from_dir(settings.runbook_dir)
    connection = connect(settings.db_path)
    store = SqlitePendingActionStore(connection)
    session_store = SqliteSessionStore(connection)
    client = build_client(settings)
    writer = SignInCastWriter(client)
    executor = ActionExecutor(store, writer)
    registry = build_registry(settings, client, store, retriever)
    model = build_model(settings)
    loop = AgentLoop(model=model, registry=registry, settings=settings)
    return Container(
        settings=settings,
        registry=registry,
        model=model,
        pending_store=store,
        action_executor=executor,
        session_store=session_store,
        retriever=retriever,
        client=client,
        loop=loop,
    )


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container(get_settings())


def reset_container() -> None:
    get_container.cache_clear()
