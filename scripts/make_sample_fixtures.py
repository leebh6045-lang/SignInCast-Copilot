"""Generate synthetic demo fixtures that match the real SignInCast contracts.

These are hand-authored samples used only for offline mode and tests. Once the
live system is recorded with `python -m app.cli --record --smoke`, real captured
responses can replace them (see README).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.business.transport import HttpRequest, fixture_key

FIXTURES = Path("data/fixtures/http-sample")

CLASSROOMS = [
    {
        "id": 1,
        "classroomName": "2026秋·数据结构（1班）",
        "description": "周三 3-4 节",
        "joinCode": "DS2026A",
        "classCode": "CS-DS-01",
        "status": "ACTIVE",
        "teacherName": "离线演示教师",
        "createdAt": "2026-09-01T08:00:00",
    },
    {
        "id": 2,
        "classroomName": "2026秋·操作系统（2班）",
        "description": "周五 1-2 节",
        "joinCode": "OS2026B",
        "classCode": "CS-OS-02",
        "status": "ACTIVE",
        "teacherName": "离线演示教师",
        "createdAt": "2026-09-02T08:00:00",
    },
]

TASKS = [
    {
        "id": 103,
        "classroomId": 1,
        "classroomName": "2026秋·数据结构（1班）",
        "taskTitle": "第10次课 考勤",
        "description": None,
        "startTime": "2026-11-12T10:00:00",
        "endTime": "2026-11-12T10:10:00",
        "status": "FINISHED",
        "createdAt": "2026-11-12T09:50:00",
        "signInType": "GESTURE",
        "qrcodeRefreshInterval": None,
        "locationRequired": True,
        "teacherLatitude": 25.2736,
        "teacherLongitude": 110.2905,
        "distanceLimit": 100,
    },
    {
        "id": 102,
        "classroomId": 1,
        "classroomName": "2026秋·数据结构（1班）",
        "taskTitle": "第9次课 考勤",
        "description": None,
        "startTime": "2026-11-05T14:00:00",
        "endTime": "2026-11-05T14:10:00",
        "status": "FINISHED",
        "createdAt": "2026-11-05T13:50:00",
        "signInType": "WECHAT",
        "qrcodeRefreshInterval": 30,
        "locationRequired": True,
        "teacherLatitude": 25.2736,
        "teacherLongitude": 110.2905,
        "distanceLimit": 100,
    },
    {
        "id": 101,
        "classroomId": 1,
        "classroomName": "2026秋·数据结构（1班）",
        "taskTitle": "第8次课 考勤",
        "description": None,
        "startTime": "2026-10-29T10:00:00",
        "endTime": "2026-10-29T10:10:00",
        "status": "FINISHED",
        "createdAt": "2026-10-29T09:50:00",
        "signInType": "GESTURE",
        "qrcodeRefreshInterval": None,
        "locationRequired": False,
        "teacherLatitude": None,
        "teacherLongitude": None,
        "distanceLimit": None,
    },
]

STUDENTS = [
    {"id": 201, "username": "20230101", "name": "陈晓"},
    {"id": 202, "username": "20230102", "name": "李明"},
    {"id": 203, "username": "20230103", "name": "王芳"},
    {"id": 204, "username": "20230104", "name": "赵磊"},
    {"id": 205, "username": "20230105", "name": "孙悦"},
    {"id": 206, "username": "20230106", "name": "周涛"},
    {"id": 207, "username": "20230107", "name": "吴倩"},
    {"id": 208, "username": "20230108", "name": "郑浩"},
    {"id": 209, "username": "20230109", "name": "冯雪"},
    {"id": 210, "username": "20230110", "name": "何俊"},
    {"id": 211, "username": "20230111", "name": "许琳"},
    {"id": 212, "username": "20230112", "name": "高翔"},
]

RECORDS = [
    (201, "SUCCESS", "GESTURE", None, False, 12),
    (202, "SUCCESS", "GESTURE", None, False, 18),
    (203, "SUCCESS", "WECHAT_SCAN", None, False, 25),
    (204, "FAILURE", "GESTURE", "DISTANCE_TOO_FAR", False, 186),
    (205, "SUCCESS", "GESTURE", None, True, 112),
    (206, "SUCCESS", "GESTURE", None, False, 9),
    (207, "FAILURE", "WECHAT_SCAN", "DEVICE_CONFLICT", False, 30),
    (208, "SUCCESS", "GESTURE", None, False, 40),
    (209, "SUCCESS", "GESTURE", None, False, 15),
    (210, "FAILURE", "GESTURE", "GESTURE_WRONG", False, 20),
    (211, "SUCCESS", "WECHAT_SCAN", None, False, 22),
    (212, "FAILURE", "GESTURE", "DISTANCE_TOO_FAR", False, 205),
]

ATTENDANCE = [
    (201, 3, 3, 0, 0, 0),
    (202, 3, 3, 0, 0, 0),
    (203, 3, 3, 0, 0, 0),
    (204, 3, 1, 2, 0, 0),
    (205, 3, 3, 0, 0, 0),
    (206, 3, 3, 0, 0, 0),
    (207, 3, 1, 1, 1, 0),
    (208, 3, 3, 0, 0, 0),
    (209, 3, 2, 1, 0, 0),
    (210, 3, 1, 1, 0, 1),
    (211, 3, 3, 0, 0, 0),
    (212, 3, 1, 2, 0, 0),
]


def _records() -> list[dict]:
    names = {item["id"]: item["name"] for item in STUDENTS}
    result = []
    for index, (student_id, status, method, reason, warning, distance) in enumerate(
        RECORDS, start=1
    ):
        result.append(
            {
                "id": 5000 + index,
                "taskId": 103,
                "taskTitle": "第10次课 考勤",
                "classroomName": "2026秋·数据结构（1班）",
                "studentId": student_id,
                "studentName": names[student_id],
                "studentAvatar": None,
                "signedInAt": f"2026-11-12T10:0{index % 10}:00",
                "result": status,
                "createdAt": f"2026-11-12T10:0{index % 10}:00",
                "signInMethod": method,
                "failureReason": reason,
                "distance": distance,
                "hasWarning": warning,
            }
        )
    return result


def _attendance() -> list[dict]:
    names = {item["id"]: item for item in STUDENTS}
    result = []
    for student_id, total, success, failure, leave, absent in ATTENDANCE:
        student = names[student_id]
        result.append(
            {
                "studentId": student_id,
                "studentName": student["name"],
                "studentAvatar": None,
                "username": student["username"],
                "totalTasks": total,
                "successCount": success,
                "failureCount": failure,
                "leaveCount": leave,
                "absentCount": absent,
            }
        )
    return result


def _write(method: str, path: str, data: Any, *, params: dict[str, Any] | None = None) -> None:
    key = fixture_key(HttpRequest(method, path, params=params or {}))
    payload = {
        "request": {"method": method, "path": path, "params": params or {}},
        "response": {
            "status": 200,
            "body": {
                "code": 200,
                "message": "success",
                "data": data,
                "timestamp": "2026-11-17T20:00:00",
            },
        },
        "meta": {"source": "synthetic-sample", "recorded_at": "2026-11-17"},
    }
    target = FIXTURES / f"{key}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {target.name}  {method} {path}")


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _write("GET", "/api/classrooms", CLASSROOMS)
    _write("GET", "/api/classrooms/1/tasks", TASKS)
    _write("GET", "/api/classrooms/1/students", STUDENTS)
    _write("GET", "/api/classrooms/1/attendance", _attendance())
    _write("GET", "/api/records/task/103", _records())
    _write("GET", "/api/classrooms/my", CLASSROOMS[:1])
    my_records = [
        {
            "id": 6001,
            "taskId": 103,
            "taskTitle": "第10次课 考勤",
            "classroomName": "2026秋·数据结构（1班）",
            "studentId": 201,
            "studentName": STUDENTS[0]["name"],
            "studentAvatar": None,
            "signedInAt": "2026-11-12T10:01:00",
            "result": "SUCCESS",
            "createdAt": "2026-11-12T10:01:00",
            "signInMethod": "GESTURE",
            "failureReason": None,
            "distance": 12,
            "hasWarning": False,
        },
        {
            "id": 6002,
            "taskId": 102,
            "taskTitle": "第9次课 考勤",
            "classroomName": "2026秋·数据结构（1班）",
            "studentId": 201,
            "studentName": STUDENTS[0]["name"],
            "studentAvatar": None,
            "signedInAt": "2026-11-05T14:02:00",
            "result": "FAILURE",
            "createdAt": "2026-11-05T14:02:00",
            "signInMethod": "WECHAT_SCAN",
            "failureReason": "DISTANCE_TOO_FAR",
            "distance": 220,
            "hasWarning": False,
        },
    ]
    _write("GET", "/api/records/my", my_records)


if __name__ == "__main__":
    main()
