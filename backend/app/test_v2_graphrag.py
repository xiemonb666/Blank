#!/usr/bin/env python3
"""
V2 GraphRAG 离线测试脚本
==========================
用途：验证 Neo4j 图数据库与向量索引的数据入库流程。

运行前提：
1. Neo4j 数据库已启动（本地或远程均可）。
2. 环境变量已配置（或采用脚本中的默认值）。
3. AI 模型 API 配置已填入（脚本会通过现有 API 配置机制读取）。

运行方式：
    cd backend
    python -m app.test_v2_graphrag

或：
    cd backend/app && python test_v2_graphrag.py
"""
from __future__ import annotations

import os
import sys

# 将项目根目录加入路径，确保能导入 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services_v2.neo4j_service import (
    extract_and_store_knowledge,
    list_all_entities,
    close_neo4j_driver,
)
from app.services_v2.vector_service import chunk_and_store, similarity_search, hybrid_graph_search
from app.store import SessionStore

# ------------------------------- 测试文本 -------------------------------
TEST_EDUCATIONAL_TEXT = """计算机网络中的 TCP 协议。

TCP（Transmission Control Protocol，传输控制协议）是一种面向连接的、可靠的、基于字节流的传输层通信协议。
TCP 建立连接需要三次握手（Three-way Handshake）：
1. 客户端发送 SYN 报文到服务器；
2. 服务器回复 SYN-ACK 报文；
3. 客户端再发送 ACK 报文确认。
三次握手的目的是保证双方收发能力的同步确认，防止历史重复连接初始化造成的混乱。

TCP 断开连接需要四次挥手（Four-way Handshake）：
1. 主动关闭方发送 FIN 报文；
2. 被动关闭方回复 ACK 报文；
3. 被动关闭方发送 FIN 报文；
4. 主动关闭方回复 ACK 报文。
四次挥手比三次握手多一次，是因为 TCP 连接是全双工的，每一方都需要单独关闭自己的发送通道。

TCP 通过序列号（Sequence Number）、确认应答（ACK）、重传机制、流量控制（滑动窗口）和拥塞控制来保证可靠性。"""

# 预置的实体与关系数据（用于跳过 LLM 直接测试 Neo4j 写入）
PREBUILT_ENTITIES = [
    {"name": "TCP协议", "type": "协议", "description": "面向连接的可靠传输协议"},
    {"name": "三次握手", "type": "机制", "description": "TCP建立连接的同步确认过程"},
    {"name": "四次挥手", "type": "机制", "description": "TCP断开连接的全双工关闭过程"},
    {"name": "SYN报文", "type": "数据单元", "description": "同步序列编号报文，用于发起连接"},
    {"name": "ACK报文", "type": "数据单元", "description": "确认应答报文"},
    {"name": "FIN报文", "type": "数据单元", "description": "结束连接报文"},
    {"name": "序列号", "type": "机制", "description": "保证数据包顺序编号的机制"},
    {"name": "滑动窗口", "type": "机制", "description": "TCP流量控制机制"},
    {"name": "拥塞控制", "type": "机制", "description": "防止网络过载的调节机制"},
    {"name": "全双工", "type": "概念", "description": "通信双方可同时发送和接收数据"},
]

PREBUILT_RELATIONS = [
    {"source": "TCP协议", "target": "三次握手", "type": "包含", "description": "TCP使用三次握手建立连接"},
    {"source": "TCP协议", "target": "四次挥手", "type": "包含", "description": "TCP使用四次挥手断开连接"},
    {"source": "三次握手", "target": "SYN报文", "type": "包含", "description": "三次握手发送SYN报文"},
    {"source": "三次握手", "target": "ACK报文", "type": "包含", "description": "三次握手发送ACK报文"},
    {"source": "四次挥手", "target": "FIN报文", "type": "包含", "description": "四次挥手发送FIN报文"},
    {"source": "四次挥手", "target": "ACK报文", "type": "包含", "description": "四次挥手发送ACK报文"},
    {"source": "TCP协议", "target": "序列号", "type": "依赖", "description": "TCP通过序列号保证可靠性"},
    {"source": "TCP协议", "target": "滑动窗口", "type": "依赖", "description": "TCP通过滑动窗口进行流量控制"},
    {"source": "TCP协议", "target": "拥塞控制", "type": "依赖", "description": "TCP通过拥塞控制防止网络过载"},
    {"source": "四次挥手", "target": "全双工", "type": "原因", "description": "四次挥手多一次是因为全双工通信"},
]


def _load_ai_config_from_store() -> dict[str, str] | None:
    """从 PostgreSQL 配置中读取当前启用的 AI 模型配置（用于测试阶段的 LLM 调用）。"""
    database_url = os.getenv("BLANK_DATABASE_URL", "postgresql://blank:blank@127.0.0.1:5432/blank")
    if not database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg2://")):
        print("[警告] BLANK_DATABASE_URL 不是 PostgreSQL 连接字符串，跳过 AI 配置自动加载。")
        return None

    try:
        store = SessionStore(database_url)
        config = store.get_active_api_config_secret_record()
        if config:
            print(f"[信息] 已加载 AI 配置：provider={config['provider']}, model={config['model']}")
        return config
    except Exception as exc:
        print(f"[警告] 读取 AI 配置失败：{exc}")
        return None


