#!/usr/bin/env python3
"""
V2 多智能体大脑离线测试脚本
==============================
用途：验证 LangGraph 多智能体网络的工作流是否正常运转。

运行方式：
    cd backend
    python -m app.test_v2_agents
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.graph import get_agent_graph
from app.agents.state import AgentState
from app.store import SessionStore


# 模拟教育场景测试用例
TEST_CASES: list[dict] = [
    {
        "name": "学习者提问",
        "state": {
            "session_id": "test-session-001",
            "user_id": "test-user",
            "node_id": "node-tcp",
            "node_title": "TCP协议",
            "node_summary": "面向连接的可靠传输协议，通过三次握手建立连接，四次挥手断开连接。",
            "persona": "plain",
            "user_message": "为什么TCP断开连接需要四次挥手而不是三次？",
            "chat_history": [],
            "memories": [],
            "graph_context": {
                "chunks": [
                    {"text": "TCP断开连接需要四次挥手，因为TCP连接是全双工的，每一方都需要单独关闭自己的发送通道。", "score": 0.95},
                ],
                "subgraphs": [
                    {
                        "center": "四次挥手",
                        "nodes": [
                            {"name": "四次挥手", "type": "机制"},
                            {"name": "全双工", "type": "概念"},
                            {"name": "FIN报文", "type": "数据单元"},
                        ],
                        "edges": [
                            {"source": "四次挥手", "target": "全双工", "type": "原因"},
                            {"source": "四次挥手", "target": "FIN报文", "type": "包含"},
                        ],
                    }
                ],
            },
            "rewrite_count": 0,
            "max_rewrites": 2,
        },
    },
    {
        "name": "学习者闲聊",
        "state": {
            "session_id": "test-session-001",
            "user_id": "test-user",
            "node_id": "node-tcp",
            "node_title": "TCP协议",
            "node_summary": "面向连接的可靠传输协议。",
            "persona": "vivid",
            "user_message": "你好呀，今天天气不错！",
            "chat_history": [],
            "memories": [],
            "graph_context": {"chunks": [], "subgraphs": []},
            "rewrite_count": 0,
            "max_rewrites": 2,
        },
    },
    {
        "name": "费曼复述",
        "state": {
            "session_id": "test-session-001",
            "user_id": "test-user",
            "node_id": "node-tcp",
            "node_title": "TCP协议",
            "node_summary": "面向连接的可靠传输协议，通过三次握手建立连接，四次挥手断开连接。",
            "persona": "academic",
            "user_message": "我的理解是，TCP通过三次握手来同步双方的序列号和确认号，确保双方都能发送和接收数据。断开时需要四次挥手，因为全双工通信需要分别关闭两个方向的数据流。",
            "chat_history": [],
            "memories": [],
            "graph_context": {
                "chunks": [
                    {"text": "TCP通过三次握手建立连接，交换 SYN 和 ACK 报文，同步序列号。", "score": 0.92},
                    {"text": "四次挥手是因为全双工，双方需独立关闭发送通道。", "score": 0.88},
                ],
                "subgraphs": [],
            },
            "rewrite_count": 0,
            "max_rewrites": 2,
        },
    },
]


def _load_ai_config_from_store() -> dict[str, str] | None:
    """从 PostgreSQL 配置中读取当前启用的 AI 模型配置。"""
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


def main() -> int:
    print("=" * 60)
    print("Blank V2 多智能体大脑离线测试")
    print("=" * 60)

    ai_config = _load_ai_config_from_store()
    if not ai_config:
        print("\n[错误] 未找到可用的 AI 配置。请在后台管理页面配置并启用一个模型后重试。")
        return 1

    graph = get_agent_graph()
    print(f"\n[信息] LangGraph 已编译，节点列表：{list(graph.nodes.keys())}")

    for idx, case in enumerate(TEST_CASES, 1):
        print(f"\n{'='*60}")
        print(f">>> 测试用例 {idx}/{len(TEST_CASES)}：{case['name']}")
        print(f"    用户消息：{case['state']['user_message']}")

        initial_state: AgentState = {
            **case["state"],  # type: ignore[misc]
            "ai_config": ai_config,
            "intent": "",
            "intent_reason": "",
            "mentor_reply": "",
            "mentor_thinking": "",
            "feynman_score": {},
            "feynman_feedback": "",
            "feynman_guidance": "",
            "critic_verdict": {},
            "final_output": "",
            "agent_trace": [],
        }

        try:
            result = graph.invoke(initial_state)
        except Exception as exc:
            print(f"    [失败] 工作流执行异常：{exc}")
            import traceback
            traceback.print_exc()
            continue

        print(f"\n    [结果] 意图识别：{result.get('intent')} ({result.get('intent_reason')})")
        print(f"    [结果] 最终输出：{result.get('final_output', '')[:200]}...")
        print(f"    [结果] 执行轨迹：")
        for step in result.get("agent_trace", []):
            print(f"      → [{step['agent']}] {step['status']} | {step['detail'][:80]}")

        # 如果是费曼模式，打印评分
        if result.get("intent") == "explanation":
            score = result.get("feynman_score", {})
            print(f"    [结果] 费曼评分：通过={score.get('overall_passed')} | {len(score.get('dimension_scores', []))} 个维度")

        # 打印审判官结果
        verdict = result.get("critic_verdict", {})
        print(f"    [结果] 幻觉审判：has_hallucination={verdict.get('has_hallucination')} | 问题数={len(verdict.get('issues', []))}")

    print("\n" + "=" * 60)
    print("所有测试用例执行完毕。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
