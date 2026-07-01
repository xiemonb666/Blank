from __future__ import annotations


def test_agent_graph_skips_critic_for_fallback_graphrag(monkeypatch) -> None:
    from app.agents import graph as graph_module

    calls: list[str] = []

    def router_node(_state):
        calls.append("router")
        return {"intent": "question", "intent_reason": "测试"}

    def socrates_node(_state):
        calls.append("socrates")
        return {"mentor_reply": "测试回复", "mentor_thinking": "测试思考"}

    def critic_node(_state):
        calls.append("critic")
        return {"critic_verdict": {"has_hallucination": False, "issues": []}}

    monkeypatch.setattr(graph_module, "router_node", router_node)
    monkeypatch.setattr(graph_module, "socrates_node", socrates_node)
    monkeypatch.setattr(graph_module, "critic_node", critic_node)
    graph = graph_module.build_agent_graph()

    result = graph.invoke(base_state({"fallback": True, "chunks": [{"text": "回退片段"}], "subgraphs": []}))

    assert result["final_output"] == "测试回复"
    assert calls == ["router", "socrates"]
    assert result.get("critic_verdict") == {}


def test_agent_graph_runs_critic_for_real_graphrag(monkeypatch) -> None:
    from app.agents import graph as graph_module

    calls: list[str] = []

    def router_node(_state):
        calls.append("router")
        return {"intent": "question", "intent_reason": "测试"}

    def socrates_node(_state):
        calls.append("socrates")
        return {"mentor_reply": "测试回复", "mentor_thinking": "测试思考"}

    def critic_node(_state):
        calls.append("critic")
        return {"critic_verdict": {"has_hallucination": False, "issues": []}}

    monkeypatch.setattr(graph_module, "router_node", router_node)
    monkeypatch.setattr(graph_module, "socrates_node", socrates_node)
    monkeypatch.setattr(graph_module, "critic_node", critic_node)
    graph = graph_module.build_agent_graph()

    result = graph.invoke(base_state({"chunks": [{"text": "真实召回片段"}], "subgraphs": []}))

    assert result["final_output"] == "测试回复"
    assert calls == ["router", "socrates", "critic"]
    assert result["critic_verdict"]["has_hallucination"] is False


def test_agent_graph_uses_feynman_guidance_as_final_output(monkeypatch) -> None:
    from app.agents import graph as graph_module

    calls: list[str] = []

    def router_node(_state):
        calls.append("router")
        return {"intent": "explanation", "intent_reason": "学习者正在复述"}

    def feynman_node(_state):
        calls.append("feynman")
        return {
            "feynman_score": {"dimension_scores": [], "overall_passed": False},
            "feynman_feedback": "这是给诊断面板看的评分报告。",
            "feynman_guidance": "这是给学习者看的苏格拉底式追问。",
        }

    monkeypatch.setattr(graph_module, "router_node", router_node)
    monkeypatch.setattr(graph_module, "feynman_node", feynman_node)
    graph = graph_module.build_agent_graph()

    result = graph.invoke(base_state({"fallback": True, "chunks": [{"text": "回退片段"}], "subgraphs": []}))

    assert result["final_output"] == "这是给学习者看的苏格拉底式追问。"
    assert result["feynman_feedback"] == "这是给诊断面板看的评分报告。"
    assert calls == ["router", "feynman"]


def test_agent_graph_runs_dynamic_agents_before_generator(monkeypatch) -> None:
    from app.agents import graph as graph_module

    calls: list[str] = []

    def router_node(_state):
        calls.append("router")
        return {
            "intent": "question",
            "intent_reason": "复杂问题且有卡顿",
            "dynamic_agents": ["planner", "analyst", "coach", "memory"],
        }

    def planner_node(_state):
        calls.append("planner")
        return {"dynamic_guidance": "先拆成目标和步骤。"}

    def analyst_node(state):
        calls.append("analyst")
        return {"dynamic_guidance": f"{state.get('dynamic_guidance', '')}补充机制分析。"}

    def coach_node(state):
        calls.append("coach")
        return {"dynamic_guidance": f"{state.get('dynamic_guidance', '')}降低表达负荷。"}

    def memory_node(state):
        calls.append("memory")
        return {"dynamic_guidance": f"{state.get('dynamic_guidance', '')}记录薄弱点。"}

    def socrates_node(state):
        calls.append("socrates")
        assert "记录薄弱点" in state.get("dynamic_guidance", "")
        return {"mentor_reply": "动态增派后的回复", "mentor_thinking": "测试思考"}

    monkeypatch.setattr(graph_module, "router_node", router_node)
    monkeypatch.setattr(graph_module, "planner_node", planner_node, raising=False)
    monkeypatch.setattr(graph_module, "analyst_node", analyst_node, raising=False)
    monkeypatch.setattr(graph_module, "coach_node", coach_node, raising=False)
    monkeypatch.setattr(graph_module, "memory_node", memory_node, raising=False)
    monkeypatch.setattr(graph_module, "socrates_node", socrates_node)
    graph = graph_module.build_agent_graph()

    result = graph.invoke(base_state({"fallback": True, "chunks": [{"text": "回退片段"}], "subgraphs": []}))

    assert result["final_output"] == "动态增派后的回复"
    assert calls == ["router", "planner", "analyst", "coach", "memory", "socrates"]


def base_state(graph_context: dict) -> dict:
    return {
        "session_id": "session",
        "user_id": "user",
        "node_id": "node",
        "node_title": "注意力机制",
        "node_summary": "根据相关性聚焦信息。",
        "persona": "plain",
        "user_message": "为什么？",
        "chat_history": [],
        "memories": [],
        "graph_context": graph_context,
        "ai_config": None,
        "intent": "",
        "intent_reason": "",
        "dynamic_agents": [],
        "dynamic_guidance": "",
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
