"""Typed configuration loaded from environment variables and .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime knobs live here; nothing else reads os.environ directly."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "SignInCast Copilot"
    env: str = "dev"
    log_level: str = "INFO"

    llm_provider: Literal["fake", "openai_compat"] = "fake"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "deepseek-chat"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2

    max_steps: int = 8
    context_token_budget: int = 8000
    run_token_budget: int = 30000
    run_timeout_s: float = 120.0
    tool_result_max_chars: int = 4000
    rag_top_k: int = 5
    enable_tool_cache: bool = True

    # ===== SignInCast 业务系统 =====
    signincast_base_url: str = "https://signin.qishiyi.cn"
    signincast_username: str = ""
    signincast_password: SecretStr = SecretStr("")
    signincast_timeout_s: float = 15.0
    signincast_max_retries: int = 2
    # mock: 只读本地录制响应（默认，离线可跑）
    # record: 调用真实接口并把响应录制下来
    # live: 调用真实接口
    signincast_mode: Literal["live", "record", "mock"] = "mock"
    signincast_fixtures_dir: Path = Path("data/fixtures/http")

    # 本地持久化（待确认动作、审计、后续会话）
    db_path: Path = Path("data/copilot.db")

    trace_enabled: bool = True
    trace_dir: Path = Path("traces")

    runbook_dir: Path = Path("data/runbook")
    report_dir: Path = Path("data/reports")

    prompt_price_per_mtok: float = 0.5
    completion_price_per_mtok: float = 2.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
