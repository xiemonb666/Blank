from __future__ import annotations


def test_feynman_node_rewrites_report_like_guidance(monkeypatch) -> None:
    from app.agents import feynman as feynman_module

    def fake_llm_chat(**_kwargs):
        return """
        {
          "dimension_scores": [
            {"stage": "warmup", "label": "基础理解", "value": 82, "note": "抓到二次方计算"},
            {"stage": "transfer", "label": "迁移应用", "value": 20, "note": "没有举例"}
          ],
          "overall_passed": false,
          "overall_feedback": "学习者掌握了注意力机制二次方计算这一要点，但最薄弱的是迁移应用维度。建议补充学习：①线性内存消耗；②长上下文延迟。",
          "guidance_reply": "学习者掌握了注意力机制二次方计算这一要点，但最薄弱的是迁移应用维度。建议补充学习：①线性内存消耗；②长上下文延迟。"
        }
        """

    monkeypatch.setattr(feynman_module, "llm_chat", fake_llm_chat)

    result = feynman_module.feynman_node(
        {
            "node_title": "注意力机制",
            "node_summary": "注意力机制在长上下文推理中会带来计算和缓存成本。",
            "user_message": "我的理解是注意力主要慢在二次方计算。",
            "graph_context": {"chunks": [{"text": "KV 缓存随序列长度增长。"}]},
            "ai_config": {"base_url": "http://127.0.0.1:1/v1", "api_key": "sk-test", "model": "test"},
        }
    )

    assert "学习者掌握了" in result["feynman_feedback"]
    guidance = result["feynman_guidance"]
    assert "学习者掌握了" not in guidance
    assert "维度" not in guidance
    assert "建议补充学习" not in guidance
    assert "你能举一个" in guidance
    assert "注意力机制" in guidance
