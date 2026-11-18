"""SignInCast REST client: login, JWT lifecycle, envelope parsing, error mapping."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from app.business.models import ApiEnvelope, LoginResult
from app.business.transport import HttpRequest, HttpResponse, Transport
from app.errors import CopilotError, ErrorCode

_LOGIN_PATH = "/api/auth/login"


class SignInCastClient:
    """Thin, explicit client. It never logs passwords or tokens."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        transport: Transport,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._username = username
        self._password = password
        self._transport = transport
        self._max_retries = max(0, max_retries)
        self._token: str | None = None
        self._identity: LoginResult | None = None

    @property
    def identity(self) -> LoginResult | None:
        return self._identity

    @property
    def is_offline(self) -> bool:
        """True for mock replay: writing is impossible, and should say so clearly."""
        return self._transport.is_offline

    async def login(self) -> LoginResult:
        if self._transport.is_offline:
            self._token = "offline-token"
            self._identity = LoginResult(
                token="offline-token",
                id=0,
                username="offline-teacher",
                name="离线演示教师",
                role="TEACHER",
            )
            return self._identity
        if not self._username or not self._password:
            raise CopilotError(
                ErrorCode.CONFIG_ERROR,
                (
                    "COPILOT_SIGNINCAST_USERNAME / COPILOT_SIGNINCAST_PASSWORD 未配置。"
                    "请在 .env 中填写，或使用 mock 模式离线运行。"
                ),
            )
        response = await self._transport.request(
            HttpRequest(
                "POST",
                _LOGIN_PATH,
                json_body={"username": self._username, "password": self._password},
            ),
            headers={},
        )
        envelope = self._parse_envelope(response, action="登录")
        if response.status >= 400 or envelope.code != 200:
            raise CopilotError(
                ErrorCode.AUTH_FAILED,
                f"SignInCast 登录失败：{envelope.message or f'HTTP {response.status}'}",
            )
        if not isinstance(envelope.data, dict):
            raise CopilotError(ErrorCode.AUTH_FAILED, "登录响应缺少 data 字段")
        try:
            identity = LoginResult.model_validate(envelope.data)
        except ValidationError as exc:
            raise CopilotError(
                ErrorCode.AUTH_FAILED, f"登录响应结构不符合约定：{exc.errors()[:1]}"
            ) from exc
        self._identity = identity
        self._token = identity.token
        return identity

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(
        self, path: str, json_body: dict[str, Any] | None = None
    ) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if self._token is None and not self._transport.is_offline:
            await self.login()
        refreshed = self._transport.is_offline
        attempts = self._max_retries + 1
        last_error: CopilotError | None = None
        for attempt in range(attempts):
            headers = self._auth_headers()
            response = await self._transport.request(
                HttpRequest(method, path, params=params or {}, json_body=json_body),
                headers,
            )
            if response.status == 401 and not refreshed:
                # Token expired: refresh once, then retry the same request.
                await self.login()
                refreshed = True
                continue
            if response.status in (401, 403):
                raise CopilotError(
                    ErrorCode.AUTH_FAILED,
                    f"无权访问 {self._base_url}{path}（HTTP {response.status}），请确认账号角色",
                )
            if response.status >= 500:
                last_error = CopilotError(
                    ErrorCode.TOOL_ERROR,
                    f"SignInCast 服务异常（HTTP {response.status}）",
                    retryable=True,
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(min(0.3 * (2**attempt), 2.0))
                    continue
                raise last_error
            if response.status >= 400:
                message = _body_message(response) or f"HTTP {response.status}"
                raise CopilotError(ErrorCode.TOOL_ERROR, f"请求失败：{message}")
            envelope = self._parse_envelope(response, action=path)
            if envelope.code != 200:
                raise CopilotError(
                    ErrorCode.TOOL_ERROR,
                    f"请求失败：{envelope.message or f'业务码 {envelope.code}'}",
                )
            return envelope.data
        raise last_error or CopilotError(ErrorCode.TOOL_ERROR, f"请求失败：{path}")

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _parse_envelope(response: HttpResponse, *, action: str) -> ApiEnvelope:
        if response.body is None:
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                f"{action}失败：SignInCast 返回非 JSON（HTTP {response.status}）",
            )
        try:
            return ApiEnvelope.model_validate(response.body)
        except ValidationError as exc:
            raise CopilotError(
                ErrorCode.TOOL_ERROR,
                f"{action}失败：响应结构不符合约定：{exc.errors()[:1]}",
            ) from exc


def _body_message(response: HttpResponse) -> str:
    body = response.body or {}
    message = body.get("message")
    return message if isinstance(message, str) else ""
