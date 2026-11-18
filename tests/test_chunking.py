from app.rag.chunking import split_document

TEXT = """# 考勤规则

## 时间窗口
任务开始前与结束后提交的签到一律拒绝。

## 地理围栏
- 距离超过半径直接判定失败。
- 距离落在半径加 30 米容忍带时判定成功但打告警标记。
- 未授权定位按失败处理。

## 设备指纹
同一任务下同一设备指纹只允许一名学生签到。
"""


def test_chunks_keep_section_titles_and_stable_ids() -> None:
    chunks = split_document(doc_id="rule", title="考勤规则", text=TEXT, source="rule.md")
    assert len(chunks) >= 3
    assert [chunk.chunk_id for chunk in chunks] == [
        f"rule#{index}" for index in range(len(chunks))
    ]
    sections = {chunk.section for chunk in chunks}
    assert {"时间窗口", "地理围栏", "设备指纹"} <= sections
    assert all(chunk.text for chunk in chunks)


def test_long_documents_are_split() -> None:
    long_text = "# 手册\n\n## 补签\n" + "补签需要填写原因。" * 200
    chunks = split_document(
        doc_id="manual", title="手册", text=long_text, source="m.md", max_chars=200
    )
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 420 for chunk in chunks)
