from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import math
import os
import re
from typing import Any

from .semantic_splitter import SemanticChunk, semantic_text_chunks


RAG_BACKEND_ENV = "BLANK_RAG_BACKEND"
SAG_LEVELS = ["lexical", "entity", "event", "neighbor"]
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
ENTITY_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+_-]{1,}|[\u4e00-\u9fffA-Za-z0-9+-]{2,18}")
CHINESE_TERM_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9+-]{0,8}"
    r"(?:协议|机制|握手|挥手|通信|控制|窗口|缓存|报文|通道|连接|权重|实体|事件)"
)
STOP_TERMS = {
    "因为",
    "所以",
    "用于",
    "需要",
    "一个",
    "这个",
    "如果",
    "为什么",
    "什么",
    "怎么",
    "有关",
    "进行",
    "通过",
}


@dataclass(frozen=True)
class SagEntity:
    name: str
    type: str = "概念"
    description: str = ""


@dataclass(frozen=True)
class SagEvent:
    label: str
    description: str
    chunk_index: int
    source_id: str = ""
    entity_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SagIndexedChunk:
    index: int
    text: str
    text_hash: str
    tenant_id: str
    user_id: str
    session_id: str
    source_id: str
    keywords: tuple[str, ...] = ()
    entity_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SagIndex:
    tenant_id: str
    user_id: str
    session_id: str
    source_id: str
    chunks: tuple[SagIndexedChunk, ...] = ()
    entities: tuple[SagEntity, ...] = ()
    events: tuple[SagEvent, ...] = ()
    backend: str = "sag"


def rag_backend() -> str:
    return os.getenv(RAG_BACKEND_ENV, "sag").strip().lower() or "sag"


def sag_enabled() -> bool:
    return rag_backend() == "sag"


def build_local_sag_index(
    content: str,
    *,
    tenant_id: str,
    user_id: str = "",
    session_id: str,
    source_id: str,
    max_chars: int = 420,
) -> SagIndex:
    semantic_chunks = semantic_text_chunks(content, max_chars=max_chars)
    entities_by_name: dict[str, SagEntity] = {}
    events: list[SagEvent] = []
    indexed_chunks: list[SagIndexedChunk] = []

    for chunk in semantic_chunks:
        keywords = tuple(top_keywords(chunk.text))
        entity_names = tuple(extract_entity_names(chunk.text))
        for name in entity_names:
            entities_by_name.setdefault(name, SagEntity(name=name, type=infer_entity_type(name), description=entity_description(name, chunk.text)))
        events.extend(extract_local_events(chunk, entity_names, source_id=source_id))
        indexed_chunks.append(
            SagIndexedChunk(
                index=chunk.index,
                text=chunk.text,
                text_hash=chunk.text_hash,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                source_id=source_id,
                keywords=keywords,
                entity_names=entity_names,
            )
        )

    return SagIndex(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        source_id=source_id,
        chunks=tuple(indexed_chunks),
        entities=tuple(sorted(entities_by_name.values(), key=lambda entity: entity.name)),
        events=tuple(events),
    )


def index_sag_text(
    store,
    content: str,
    *,
    tenant_id: str,
    session_id: str,
    source_id: str,
    user_id: str = "",
    ai_config: dict[str, str] | None = None,
) -> dict[str, int | str]:
    """构建 SAG 索引并写入 PostgreSQL。ai_config 预留给 LLM 事件抽取增强。"""
    _ = ai_config
    index = build_local_sag_index(
        content,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        source_id=source_id,
    )
    store.replace_sag_index(index)
    return {
        "backend": "sag",
        "chunks": len(index.chunks),
        "entities": len(index.entities),
        "events": len(index.events),
    }


