from __future__ import annotations

from typing import Annotated, TypedDict
import operator


class AgentState(TypedDict):
    """
    LangGraph 多智能体网络的全局状态定义。
    所有节点函数接收此状态的子集，返回需要更新的字段字典。
    """

    # ========== 输入上下文（由调用方注入）==========
    session_id: str
    user_id: str
    node_id: str
    node_title: str
    node_summary: str
    persona: str  # "plain" | "vivid" | "academic"
    user_message: str
    chat_history: list[dict[str, str]]  # [{"role": "learner"/"mentor", "text": "..."}]
    memories: list[dict[str, str]]  # 长期记忆条目
    graph_context: dict  # GraphRAG 混合检索结果 {"chunks": [...], "subgraphs": [...]}
    ai_config: dict[str, str] | None  # {base_url, api_key, model}

    # ========== Router 输出 ==========
    intent: str  # "question" | "explanation" | "chat"
    intent_reason: str

    # ========== Socrates 输出 ==========
    mentor_reply: str
    mentor_thinking: str

    # ========== Feynman 输出 ==========
    feynman_score: dict  # 五维度评分 + 总体评价
    feynman_feedback: str
    feynman_guidance: str

    # ========== Critic 输出 ==========
    critic_verdict: dict  # {"has_hallucination": bool, "issues": [...], "suggestion": "..."}

    # ========== 最终输出（由 graph 终点整理）==========
    final_output: str

    # ========== 执行轨迹（前端用于展示 Agent 工作流动画）==========
    agent_trace: Annotated[list[dict[str, str]], operator.add]
    # 每项示例：{"agent": "router", "status": "thinking", "timestamp": "...", "detail": "..."}

    # ========== 内部循环控制（防止无限重写）==========
    rewrite_count: int
    max_rewrites: int
