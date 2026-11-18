"""Role/permission visibility: one matrix so drift is easy to spot."""

from __future__ import annotations

from app.roles import Role
from app.tools.registry import ToolRegistry


def describe_matrix(registry: ToolRegistry) -> dict[str, list[str]]:
    """Return {role: sorted tool names} for docs and tests."""
    matrix: dict[str, list[str]] = {role.value: [] for role in Role}
    for tool in registry.describe():
        for role_name in tool["roles"]:
            matrix[role_name].append(tool["name"])
    return {role: sorted(names) for role, names in matrix.items()}


def can_call(role: Role, allowed_roles: frozenset[Role]) -> bool:
    return role in allowed_roles
