from __future__ import annotations

from typing import Any

from ..models import LearningSession
from ..security import redact_secret_text
from .sag_service import index_sag_text, rag_backend, sag_enabled, search_sag_context


def index_learning_material(store, session: LearningSession, content: str, ai_config: dict[str, str]) -> str:
    if sag_enabled():
        result = index_sag_text(
            store,
            content,
            tenant_id=session.user_id,
            user_id=session.user_id,
            session_id=session.id,
            source_id=session.id,
            ai_config=ai_config,
        )
        return (
            f"SAG 已索引：{result.get('chunks', 0)} 个语义片段、"
            f"{result.get('entities', 0)} 个实体、{result.get('events', 0)} 个事件"
        )
    return index_legacy_neo4j_material(session, content, ai_config)


def index_organization_material(
    store,
    organization_id: str,
    user_id: str,
    source_id: str,
    content: str,
    ai_config: dict[str, str],
) -> str:
    if sag_enabled():
        result = index_sag_text(
            store,
            content,
            tenant_id=organization_id,
            user_id=user_id,
            session_id=organization_id,
            source_id=source_id,
            ai_config=ai_config,
        )
        return (
            f"组织知识库 SAG 已索引：{result.get('chunks', 0)} 个语义片段、"
            f"{result.get('entities', 0)} 个实体、{result.get('events', 0)} 个事件"
        )
    return index_legacy_neo4j_organization(organization_id, user_id, source_id, content, ai_config)


def delete_organization_source(store, organization_id: str, source_id: str) -> str:
    if sag_enabled():
        store.delete_sag_source(organization_id, organization_id, source_id)
        return "组织知识库 SAG 索引已清理"
    return delete_legacy_neo4j_organization(organization_id, source_id)


def retrieve_rag_context(
    store,
    session: LearningSession,
    ai_config: dict[str, str] | None,
    *,
    query: str,
    top_k: int = 3,
) -> dict[str, Any]:
    if not sag_enabled():
        return retrieve_legacy_neo4j_context(session, ai_config, query=query, top_k=top_k)

    personal = search_sag_context(
        store,
        query,
        tenant_id=session.user_id,
        user_id=session.user_id,
        session_id=session.id,
        source_id=session.id,
        top_k=top_k,
        ai_config=ai_config,
    )
    contexts = [personal]
    if session.organization_id:
        organization = search_sag_context(
            store,
            query,
            tenant_id=session.organization_id,
            session_id=session.organization_id,
            top_k=top_k,
            ai_config=ai_config,
        )
        contexts.append(organization)
    return merge_rag_contexts(*contexts)


def merge_rag_contexts(*contexts: dict[str, Any]) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    subgraphs: list[dict[str, Any]] = []
    reasons: list[str] = []
    backend = rag_backend()
    levels: list[str] = []
    for context in contexts:
        chunks.extend(context.get("chunks") or [])
        subgraphs.extend(context.get("subgraphs") or [])
        if context.get("reason"):
            reasons.append(str(context["reason"]))
        if context.get("backend"):
            backend = str(context["backend"])
        for level in context.get("levels") or []:
            if level not in levels:
                levels.append(level)
    merged: dict[str, Any] = {
        "chunks": dedupe_chunks(chunks),
        "subgraphs": subgraphs[:6],
        "backend": backend,
        "levels": levels,
    }
    if reasons:
        merged["reason"] = "；".join(reasons)
    return merged


def dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, str]] = set()
    unique: list[dict[str, Any]] = []
    for chunk in sorted(chunks, key=lambda item: float(item.get("score") or 0), reverse=True):
        key = (str(chunk.get("source_id") or ""), int(chunk.get("chunk_index") or -1), str(chunk.get("text") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique[:8]


def index_legacy_neo4j_material(session: LearningSession, content: str, ai_config: dict[str, str]) -> str:
    from .neo4j_service import extract_and_store_knowledge
    from .vector_service import chunk_and_store

    entity_result = extract_and_store_knowledge(
        content,
        ai_config,
        tenant_id=session.user_id,
        user_id=session.user_id,
        session_id=session.id,
        source_id=session.id,
    )
    chunk_result = chunk_and_store(
        content,
        session.id,
        ai_config,
        tenant_id=session.user_id,
        user_id=session.user_id,
        session_id=session.id,
    )
    return (
        f"GraphRAG 已索引：{entity_result.get('entities', 0)} 个实体、"
        f"{entity_result.get('relations', 0)} 条关系、{chunk_result.get('chunks', 0)} 个向量片段"
    )


def index_legacy_neo4j_organization(
    organization_id: str,
    user_id: str,
    source_id: str,
    content: str,
    ai_config: dict[str, str],
) -> str:
    from .neo4j_service import extract_and_store_knowledge
    from .vector_service import chunk_and_store

    entity_result = extract_and_store_knowledge(
        content,
        ai_config,
        tenant_id=organization_id,
        user_id=user_id,
        session_id=organization_id,
        source_id=source_id,
    )
    chunk_result = chunk_and_store(
        content,
        source_id,
        ai_config,
        tenant_id=organization_id,
        user_id=user_id,
        session_id=organization_id,
    )
    return (
        f"组织知识库 GraphRAG 已索引：{entity_result.get('entities', 0)} 个实体、"
        f"{entity_result.get('relations', 0)} 条关系、{chunk_result.get('chunks', 0)} 个向量片段"
    )


def retrieve_legacy_neo4j_context(
    session: LearningSession,
    ai_config: dict[str, str] | None,
    *,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    from .neo4j_service import graphrag_enabled
    from .vector_service import hybrid_graph_search

    if not graphrag_enabled() or not ai_config:
        return {"chunks": [], "subgraphs": [], "backend": "legacy_neo4j", "fallback": True}
    graph_context = hybrid_graph_search(
        query,
        ai_config,
        top_k=top_k,
        tenant_id=session.user_id,
        user_id=session.user_id,
        session_id=session.id,
        source_id=session.id,
    )
    if session.organization_id:
        organization_context = hybrid_graph_search(
            query,
            ai_config,
            top_k=top_k,
            tenant_id=session.organization_id,
            session_id=session.organization_id,
        )
        graph_context = merge_rag_contexts(graph_context, organization_context)
    graph_context["backend"] = "legacy_neo4j"
    return graph_context


def delete_legacy_neo4j_organization(organization_id: str, source_id: str) -> str:
    from .neo4j_service import get_neo4j_driver, graphrag_enabled

    if not graphrag_enabled():
        return "组织知识库 GraphRAG 未启用，无需清理"
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n)
            WHERE n.tenant_id = $tenant_id
              AND n.session_id = $session_id
              AND n.source_id = $source_id
            WITH collect(n) AS nodes, count(n) AS deleted
            FOREACH (node IN nodes | DETACH DELETE node)
            RETURN deleted
            """,
            tenant_id=organization_id,
            session_id=organization_id,
            source_id=source_id,
        )
        record = result.single()
    deleted = int(record["deleted"] if record else 0)
    return f"组织知识库 GraphRAG 已清理：{deleted} 个节点"


def safe_rag_error(exc: Exception) -> str:
    return redact_secret_text(str(exc), limit=180)
