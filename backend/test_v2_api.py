from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.models import (
    ChatMessage,
    DimensionScore,
    FeynmanAnswer,
    FeynmanAssessmentRecord,
    FeynmanQuestion,
    LearningSession,
    KnowledgeNode,
)
from app.security import clear_rate_limits
from app.store import SessionStore


TEST_PASSWORD = "Passw0rd123"
TRUSTED_ORIGIN = "http://127.0.0.1:5173"


def test_database_url() -> str:
    import os

    return os.getenv("BLANK_TEST_DATABASE_URL", "postgresql://blank:blank@127.0.0.1:5432/blank_test")


def clear_store_tables(store: SessionStore) -> None:
    with store._connect() as connection:
        connection.execute("delete from research_experiment_records")
        connection.execute("delete from llm_token_usage")
        connection.execute("delete from audit_logs")
        connection.execute("delete from parse_jobs")
        connection.execute("delete from sessions")
        connection.execute("delete from organization_knowledge_chunks")
        connection.execute("delete from organization_knowledge_items")
        connection.execute("delete from organization_task_assignments")
        connection.execute("delete from organization_learning_tasks")
        connection.execute("delete from organization_memberships")
        connection.execute("delete from organizations")
        connection.execute("delete from api_configs")
        connection.execute("delete from auth_tokens")
        connection.execute("delete from users")


class FakeV2Graph:
    async def astream(self, initial_state, stream_mode="updates"):
        assert stream_mode == "updates"
        yield {"router": {"intent": "question", "intent_reason": "测试路由"}}
        yield {
            "socrates": {
                "mentor_thinking": "测试公开思考",
                "mentor_reply": f"围绕 {initial_state['node_title']} 的测试回复。",
            }
        }
        graph_context = initial_state.get("graph_context", {})
        if not graph_context.get("fallback") and (graph_context.get("chunks") or graph_context.get("subgraphs")):
            yield {"critic": {"critic_verdict": {"has_hallucination": False}}}
        yield {"finalize": {"final_output": "完成"}}
        await asyncio.sleep(0)


class FakeV2FeynmanOnlyGraph:
    async def astream(self, initial_state, stream_mode="updates"):
        assert stream_mode == "updates"
        feedback = "费曼反馈：理解正确，但还需要补充推理效率瓶颈。"
        guidance = "你已经抓到注意力会算相关性了。我们先补一个小口子：长上下文时缓存会越存越多。你能说说这会怎样影响显存吗？"
        yield {"router": {"intent": "explanation", "intent_reason": "学习者正在复述理解"}}
        yield {
            "feynman": {
                "feynman_score": {
                    "dimension_scores": [
                        {"stage": "warmup", "label": "基础理解", "value": 82, "note": "基本准确"},
                        {"stage": "mechanism", "label": "机制解释", "value": 66, "note": "机制不完整"},
                    ],
                    "overall_passed": False,
                },
                "feynman_feedback": feedback,
                "feynman_guidance": guidance,
            }
        }
        yield {"finalize": {"final_output": guidance}}
        await asyncio.sleep(0)


class FakeV2SettingsGraph:
    async def astream(self, initial_state, stream_mode="updates"):
        assert stream_mode == "updates"
        assert initial_state["tutor_settings"]["communication_type"] == "story"
        yield {"router": {"intent": "question", "intent_reason": "设置测试", "dynamic_agents": []}}
        yield {"socrates": {"mentor_thinking": "设置已生效", "mentor_reply": "讲故事风格回复。"}}
        yield {"finalize": {"final_output": "讲故事风格回复。"}}
        await asyncio.sleep(0)


def parse_sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line.removeprefix("data: ")))
    return events


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    test_store = SessionStore(test_database_url())
    clear_store_tables(test_store)
    monkeypatch.setattr(app_main, "store", test_store)
    monkeypatch.setenv("BLANK_ALLOW_PRIVATE_MODEL_URLS", "true")
    monkeypatch.setenv("BLANK_GRAPHRAG_ENABLED", "true")
    monkeypatch.setenv("BLANK_ENV", "test")
    monkeypatch.setenv("BLANK_REDIS_URL", "")
    monkeypatch.setenv("BLANK_ALLOW_IN_MEMORY_RATE_LIMIT", "true")
    clear_rate_limits()
    app_main.reset_parse_job_semaphore_for_tests()
    return test_store


