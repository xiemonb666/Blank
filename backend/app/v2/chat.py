from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from ..agents.graph import get_agent_graph
from ..agents.state import AgentState
from ..debug_logging import log_debug_event, sanitize_debug_text, sanitize_debug_value
from ..models import ChatMessage, LearningSession, NodeLearningProfile, StrictRequestModel, UserPublic
from ..security import (
    CSRF_COOKIE_NAME,
    LEGACY_CSRF_COOKIE_NAME,
    LEGACY_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    redact_secret_text,
    resource_id_is_valid,
)
from ..services import (
    apply_confusion_resolution_if_needed,
    compact_session_history,
    evidence_context_for_turn,
    find_node,
    llm_usage_context,
    messages_for_node,
    normalize_stage,
)

router = APIRouter(tags=["v2-chat"])


class V2ChatRequest(StrictRequestModel):
    """V2 流式对话请求体。"""

    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)
    persona: str = Field(default="plain", pattern=r"^(plain|vivid|academic)$")
    confusion_event: bool = False
    starter_event: bool = False


def _format_sse(data: dict) -> str:
    """将字典格式化为 SSE 标准格式：data: {json}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, chunk_size: int = 4) -> list[str]:
    """
    将长文本切分为小片段，模拟流式 Token 输出效果。
    中文按字符切分，英文按 chunk_size 字符一组切分。
    """
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        # 优先在标点处断句，提升阅读体验
        end = min(i + chunk_size * 3, len(text))
        if end < len(text):
            for p in "。！？；\n":
                pos = text.rfind(p, i, end)
                if pos > i:
                    end = pos + 1
                    break
        chunks.append(text[i:end])
        i = end
    return chunks


def _build_agent_state(
    payload: V2ChatRequest,
    session: LearningSession,
    graph_context: dict,
    ai_config: dict[str, str] | None,
) -> AgentState:
    """
    根据请求、现有 Session 和 GraphRAG 上下文，组装 LangGraph 初始状态。
    """
    raw_messages = session.messages
    chat_history = [
        {"role": msg.role, "text": msg.text}
        for msg in raw_messages[-20:]  # 最近 20 条
    ]

    raw_memories = session.memories
    memories = [
        {"kind": m.kind, "title": m.title, "body": m.body}
        for m in raw_memories[-10:]
    ]

    active_node_id = session.active_node_id
    active_node = find_node(session.nodes, active_node_id)

    return {
        "session_id": payload.session_id,
        "user_id": session.user_id,
        "node_id": active_node_id,
        "node_title": active_node.title,
        "node_summary": active_node.summary,
        "persona": payload.persona,
        "tutor_settings": session.tutor_settings.model_dump(),
        "user_message": (
            "学习者刚进入这个知识节点，还没有回答。请先提出第一个苏格拉底式起始问题：问题必须具体、容易开口、只聚焦当前节点的一个核心点。"
            if payload.starter_event
            else payload.message
        ),
        "chat_history": chat_history,
        "memories": memories,
        "graph_context": graph_context,
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
        "rewrite_count": 0,
        "max_rewrites": 2,
    }


def _fallback_graph_context(session: LearningSession, reason: str = "") -> dict:
    payload = {
        "chunks": [{"text": session.material_context[:800], "score": 1.0, "source_id": session.id}],
        "subgraphs": [],
        "fallback": True,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _critic_should_run(graph_context: dict) -> bool:
    if graph_context.get("fallback"):
        return False
    return bool(graph_context.get("chunks") or graph_context.get("subgraphs"))


def _retrieve_graph_context(session: LearningSession, ai_config: dict[str, str] | None) -> dict:
    """
    尝试通过 GraphRAG 混合检索获取知识上下文。
    若检索失败或 Neo4j 未配置，则回退到 session 的 material_context。
    """
    from ..services_v2.neo4j_service import graphrag_enabled

    active_node = find_node(session.nodes, session.active_node_id)
    node_title = active_node.title
    material_context = session.material_context

    # 构建查询文本：节点标题 + 用户问题关键词
    query = f"{node_title} {material_context[:200]}".strip()
    if not query:
        return {"chunks": [], "subgraphs": []}
    if not graphrag_enabled():
        return _fallback_graph_context(session, "GraphRAG 未启用，使用当前材料片段回退")

    try:
        from ..services_v2.vector_service import hybrid_graph_search
        if ai_config:
            return hybrid_graph_search(
                query,
                ai_config,
                top_k=3,
                tenant_id=session.user_id,
                user_id=session.user_id,
                session_id=session.id,
                source_id=session.id,
            )
    except Exception as exc:
        safe_detail = redact_secret_text(str(exc), limit=180)
        return _fallback_graph_context(session, f"GraphRAG 回退：{safe_detail}")

    return _fallback_graph_context(session)


def require_v2_user(
    request: Request,
    authorization: str | None = Header(default=None),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    legacy_session_cookie: str | None = Cookie(default=None, alias=LEGACY_SESSION_COOKIE_NAME),
    legacy_csrf_cookie: str | None = Cookie(default=None, alias=LEGACY_CSRF_COOKIE_NAME),
) -> UserPublic:
    from ..main import require_token, require_user

    token = require_token(
        request=request,
        authorization=authorization,
        csrf_header=csrf_header,
        session_cookie=session_cookie,
        csrf_cookie=csrf_cookie,
        legacy_session_cookie=legacy_session_cookie,
        legacy_csrf_cookie=legacy_csrf_cookie,
    )
    return require_user(token)


def _public_dimension_scores(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    values = raw.get("dimension_scores")
    if not isinstance(values, list):
        return {}
    scores: dict[str, int] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        stage = normalize_stage(item.get("stage"))
        try:
            score = int(item.get("value", 0))
        except (TypeError, ValueError):
            score = 0
        scores[stage] = max(0, min(100, score))
    return scores


def _save_v2_turn(
    session: LearningSession,
    user_text: str,
    mentor_text: str,
    thinking: str,
    feynman_score: dict | None,
    starter_event: bool = False,
) -> None:
    node = find_node(session.nodes, session.active_node_id)
    if not starter_event:
        session.messages.append(ChatMessage(role="learner", text=user_text.strip(), node_id=node.id))
    final_text = mentor_text.strip()
    if feynman_score:
        feedback = str(feynman_score.get("feedback") or "").strip()
        final_text = final_text or feedback or "费曼评分已完成，请查看本轮诊断结果。"
        scores = _public_dimension_scores(feynman_score.get("score"))
        if scores:
            current = session.node_profiles.get(node.id, NodeLearningProfile(node_id=node.id))
            merged = dict(current.dimension_scores)
            merged.update(scores)
            weak_labels = [stage for stage, value in scores.items() if value < 70]
            session.node_profiles[node.id] = current.model_copy(
                update={
                    "stage": next((stage for stage, value in scores.items() if value < 70), "recap"),
                    "dimension_scores": merged,
                    "weak_points": list(dict.fromkeys([*current.weak_points, *weak_labels]))[-6:],
                    "last_challenge": "V2 费曼评分",
                    "next_challenge": "继续补强薄弱维度。" if any(value < 70 for value in scores.values()) else "进入下一个知识点挑战。",
                    "badge": "V2 费曼达标" if scores and all(value >= 70 for value in scores.values()) else current.badge,
                    "updated_at": datetime.now(UTC),
                }
            )
    if not final_text:
        final_text = "本轮 V2 工作流已完成，但没有生成可保存的导师回复。"
    session.messages.append(ChatMessage(role="mentor", text=final_text[:1000], node_id=node.id, thinking=thinking or None))
    compact_session_history(session)
    session.updated_at = datetime.now(UTC)


@router.post("/chat/stream")
async def v2_chat_stream(payload: V2ChatRequest, user: UserPublic = Depends(require_v2_user)):
    """
    V2 多智能体流式对话接口。

    接收学习者的消息，调用 LangGraph 多智能体网络处理，
    以 SSE (Server-Sent Events) 格式实时返回 Agent 状态、思考过程与最终回复。

    SSE 事件类型：
        - status: 当前活跃 Agent 状态变化
        - thought: 导师的公开思考摘要
        - message: 导师回复的逐段内容（模拟流式）
        - feynman_result: 费曼五维度评分结果
        - done: 工作流结束标记
        - error: 异常信息
    """
    from ..main import store

    # 1. 获取现有 Session
    if not resource_id_is_valid(payload.session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        session_obj = store.get_session(payload.session_id, None if user.role == "admin" else user.id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"数据库查询异常：{redact_secret_text(str(exc), limit=180)}") from exc

    if session_obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    log_debug_event(
        "v2.chat.request",
        user_id=user.id,
        session_id=payload.session_id,
        persona=payload.persona,
        message=payload.message,
        active_node_id=session_obj.active_node_id,
    )

    # 2. 获取 AI 配置
    ai_config = None
    try:
        ai_config = store.get_active_api_config_secret_record()
    except Exception:
        pass

    if not ai_config:
        raise HTTPException(status_code=502, detail="未启用 API 配置，无法执行 V2 多智能体对话。")

    # 3. 获取 GraphRAG 上下文
    with llm_usage_context(user_id=session_obj.user_id, session_id=session_obj.id, source="rag.search"):
        graph_context = _retrieve_graph_context(session_obj, ai_config)
    log_debug_event(
        "v2.chat.graphrag",
        session_id=payload.session_id,
        fallback=graph_context.get("fallback", False),
        graph_context=graph_context,
    )

    # 4. 组装初始状态
    try:
        initial_state = _build_agent_state(payload, session_obj, graph_context, ai_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 5. 定义 SSE 生成器
    async def event_generator():
        with llm_usage_context(user_id=session_obj.user_id, session_id=session_obj.id, source="v2.agent"):
            graph = get_agent_graph()
            mentor_chunks: list[str] = []
            thinking_chunks: list[str] = []
            feynman_payload: dict | None = None
            feynman_guidance_text = ""
            try:
                # 发送初始状态
                log_debug_event("v2.agent.status", session_id=payload.session_id, agent="router", message="总控路由正在分析意图...")
                yield _format_sse({"type": "status", "agent": "router", "message": "总控路由正在分析意图..."})
                if graph_context.get("fallback"):
                    yield _format_sse({
                        "type": "status",
                        "agent": "graphrag",
                        "message": "本轮使用材料片段回退",
                        "detail": graph_context.get("reason", ""),
                    })

                # 遍历 LangGraph 状态更新
                async for event in graph.astream(initial_state, stream_mode="updates"):
                    log_debug_event("v2.agent.update", session_id=payload.session_id, update=sanitize_debug_value(event))
                    for node_name, update in event.items():
                        if node_name == "router":
                            intent = update.get("intent", "question")
                            reason = update.get("intent_reason", "")
                            log_debug_event("v2.agent.router", session_id=payload.session_id, intent=intent, reason=reason)
                            yield _format_sse({"type": "status", "agent": "router", "message": f"意图识别完成：{intent}", "detail": reason})
                            if intent == "question":
                                yield _format_sse({"type": "status", "agent": "socrates", "message": "苏格拉底导师正在生成引导回复..."})
                            elif intent == "explanation":
                                yield _format_sse({"type": "status", "agent": "feynman", "message": "费曼考官正在进行五维度评分..."})
                            elif intent == "chat":
                                yield _format_sse({"type": "status", "agent": "socrates", "message": "正在生成友好回复..."})

                        elif node_name == "socrates":
                            thinking = update.get("mentor_thinking", "")
                            reply = update.get("mentor_reply", "")
                            if thinking:
                                thinking_chunks.append(thinking)
                                log_debug_event("v2.agent.thought", session_id=payload.session_id, agent="socrates", content=thinking)
                                yield _format_sse({"type": "thought", "content": thinking})
                            if reply:
                                log_debug_event("v2.agent.reply", session_id=payload.session_id, agent="socrates", reply=reply)
                                for chunk in _chunk_text(reply):
                                    mentor_chunks.append(chunk)
                                    log_debug_event("v2.agent.message_delta", session_id=payload.session_id, agent="socrates", content=chunk)
                                    yield _format_sse({"type": "message", "content": chunk})
                                    await asyncio.sleep(0.01)
                            if _critic_should_run(graph_context):
                                yield _format_sse({"type": "status", "agent": "critic", "message": "幻觉审判官正在核查事实一致性..."})

                        elif node_name == "socrates_chat":
                            reply = update.get("mentor_reply", "")
                            if reply:
                                log_debug_event("v2.agent.reply", session_id=payload.session_id, agent="socrates_chat", reply=reply)
                                for chunk in _chunk_text(reply):
                                    mentor_chunks.append(chunk)
                                    log_debug_event("v2.agent.message_delta", session_id=payload.session_id, agent="socrates_chat", content=chunk)
                                    yield _format_sse({"type": "message", "content": chunk})
                                    await asyncio.sleep(0.01)

                        elif node_name == "feynman":
                            score = update.get("feynman_score", {})
                            feedback = update.get("feynman_feedback", "")
                            guidance = update.get("feynman_guidance", "")
                            if guidance:
                                feynman_guidance_text = str(guidance)
                            if score:
                                feynman_payload = {"score": score, "feedback": feedback}
                                log_debug_event(
                                    "v2.agent.feynman_result",
                                    session_id=payload.session_id,
                                    score=score,
                                    feedback=feedback,
                                    guidance=guidance,
                                )
                                yield _format_sse({"type": "feynman_result", "data": score, "feedback": feedback})
                            if _critic_should_run(graph_context):
                                yield _format_sse({"type": "status", "agent": "critic", "message": "幻觉审判官正在核查评分依据..."})

                        elif node_name == "critic":
                            verdict = update.get("critic_verdict", {})
                            has_hallucination = verdict.get("has_hallucination", False)
                            log_debug_event("v2.agent.critic", session_id=payload.session_id, verdict=verdict)
                            if has_hallucination:
                                yield _format_sse({"type": "status", "agent": "critic", "message": "发现事实不一致，正在打回重写..."})
                            else:
                                yield _format_sse({"type": "status", "agent": "critic", "message": "事实核查通过"})

                        elif node_name == "increment_rewrite":
                            yield _format_sse({"type": "status", "agent": "graph", "message": "进入重写循环，重新生成内容..."})

                        elif node_name == "finalize":
                            final = str(update.get("final_output") or "").strip()
                            if not final and feynman_payload:
                                final = feynman_guidance_text.strip() or str(feynman_payload.get("feedback") or "").strip()
                            log_debug_event("v2.agent.finalize", session_id=payload.session_id, final_output=final)
                            if final and not "".join(mentor_chunks).strip():
                                for chunk in _chunk_text(final):
                                    mentor_chunks.append(chunk)
                                    log_debug_event("v2.agent.message_delta", session_id=payload.session_id, agent="graph", content=chunk)
                                    yield _format_sse({"type": "message", "content": chunk})
                                    await asyncio.sleep(0.01)
                            yield _format_sse({"type": "status", "agent": "graph", "message": "工作流完成"})

                _save_v2_turn(
                    session_obj,
                    payload.message,
                    "".join(mentor_chunks),
                    "\n".join(item for item in thinking_chunks if item),
                    feynman_payload,
                    starter_event=payload.starter_event,
                )
                if payload.confusion_event and not payload.starter_event:
                    node = find_node(session_obj.nodes, session_obj.active_node_id)
                    apply_confusion_resolution_if_needed(
                        session=session_obj,
                        node=node,
                        user_message=payload.message,
                        mentor_reply="".join(mentor_chunks),
                        persona=payload.persona,  # type: ignore[arg-type]
                        confusion_event=True,
                        ai_config=ai_config,
                        evidence_context=evidence_context_for_turn(session_obj, node, payload.message),
                    )
                store.save_session(session_obj)
                log_debug_event(
                    "v2.chat.saved",
                    session_id=payload.session_id,
                    mentor_text="".join(mentor_chunks),
                    thinking="\n".join(item for item in thinking_chunks if item),
                    feynman_payload=feynman_payload,
                    node_profiles={key: value.model_dump(mode="json") for key, value in session_obj.node_profiles.items()},
                )
                yield _format_sse({
                    "type": "done",
                    "messages": [message.model_dump(mode="json") for message in messages_for_node(session_obj, session_obj.active_node_id)],
                    "node_profiles": {key: value.model_dump(mode="json") for key, value in session_obj.node_profiles.items()},
                })

            except asyncio.CancelledError:
                # 客户端断开连接（关闭页面或取消请求），安全退出
                log_debug_event("v2.chat.cancelled", session_id=payload.session_id)
                yield _format_sse({"type": "status", "agent": "graph", "message": "用户已中断生成"})
                yield _format_sse({"type": "done"})
                raise
            except Exception as exc:
                safe_detail = redact_secret_text(str(exc), limit=200)
                log_debug_event("v2.chat.error", session_id=payload.session_id, error=safe_detail)
                yield _format_sse({"type": "error", "error": f"V2 工作流执行异常：{safe_detail}"})
                yield _format_sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