def search_sag_context(
    store,
    query: str,
    *,
    tenant_id: str,
    session_id: str,
    source_id: str | None = None,
    user_id: str | None = None,
    top_k: int = 5,
    ai_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    """从 PostgreSQL 读取 SAG 索引并执行多级召回。"""
    _ = ai_config
    index = store.load_sag_index(
        tenant_id=tenant_id,
        session_id=session_id,
        source_id=source_id,
        user_id=user_id,
    )
    return search_sag_index(index, query, top_k=top_k)


def search_sag_index(index: SagIndex, query: str, top_k: int = 5) -> dict[str, Any]:
    if not query.strip():
        return {"chunks": [], "subgraphs": [], "backend": "sag", "levels": SAG_LEVELS}

    query_tokens = set(tokenize(query))
    query_entities = set(extract_entity_names(query))
    chunk_by_key = {(chunk.source_id, chunk.index): chunk for chunk in index.chunks}
    ordered_keys = list(chunk_by_key.keys())
    scores: dict[tuple[str, int], float] = defaultdict(float)
    reasons: dict[tuple[str, int], set[str]] = defaultdict(set)

    for chunk in index.chunks:
        chunk_key = (chunk.source_id, chunk.index)
        lexical_score = overlap_score(query_tokens, set(chunk.keywords) | set(tokenize(chunk.text)))
        if lexical_score:
            scores[chunk_key] += lexical_score
            reasons[chunk_key].add("lexical")
        entity_overlap = query_entities & set(chunk.entity_names)
        if entity_overlap:
            scores[chunk_key] += 1.2 + 0.35 * len(entity_overlap)
            reasons[chunk_key].add("entity")

    for event in index.events:
        event_tokens = set(tokenize(f"{event.label} {event.description}"))
        event_entities = set(event.entity_names)
        event_score = overlap_score(query_tokens, event_tokens) + 0.8 * len(query_entities & event_entities)
        if event_score:
            event_source_id = event.source_id or index.source_id
            event_key = (event_source_id, event.chunk_index)
            if event_key not in chunk_by_key:
                continue
            scores[event_key] += event_score + 0.8
            reasons[event_key].add("event")
            for neighbor in (event.chunk_index - 1, event.chunk_index + 1):
                neighbor_key = (event_source_id, neighbor)
                if neighbor_key in chunk_by_key:
                    scores[neighbor_key] += event_score * 0.25
                    reasons[neighbor_key].add("neighbor")

    key_position = {chunk_key: position for position, chunk_key in enumerate(ordered_keys)}
    ranked = sorted(scores.items(), key=lambda item: (-item[1], key_position.get(item[0], 0)))[: max(1, top_k)]
    chunks = [
        {
            "text": chunk_by_key[chunk_key].text,
            "score": round(score, 4),
            "source_id": chunk_by_key[chunk_key].source_id,
            "chunk_index": chunk_by_key[chunk_key].index,
            "levels": sorted(reasons[chunk_key]),
        }
        for chunk_key, score in ranked
    ]
    subgraphs = build_subgraphs(index, query_entities, [chunk_key for chunk_key, _score in ranked])
    return {
        "chunks": chunks,
        "subgraphs": subgraphs,
        "backend": "sag",
        "levels": SAG_LEVELS,
    }


def build_subgraphs(index: SagIndex, query_entities: set[str], chunk_keys: list[tuple[str, int]]) -> list[dict[str, Any]]:
    entity_map = {entity.name: entity for entity in index.entities}
    chunk_by_key = {(chunk.source_id, chunk.index): chunk for chunk in index.chunks}
    selected_chunks = [chunk_by_key[chunk_key] for chunk_key in chunk_keys if chunk_key in chunk_by_key]
    centers = list(dict.fromkeys([*query_entities, *(name for chunk in selected_chunks for name in chunk.entity_names)]))[:4]
    selected_keys = set(chunk_keys)
    subgraphs: list[dict[str, Any]] = []
    for center in centers:
        related_events = [
            event
            for event in index.events
            if center in event.entity_names or ((event.source_id or index.source_id), event.chunk_index) in selected_keys
        ]
        related_names = list(dict.fromkeys(name for event in related_events for name in event.entity_names))[:8]
        nodes = [
            {
                "name": name,
                "type": entity_map.get(name, SagEntity(name=name)).type,
                "description": entity_map.get(name, SagEntity(name=name)).description,
            }
            for name in related_names
        ]
        edges = []
        for event in related_events[:8]:
            for name in event.entity_names:
                if name == center:
                    continue
                edges.append({
                    "source": center,
                    "target": name,
                    "type": event.label,
                    "description": event.description,
                })
        if nodes or edges:
            subgraphs.append({"center": center, "nodes": nodes, "edges": edges[:8]})
    return subgraphs


def extract_local_events(chunk: SemanticChunk, entity_names: tuple[str, ...], *, source_id: str) -> list[SagEvent]:
    events: list[SagEvent] = []
    for sentence in split_event_sentences(chunk.text):
        names = tuple(name for name in entity_names if name in sentence)
        if not names:
            continue
        label = infer_event_label(sentence)
        events.append(SagEvent(label=label, description=sentence[:220], chunk_index=chunk.index, source_id=source_id, entity_names=names[:6]))
    return events


def split_event_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？；.!?;])\s*", text) if item.strip()]