def _store_prebuilt_knowledge() -> dict[str, int]:
    """绕过 LLM，直接将预置的实体与关系写入 Neo4j（用于快速验证图数据库底座）。"""
    from app.services_v2.neo4j_service import get_neo4j_driver
    driver = get_neo4j_driver()
    stored_entities = 0
    stored_relations = 0
    try:
        with driver.session() as session:
            for entity in PREBUILT_ENTITIES:
                session.run(
                    """
                    MERGE (e:Entity {name: $name})
                    ON CREATE SET e.type = $type, e.description = $description, e.created_at = datetime()
                    ON MATCH  SET e.type = $type, e.description = $description, e.updated_at = datetime()
                    """,
                    name=entity["name"],
                    type=entity["type"],
                    description=entity["description"],
                )
                stored_entities += 1
            for rel in PREBUILT_RELATIONS:
                session.run(
                    """
                    MERGE (a:Entity {name: $src})
                    MERGE (b:Entity {name: $tgt})
                    MERGE (a)-[r:RELATES {type: $rel_type}]->(b)
                    ON CREATE SET r.description = $description, r.created_at = datetime()
                    ON MATCH  SET r.description = $description, r.updated_at = datetime()
                    """,
                    src=rel["source"],
                    tgt=rel["target"],
                    rel_type=rel["type"],
                    description=rel["description"],
                )
                stored_relations += 1
    except Exception as exc:
        raise RuntimeError(f"Neo4j 预置数据写入失败：{exc}") from exc
    return {"entities": stored_entities, "relations": stored_relations}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Blank V2 GraphRAG 离线测试")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 调用，使用预置数据直接测试 Neo4j 与向量索引（推荐首次测试或网络不通时使用）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Blank V2 GraphRAG 离线测试")
    print("=" * 60)

    # 1. 加载 AI 配置（向量入库/检索需要，图入库若 skip-llm 则不需要）
    ai_config = _load_ai_config_from_store()
    if not ai_config and not args.skip_llm:
        print("\n[错误] 未找到可用的 AI 配置。请在后台管理页面配置并启用一个模型后重试，")
        print("       或添加 --skip-llm 参数跳过 LLM 调用，仅测试 Neo4j 图数据库底座。")
        return 1

    # 2. 测试图数据入库
    print("\n>>> 测试 1/4：图实体与关系抽取入库")
    if args.skip_llm:
        print("    [模式] --skip-llm 已启用，跳过 LLM 调用，使用预置数据直接写入 Neo4j。")
        try:
            result = _store_prebuilt_knowledge()
            print(f"    成功存储实体：{result['entities']} 个")
            print(f"    成功存储关系：{result['relations']} 条")
        except Exception as exc:
            print(f"    [失败] {exc}")
            return 1
    else:
        print(f"    [诊断] 即将调用 LLM：base_url={ai_config.get('base_url')}, model={ai_config.get('model')}")
        print("    [诊断] 若此处长时间无响应，通常是网络不通或 LLM 服务未就绪，可按 Ctrl+C 中断后检查网络。")
        try:
            result = extract_and_store_knowledge(TEST_EDUCATIONAL_TEXT, ai_config)
            print(f"    成功存储实体：{result['entities']} 个")
            print(f"    成功存储关系：{result['relations']} 条")
        except KeyboardInterrupt:
            print("\n    [中断] 用户手动中断。建议添加 --skip-llm 参数跳过 LLM 测试。")
            return 1
        except Exception as exc:
            print(f"    [失败] {exc}")
            return 1

    # 3. 验证图数据可读性
    print("\n>>> 测试 2/4：图数据回读验证")
    try:
        entities = list_all_entities(limit=20)
        print(f"    数据库中已有实体：{len(entities)} 个")
        for e in entities[:5]:
            print(f"      - [{e['type']}] {e['name']}: {e['description'][:40]}...")
        if len(entities) > 5:
            print(f"      ... 还有 {len(entities) - 5} 个")
    except Exception as exc:
        print(f"    [失败] {exc}")
        return 1

    # 4. 测试向量入库（需要 Embedding，若 skip-llm 但无 ai_config 则跳过）
    print("\n>>> 测试 3/4：文本切块与向量入库")
    if not ai_config:
        print("    [跳过] 未配置 AI 模型，无法生成 Embedding，跳过向量入库测试。")
    else:
        try:
            vec_result = chunk_and_store(
                text=TEST_EDUCATIONAL_TEXT,
                source_id="test-session-001",
                ai_config=ai_config,
            )
            print(f"    成功切块：{vec_result['chunks']} 块")
            print(f"    向量维度：{vec_result['dimension']}")
        except Exception as exc:
            print(f"    [失败] {exc}")
            return 1

    # 5. 测试向量检索与混合检索（需要 Embedding）
    print("\n>>> 测试 4/4：向量相似度检索与 GraphRAG 混合检索")
    if not ai_config:
        print("    [跳过] 未配置 AI 模型，跳过检索测试。")
    else:
        test_queries = [
            "TCP 三次握手的过程是什么？",
            "TCP 如何保证可靠性？",
            "四次挥手为什么比三次握手多一次？",
        ]
        for q in test_queries:
            print(f"\n    [查询] {q}")
            try:
                chunks = similarity_search(q, ai_config, top_k=3)
                print(f"      向量召回：{len(chunks)} 条")
                for c in chunks:
                    print(f"        - (score={c['score']:.3f}) {c['text'][:50]}...")

                hybrid = hybrid_graph_search(q, ai_config, top_k=3)
                print(f"      混合检索召回子图：{len(hybrid['subgraphs'])} 个")
                for sg in hybrid["subgraphs"]:
                    print(f"        - 中心实体：{sg['center']}，邻域节点：{len(sg['nodes'])} 个，边：{len(sg['edges'])} 条")
            except Exception as exc:
                print(f"      [失败] {exc}")

    # 6. 清理连接
    print("\n>>> 清理资源")
    close_neo4j_driver()
    print("    Neo4j 驱动已关闭。")

    print("\n" + "=" * 60)
    print("所有测试步骤执行完毕，请检查上方输出确认数据已正确入库。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
