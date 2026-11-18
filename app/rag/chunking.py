"""Split runbook markdown into small, citable chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BOUNDARIES = ("。", "！", "？", "；", "\n")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    text: str
    source: str


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            for punct in _BOUNDARIES:
                position = text.rfind(punct, start, end)
                if position > start + max_chars // 3:
                    end = position + 1
                    break
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return pieces


def _sections(text: str, fallback_title: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = fallback_title
    buffer: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match and len(match.group(1)) <= 2:
            if buffer:
                sections.append((current_title, buffer))
                buffer = []
            current_title = match.group(2).strip() or fallback_title
            continue
        buffer.append(line)
    if buffer:
        sections.append((current_title, buffer))
    return [(title, "\n".join(lines).strip()) for title, lines in sections]


def split_document(
    *,
    doc_id: str,
    title: str,
    text: str,
    source: str,
    max_chars: int = 420,
    overlap: int = 80,
) -> list[Chunk]:
    """Return chunks that keep their section title so citations are readable."""
    chunks: list[Chunk] = []
    for section_title, body in _sections(text, title):
        if not body:
            continue
        for piece in _split_long(body, max_chars, overlap):
            chunk_id = f"{doc_id}#{len(chunks)}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    title=title,
                    section=section_title,
                    text=f"{section_title}\n{piece}",
                    source=source,
                )
            )
    return chunks
