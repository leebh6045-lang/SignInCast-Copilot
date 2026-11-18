"""User roles recognized by the agent service."""

from enum import StrEnum


class Role(StrEnum):
    """Roles a single agent run can act as."""

    TEACHER = "teacher"
    STUDENT = "student"
    SERVICE = "service"

    @classmethod
    def parse(cls, value: str) -> "Role":
        try:
            return cls(value.strip().lower())
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"unknown role: {value!r}") from exc
