"""One-round reflection: convert failures into an explicit re-plan instruction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReflectionContext:
    reason: str
    failed_tools: list[str] = field(default_factory=list)
    verification_problems: list[str] = field(default_factory=list)


def build_reflection(context: ReflectionContext) -> str:
    lines = ["【反思】上一轮没有成功，请改变策略，不要重复相同动作。"]
    if context.reason:
        lines.append(f"失败原因：{context.reason}")
    if context.failed_tools:
        lines.append("失败工具：" + "、".join(context.failed_tools))
    if context.verification_problems:
        lines.append("回答校验问题：" + "；".join(context.verification_problems[:3]))
    lines.append("下一步：换工具/换参数/缩小范围；若数据确实不足，明确说明后结束。")
    return "\n".join(lines)
