"""Real-model evaluation: tool metrics, LLM-as-judge, latency/cost, baseline."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.container import build_container
from app.llm.base import LLMMessage, TokenUsage
from app.roles import Role

_JUDGE_SYSTEM = """你是严格的 Agent 评测员。给定用户问题、期望要点和 Agent 回答，
输出 JSON：{"score": 1-5, "pass": true/false, "reason": "一句话"}。
评分标准：5=完全满足；4=基本满足有轻微瑕疵；3=部分满足；2=明显不足；1=错误、编造或拒绝合理请求。
只输出 JSON，不要解释。"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def tool_metrics(expected: list[str], actual: list[str]) -> tuple[float, float]:
    expected_set, actual_set = set(expected), set(actual)
    if not actual_set:
        return 0.0, (0.0 if expected_set else 1.0)
    precision = len(expected_set & actual_set) / len(actual_set)
    recall = len(expected_set & actual_set) / len(expected_set) if expected_set else 1.0
    return round(precision, 3), round(recall, 3)


async def _judge(
    model, case: dict[str, Any], answer: str
) -> tuple[dict[str, Any], TokenUsage]:
    prompt = (
        f"用户问题：{case['query']}\n"
        f"期望要点：{json.dumps(case.get('judge_points', []), ensure_ascii=False)}\n"
        f"角色：{case.get('role')}\n"
        f"Agent 回答：\n{answer[:1500]}"
    )
    decision = await model.decide(
        [LLMMessage(role="system", content=_JUDGE_SYSTEM), LLMMessage(role="user", content=prompt)],
        [],
    )
    parsed = _parse_judge(decision.content)
    return parsed, decision.usage