def infer_event_label(sentence: str) -> str:
    if any(word in sentence for word in ("因为", "导致", "原因", "所以")):
        return "因果"
    if any(word in sentence for word in ("步骤", "第一", "第二", "第三", "过程")):
        return "过程"
    if any(word in sentence for word in ("用于", "为了", "作用", "目的")):
        return "功能"
    if any(word in sentence for word in ("包含", "包括", "由")):
        return "组成"
    return "关联"


def extract_entity_names(text: str, limit: int = 12) -> list[str]:
    names: list[str] = []
    candidates = [*CHINESE_TERM_PATTERN.findall(text), *ENTITY_PATTERN.findall(text)]
    for raw in candidates:
        name = raw.strip("：:，,。；;（）()[]【】")
        name = normalize_entity_name(name)
        if len(name) < 2 or name in STOP_TERMS:
            continue
        if name.isdigit():
            continue
        if name not in names:
            names.append(name)
        if name.endswith("通信") and len(name) > 2:
            short_name = name.removesuffix("通信")
            if len(short_name) >= 2 and short_name not in names:
                names.append(short_name)
        if len(names) >= limit:
            break
    return names


def normalize_entity_name(name: str) -> str:
    cleaned = re.sub(r"^(为什么|什么是|请解释|解释一下|因为|所以)", "", name)
    cleaned = re.sub(r"(有关|是什么|为什么|怎么)$", "", cleaned)
    parts = [part for part in re.split(r"[和与及的是否会能,，。；;：:]", cleaned) if part]
    if len(parts) > 1:
        preferred = [part for part in parts if CHINESE_TERM_PATTERN.fullmatch(part) or len(part) <= 8]
        return preferred[-1] if preferred else parts[-1]
    return cleaned


def infer_entity_type(name: str) -> str:
    if any(marker in name for marker in ("协议", "TCP", "HTTP")):
        return "协议"
    if any(marker in name for marker in ("机制", "控制", "握手", "挥手")):
        return "机制"
    if any(marker in name for marker in ("SYN", "ACK", "FIN")):
        return "报文"
    return "概念"


def entity_description(name: str, text: str) -> str:
    for sentence in split_event_sentences(text):
        if name in sentence:
            return sentence[:120]
    return ""


def top_keywords(text: str, limit: int = 18) -> list[str]:
    counter = Counter(token for token in tokenize(text) if token not in STOP_TERMS)
    return [token for token, _count in counter.most_common(limit)]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
            tokens.extend(token[index : index + 2] for index in range(0, len(token) - 1))
        tokens.append(token)
    return [token for token in tokens if token and token not in STOP_TERMS]


def overlap_score(query_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = query_tokens & candidate_tokens
    if not overlap:
        return 0.0
    return len(overlap) / math.sqrt(len(query_tokens) * len(candidate_tokens))
