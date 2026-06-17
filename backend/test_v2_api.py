from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.models import LearningSession, KnowledgeNode
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


def make_session(user_id: str, title: str = "V2 测试材料") -> LearningSession:
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
