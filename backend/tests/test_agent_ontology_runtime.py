from app.api.endpoints.agents import AgentProfileValidationRequest, _normalize_agent_payload
from app.agents.nodes.tools import inject_runtime_tool_args
from app.core.plugins import PluginRegistry, registry
from app.ontology.runtime import ONTOLOGY_AGENT_TOOL_NAMES, ontology_runtime
from app.tools.ontology_tools import OntologyMapInputTool


def test_ontology_runtime_config_defaults_to_off():
    assert ontology_runtime.normalize_config({})["mode"] == "off"
    assert ontology_runtime.normalize_config({})["enabled"] is False


def test_ontology_runtime_config_auto_enabled():
    config = ontology_runtime.normalize_config({"enabled": True, "space_id": "space-1"})
    assert config["enabled"] is True
    assert config["mode"] == "auto"
    assert config["space_id"] == "space-1"


def test_ontology_tools_are_registered_by_plugin_loader():
    local_registry = PluginRegistry()
    local_registry.load_plugins("app.tools")
    names = {item["name"] for item in local_registry.get_action_catalog()}
    assert set(ONTOLOGY_AGENT_TOOL_NAMES).issubset(names)


def test_agent_ontology_config_adds_tools():
    registry.load_plugins("app.tools")
    normalized, warnings = _normalize_agent_payload(
        AgentProfileValidationRequest(
            name="Ontology Agent",
            model_config_id=1,
            tools=[],
            ontology_config={"enabled": True, "space_id": "space-1"},
        )
    )
    assert normalized["ontology_config"]["enabled"] is True
    assert set(ONTOLOGY_AGENT_TOOL_NAMES).issubset(set(normalized["tools"]))
    assert isinstance(warnings, list)


def test_ontology_tool_schema_does_not_expose_user_id():
    schema = OntologyMapInputTool().parameters_schema
    assert "user_id" not in schema["properties"]
    assert "user_id" not in schema["required"]


def test_tool_executor_injects_trusted_ontology_context():
    args = {"user_id": "llm-forged-user", "input_payload": {"item": {"id": 1}}}
    injected = inject_runtime_tool_args(
        "ontology_map_input",
        args,
        {"user_id": "trusted-user"},
        {"ontology_config": {"enabled": True, "space_id": "trusted-space"}},
    )
    assert injected["user_id"] == "trusted-user"
    assert injected["space_id"] == "trusted-space"
    assert injected["input_payload"] == {"item": {"id": 1}}


def test_tool_executor_does_not_mutate_non_ontology_tools():
    args = {"query": "hello"}
    injected = inject_runtime_tool_args(
        "web_search",
        args,
        {"user_id": "trusted-user"},
        {"ontology_config": {"enabled": True, "space_id": "trusted-space"}},
    )
    assert injected is args
