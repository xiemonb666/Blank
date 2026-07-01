from __future__ import annotations

import os


def test_semantic_splitter_preserves_headings_and_limits_chunk_size() -> None:
    from app.services_v2.semantic_splitter import semantic_text_chunks

    content = "\n".join(
        [
            "# 注意力机制",
            "注意力机制会根据查询和键的相关性分配权重。",
            "",
            "## 计算步骤",
            "第一步计算相关性。第二步归一化权重。第三步加权求和。",
            "",
            "这个段落很长。" * 80,
        ]
    )

    chunks = semantic_text_chunks(content, max_chars=120, overlap_chars=20)

    assert len(chunks) >= 3
    assert chunks[0].text.startswith("# 注意力机制")
    assert any("## 计算步骤" in chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= 120 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_sag_index_and_multi_level_search_expand_events_and_entities() -> None:
    from app.services_v2.sag_service import build_local_sag_index, search_sag_index

    content = """
    TCP 建立连接需要三次握手，客户端发送 SYN，服务器返回 SYN-ACK，客户端再返回 ACK。

    TCP 断开连接需要四次挥手。四次挥手多一次，是因为 TCP 是全双工通信，两个方向的发送通道需要分别关闭。

    滑动窗口用于流量控制，拥塞控制用于避免网络过载。
    """

    index = build_local_sag_index(
        content,
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="session-a",
        source_id="source-a",
    )
    result = search_sag_index(index, "为什么四次挥手和全双工有关？", top_k=2)

    assert result["backend"] == "sag"
    assert result["levels"] == ["lexical", "entity", "event", "neighbor"]
    assert result["chunks"]
    assert "全双工" in result["chunks"][0]["text"]
    centers = {subgraph["center"] for subgraph in result["subgraphs"]}
    assert {"四次挥手", "全双工"} & centers


def test_sag_postgres_index_is_scoped_and_searchable() -> None:
    from app.services_v2.sag_service import index_sag_text, search_sag_context
    from app.store import SessionStore

    store = SessionStore(os.getenv("BLANK_DATABASE_URL", "postgresql://blank:blank@postgres:5432/blank"))
    with store._connect() as connection:
        connection.execute("delete from sag_event_entities")
        connection.execute("delete from sag_chunk_entities")
        connection.execute("delete from sag_events")
        connection.execute("delete from sag_entities")
        connection.execute("delete from sag_chunks")

    index_sag_text(
        store,
        "四次挥手多一次，是因为 TCP 是全双工通信，两个方向需要分别关闭发送通道。",
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="session-a",
        source_id="source-a",
        ai_config=None,
    )
    index_sag_text(
        store,
        "滑动窗口用于流量控制。",
        tenant_id="tenant-b",
        user_id="user-b",
        session_id="session-b",
        source_id="source-b",
        ai_config=None,
    )

    result = search_sag_context(
        store,
        "四次挥手为什么和全双工有关？",
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="session-a",
        source_id="source-a",
        top_k=3,
        ai_config=None,
    )

    assert result["backend"] == "sag"
    assert result["chunks"]
    assert all(chunk["source_id"] == "source-a" for chunk in result["chunks"])
    assert "全双工" in result["chunks"][0]["text"]


def test_sag_search_keeps_same_chunk_indexes_separated_by_source() -> None:
    from app.services_v2.sag_service import index_sag_text, search_sag_context
    from app.store import SessionStore

    store = SessionStore(os.getenv("BLANK_DATABASE_URL", "postgresql://blank:blank@postgres:5432/blank"))
    with store._connect() as connection:
        connection.execute("delete from sag_event_entities")
        connection.execute("delete from sag_chunk_entities")
        connection.execute("delete from sag_events")
        connection.execute("delete from sag_entities")
        connection.execute("delete from sag_chunks")

    index_sag_text(
        store,
        "注意力机制会根据查询和键的相关性分配权重。",
        tenant_id="org-a",
        user_id="",
        session_id="org-knowledge",
        source_id="source-a",
        ai_config=None,
    )
    index_sag_text(
        store,
        "梯度裁剪用于限制梯度范数，避免训练过程发生梯度爆炸。",
        tenant_id="org-a",
        user_id="",
        session_id="org-knowledge",
        source_id="source-b",
        ai_config=None,
    )

    result = search_sag_context(
        store,
        "为什么要使用梯度裁剪？",
        tenant_id="org-a",
        session_id="org-knowledge",
        top_k=1,
        ai_config=None,
    )

    assert result["chunks"]
    assert result["chunks"][0]["source_id"] == "source-b"
    assert "梯度裁剪" in result["chunks"][0]["text"]
