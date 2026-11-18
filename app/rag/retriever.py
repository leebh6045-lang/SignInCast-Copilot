"""Hybrid retrieval: TF-IDF vector cosine + keyword coverage, over runbook chunks.

This is an offline, deterministic retriever. It is genuinely vector-based (sparse
TF-IDF vectors), but it is not a neural embedding model; the ``Retriever``
protocol keeps room for a bge/embedding backend later (see limitations).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.rag.chunking import Chunk, split_document

_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_VECTOR_WEIGHT = 0.65
_KEYWORD_WEIGHT = 0.35


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    snippet: str
    score: float
    source: str


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchHit]: ...


def terms(text: str) -> set[str]:
    lowered = text.lower()
    found = {word for word in _ASCII_WORD.findall(lowered) if len(word) > 1}
    chars = _CJK_CHAR.findall(text)
    for index in range(len(chars) - 1):
        found.add(chars[index] + chars[index + 1])
    return found


def _snippet(text: str, query_terms: set[str], width: int = 150) -> str:
    lowered = text.lower()
    position = -1
    for term in sorted(query_terms, key=len, reverse=True):
        found = lowered.find(term.lower())
        if found >= 0:
            position = found
            break
    if position < 0:
        return text[:width].replace("\n", " ")
    start = max(0, position - width // 3)
    return text[start : start + width].replace("\n", " ")


class HybridRetriever:
    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks = list(chunks or [])
        self._idf: dict[str, float] = {}
        self._vectors: list[dict[str, float]] = []
        self._chunk_terms: list[set[str]] = []
        self._build_index()

    @classmethod
    def from_dir(cls, directory: Path) -> HybridRetriever:
        chunks: list[Chunk] = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.md")):
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                title = text.splitlines()[0].lstrip("# ").strip() or path.stem
                chunks.extend(
                    split_document(
                        doc_id=path.stem,
                        title=title,
                        text=text,
                        source=path.as_posix(),
                    )
                )
        return cls(chunks)

    def _build_index(self) -> None:
        document_frequency: dict[str, int] = {}
        self._chunk_terms = [terms(f"{chunk.section}\n{chunk.text}") for chunk in self._chunks]
        for chunk_terms in self._chunk_terms:
            for term in chunk_terms:
                document_frequency[term] = document_frequency.get(term, 0) + 1
        total = max(len(self._chunks), 1)
        self._idf = {
            term: math.log((total + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }
        for chunk_terms in self._chunk_terms:
            vector = {
                term: (1.0 + math.log(1.0)) * self._idf.get(term, 1.0)
                for term in chunk_terms
            }
            self._vectors.append(_normalize(vector))

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        query_terms = terms(query)
        if not query_terms or not self._chunks:
            return []
        query_idf = {term: self._idf.get(term, 1.0) for term in query_terms}
        query_vector = _normalize(dict(query_idf))
        idf_sum = sum(query_idf.values()) or 1.0
        scored: list[SearchHit] = []
        for index, chunk in enumerate(self._chunks):
            vector = self._vectors[index]
            cosine = sum(
                weight * query_vector.get(term, 0.0)
                for term, weight in vector.items()
            )
            matched = query_terms & self._chunk_terms[index]
            keyword = sum(query_idf[term] for term in matched) / idf_sum
            score = _VECTOR_WEIGHT * cosine + _KEYWORD_WEIGHT * keyword
            if score <= 0:
                continue
            scored.append(
                SearchHit(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    title=chunk.title,
                    section=chunk.section,
                    snippet=_snippet(f"{chunk.section}\n{chunk.text}", matched),
                    score=round(score, 4),
                    source=chunk.source,
                )
            )
        scored.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return scored[:top_k]


def _normalize(vector: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(weight * weight for weight in vector.values()))
    if norm <= 0:
        return {}
    return {term: weight / norm for term, weight in vector.items()}
