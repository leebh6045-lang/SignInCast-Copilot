"""Smoke-test a real LLM backend with one tool-using query."""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.container import build_container
from app.roles import Role


def _explain_configuration() -> None:
    print("未配置真实模型。请在 .env 中设置（任选其一）：")
    print("")
    print("A. 云端 OpenAI 兼容接口（如 DeepSeek）")
    print("   COPILOT_LLM_PROVIDER=openai_compat")
    print("   COPILOT_LLM_BASE_URL=https://api.deepseek.com/v1")
    print("   COPILOT_LLM_API_KEY=sk-...")
    print("   COPILOT_LLM_MODEL=deepseek-chat")
    print("")
    print("B. 本地 Ollama")
    print("   COPILOT_LLM_PROVIDER=openai_compat")
    print("   COPILOT_LLM_BASE_URL=http://localhost:11434/v1")
    print("   COPILOT_LLM_API_KEY=ollama")
    print("   COPILOT_LLM_MODEL=qwen3:8b   # 以 ollama list 为准")


def main() -> int:
    settings = get_settings()
    if settings.llm_provider != "openai_compat" or not settings.llm_api_key.get_secret_value():
        _explain_configuration()
        return 1
    container = build_container(settings)
    outcome = asyncio.run(
        container.loop.run(
            "刚才那节课的签到情况怎么样？给出结论和依据。", Role.TEACHER
        )
    )
    print(f"model={settings.llm_model} provider={settings.llm_provider}")
    print(f"steps={[[tool.name for tool in step.tools] for step in outcome.steps]}")
    print(f"answer={outcome.answer}")
    print(f"usage={outcome.usage.to_dict()} cost=${outcome.cost_usd:.6f}")
    print(f"trace={outcome.trace_path}")
    if outcome.error_code:
        print(f"error={outcome.error_code} {outcome.error_message}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
