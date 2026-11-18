from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        trace_enabled=False,
        trace_dir=tmp_path / "traces",
        signincast_mode="mock",
        signincast_fixtures_dir=Path("data/fixtures/http-sample"),
        db_path=tmp_path / "copilot-test.db",
    )
