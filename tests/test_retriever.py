from pathlib import Path

from app.rag.retriever import HybridRetriever


def test_hybrid_search_finds_relevant_chunk(tmp_path: Path) -> None:
    (tmp_path / "rule.md").write_text(
        "# 考勤规则\n\n## 地理围栏\n地理围栏默认 30 米，超出直接拒绝。\n",
        encoding="utf-8",
    )
    (tmp_path / "faq.md").write_text(
        "# 常见问题\n\n## 二维码\n二维码每 30 秒刷新一次。\n", encoding="utf-8"
    )
    retriever = HybridRetriever.from_dir(tmp_path)
    hits = retriever.search("地理围栏是多少米", top_k=2)
    assert hits
    assert hits[0].doc_id == "rule"
    assert hits[0].section == "地理围栏"
    assert hits[0].chunk_id.startswith("rule#")
    assert "围栏" in hits[0].snippet


def test_empty_corpus_returns_nothing(tmp_path: Path) -> None:
    retriever = HybridRetriever.from_dir(tmp_path / "missing")
    assert retriever.search("签到") == []


def test_scores_are_ordered(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n\n## 补签\n补签需要填写原因。\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\n## 二维码\n二维码会刷新。\n", encoding="utf-8")
    hits = HybridRetriever.from_dir(tmp_path).search("补签原因", top_k=5)
    assert hits[0].doc_id == "a"
    assert all(hits[index].score >= hits[index + 1].score for index in range(len(hits) - 1))
