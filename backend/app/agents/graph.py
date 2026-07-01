from __future__ import annotations

from langgraph.graph import END, StateGraph

from .critic import critic_node
from .dynamic import analyst_node, coach_node, memory_node, planner_node
from .feynman import feynman_node
from .router import router_node
from .socrates import socrates_chat_node, socrates_node
from .state import AgentState
from .utils import trace


def _route_by_intent(state: AgentState) -> str:
    """根据 Router 识别的意图，路由到不同分支。"""
    intent = state.get("intent", "question")
    if intent == "explanation":
        return "feynman"
    if intent == "chat":
        return "socrates_chat"
    return "socrates"


def _wants_dynamic_agent(state: AgentState, agent: str) -> bool:
    return agent in set(state.get("dynamic_agents") or [])


def _route_after_router(state: AgentState) -> str:
    if _wants_dynamic_agent(state, "planner"):
        return "planner"
    return _route_after_planner(state)


def _route_after_planner(state: AgentState) -> str:
    if _wants_dynamic_agent(state, "analyst"):
        return "analyst"
    return _route_after_analyst(state)


def _route_after_analyst(state: AgentState) -> str:
    if _wants_dynamic_agent(state, "coach"):
        return "coach"
    return _route_after_coach(state)


def _route_after_coach(state: AgentState) -> str:
    if _wants_dynamic_agent(state, "memory"):
        return "memory"
    return _route_by_intent(state)


def _route_by_critic(state: AgentState) -> str:
    """
    根据 Critic 的判决决定是否需要重写。
    如果存在幻觉且未达到最大重写次数，则打回上游节点重写；否则放行到终点。
    """
    verdict = state.get("critic_verdict", {})
    has_hallucination = verdict.get("has_hallucination", False)
    rewrite_count = state.get("rewrite_count", 0)
    max_rewrites = state.get("max_rewrites", 2)

    if has_hallucination and rewrite_count < max_rewrites:
        return "rewrite"
    return "end"


def _route_after_generation(state: AgentState) -> str:
    """只有真实 GraphRAG 召回可用时才进入 Critic，避免回退上下文触发额外模型调用。"""
    graph_context = state.get("graph_context", {})
    if graph_context.get("fallback"):
        return "finalize"
    if not graph_context.get("chunks") and not graph_context.get("subgraphs"):
        return "finalize"
    return "critic"


def _increment_rewrite(state: AgentState) -> dict:
    """内部辅助节点：每次进入重写前，计数器 +1。"""
    return {
        "rewrite_count": state.get("rewrite_count", 0) + 1,
        "agent_trace": [trace("graph", "rewrite", f"检测到幻觉，进入第 {state.get('rewrite_count', 0) + 1} 次重写")],
    }


def _finalize_output(state: AgentState) -> dict:
    """
    终点节点：整理最终输出，根据上游意图聚合所有字段。
    """
    intent = state.get("intent", "question")
    if intent == "explanation":
        final = state.get("feynman_guidance", "") or state.get("feynman_feedback", "")
    elif intent == "chat":
        final = state.get("mentor_reply", "")
    else:
        final = state.get("mentor_reply", "")

    return {
        "final_output": final,
        "agent_trace": [
            trace("graph", "finalize", f"工作流结束，意图=[{intent}]，重写次数={state.get('rewrite_count', 0)}"),
        ],
    }


def build_agent_graph() -> StateGraph:
    """
    构建并编译 LangGraph 多智能体状态图。

    工作流：
        router → (question→socrates→critic→[rewrite|end])
                → (explanation→feynman→critic→[rewrite|end])
                → (chat→socrates_chat→end)
    """
    builder = StateGraph(AgentState)

    # 注册节点
    builder.add_node("router", router_node)
    builder.add_node("planner", planner_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("coach", coach_node)
    builder.add_node("memory", memory_node)
    builder.add_node("socrates", socrates_node)
    builder.add_node("socrates_chat", socrates_chat_node)
    builder.add_node("feynman", feynman_node)
    builder.add_node("critic", critic_node)
    builder.add_node("increment_rewrite", _increment_rewrite)
    builder.add_node("finalize", _finalize_output)

    # 入口
    builder.set_entry_point("router")

    dynamic_or_intent_edges = {
        "planner": "planner",
        "analyst": "analyst",
        "coach": "coach",
        "memory": "memory",
        "socrates": "socrates",
        "socrates_chat": "socrates_chat",
        "feynman": "feynman",
    }

    # Router 后先执行可选动态角色，再进入固定意图分支
    builder.add_conditional_edges(
        "router",
        _route_after_router,
        dynamic_or_intent_edges,
    )
    builder.add_conditional_edges("planner", _route_after_planner, dynamic_or_intent_edges)
    builder.add_conditional_edges("analyst", _route_after_analyst, dynamic_or_intent_edges)
    builder.add_conditional_edges("coach", _route_after_coach, dynamic_or_intent_edges)
    builder.add_conditional_edges("memory", _route_by_intent, dynamic_or_intent_edges)

    # Socrates / Feynman 后根据上下文质量决定是否进入 Critic
    builder.add_conditional_edges(
        "socrates",
        _route_after_generation,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "feynman",
        _route_after_generation,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )

    # Critic 后的条件分支：重写或结束
    builder.add_conditional_edges(
        "critic",
        _route_by_critic,
        {
            "rewrite": "increment_rewrite",
            "end": "finalize",
        },
    )

    # 重写计数器增加后，根据上游意图回到对应生成节点
    # 需要判断当前意图来决定回到 socrates 还是 feynman
    def _back_to_generator(state: AgentState) -> str:
        intent = state.get("intent", "question")
        if intent == "explanation":
            return "feynman"
        return "socrates"

    builder.add_conditional_edges(
        "increment_rewrite",
        _back_to_generator,
        {
            "socrates": "socrates",
            "feynman": "feynman",
        },
    )

    # 闲聊直接结束
    builder.add_edge("socrates_chat", "finalize")

    # 终点
    builder.add_edge("finalize", END)

    return builder.compile()


# 全局编译后的图实例（线程安全，可复用）
_AGENT_GRAPH = None


def get_agent_graph():
    """获取已编译的全局 Agent 图实例（懒加载）。"""
    global _AGENT_GRAPH
    if _AGENT_GRAPH is None:
        _AGENT_GRAPH = build_agent_graph()
    return _AGENT_GRAPH
