from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


DEFAULT_CHUNK_SIZE = 420
DEFAULT_CHUNK_OVERLAP = 50
MIN_CHUNK_SIZE = 80
MAX_CHUNK_SIZE = 2000
SENTENCE_PATTERN = re.compile(r"[^。！？；.!?;\n]+[。！？；.!?;]?|\n+")
HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6}\s+|第[一二三四五六七八九十百千万0-9]+[章节篇部分]|[一二三四五六七八九十]+[、.．])")


@dataclass(frozen=True)
class SemanticChunk:
    index: int
    text: str
    text_hash: str


def semantic_text_chunks(
    content: str,
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP,
) -> list[SemanticChunk]:
    """按标题、段落和句子边界生成可追溯语义片段。"""
    normalized = normalize_learning_text(content)
    if not normalized:
        return []

    size = max(MIN_CHUNK_SIZE, min(max_chars, MAX_CHUNK_SIZE))
    overlap = max(0, min(overlap_chars, size // 3))
    units = split_semantic_units(normalized, size)
    merged = merge_units(units, size)
    if overlap:
        merged = add_context_overlap(merged, size, overlap)

    chunks: list[SemanticChunk] = []
    for index, text in enumerate(merged):
        cleaned = text.strip()
        if not cleaned:
            continue
        chunks.append(
            SemanticChunk(
                index=len(chunks),
                text=cleaned,
                text_hash=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def normalize_learning_text(content: str) -> str:
    lines = [line.strip() for line in content.replace("\x00", "").splitlines()]
    normalized: list[str] = []
    blank_seen = False
    for line in lines:
        if not line:
            if normalized and not blank_seen:
                normalized.append("")
            blank_seen = True
            continue
        normalized.append(line)
        blank_seen = False
    return "\n".join(normalized).strip()


def split_semantic_units(content: str, max_chars: int) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    units: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            units.append(block)
            continue
        units.extend(split_long_block(block, max_chars))
    return units


def split_long_block(block: str, max_chars: int) -> list[str]:
    heading = ""
    body = block
    lines = block.splitlines()
    if lines and is_heading(lines[0]) and len(lines) > 1:
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

    segments: list[str] = []
    current = heading
    for sentence in split_sentences(body):
        candidate = f"{current}{sentence}" if not current else f"{current}\n{sentence}"
        if current and len(candidate) > max_chars:
            segments.append(current)
            current = f"{heading}\n{sentence}".strip() if heading and len(sentence) + len(heading) + 1 <= max_chars else sentence
            continue
        if len(sentence) > max_chars:
            if current:
                segments.append(current)
                current = ""
            segments.extend(fixed_width_split(sentence, max_chars))
            continue
        current = candidate if current else sentence
    if current:
        segments.append(current)
    return segments


def split_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in SENTENCE_PATTERN.findall(text) if part.strip()]
    return parts or [text.strip()]


def fixed_width_split(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars) if text[index : index + max_chars].strip()]


def merge_units(units: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
            continue
        separator = "\n\n" if is_heading(unit) or "\n" in unit else "\n"
        candidate = f"{current}{separator}{unit}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = unit
    if current:
        chunks.append(current)
    return chunks


def add_context_overlap(chunks: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    if len(chunks) <= 1:
        return chunks
    with_overlap = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:]):
        if is_heading(current):
            with_overlap.append(current)
            continue
        prefix = previous[-overlap_chars:].strip()
        candidate = f"{prefix}\n{current}".strip() if prefix else current
        with_overlap.append(candidate[-max_chars:] if len(candidate) > max_chars else candidate)
    return with_overlap


def is_heading(text: str) -> bool:
    first_line = text.splitlines()[0] if text else ""
    return bool(HEADING_PATTERN.match(first_line))
