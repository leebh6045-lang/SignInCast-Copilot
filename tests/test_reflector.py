from app.runtime.reflector import ReflectionContext, build_reflection


def test_reflection_mentions_reason_and_tools() -> None:
    text = build_reflection(
        ReflectionContext(
            reason="工具超时",
            failed_tools=["get_task_records"],
            verification_problems=["数字 999 未出现在工具结果中"],
        )
    )
    assert "反思" in text
    assert "工具超时" in text
    assert "get_task_records" in text
    assert "999" in text
