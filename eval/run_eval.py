"""M0 harness: replay expected tool calls to validate wiring, permissions and metrics.

This runner proves the pipeline (registry, roles, loop, metrics) works. Quality
metrics against a real model and an LLM judge arrive in M3.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.container import build_container
from app.llm.base import LLMDecision, ToolCall
from app.llm.fake import FakeChatModel
from app.roles import Role
from app.runtime.loop import AgentLoop
from app.tools.registry import ToolRegistry


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(json.loads(stripped))
    return cases


def replay_policy(case: dict[str, Any]):
    calls = case.get("tool_calls", [])

    def policy(messages, tools) -> LLMDecision:
        done = [item for item in messages if item.role == "tool"]
        if len(done) < len(calls):
            call = calls[len(done)]
            return LLMDecision(
                tool_calls=(
                    ToolCall(
                        id=f"replay-{len(done)}",
                        name=call["name"],
                        arguments=call.get("arguments", {}),
                    ),
                )
            )
        return LLMDecision(content=case.get("expect_answer", "回放完成。"))

    return policy


def validate_case(case: dict[str, Any], registry: ToolRegistry) -> list[str]:
    problems: list[str] = []
    for name in case.get("expect_tools", []):
        if name not in registry.names():
            problems.append(f"missing tool: {name}")
    return problems


def evaluate(cases: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    container = build_container(settings)
    results: list[dict[str, Any]] = []
    for case in cases:
        problems = validate_case(case, container.registry)
        role = Role.parse(case.get("role", "teacher"))
        loop = AgentLoop(
            model=FakeChatModel(replay_policy(case)),
            registry=container.registry,
            settings=settings,
        )
        started = time.monotonic()
        outcome = asyncio.run(loop.run(case["query"], role))
        executed = [tool.name for step in outcome.steps for tool in step.tools]
        expected = case.get("expect_tools", [])
        forbidden = [name for name in case.get("forbid_tools", []) if name in executed]
        passed = (
            outcome.error_code is None
            and executed == expected
            and not forbidden
            and not problems
        )
        results.append(
            {
                "id": case["id"],
                "scenario": case.get("scenario", ""),
                "passed": passed,
                "terminated": outcome.error_code is None,
                "tool_sequence_match": executed == expected,
                "executed": executed,
                "expected": expected,
                "forbidden_calls": forbidden,
                "problems": problems,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
    passed_count = sum(1 for item in results if item["passed"])
    return {"total": len(results), "passed": passed_count, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M0 评测回放（验证工具接线与指标计算）")
    parser.add_argument("--cases", default="eval/cases.jsonl")
    parser.add_argument("--report", default="eval/reports/latest.json")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            _env_file=None,
            trace_enabled=False,
            db_path=Path(tmp) / "eval.db",
        )
        report = evaluate(load_cases(Path(args.cases)), settings)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"cases={report['total']} passed={report['passed']}")
    for item in report["results"]:
        flag = "PASS" if item["passed"] else "FAIL"
        print(
            f"  [{flag}] {item['id']}: executed={item['executed']} "
            f"expected={item['expected']} problems={item['problems']}"
        )
    print(f"report: {report_path}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
