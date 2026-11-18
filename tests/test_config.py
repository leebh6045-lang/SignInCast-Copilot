from app.config import Settings


def test_env_overrides_defaults(monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_LLM_MODEL", "qwen-plus")
    monkeypatch.setenv("COPILOT_MAX_STEPS", "5")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "qwen-plus"
    assert settings.max_steps == 5


def test_secret_is_masked_in_repr() -> None:
    settings = Settings(_env_file=None, llm_api_key="sk-test")
    assert "sk-test" not in repr(settings)
    assert settings.llm_api_key.get_secret_value() == "sk-test"
