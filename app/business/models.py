"""Pydantic mirrors of the SignInCast REST contracts.

Field names match the Spring DTOs; optional fields stay optional because the
server may legitimately omit them (for example location fields when the task
does not use geofencing). Unknown fields are ignored so additive server changes
do not break the agent, while removed required fields do fail loudly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiEnvelope(BaseModel):
    """Every SignInCast REST response is wrapped in ApiResponse."""

    model_config = ConfigDict(extra="ignore")

    code: int
    message: str = ""
    data: Any = None
    timestamp: str | None = None


class LoginResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str
    type: str = "Bearer"
    id: int
    username: str
    name: str = ""
    role: str


class Classroom(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    classroomName: str
    description: str | None = None
    joinCode: str | None = None
    classCode: str | None = None
    status: str | None = None
    teacherName: str | None = None
    createdAt: str | None = None


class SignInTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    classroomId: int
    classroomName: str | None = None
    taskTitle: str | None = None
    description: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    status: str | None = None
    createdAt: str | None = None
    signInType: str | None = None
    qrcodeRefreshInterval: int | None = None
    locationRequired: bool | None = None
    teacherLatitude: float | None = None
    teacherLongitude: float | None = None
    distanceLimit: int | None = None


class SignInRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    taskId: int | None = None
    taskTitle: str | None = None
    classroomName: str | None = None
    studentId: int | None = None
    studentName: str | None = None
    studentAvatar: str | None = None
    signedInAt: str | None = None
    result: str | None = None
    createdAt: str | None = None
    signInMethod: str | None = None
    failureReason: str | None = None
    distance: int | None = None
    hasWarning: bool | None = None


class Student(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str
    name: str = ""


class AttendanceStat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    studentId: int
    studentName: str | None = None
    studentAvatar: str | None = None
    username: str | None = None
    totalTasks: int = 0
    successCount: int = 0
    failureCount: int = 0
    leaveCount: int = 0
    absentCount: int = 0