def _parse_judge(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", text or "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return {
                "score": int(data.get("score", 0)) or None,
                "pass": bool(data.get("pass", False)),
                "reason": str(data.get("reason", ""))[:200],
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return {"score": None, "pass": None, "reason": f"judge 输出无法解析: {text[:120]}"}


async def run_suite(
    settings: Settings,
    cases: list[dict[str, Any]],
    *,
    judge: bool,
    verbose: bool,
) -> dict[str, Any]:
    container = build_container(settings)
    results: list[dict[str, Any]] = []
    judge_usage = TokenUsage()
    for index, case in enumerate(cases, start=1):
        role = Role.parse(case.get("role", "teacher"))
        started = time.monotonic()
        outcome = await container.loop.run(case["query"], role)
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        tools = [tool.name for step in outcome.steps for tool in step.tools]
        precision, recall = tool_metrics(case.get("expect_tools", []), tools)
        forbidden = [name for name in case.get("forbid_tools", []) if name in tools]
        judged: dict[str, Any] = {}
        if judge and outcome.ok:
            judged, usage = await _judge(container.model, case, outcome.answer)
            judge_usage = judge_usage + usage
        result = {
            "id": case["id"],
            "category": case.get("category", ""),
            "role": case.get("role", "teacher"),
            "query": case["query"],
            "ok": outcome.ok,
            "error_code": outcome.error_code,
            "answer": outcome.answer,
            "tools": tools,
            "tool_precision": precision,
            "tool_recall": recall,
            "forbidden_calls": forbidden,
            "steps": len(outcome.steps),
            "latency_ms": latency_ms,
            "tokens": outcome.usage.total_tokens,
            "cost_usd": round(outcome.cost_usd, 6),
            "judge": judged,
        }
        results.append(result)
        if verbose:
            flag = "OK " if outcome.ok else "ERR"
            print(
                f"[{index:02d}/{len(cases)}] {flag} {result['id']} "
                f"steps={result['steps']} tokens={result['tokens']} "
                f"latency={latency_ms}ms judge={judged.get('score')}",
                flush=True,
            )

    judge_cost = (
        judge_usage.prompt_tokens / 1_000_000 * settings.prompt_price_per_mtok
        + judge_usage.completion_tokens / 1_000_000 * settings.completion_price_per_mtok
    )
    latencies = sorted(item["latency_ms"] for item in results)
    scores = [
        item["judge"].get("score")
        for item in results
        if item["judge"].get("score")
    ]
    passes = [
        item["judge"].get("pass")
        for item in results
        if item["judge"].get("pass") is not None
    ]
    summary = {
        "model": settings.llm_model,
        "rag_top_k": settings.rag_top_k,
        "tool_cache": settings.enable_tool_cache,
        "cases": len(results),
        "completed": sum(1 for item in results if item["ok"]),
        "completion_rate": _rate(sum(1 for item in results if item["ok"]), len(results)),
        "tool_precision": _mean([item["tool_precision"] for item in results]),
        "tool_recall": _mean([item["tool_recall"] for item in results]),
        "forbidden_violations": sum(len(item["forbidden_calls"]) for item in results),
        "avg_steps": _mean([item["steps"] for item in results]),
        "p95_latency_ms": _p95(latencies),
        "avg_latency_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        "run_tokens": sum(item["tokens"] for item in results),
        "judge_tokens": judge_usage.total_tokens,
        "judge_pass_rate": (
            _rate(sum(1 for value in passes if value), len(passes)) if passes else None
        ),
        "avg_judge_score": round(statistics.fmean(scores), 2) if scores else None,
        "run_cost_usd": round(sum(item["cost_usd"] for item in results), 6),
        "judge_cost_usd": round(judge_cost, 6),
        "total_cost_usd": round(sum(item["cost_usd"] for item in results) + judge_cost, 6),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return {"summary": summary, "results": results}


def _rate(part: int, total: int) -> float:
    return round(part / total, 3) if total else 0.0


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 3) if values else 0.0


def _p95(sorted_values: list[float]) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(round(0.95 * (len(sorted_values) - 1))))
    return sorted_values[index]


def compare_baseline(summary: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    lines = ["| 指标 | 基线 | 当前 | 变化 |", "| --- | --- | --- | --- |"]
    for key, label in (
        ("completion_rate", "完成率"),
        ("tool_precision", "工具精确率"),
        ("tool_recall", "工具召回率"),
        ("avg_steps", "平均步数"),
        ("p95_latency_ms", "P95 延迟(ms)"),
        ("run_tokens", "运行 tokens"),
        ("run_cost_usd", "运行成本($)"),
        ("judge_pass_rate", "Judge 通过率"),
    ):
        before = baseline.get(key)
        after = summary.get(key)
        if before is None or after is None:
            continue
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
            lines.append(f"| {label} | {before} | {after} | {delta:+.3f} |")
    return lines


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# 真实模型评测报告",
        "",
        f"- 模型：`{summary['model']}`",
        f"- 配置：rag_top_k={summary['rag_top_k']} · tool_cache={summary['tool_cache']}",
        f"- 生成时间：{summary['generated_at']}",
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 用例数 | {summary['cases']} |",
        f"| 完成率 | {summary['completion_rate']:.1%} |",
        f"| 工具精确率 / 召回率 | {summary['tool_precision']} / {summary['tool_recall']} |",
        f"| 越权/禁用工具调用 | {summary['forbidden_violations']} |",
        f"| 平均步数 | {summary['avg_steps']} |",
        f"| P95 延迟 | {summary['p95_latency_ms']} ms |",
        f"| 运行 tokens | {summary['run_tokens']} |",
        "| Judge 通过率 / 均分 | "
        f"{summary['judge_pass_rate']:.1%} / {summary['avg_judge_score']} |",
        f"| 总成本（运行+judge） | ${summary['total_cost_usd']} |",
    ]
    if report.get("baseline_lines"):
        lines += ["", "## 对比基线", "", *report["baseline_lines"]]
    lines += [
        "",
        "## 用例结果",
        "",
        "| 用例 | 分类 | 完成 | 步数 | tokens | 延迟(ms) | judge | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        judge = item["judge"].get("score")
        note = item["error_code"] or item["judge"].get("reason", "")
        lines.append(
            f"| {item['id']} | {item['category']} | {'✅' if item['ok'] else '❌'} | "
            f"{item['steps']} | {item['tokens']} | {item['latency_ms']} | "
            f"{judge} | {str(note)[:60]} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实模型评测（指标 + LLM judge + 基线对比）")
    parser.add_argument("--cases", default="eval/cases.model.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default="")
    parser.add_argument("--rag-top-k", type=int, default=5)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--report", default="eval/reports/model-last.json")
    parser.add_argument("--markdown", default="")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    base = get_settings()
    if base.llm_provider != "openai_compat" or not base.llm_api_key.get_secret_value():
        print("需要真实模型：请在 .env 配置 COPILOT_LLM_PROVIDER=openai_compat 与 API Key")
        return 1
    tmp_dir = Path(tempfile.mkdtemp(prefix="model-eval-"))
    settings = base.model_copy(
        update={
            "llm_model": args.model or base.llm_model,
            "rag_top_k": args.rag_top_k,
            "enable_tool_cache": not args.no_cache,
            "signincast_mode": "mock",
            "signincast_fixtures_dir": Path("data/fixtures/http-sample"),
            "db_path": tmp_dir / "eval.db",
            "trace_enabled": False,
        }
    )
    cases = load_cases(Path(args.cases))
    if args.limit:
        cases = cases[: args.limit]
    report = asyncio.run(
        run_suite(settings, cases, judge=not args.no_judge, verbose=args.verbose)
    )
    if args.baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.is_file():
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            report["baseline_lines"] = compare_baseline(
                report["summary"], baseline["summary"]
            )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.markdown:
        write_markdown(report, Path(args.markdown))
        print(f"markdown: {args.markdown}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
