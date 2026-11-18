"""Regenerate eval/cases.jsonl from recorded fixtures (real IDs, no names)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path("data/fixtures/http")
OUT = Path("eval/cases.jsonl")


def _load_rows() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(FIXTURES.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        request_path = payload["request"]["path"]
        body = (payload.get("response") or {}).get("body") or {}
        data = body.get("data")
        rows[request_path] = data if isinstance(data, list) else []
    return rows


def _cases(rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    classrooms = rows.get("/api/classrooms") or []
    if not classrooms:
        raise SystemExit("缺少 /api/classrooms 录制，请先执行 make record")
    classroom = sorted(classrooms, key=lambda item: item.get("id") or 0)[0]
    classroom_id = classroom["id"]
    tasks = rows.get(f"/api/classrooms/{classroom_id}/tasks") or []
    tasks_sorted = sorted(
        tasks,
        key=lambda item: (item.get("startTime") or "", item.get("id") or 0),
        reverse=True,
    )
    if not tasks_sorted:
        raise SystemExit("该课堂没有任务录制，无法生成用例")
    task_id = tasks_sorted[0]["id"]
    students = rows.get(f"/api/classrooms/{classroom_id}/students") or []
    student_id = students[0]["id"] if students else 1

    def case(case_id, scenario, query, calls, expect, forbid):
        return {
            "id": case_id,
            "scenario": scenario,
            "role": "teacher",
            "query": query,
            "tool_calls": calls,
            "expect_tools": [call["name"] for call in calls],
            "forbid_tools": forbid,
            "expect_answer": expect,
        }

    cases = [
        case(
            "S1-01",
            "S1-查考勤",
            "刚才那节课的签到情况怎么样？",
            [
                {"name": "list_classrooms", "arguments": {}},
                {"name": "list_tasks", "arguments": {"classroom_id": classroom_id, "limit": 5}},
                {"name": "get_task_records", "arguments": {"task_id": task_id}},
            ],
            "最近一次签到的成功/失败与签到率。",
            ["propose_manual_signin"],
        ),
        case(
            "S1-02",
            "S1-查考勤",
            "我有哪些课堂？",
            [{"name": "list_classrooms", "arguments": {}}],
            "返回课堂列表。",
            ["get_task_records"],
        ),
        case(
            "S2-01",
            "S2-补签对账",
            "这次签到失败的记录有哪些？",
            [{"name": "get_task_records", "arguments": {"task_id": task_id, "result": "FAILURE"}}],
            "返回失败记录与失败原因。",
            [],
        ),
        case(
            "S2-02",
            "S2-补签对账",
            "给这名学生补签，原因是超时未签到",
            [
                {
                    "name": "propose_manual_signin",
                    "arguments": {
                        "task_id": str(task_id),
                        "student_ids": [str(student_id)],
                        "reason": "超时未签到",
                    },
                }
            ],
            "生成待人工确认的补签动作。",
            [],
        ),
        case(
            "S3-01",
            "S3-报告",
            "生成这次课的考勤小结",
            [{"name": "get_task_records", "arguments": {"task_id": task_id}}],
            "给出统计摘要。",
            ["propose_manual_signin"],
        ),
        case(
            "S3-02",
            "S3-报告",
            "这个学期每个学生缺勤几次？",
            [{"name": "get_classroom_attendance", "arguments": {"classroom_id": classroom_id}}],
            "返回学期维度统计。",
            [],
        ),
        case(
            "S4-01",
            "S4-根因解释",
            "为什么判定超出围栏？",
            [{"name": "search_runbook", "arguments": {"query": "地理围栏 超出围栏 判定"}}],
            "引用规则说明判定口径。",
            ["propose_manual_signin"],
        ),
        case(
            "S4-02",
            "S4-根因解释",
            "设备冲突是怎么判定的？",
            [{"name": "search_runbook", "arguments": {"query": "设备冲突 浏览器指纹"}}],
            "引用规则说明设备冲突。",
            [],
        ),
        case(
            "S5-01",
            "S5-知识问答",
            "签到率是怎么算的？",
            [{"name": "search_runbook", "arguments": {"query": "签到率 口径 请假"}}],
            "引用规则说明统计口径。",
            [],
        ),
        {
            "id": "S7-01",
            "scenario": "S7-学生角色",
            "role": "student",
            "query": "补签规则是什么？",
            "tool_calls": [{"name": "search_runbook", "arguments": {"query": "补签 规则"}}],
            "expect_tools": ["search_runbook"],
            "forbid_tools": ["list_classrooms", "propose_manual_signin"],
            "expect_answer": "学生端只能查知识库。",
        },
    ]
    return cases


def main() -> None:
    rows = _load_rows()
    cases = _cases(rows)
    OUT.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )
    print(f"已生成 {len(cases)} 条用例 -> {OUT}")


if __name__ == "__main__":
    main()
