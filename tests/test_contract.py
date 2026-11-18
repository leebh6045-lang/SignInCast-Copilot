import json
import re
from pathlib import Path

from pydantic import BaseModel

from app.business.models import (
    ApiEnvelope,
    AttendanceStat,
    Classroom,
    SignInRecord,
    SignInTask,
    Student,
)

FIXTURE_DIRS = [Path("data/fixtures/http"), Path("data/fixtures/http-sample")]
ENDPOINTS: list[tuple[str, type[BaseModel]]] = [
    (r"^/api/classrooms$", Classroom),
    (r"^/api/classrooms/my$", Classroom),
    (r"^/api/records/my$", SignInRecord),
    (r"^/api/classrooms/\d+/tasks$", SignInTask),
    (r"^/api/classrooms/\d+/students$", Student),
    (r"^/api/classrooms/\d+/attendance$", AttendanceStat),
    (r"^/api/records/task/\d+$", SignInRecord),
]


def _fixture_files() -> list[Path]:
    files: list[Path] = []
    for directory in FIXTURE_DIRS:
        files.extend(sorted(directory.glob("*.json")))
    return files


def _model_for(path: str):
    for pattern, model in ENDPOINTS:
        if re.match(pattern, path):
            return model
    return None


def test_fixtures_exist() -> None:
    assert _fixture_files(), "没有可回放的响应；请先录制或运行 scripts/make_sample_fixtures.py"


def test_every_fixture_matches_contract() -> None:
    for path in _fixture_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["meta"]["source"] in {"live", "synthetic-sample"}
        if payload["meta"]["source"] == "live":
            assert payload["meta"].get("desensitized") is True
        envelope = ApiEnvelope.model_validate(payload["response"]["body"])
        assert envelope.code == 200
        request_path = payload["request"]["path"]
        model = _model_for(request_path)
        assert model is not None, f"未映射的接口：{request_path}"
        assert isinstance(envelope.data, list), request_path
        for row in envelope.data:
            model.model_validate(row)


def test_required_endpoints_are_fixtured() -> None:
    paths = {
        json.loads(path.read_text(encoding="utf-8"))["request"]["path"]
        for path in _fixture_files()
    }
    required = {
        "/api/classrooms",
        "/api/classrooms/1/tasks",
        "/api/classrooms/1/students",
        "/api/classrooms/1/attendance",
        "/api/records/task/103",
    }
    assert required <= paths
