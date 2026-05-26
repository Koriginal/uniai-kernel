from app.api.endpoints.agents import _runtime_policy_explanation
from app.models.agent import AgentProfile


def test_runtime_policy_explanation_reports_effects_and_warnings():
    agent = AgentProfile(
        id="agent-1",
        name="合同审核专家",
        role="expert",
        agent_type="ontology",
        tools=["web_search"],
        runtime_policy={
            "allow_tools": False,
            "allow_web_search": True,
            "allow_swarm": False,
            "allow_canvas": True,
            "allow_ontology": False,
            "tool_call_mode": "controlled",
        },
        ontology_config={
            "enabled": True,
            "mode": "required",
            "space_id": "space-1",
        },
    )

    payload = _runtime_policy_explanation(agent)

    assert payload["agent_id"] == "agent-1"
    assert payload["agent_type"] == "ontology"
    assert payload["tool_call_mode"] == "controlled"
    assert payload["tools_count"] == 1
    assert payload["ontology_mode"] == "required"
    assert any(item["key"] == "allow_tools" and item["enabled"] is False for item in payload["items"])
    assert "已配置工具，但运行策略禁止工具调用。" in payload["warnings"]
    assert "联网检索依赖工具调用；当前工具调用关闭。" in payload["warnings"]
    assert "已启用本体配置，但运行策略禁止本体运行。" in payload["warnings"]