@pytest.fixture(autouse=True)
def fake_v2_runtime(monkeypatch):
    from app.services_v2 import vector_service

    monkeypatch.setattr(
        "app.v2.chat.get_agent_graph",
        lambda: FakeV2Graph(),
    )
    monkeypatch.setattr(
        vector_service,
        "hybrid_graph_search",
        lambda query, ai_config, top_k=5, **scope: {
            "chunks": [{"text": "测试材料片段", "score": 1.0, "source_id": scope.get("source_id", "")}],
            "subgraphs": [],
        },
    )


def auth_origin_headers() -> dict[str, str]:
    return {"Origin": TRUSTED_ORIGIN}


def auth_headers(client: TestClient, username: str, role: str = "learner") -> dict[str, str]:
    registered = client.post(
        "/api/auth/register",
        headers=auth_origin_headers(),
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert registered.status_code == 200
    if role != "learner":
        app_main.store.update_user(
            user_id=registered.json()["user"]["id"],
            role=role,
            is_active=True,
            updated_at=datetime.now(UTC).isoformat(),
        )
    token = registered.cookies.get(app_main.SESSION_COOKIE_NAME)
    assert token
    return {"Authorization": f"Bearer {token}"}


def cookie_client(username: str, role: str = "learner") -> tuple[TestClient, str]:
    client = TestClient(app_main.app)
    registered = client.post(
        "/api/auth/register",
        headers=auth_origin_headers(),
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert registered.status_code == 200
    if role != "learner":
        app_main.store.update_user(
            user_id=registered.json()["user"]["id"],
            role=role,
            is_active=True,
            updated_at=datetime.now(UTC).isoformat(),
        )
    csrf_token = registered.cookies.get(app_main.CSRF_COOKIE_NAME)
    assert csrf_token
    return client, csrf_token


def make_session(user_id: str, title: str = "V2 测试材料", organization_id: str | None = None) -> LearningSession:
    node = KnowledgeNode(
        id="node-a",
        title="注意力机制",
        summary="模型根据相关性聚焦关键信息。",
        complexity=2,
        weight=1.0,
        status="active",
        x=20,
        y=30,
        deps=[],
    )
    session = LearningSession(
        id="0123456789abcdef0123456789abcdef",
        user_id=user_id,
        organization_id=organization_id,
        material_title=title,
        material_context="注意力机制会根据查询和键的相关性分配权重。",
        nodes=[node],
        active_node_id=node.id,
        messages=[],
    )
    return app_main.store.save_session(session)


def active_config() -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    app_main.store.upsert_api_config(
        config_id="fedcba9876543210fedcba9876543210",
        provider="openai",
        base_url="http://127.0.0.1:12345/v1",
        api_key="sk-v2-test",
        model="test-model",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    return app_main.store.get_active_api_config_secret_record() or {}


def registered_user_id(username: str):
    record = app_main.store.get_user_password_hash(username)
    assert record is not None
    return record[0].id


def test_router_treats_short_reply_to_mentor_question_as_answer(monkeypatch) -> None:
    from app.agents import router as router_module

    monkeypatch.setattr(
        router_module,
        "llm_chat",
        lambda **_: '{"intent":"chat","reason":"短句像闲聊","dynamic_agents":[]}',
    )

    result = router_module.router_node(
        {
            "node_title": "瞬时速度",
            "user_message": "因为会时快时慢",
            "chat_history": [
                {"role": "mentor", "text": "要描述一个物体在某一瞬间的速度，为什么用平均速度不算数？"}
            ],
        }
    )

    assert result["intent"] == "answer"
    assert "上一题" in result["intent_reason"]


def test_node_primer_is_cached_without_creating_chat_messages() -> None:
    client = TestClient(app_main.app)
    headers = auth_headers(client, "tester_node_primer")
    session = make_session(registered_user_id("tester_node_primer"), title="想学：微积分")

    first = client.post(
        f"/api/sessions/{session.id}/node-primer",
        headers=headers,
        json={"node_id": session.active_node_id},
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["reused"] is False
    assert payload["primer"]["node_id"] == session.active_node_id
    assert payload["primer"]["plain_explanation"]
    assert payload["primer"]["example"]
    assert payload["primer"]["keywords"]

    second = client.post(
        f"/api/sessions/{session.id}/node-primer",
        headers=headers,
        json={"node_id": session.active_node_id},
    )
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["primer"] == payload["primer"]

    saved = client.get(f"/api/sessions/{session.id}", headers=headers).json()
    assert saved["messages"] == []
    assert saved["node_primers"][session.active_node_id] == payload["primer"]


def test_v2_streams_thought_delta_and_message_with_real_graph(monkeypatch) -> None:
    from app.agents.graph import build_agent_graph
    from app.agents import router as router_module

    monkeypatch.setattr("app.v2.chat.get_agent_graph", lambda: build_agent_graph())
    monkeypatch.setattr(
        router_module,
        "llm_chat",
        lambda **_: '{"intent":"question","reason":"测试真实图流式","dynamic_agents":[]}',
    )

    def fake_llm_chat_stream(_ai_config, system_prompt, _user_prompt, temperature=0.35):
        if "公开思考摘要" in system_prompt:
            yield "材料依据：测试片段。"
            yield "回答策略：先讲后问。"
            return
        yield "这是"
        yield "真流式回复。"

    monkeypatch.setattr("app.v2.chat.llm_chat_stream", fake_llm_chat_stream)

    client = TestClient(app_main.app)
    headers = auth_headers(client, "tester_v2_true_stream")
    active_config()
    session = make_session(registered_user_id("tester_v2_true_stream"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, "Accept": "text/event-stream"},
        json={"session_id": session.id, "message": "为什么会这样？", "persona": "plain"},
    ) as response:
        assert response.status_code == 200
        events = [
            json.loads(line.removeprefix("data: ").strip())
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]

    assert any(event["type"] == "thought_delta" for event in events)
    assert any(event["type"] == "message" for event in events)
    assert "".join(event.get("content", "") for event in events if event["type"] == "message") == "这是真流式回复。"
    saved = client.get(f"/api/sessions/{session.id}", headers=headers).json()
    assert saved["messages"][-1]["text"] == "这是真流式回复。"
    assert "材料依据" in (saved["messages"][-1]["thinking"] or "")


def test_v2_chat_uses_tutor_settings_from_current_request(monkeypatch) -> None:
    monkeypatch.setattr("app.v2.chat.get_agent_graph", lambda: FakeV2SettingsGraph())
    client = TestClient(app_main.app)
    headers = auth_headers(client, "tester_v2_tutor_settings")
    active_config()
    session = make_session(registered_user_id("tester_v2_tutor_settings"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, "Accept": "text/event-stream"},
        json={
            "session_id": session.id,
            "message": "给我讲一下",
            "persona": "plain",
            "tutor_settings": {"depth_level": 3, "learning_style": "visual", "communication_type": "story"},
        },
    ) as response:
        assert response.status_code == 200
        events = [
            json.loads(line.removeprefix("data: ").strip())
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]

    assert events[-1]["type"] == "done"
    saved = client.get(f"/api/sessions/{session.id}", headers=headers).json()
    assert saved["tutor_settings"]["communication_type"] == "story"
    assert saved["tutor_settings"]["learning_style"] == "visual"


def test_v2_requires_auth() -> None:
    active_config()
    client = TestClient(app_main.app)
    response = client.post(
        "/api/v2/chat/stream",
        headers=auth_origin_headers(),
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "你好", "persona": "plain"},
    )
    assert response.status_code == 401


def test_v2_rejects_missing_csrf_for_cookie_session() -> None:
    active_config()
    client, _csrf = cookie_client("v2_cookie_user")
    make_session(registered_user_id("v2_cookie_user"))

    response = client.post(
        "/api/v2/chat/stream",
        headers=auth_origin_headers(),
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "解释一下", "persona": "plain"},
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_v2_cannot_read_other_users_session() -> None:
    active_config()
    client = TestClient(app_main.app)
    owner_headers = auth_headers(client, "v2_owner")
    intruder_headers = auth_headers(client, "v2_intruder")
    make_session(registered_user_id("v2_owner"))

    response = client.post(
        "/api/v2/chat/stream",
        headers={**intruder_headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "能看见吗", "persona": "plain"},
    )
    assert owner_headers
    assert response.status_code == 404


def test_v2_admin_can_read_session_if_policy_allows() -> None:
    active_config()
    client = TestClient(app_main.app)
    auth_headers(client, "v2_owner_admin_case")
    admin_headers = auth_headers(client, "v2_admin", role="admin")
    make_session(registered_user_id("v2_owner_admin_case"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**admin_headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "管理员查看", "persona": "plain"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"type": "done"' in body


def test_v2_persists_user_and_mentor_messages() -> None:
    active_config()
    client = TestClient(app_main.app)
    headers = auth_headers(client, "v2_persist")
    make_session(registered_user_id("v2_persist"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "我不理解注意力", "persona": "plain"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"type": "message"' in body
    saved = app_main.store.get_session("0123456789abcdef0123456789abcdef", registered_user_id("v2_persist"))
    assert saved is not None
    assert [message.role for message in saved.messages] == ["learner", "mentor"]
    assert saved.messages[0].text == "我不理解注意力"
    assert "测试回复" in saved.messages[1].text
    assert saved.messages[1].thinking == "测试公开思考"


def test_v2_streams_finalize_output_when_graph_has_no_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.v2.chat.get_agent_graph",
        lambda: FakeV2FeynmanOnlyGraph(),
    )
    active_config()
    client = TestClient(app_main.app)
    headers = auth_headers(client, "v2_finalize_fallback")
    make_session(registered_user_id("v2_finalize_fallback"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "我的复述是注意力能减少推理开销", "persona": "plain"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    events = parse_sse_events(body)
    message_text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "message")
    assert message_text == "你已经抓到注意力会算相关性了。我们先补一个小口子：长上下文时缓存会越存越多。你能说说这会怎样影响显存吗？"
    feynman_events = [event for event in events if event.get("type") == "feynman_result"]
    assert feynman_events
    assert feynman_events[0]["feedback"] == "费曼反馈：理解正确，但还需要补充推理效率瓶颈。"
    assert events[-1]["type"] == "done"

    saved = app_main.store.get_session("0123456789abcdef0123456789abcdef", registered_user_id("v2_finalize_fallback"))
    assert saved is not None
    assert [message.role for message in saved.messages] == ["learner", "mentor"]
    assert saved.messages[1].text == "你已经抓到注意力会算相关性了。我们先补一个小口子：长上下文时缓存会越存越多。你能说说这会怎样影响显存吗？"


def test_v2_graphrag_search_is_scoped_by_session(monkeypatch) -> None:
    from app.services_v2 import vector_service

    monkeypatch.setenv("BLANK_RAG_BACKEND", "legacy_neo4j")
    monkeypatch.setenv("BLANK_GRAPHRAG_ENABLED", "true")
    calls: list[dict[str, str]] = []

    def scoped_search(query, ai_config, top_k=5, **scope):
        calls.append(scope)
        return {"chunks": [{"text": query, "score": 1.0, "source_id": scope["source_id"]}], "subgraphs": []}

    monkeypatch.setattr(vector_service, "hybrid_graph_search", scoped_search)
    active_config()
    client = TestClient(app_main.app)
    headers = auth_headers(client, "v2_graphrag_scope")
    user_id = registered_user_id("v2_graphrag_scope")
    make_session(user_id)

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "检索范围", "persona": "plain"},
    ) as response:
        _body = "".join(response.iter_text())

    assert response.status_code == 200
    assert calls == [
        {
            "tenant_id": user_id,
            "user_id": user_id,
            "session_id": "0123456789abcdef0123456789abcdef",
            "source_id": "0123456789abcdef0123456789abcdef",
        }
    ]


def test_v2_graphrag_search_includes_organization_scope(monkeypatch) -> None:
    from app.services_v2 import vector_service

    monkeypatch.setenv("BLANK_RAG_BACKEND", "legacy_neo4j")
    monkeypatch.setenv("BLANK_GRAPHRAG_ENABLED", "true")
    calls: list[dict[str, str]] = []

    def scoped_search(query, ai_config, top_k=5, **scope):
        calls.append(scope)
        label = "组织知识库片段" if scope["tenant_id"].startswith("org") else "个人材料片段"
        return {"chunks": [{"text": label, "score": 1.0, "source_id": scope["source_id"]}], "subgraphs": []}

    monkeypatch.setattr(vector_service, "hybrid_graph_search", scoped_search)
    active_config()
    client = TestClient(app_main.app)
    manager_headers = auth_headers(client, "v2_org_manager", role="org_manager")
    manager_id = registered_user_id("v2_org_manager")
    organization = app_main.store.create_organization(
        organization_id="org00000000000000000000000000001",
        code="ORG-V2SCOPE",
        name="V2 组织",
        owner_user_id=manager_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    member_headers = auth_headers(client, "v2_org_member", role="org_member")
    member_id = registered_user_id("v2_org_member")
    app_main.store.add_organization_member(organization.id, member_id, "org_member", datetime.now(UTC).isoformat())
    make_session(member_id, organization_id=organization.id)

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**member_headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "组织检索", "persona": "plain"},
    ) as response:
        _body = "".join(response.iter_text())

    assert manager_headers
    assert response.status_code == 200
    assert calls == [
        {
            "tenant_id": member_id,
            "user_id": member_id,
            "session_id": "0123456789abcdef0123456789abcdef",
            "source_id": "0123456789abcdef0123456789abcdef",
        },
        {
            "tenant_id": organization.id,
            "session_id": organization.id,
        },
    ]


def test_v2_uses_sag_by_default(monkeypatch) -> None:
    from app.services_v2.sag_service import index_sag_text

    active_config()
    client = TestClient(app_main.app)
    headers = auth_headers(client, "v2_sag_default")
    user_id = registered_user_id("v2_sag_default")
    session = make_session(user_id)
    index_sag_text(
        app_main.store,
        "注意力机制会根据查询和键的相关性分配权重，帮助模型聚焦关键信息。",
        tenant_id=user_id,
        user_id=user_id,
        session_id=session.id,
        source_id=session.id,
        ai_config=None,
    )

    captured_contexts: list[dict] = []

    class CaptureGraph:
        async def astream(self, initial_state, stream_mode="updates"):
            captured_contexts.append(initial_state["graph_context"])
            yield {"router": {"intent": "question", "intent_reason": "测试"}}
            yield {"socrates": {"mentor_reply": "测试回复", "mentor_thinking": ""}}
            yield {"critic": {"critic_verdict": {"has_hallucination": False, "issues": []}}}
            yield {"finalize": {"final_output": "测试回复"}}

    monkeypatch.setattr("app.v2.chat.get_agent_graph", lambda: CaptureGraph())

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, **auth_origin_headers()},
        json={"session_id": session.id, "message": "注意力如何聚焦？", "persona": "plain"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"type": "done"' in body
    assert captured_contexts
    assert captured_contexts[0]["backend"] == "sag"
    assert captured_contexts[0]["chunks"]


def test_v2_uses_material_context_when_graphrag_is_disabled(monkeypatch) -> None:
    from app.services_v2 import vector_service

    monkeypatch.setenv("BLANK_GRAPHRAG_ENABLED", "false")
    calls = 0

    def blocked_search(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("显式关闭 GraphRAG 时不应调用混合检索")

    monkeypatch.setattr(vector_service, "hybrid_graph_search", blocked_search)
    active_config()
    client = TestClient(app_main.app)
    headers = auth_headers(client, "v2_default_graphrag_fallback")
    make_session(registered_user_id("v2_default_graphrag_fallback"))

    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        headers={**headers, **auth_origin_headers()},
        json={"session_id": "0123456789abcdef0123456789abcdef", "message": "默认检索", "persona": "plain"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "本轮使用材料片段回退" in body
    assert calls == 0


def test_org_manager_can_export_member_conversation_and_feynman_trace() -> None:
    client = TestClient(app_main.app)
    manager_headers = auth_headers(client, "v2_export_manager", role="org_manager")
    manager_id = registered_user_id("v2_export_manager")
    organization = app_main.store.create_organization(
        organization_id="org00000000000000000000000000002",
        code="ORG-EXPORT",
        name="导出组织",
        owner_user_id=manager_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    member_headers = auth_headers(client, "v2_export_member", role="org_member")
    member_id = registered_user_id("v2_export_member")
    app_main.store.add_organization_member(organization.id, member_id, "org_member", datetime.now(UTC).isoformat())
    session = make_session(member_id, organization_id=organization.id)
    node_id = session.active_node_id
    session.messages = [
        ChatMessage(role="learner", text="我认为注意力会计算相关性。", node_id=node_id),
        ChatMessage(role="mentor", text="那权重归一化解决什么问题？", node_id=node_id),
    ]
    question = FeynmanQuestion(
        id="fq-1",
        label="机制解释",
        question="解释注意力权重如何产生。",
        focus="相关性与归一化",
        difficulty=3,
        stage="mechanism",
    )
    answer = FeynmanAnswer(
        question_id=question.id,
        label=question.label,
        question=question.question,
        answer="先算查询和键的相关性，再归一化成权重。",
        stage="mechanism",
    )
    session.feynman_questions = {node_id: [question]}
    session.feynman_answers = {node_id: {answer.question_id: answer}}
    session.feynman_assessments = {
        node_id: FeynmanAssessmentRecord(
            dimension_scores=[
                DimensionScore(stage="mechanism", label="机制解释", value=82, note="能说明权重产生")
            ],
            passed=True,
        )
    }
    app_main.store.save_session(session)

    response = client.get("/api/organizations/current/export", headers=manager_headers)

    assert member_headers
    assert response.status_code == 200
    payload = response.json()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "我认为注意力会计算相关性" in encoded
    assert "解释注意力权重如何产生" in encoded
    assert payload["organization"]["id"] == organization.id
    exported_member = next(item for item in payload["members"] if item["user"]["id"] == member_id)
    assert exported_member["session_traces"][0]["messages"][0]["role"] == "learner"
