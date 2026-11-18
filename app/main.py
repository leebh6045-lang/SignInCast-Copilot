"""HTTP entry point: one-shot runs plus the human confirmation endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.config import get_settings
from app.container import get_container
from app.errors import CopilotError, ErrorCode
from app.guard.hitl import ActionStatus
from app.llm.base import LLMMessage
from app.roles import Role

app = FastAPI(title="SignInCast Copilot", version=__version__)
_WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")


class RunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    role: str = "teacher"
    session_id: str | None = Field(default=None, max_length=64)


class ActionRequest(BaseModel):
    confirm_token: str = Field(min_length=1, max_length=64)


def _http_error(exc: CopilotError) -> HTTPException:
    status = 404 if exc.code is ErrorCode.ACTION_NOT_FOUND else 400
    return HTTPException(status_code=status, detail=exc.to_dict())


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_WEB_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.env,
        "llm_provider": settings.llm_provider,
    }


@app.post("/api/run")
async def run_agent(request: RunRequest) -> dict[str, Any]:
    try:
        role = Role.parse(request.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    container = get_container()
    history: list[LLMMessage] = []
    if request.session_id:
        container.session_store.get_or_create(
            request.session_id, user_id=role.value, role=role
        )
        history = container.session_store.messages(request.session_id)
    outcome = await container.loop.run(request.query, role, history=history)
    if request.session_id:
        container.session_store.append(
            request.session_id, LLMMessage(role="user", content=request.query)
        )
        container.session_store.append(
            request.session_id,
            LLMMessage(
                role="assistant",
                content=outcome.answer or outcome.error_message or "",
            ),
        )
    return outcome.to_dict()


@app.get("/api/actions")
async def list_actions(status: str | None = None) -> dict[str, Any]:
    try:
        status_filter = ActionStatus(status) if status else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown status: {status}") from exc
    actions = get_container().pending_store.list_actions(status_filter)
    return {"count": len(actions), "actions": [item.to_dict() for item in actions]}


@app.get("/api/actions/{action_id}")
async def get_action(action_id: str) -> dict[str, Any]:
    # TODO(M2): require an authenticated owner; the token must only reach the proposer.
    try:
        action = get_container().pending_store.get(action_id)
    except CopilotError as exc:
        raise _http_error(exc) from exc
    return action.to_dict(include_token=True)


@app.post("/api/actions/{action_id}/confirm")
async def confirm_action(action_id: str, request: ActionRequest) -> dict[str, Any]:
    try:
        action = get_container().pending_store.confirm(
            action_id, request.confirm_token
        )
    except CopilotError as exc:
        raise _http_error(exc) from exc
    return action.to_dict()


@app.post("/api/actions/{action_id}/execute")
async def execute_action(action_id: str, request: ActionRequest) -> dict[str, Any]:
    try:
        return await get_container().action_executor.execute(
            action_id, request.confirm_token
        )
    except CopilotError as exc:
        raise _http_error(exc) from exc
