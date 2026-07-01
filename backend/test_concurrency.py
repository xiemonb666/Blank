from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os
from uuid import uuid4


def test_store_allows_parallel_session_saves_for_different_users() -> None:
    from app.models import KnowledgeNode, LearningSession
    from app.store import SessionStore

    store = SessionStore(os.getenv("BLANK_DATABASE_URL", "postgresql://blank:blank@postgres:5432/blank"))
    run_id = uuid4().hex[:8]

    node = KnowledgeNode(
        id="node-a",
        title="并发节点",
        summary="验证多用户并行保存。",
        complexity=1,
        weight=1.0,
        status="active",
        x=10,
        y=10,
        deps=[],
    )
    now = datetime.now(UTC).isoformat()
    for index in range(12):
        store.create_user(
            user_id=f"user-{run_id}-{index:02d}",
            username=f"concurrent_{run_id}_{index:02d}",
            password_hash="hash",
            role="learner",
            is_active=True,
            created_at=now,
        )

    def save_one(index: int) -> str:
        session = LearningSession(
            id=uuid4().hex,
            user_id=f"user-{run_id}-{index:02d}",
            material_title=f"并发材料 {index}",
            material_context="并发测试材料",
            nodes=[node],
            active_node_id=node.id,
            messages=[],
        )
        return store.save_session(session).id

    with ThreadPoolExecutor(max_workers=12) as executor:
        saved_ids = list(executor.map(save_one, range(12)))

    assert len(set(saved_ids)) == 12
    assert len(store.list()) >= 12
