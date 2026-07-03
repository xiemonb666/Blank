from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..debug_logging import log_debug_event
from ..services import call_ollama_chat, call_openai_compatible_chat, chunk_text, normalized_ai_config, stream_openai_compatible_chat


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(UTC).isoformat()


def trace(agent: str, status: str, detail: str = "") -> dict[str, str]:
    """生成一条 Agent 执行轨迹记录。"""
    return {
        "agent": agent,
        "status": status,
        "timestamp": now_iso(),
        "detail": detail,
    }


def llm_chat(
    ai_config: dict[str, str] | None,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.35,
) -> str:
    """
    复用现有基础设施调用 LLM，返回完整的文本回复。

    参数：
        ai_config: 包含 base_url / api_key / model 的字典。
        system_prompt: 系统提示词。
        user_prompt: 用户提示词。
        temperature: 采样温度。

    返回：
        LLM 的文本回复。
    """
    if not ai_config:
        raise RuntimeError("未配置 AI 模型，无法调用 LLM。")

    try:
        log_debug_event(
            "agent.llm.request",
            model=ai_config.get("model"),
            base_url=ai_config.get("base_url"),
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        output = call_openai_compatible_chat(
            base_url=ai_config["base_url"],
            api_key=ai_config["api_key"],
            model=ai_config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            reasoning_effort=ai_config.get("reasoning_effort"),
        )
        log_debug_event("agent.llm.output", model=ai_config.get("model"), output=output)
        return output
    except Exception as exc:
        log_debug_event("agent.llm.error", model=ai_config.get("model"), error=str(exc))
        raise RuntimeError(f"LLM 调用失败：{exc}") from exc


def llm_chat_stream(
    ai_config: dict[str, str] | None,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.35,
):
    """复用现有模型客户端，以逐段文本形式返回可公开内容。"""
    if not ai_config:
        raise RuntimeError("未配置 AI 模型，无法调用 LLM。")
    try:
        provider, base_url, api_key, model = normalized_ai_config(ai_config)
        if provider == "ollama":
            text = call_ollama_chat(
                base_url=base_url,
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            yield from chunk_text(text)
            return
        yield from stream_openai_compatible_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            reasoning_effort=ai_config.get("reasoning_effort"),
        )
    except Exception as exc:
        log_debug_event("agent.llm.stream.error", model=(ai_config or {}).get("model"), error=str(exc))
        raise RuntimeError(f"LLM 流式调用失败：{exc}") from exc


def parse_json_from_llm(raw: str) -> dict[str, Any]:
    """
    清理 LLM 返回的 Markdown 代码块包裹，并解析为 JSON 对象。

    参数：
        raw: LLM 原始返回文本。

    返回：
        解析后的 JSON 字典。
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM 返回的 JSON 格式不合法：{exc}\n原始内容前 300 字符：{raw[:300]}") from exc


def format_chat_history(history: list[dict[str, str]], limit: int = 8) -> str:
    """
    将聊天历史格式化为 LLM 可读的文本。

    参数：
        history: 消息列表，每项包含 role 和 text。
        limit: 最多取最近多少条。

    返回：
        格式化后的历史对话文本。
    """
    if not history:
        return "（无历史对话）"
    lines = []
    for msg in history[-limit:]:
        role_label = "学习者" if msg.get("role") == "learner" else "导师"
        lines.append(f"[{role_label}] {msg.get('text', '')}")
    return "\n".join(lines)


def format_memories(memories: list[dict[str, str]], limit: int = 5) -> str:
    """将长期记忆格式化为文本。"""
    if not memories:
        return "（无长期记忆）"
    lines = []
    for m in memories[-limit:]:
        lines.append(f"- [{m.get('kind', '记忆')}] {m.get('title', '')}: {m.get('body', '')}")
    return "\n".join(lines)


def format_graph_context(graph_context: dict) -> str:
    """将 GraphRAG 检索结果格式化为文本。"""
    chunks = graph_context.get("chunks", [])
    subgraphs = graph_context.get("subgraphs", [])
    parts = []
    if chunks:
        parts.append("【相关文本片段】")
        for i, c in enumerate(chunks[:3], 1):
            parts.append(f"{i}. {c.get('text', '')}")
    if subgraphs:
        parts.append("\n【知识图谱邻域】")
        for sg in subgraphs[:2]:
            parts.append(f"中心实体：{sg.get('center', '')}")
            for edge in sg.get("edges", [])[:4]:
                parts.append(f"  - {edge.get('source')} --[{edge.get('type')}]--> {edge.get('target')}")
    return "\n".join(parts) if parts else "（无 GraphRAG 上下文）"
