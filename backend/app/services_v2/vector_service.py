from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from neo4j import Driver

from ..debug_logging import log_debug_event, sanitize_debug_text
from ..security import validate_model_request_parts
from ..services import (
    estimate_tokens_from_text,
    openai_compatible_headers,
    openai_request_timeout,
    open_model_request,
    read_model_response,
    record_llm_token_usage,
)
from .neo4j_service import get_neo4j_driver

# 向量索引默认维度（OpenAI text-embedding-3-small 为 1536，Ollama nomic-embed-text 为 768）
_DEFAULT_EMBEDDING_DIM = int(os.getenv("BLANK_EMBEDDING_DIM", "1536"))
# 向量索引默认相似度函数
_DEFAULT_SIMILARITY = os.getenv("BLANK_EMBEDDING_SIMILARITY", "cosine")


def _get_embedding_endpoint(base_url: str) -> str:
    """根据 Base URL 拼接出 OpenAI 兼容的 Embedding 端点。"""
    normalized = base_url.rstrip("/")
    return f"{normalized}/embeddings"


def get_embedding(texts: list[str], ai_config: dict[str, str]) -> list[list[float]]:
    """
    调用 OpenAI 兼容接口获取文本 Embedding。

    参数：
        texts: 待编码的文本列表（单次建议不超过 16 条）。
        ai_config: 包含 base_url / api_key / model 的字典。

    返回：
        与输入顺序一致的向量列表。
    """
    if not texts:
        return []

    safe_base_url, safe_api_key, safe_model = validate_model_request_parts(
        ai_config["base_url"],
        ai_config["api_key"],
        ai_config.get("embedding_model") or ai_config["model"],
    )
    endpoint = _get_embedding_endpoint(safe_base_url)
    body = {
        "model": safe_model,
        "input": texts,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={**openai_compatible_headers(safe_base_url, safe_api_key), "Content-Type": "application/json"},
        method="POST",
    )
    log_debug_event(
        "embedding.request",
        endpoint=endpoint,
        model=safe_model,
        input_count=len(texts),
        inputs=[sanitize_debug_text(text, limit=1200) for text in texts],
    )
    try:
        with open_model_request(request, timeout=openai_request_timeout(safe_base_url)) as response:
            raw_body = read_model_response(response).decode("utf-8")
            status = getattr(response, "status", None) or getattr(response, "code", None)
            payload = json.loads(raw_body)
    except Exception as exc:
        log_debug_event("embedding.error", endpoint=endpoint, model=safe_model, error=str(exc))
        raise RuntimeError(f"Embedding 接口调用失败：{exc}") from exc

    # OpenAI 格式：data[*].embedding
    data = payload.get("data", [])
    if not isinstance(data, list) or len(data) != len(texts):
        log_debug_event("embedding.response.invalid", endpoint=endpoint, model=safe_model, payload=payload)
        raise RuntimeError(f"Embedding 返回格式异常：期望 {len(texts)} 条，实际 {len(data)} 条。")

    # 按 index 排序，保证与输入顺序一致
    data.sort(key=lambda x: x.get("index", 0))
    vectors = [item["embedding"] for item in data]
    record_llm_token_usage(
        provider="embedding",
        model=safe_model,
        messages=[{"role": "input", "content": "\n".join(texts)}],
        output_text="",
        payload={
            "usage": {
                "prompt_tokens": sum(estimate_tokens_from_text(text) for text in texts),
                "completion_tokens": 0,
            }
        },
        source="rag.embedding",
    )
    log_debug_event(
        "embedding.response",
        endpoint=endpoint,
        model=safe_model,
        status=status,
        vector_count=len(vectors),
        dimensions=[len(vector) if isinstance(vector, list) else 0 for vector in vectors],
    )
    return vectors


def _ensure_vector_index(driver: Driver, dimension: int) -> None:
    """
    检查并创建 Neo4j 向量索引（若不存在）。
    使用 Chunk 节点的 embedding 属性作为向量字段。
    """
    try:
        with driver.session() as session:
            # 查询是否已存在同名索引
            result = session.run(
                """
                SHOW INDEXES YIELD name, type
                WHERE name = 'chunk_embedding' AND type = 'VECTOR'
                RETURN count(*) AS cnt
                """
            )
            record = result.single()
            if record and record["cnt"] > 0:
                return

            # 创建向量索引，指定维度和相似度函数
            session.run(
                f"""
                CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                FOR (c:Chunk) ON (c.embedding)
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: $dim,
                        `vector.similarity_function`: $sim
                    }}
                }}
                """,
                dim=dimension,
                sim=_DEFAULT_SIMILARITY,
            )
    except Exception as exc:
        raise RuntimeError(f"Neo4j 向量索引创建失败：{exc}") from exc


