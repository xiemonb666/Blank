from __future__ import annotations

from .state import AgentState
from .utils import trace


VALID_DYNAMIC_AGENTS = ("planner", "analyst", "coach", "memory")


def normalize_dynamic_agents(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        agent = str(item).strip().lower()
        if agent in VALID_DYNAMIC_AGENTS and agent not in normalized:
            normalized.append(agent)
    return normalized


def heuristic_dynamic_agents(user_message: str, intent: str) -> list[str]:
    message = user_message.strip()
    agents: list[str] = []
    if intent != "chat" and (len(message) >= 80 or any(word in message for word in ("步骤", "路径", "怎么学", "拆解"))):
        agents.append("planner")
    if intent == "question" and any(word in message for word in ("为什么", "机制", "原理", "导致", "关系", "区别")):
        agents.append("analyst")
    if any(word in message for word in ("不懂", "太难", "卡住", "不会", "迷糊", "听不懂")):
        agents.append("coach")
    if intent == "explanation" or any(word in message for word in ("我总是", "容易忘", "记住", "薄弱")):
        agents.append("memory")
    return agents


def planner_node(state: AgentState) -> dict:
    node_title = state.get("node_title", "当前节点")
    guidance = append_guidance(
        state,
        f"Planner：先把「{node_title}」拆成目标、前置概念、关键机制和一个可回答的小问题。",
    )
    return {
        "dynamic_guidance": guidance,
        "agent_trace": [trace("planner", "done", "已生成本轮学习拆解策略")],
    }


def analyst_node(state: AgentState) -> dict:
    guidance = append_guidance(
        state,
        "Analyst：优先解释因果链、机制边界和容易混淆的相邻概念，避免只给结论。",
    )
    return {
        "dynamic_guidance": guidance,
        "agent_trace": [trace("analyst", "done", "已补充机制分析提示")],
    }


def coach_node(state: AgentState) -> dict:
    guidance = append_guidance(
        state,
        "Coach：降低表达负荷，使用短句、确认卡点，并把下一步问题压缩到一个判断。",
    )
    return {
        "dynamic_guidance": guidance,
        "agent_trace": [trace("coach", "done", "已切换为低负荷引导策略")],
    }


def memory_node(state: AgentState) -> dict:
    guidance = append_guidance(
        state,
        "Memory：留意本轮可沉淀的薄弱点、偏好和反复卡住的位置，方便后续追踪。",
    )
    return {
        "dynamic_guidance": guidance,
        "agent_trace": [trace("memory", "done", "已标记需要沉淀的学习线索")],
    }


def append_guidance(state: AgentState, item: str) -> str:
    current = str(state.get("dynamic_guidance") or "").strip()
    return f"{current}\n{item}".strip() if current else item
