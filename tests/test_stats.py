from app.tools.stats import compute_attendance_stats


def test_counts_and_rate() -> None:
    records = [
        {"student_id": "1", "status": "SUCCESS"},
        {"student_id": "2", "status": "SUCCESS"},
        {"student_id": "3", "status": "MAKEUP"},
        {"student_id": "4", "status": "LEAVE"},
        {"student_id": "5", "status": "FAIL", "failure_reason": "GPS 超出围栏"},
        {"student_id": "6", "status": "FAIL", "failure_reason": "GPS 超出围栏"},
    ]
    stats = compute_attendance_stats(records, expected_count=8)
    assert stats["expected"] == 8
    assert stats["signed"] == 3
    assert stats["leave"] == 1
    assert stats["absent"] == 4
    assert stats["attendance_rate"] == round(3 / 7, 4)
    assert stats["failure_reasons"] == {"GPS 超出围栏": 2}
    assert stats["data_inconsistent"] is False


def test_zero_denominator_is_safe() -> None:
    assert compute_attendance_stats([], expected_count=0)["attendance_rate"] == 0.0


def test_inconsistent_expected_count_is_flagged() -> None:
    stats = compute_attendance_stats(
        [{"student_id": "1", "status": "SUCCESS"}], expected_count=0
    )
    assert stats["data_inconsistent"] is True
    assert stats["absent"] == 0
