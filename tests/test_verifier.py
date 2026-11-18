from app.runtime.verifier import collect_numbers, verify_answer


def test_empty_answer_rejected() -> None:
    result = verify_answer("   ")
    assert result.ok is False


def test_raw_tool_payload_rejected() -> None:
    result = verify_answer('{"ok": true, "data": {}}')
    assert result.ok is False


def test_numbers_must_come_from_tools() -> None:
    result = verify_answer(
        "应到 45 人，实到 42 人，签到率 93.3%。",
        tool_numbers=collect_numbers(
            ['{"expected": 45, "signed": 42, "attendance_rate": 0.9333}']
        ),
    )
    assert result.ok is True, result.problems


def test_fabricated_number_is_rejected() -> None:
    result = verify_answer(
        "这次签到成功 47 人。",
        tool_numbers=collect_numbers(['{"success": 8, "failure": 4}']),
    )
    assert result.ok is False
    assert any("47" in problem for problem in result.problems)


def test_fabricated_percentage_is_rejected() -> None:
    result = verify_answer(
        "签到率 99.9%。",
        tool_numbers=collect_numbers(['{"success": 8, "failure": 4}']),
    )
    assert result.ok is False
    assert any("99.9" in problem for problem in result.problems)


def test_small_numbers_are_tolerated() -> None:
    result = verify_answer(
        "共 3 类异常，其中 2 类可自动处理。",
        tool_numbers=collect_numbers(['{"success": 8}']),
    )
    assert result.ok is True
