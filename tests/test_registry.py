import asyncio

import pytest
from pydantic import Field

from app.errors import ErrorCode
from app.roles import Role
from app.tools.base import ToolArgs, ToolContext, ToolResult, ToolSpec
from app.tools.registry import ToolRegistry


def _spec(**overrides) -> ToolSpec:
    class EchoArgs(ToolArgs):
        text: str = Field(default="hi", max_length=20)

    async def handler(args, context):
        return ToolResult(ok=True, data={"echo": args.text})

    options = {
        "name": "echo",
        "description": "echo back",
        "args_model": EchoArgs,
        "handler": handler,
        "allowed_roles": frozenset({Role.TEACHER}),
        "timeout_s": 1.0,
        "max_retries": 0,
    }
    options.update(overrides)
    return ToolSpec(**options)


def _registry(settings, spec: ToolSpec | None = None) -> ToolRegistry:
    registry = ToolRegistry(settings)
    registry.register(spec or _spec())
    return registry


def _invoke(registry, args):
    return asyncio.run(
        registry.invoke("echo", args, ToolContext(role=Role.TEACHER))
    )


def test_duplicate_registration_rejected(settings) -> None:
    registry = _registry(settings)
    with pytest.raises(ValueError):
        registry.register(_spec())


def test_unknown_tool_returns_structured_error(settings) -> None:
    result = asyncio.run(
        _registry(settings).invoke("missing", {}, ToolContext(role=Role.TEACHER))
    )
    assert result.ok is False
    assert result.error_code == ErrorCode.TOOL_NOT_FOUND.value


def test_role_permission_denied(settings) -> None:
    result = asyncio.run(
        _registry(settings).invoke("echo", {}, ToolContext(role=Role.STUDENT))
    )
    assert result.error_code == ErrorCode.TOOL_PERMISSION_DENIED.value


def test_invalid_arguments_are_rejected(settings) -> None:
    result = _invoke(_registry(settings), {"text": "x" * 50})
    assert result.error_code == ErrorCode.TOOL_INVALID_ARGS.value


def test_unknown_argument_field_is_rejected(settings) -> None:
    result = _invoke(_registry(settings), {"nope": 1})
    assert result.error_code == ErrorCode.TOOL_INVALID_ARGS.value


def test_timeout_is_retried_once_for_read_only_tool(settings) -> None:
    calls = {"count": 0}

    async def slow(args, context):
        calls["count"] += 1
        await asyncio.sleep(0.2)
        return ToolResult(ok=True, data={})

    spec = _spec(handler=slow, timeout_s=0.05, max_retries=1)
    result = _invoke(_registry(settings, spec), {})
    assert result.error_code == ErrorCode.TOOL_TIMEOUT.value
    assert calls["count"] == 2


def test_write_tool_is_never_retried(settings) -> None:
    calls = {"count": 0}

    async def slow(args, context):
        calls["count"] += 1
        await asyncio.sleep(0.2)
        return ToolResult(ok=True, data={})

    spec = _spec(handler=slow, timeout_s=0.05, max_retries=2, read_only=False)
    result = _invoke(_registry(settings, spec), {})
    assert result.error_code == ErrorCode.TOOL_TIMEOUT.value
    assert calls["count"] == 1


def test_handler_exception_becomes_tool_error(settings) -> None:
    async def boom(args, context):
        raise RuntimeError("database down")

    result = _invoke(_registry(settings, _spec(handler=boom)), {})
    assert result.error_code == ErrorCode.TOOL_ERROR.value
    assert "database down" in result.error_message


def test_content_is_trimmed() -> None:
    content = ToolResult(ok=True, data={"text": "x" * 500}).to_content(max_chars=80)
    assert content.startswith('{"ok": true')
    assert "[truncated" in content