def chunk_and_store(
    text: str,
    source_id: str,
    ai_config: dict[str, str],
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    将文本切分为小块，生成 Embedding 后存入 Neo4j 向量索引。

    参数：
        text: 原始长文本。
        source_id: 来源标识（如 session_id 或 material_id）。
        ai_config: 包含 base_url / api_key / model 的字典。

    返回：
        {"chunks": 切块数量, "dimension": 向量维度}
    """
    if not text or not text.strip():
        raise ValueError("输入文本不能为空。")
    from .neo4j_service import _normalize_scope

    scope = _normalize_scope(tenant_id, user_id, session_id or source_id, source_id)

    # 1. 文本切块：按段落+句子递归切分，每块约 300-500 字符，重叠 50 字符保证上下文连贯
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", " ", ""],
        )
        chunks = splitter.split_text(text)
    except Exception as exc:
        raise RuntimeError(f"文本切块失败：{exc}") from exc

    if not chunks:
        raise RuntimeError("文本切块后为空，请检查输入内容长度。")

    # 2. 批量生成 Embedding（每批 8 条，防止请求过大）
    embeddings: list[list[float]] = []
    batch_size = 8
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        try:
            batch_embeddings = get_embedding(batch, ai_config)
        except Exception as exc:
            raise RuntimeError(f"第 {i // batch_size + 1} 批 Embedding 生成失败：{exc}") from exc
        embeddings.extend(batch_embeddings)

    dimension = len(embeddings[0]) if embeddings else _DEFAULT_EMBEDDING_DIM

    # 3. 确保向量索引存在
    driver = get_neo4j_driver()
    _ensure_vector_index(driver, dimension)

    # 4. 写入 Neo4j
    try:
        with driver.session() as session:
            for idx, (chunk_text, vector) in enumerate(zip(chunks, embeddings)):
                session.run(
                    """
                    CREATE (c:Chunk {
                        text: $text,
                        embedding: $embedding,
                        tenant_id: $tenant_id,
                        user_id: $user_id,
                        session_id: $session_id,
                        source_id: $source_id,
                        index: $index,
                        created_at: datetime()
                    })
                    """,
                    text=chunk_text,
                    embedding=vector,
                    tenant_id=scope["tenant_id"],
                    user_id=scope["user_id"],
                    session_id=scope["session_id"],
                    source_id=scope["source_id"],
                    index=idx,
                )
    except Exception as exc:
        raise RuntimeError(f"Neo4j 向量写入失败：{exc}") from exc

    return {"chunks": len(chunks), "dimension": dimension}


def similarity_search(
    query: str,
    ai_config: dict[str, str],
    top_k: int = 5,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    对查询文本生成 Embedding，并在 Neo4j 向量索引中进行相似度检索。

    参数：
        query: 用户查询。
        ai_config: 包含 base_url / api_key / model 的字典。
        top_k: 返回最相似的文本块数量。

    返回：
        相似文本块列表，每项包含 text / score / source_id。
    """
    if not query or not query.strip():
        return []
    from .neo4j_service import _normalize_scope

    scope = _normalize_scope(tenant_id, user_id, session_id, source_id)

    # 1. 查询向量化
    try:
        query_embedding = get_embedding([query.strip()], ai_config)[0]
    except Exception as exc:
        raise RuntimeError(f"查询向量化失败：{exc}") from exc

    # 2. 向量相似度检索（使用 Neo4j 5.x 的 db.index.vector.queryNodes）
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('chunk_embedding', $candidate_k, $embedding)
                YIELD node, score
                WHERE node.tenant_id = $tenant_id
                  AND node.user_id = $user_id
                  AND node.session_id = $session_id
                  AND node.source_id = $source_id
                RETURN node.text AS text, node.source_id AS source_id, score
                ORDER BY score DESC
                LIMIT $top_k
                """,
                top_k=top_k,
                candidate_k=max(top_k * 20, top_k),
                embedding=query_embedding,
                tenant_id=scope["tenant_id"],
                user_id=scope["user_id"],
                session_id=scope["session_id"],
                source_id=scope["source_id"],
            )
            return [
                {
                    "text": record["text"],
                    "source_id": record["source_id"],
                    "score": record["score"],
                }
                for record in result
            ]
    except Exception as exc:
        raise RuntimeError(f"Neo4j 向量检索失败：{exc}") from exc


def hybrid_graph_search(
    query: str,
    ai_config: dict[str, str],
    top_k: int = 5,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    """
    GraphRAG 混合检索：先通过向量检索找到最相关的文本块，
    再提取这些文本块中涉及的实体，并查询其图邻域作为补充上下文。

    返回：
        {"chunks": [...], "subgraphs": [{"center": "实体名", "nodes": [...], "edges": [...]}]}
    """
    from .neo4j_service import _normalize_scope, get_entity_subgraph

    scope = _normalize_scope(tenant_id, user_id, session_id, source_id)

    # 1. 向量检索召回文本块
    chunks = similarity_search(query, ai_config, top_k=top_k, **scope)
    if not chunks:
        return {"chunks": [], "subgraphs": []}

    # 2. 从召回文本中提取可能提及的实体（简单策略：匹配已有实体名称）
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            # 获取数据库中所有实体名称
            entity_names = [
                record["name"]
                for record in session.run(
                    """
                    MATCH (e:Entity {tenant_id: $tenant_id, session_id: $session_id, source_id: $source_id})
                    RETURN e.name AS name
                    """,
                    tenant_id=scope["tenant_id"],
                    session_id=scope["session_id"],
                    source_id=scope["source_id"],
                )
            ]
    except Exception as exc:
        raise RuntimeError(f"获取实体列表失败：{exc}") from exc

    # 3. 在查询文本和召回文本中查找匹配的实体
    combined_text = query + " " + " ".join(c["text"] for c in chunks)
    matched_entities = [name for name in entity_names if name in combined_text]
    # 去重并限制数量
    matched_entities = list(dict.fromkeys(matched_entities))[:3]

    # 4. 查询每个匹配实体的子图
    subgraphs = []
    for entity_name in matched_entities:
        try:
            subgraph = get_entity_subgraph(entity_name, depth=2, **scope)
            subgraphs.append({"center": entity_name, **subgraph})
        except Exception:
            # 单个子图查询失败不应阻断整体流程
            continue

    return {"chunks": chunks, "subgraphs": subgraphs}
