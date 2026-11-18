"""OpenAI-compatible chat model: DeepSeek / Qwen / Zhipu / Kimi / local Ollama."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx

from app.errors import CopilotError, ErrorCode
from app.llm.base import (
    LLMDecision,
    LLMMessage,
    TokenUsage,
    ToolCall,
    to_openai_messages,
)


class OpenAICompatibleModel:
    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max(0, max_retries)

    async def decide(
        self, messages: Sequence[LLMMessage], tools: Sequence[dict[str, Any]]
    ) -> LLMDecision:
        if not self._api_key:
            raise CopilotError(
                ErrorCode.CONFIG_ERROR,
                "COPILOT_LLM_API_KEY 未配置：请写入 .env，或把 provider 切回 fake",
            )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": to_openai_messages(messages),
            "temperature": 0.0,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        last_error: CopilotError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                body = await self._post(payload)
            except CopilotError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self._max_retries:
                    raise
                await asyncio.sleep(min(0.5 * (2**attempt), 4.0))
                continue
            return self._parse(body)
        raise last_error or CopilotError(ErrorCode.MODEL_ERROR, "model call failed")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise CopilotError(
                ErrorCode.MODEL_TIMEOUT,
                f"model request timed out after {self._timeout_s:.0f}s",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise CopilotError(
                ErrorCode.MODEL_ERROR,
                f"model transport error: {type(exc).__name__}",
                retryable=True,
            ) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise CopilotError(
                ErrorCode.MODEL_ERROR,
                f"model returned HTTP {response.status_code}",
                retryable=True,
            )
        if response.status_code >= 400:
            raise CopilotError(
                ErrorCode.MODEL_ERROR,
                f"model returned HTTP {response.status_code}: {response.text[:200]}",
            )
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise CopilotError(
                ErrorCode.MODEL_ERROR, "model returned a non-JSON body"
            ) from exc
        if not isinstance(body, dict):
            raise CopilotError(ErrorCode.MODEL_ERROR, "model returned an unexpected payload")
        return body

    def _parse(self, body: dict[str, Any]) -> LLMDecision:
        choices = body.get("choices") or []
        if not choices:
            raise CopilotError(ErrorCode.MODEL_ERROR, "model returned no choices")
        message = (choices[0] or {}).get("message") or {}
        content = str(message.get("content") or "").strip()
        calls: list[ToolCall] = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = (raw or {}).get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise CopilotError(
                    ErrorCode.TOOL_INVALID_ARGS,
                    f"model produced invalid tool arguments: {exc}",
                ) from exc
            if not isinstance(arguments, dict):
                raise CopilotError(
                    ErrorCode.TOOL_INVALID_ARGS, "tool arguments must be a JSON object"
                )
            calls.append(
                ToolCall(
                    id=str((raw or {}).get("id") or f"call-{index}"),
                    name=str(function.get("name") or ""),
                    arguments=arguments,
                )
            )
        usage = body.get("usage") or {}
        reasoning = message.get("reasoning_content")
        return LLMDecision(
            content=content,
            reasoning_content=str(reasoning) if reasoning else None,
            tool_calls=tuple(calls),
            usage=TokenUsage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )
