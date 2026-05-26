from datetime import datetime, timezone

from app.api.endpoints.agents import AgentProfileValidationRequest, _normalize_agent_payload
from app.agents.nodes.agent import _looks_like_business_review_task
from app.agents.nodes.tools import _is_tool_allowed_by_policy, _redact_tool_args, _summarize_tool_result, inject_runtime_tool_args
from app.core.plugins import PluginRegistry, registry
from app.ontology.action_planner import OntologyActionPlanner
from app.ontology.action_executor import OntologyActionExecutor
from app.ontology.domain_models import (
    DataSourceKind,
    DataSourceStatus,
    EntityInstance,
    InstanceGraph,
    MappingExecuteRequest,
    MappingTraceItem,
    OntologyDataSourceRecord,
    OntologyRuntimeExecuteRequest,
)
from app.ontology.pipeline import OntologyPipelineResult, OntologyRuntimePipeline
from app.ontology.persistent_service import PersistentOntologyService
from app.ontology.runtime import ONTOLOGY_AGENT_TOOL_NAMES, ontology_runtime
from app.ontology.templates import get_template, list_template_summaries
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


def test_agent_ontology_config_sets_runtime_policy_without_exposing_tools():
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
    assert normalized["agent_type"] == "ontology"
    assert normalized["runtime_policy"]["allow_ontology"] is True
    assert normalized["runtime_policy"]["tool_call_mode"] == "ontology_preflight"
    assert set(ONTOLOGY_AGENT_TOOL_NAMES).isdisjoint(set(normalized["tools"]))
    assert isinstance(warnings, list)


def test_agent_type_tool_allows_controlled_tools():
    registry.load_plugins("app.tools")
    normalized, _ = _normalize_agent_payload(
        AgentProfileValidationRequest(
            name="Search Agent",
            model_config_id=1,
            agent_type="tool",
            tools=["web_search"],
        )
    )
    assert normalized["agent_type"] == "tool"
    assert normalized["runtime_policy"]["allow_tools"] is True
    assert normalized["runtime_policy"]["allow_web_search"] is True
    assert normalized["runtime_policy"]["allow_ontology"] is False


def test_agent_type_general_defaults_to_no_tools():
    normalized, _ = _normalize_agent_payload(
        AgentProfileValidationRequest(
            name="General Agent",
            model_config_id=1,
            agent_type="general",
            tools=[],
        )
    )
    assert normalized["runtime_policy"]["allow_tools"] is False
    assert normalized["runtime_policy"]["allow_swarm"] is False


def test_ontology_tool_schema_does_not_expose_user_id():
    schema = OntologyMapInputTool().parameters_schema
    assert "user_id" not in schema["properties"]
    assert "user_id" not in schema["required"]


def test_tool_executor_injects_trusted_ontology_context():
    args = {"user_id": "llm-forged-user", "input_payload": {"item": {"id": 1}}}
    injected = inject_runtime_tool_args(
        "ontology_map_input",
        args,
        {"user_id": "trusted-user", "is_admin": True},
        {"ontology_config": {"enabled": True, "space_id": "trusted-space"}},
    )
    assert injected["user_id"] == "trusted-user"
    assert injected["is_admin"] is True
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


def test_tool_runtime_redacts_sensitive_arguments():
    args = {
        "query": "hello",
        "api_key": "sk-test",
        "nested": {"authorization": "Bearer secret", "safe": "value"},
        "items": [{"password": "pass"}, {"name": "ok"}],
    }
    redacted = _redact_tool_args(args)
    assert redacted["query"] == "hello"
    assert redacted["api_key"] == "***"
    assert redacted["nested"]["authorization"] == "***"
    assert redacted["nested"]["safe"] == "value"
    assert redacted["items"][0]["password"] == "***"
    assert redacted["items"][1]["name"] == "ok"


def test_tool_runtime_policy_blocks_disallowed_tools():
    allowed, reason = _is_tool_allowed_by_policy("web_search", {"allow_tools": True, "allow_web_search": False})
    assert allowed is False
    assert "联网检索" in reason

    allowed, reason = _is_tool_allowed_by_policy("calculator", {"allow_tools": False})
    assert allowed is False
    assert "禁止执行工具" in reason

    allowed, reason = _is_tool_allowed_by_policy("calculator", {"allow_tools": True})
    assert allowed is True
    assert reason is None


def test_tool_runtime_result_summary_truncates_large_payloads():
    summary = _summarize_tool_result({"text": "x" * 100}, max_chars=30)
    assert summary["result_type"] == "dict"
    assert summary["truncated"] is True
    assert len(summary["preview"]) <= 33


def test_ontology_pipeline_extracts_fenced_json_payload():
    payload = OntologyRuntimePipeline.extract_json_payload(
        '请审核：```json\n{"item": {"id": "demo-1", "name": "demo"}}\n```'
    )
    assert payload == {"item": {"id": "demo-1", "name": "demo"}}


def test_ontology_pipeline_extracts_inline_nested_json_payload():
    payload = OntologyRuntimePipeline.extract_json_payload(
        '跑一下本体 {"item": {"id": "demo-1", "attrs": {"level": 3}}} 看风险'
    )
    assert payload == {"item": {"id": "demo-1", "attrs": {"level": 3}}}


def test_ontology_pipeline_extracts_contract_text_payload():
    payload = OntologyRuntimePipeline.extract_domain_text_payload(
        """
        TECHNICAL CONSULTING CONTRACT
        Project Name: Integrated Technical Services
        Contract No.: J-2024-XN-017-ZX
        Party A (Client): China Energy Construction Group
        Party B (Consultant): UniAI Services Ltd.
        Total Amount: RMB 1,250,000
        Payment terms: 50% after acceptance.
        Governing law: PRC law
        """
    )
    assert payload is not None
    contract = payload["contract"]
    assert contract["contract_id"] == "J-2024-XN-017-ZX"
    assert contract["title"] == "Integrated Technical Services"
    assert contract["counterparty_name"] == "UniAI Services Ltd."
    assert contract["amount"] == 1250000.0
    assert contract["currency"] == "CNY"
    assert "raw_text" in contract


def test_ontology_pipeline_state_payload_is_json_safe():
    result = OntologyPipelineResult(
        enabled=True,
        status="waiting_for_input",
        space_id="space-1",
        message="need input",
        active_versions={"schema": "1.0.0"},
        graph_id="onto-graph-test",
        trigger_reason="已触发本体契约注入",
        trigger_signals=["auto 模式", "命中本体/审核/风控关键词"],
    )
    state_payload = {"prompt_block": result.to_prompt_block(), "event": result.to_event()}
    assert state_payload["event"]["status"] == "waiting_for_input"
    assert state_payload["event"]["graph_id"] == "onto-graph-test"
    assert state_payload["event"]["trigger_reason"] == "已触发本体契约注入"
    assert state_payload["event"]["trigger_signals"] == ["auto 模式", "命中本体/审核/风控关键词"]
    assert "[ONTOLOGY PIPELINE SNAPSHOT]" in state_payload["prompt_block"]


def test_ontology_pipeline_response_contract_is_console_safe():
    result = OntologyPipelineResult(
        enabled=True,
        status="waiting_for_input",
        space_id="space-1",
        message="need input",
        active_versions={"schema": "1.0.0"},
        missing_active_packages=["mapping"],
        graph_id="onto-graph-test",
        action_plan={"summary": "complete missing fields", "steps": []},
        warnings=["mapping package is missing"],
        should_block=True,
    )
    response = result.to_response()
    assert response["enabled"] is True
    assert response["status"] == "waiting_for_input"
    assert response["space_id"] == "space-1"
    assert response["graph_id"] == "onto-graph-test"
    assert response["missing_active_packages"] == ["mapping"]
    assert response["action_plan"]["summary"] == "complete missing fields"
    assert response["should_block"] is True


def test_ontology_runtime_execute_request_defaults_are_safe():
    request = OntologyRuntimeExecuteRequest(space_id="space-1", input_payload={"item": {"id": "1"}})
    assert request.strict_rules is False
    assert request.explain_required is True
    assert request.fallback_when_unavailable == "stop_and_ask"
    assert request.session_id is None


def test_ontology_pipeline_ignores_plain_chitchat_in_auto_mode():
    assert OntologyRuntimePipeline.looks_like_ontology_task("你好，帮我写一段欢迎语") is False
    assert OntologyRuntimePipeline.looks_like_ontology_task("请审核这份数据的风险") is True
    assert OntologyRuntimePipeline.looks_like_ontology_task("Contract No.: C-1\nParty A: A\nParty B: B") is True


def test_business_review_task_lock_detects_contract_review_without_realtime_search():
    contract_text = """
    请审核这份合同风险：
    TECHNICAL CONSULTING CONTRACT
    Contract No.: C-2026-001
    Party A: UniAI Buyer
    Party B: Service Vendor
    Total Amount: RMB 260,000
    Automatic renewal applies unless cancelled.
    """
    assert _looks_like_business_review_task(contract_text) is True
    assert _looks_like_business_review_task("搜索一下今日合同法最新新闻") is False
    assert _looks_like_business_review_task("你好，帮我写欢迎语") is False


def test_contract_review_template_is_backend_visible_and_runtime_compatible():
    summaries = list_template_summaries()
    assert any(item.id == "contract-review" for item in summaries)

    template = get_template("contract-review")
    payload = OntologyRuntimePipeline.extract_domain_text_payload(
        """
        TECHNICAL CONSULTING CONTRACT
        Contract No.: C-2026-001
        Party A: UniAI Buyer
        Party B: Service Vendor
        Total Amount: RMB 260,000
        Automatic renewal applies unless cancelled.
        """
    )
    assert payload is not None
    field_paths = {
        item["source_path"]
        for item in template["mapping"]["entity_mappings"][0]["field_mappings"]
    }
    assert "id" in field_paths
    assert "amount" in field_paths
    assert "auto_renewal" in field_paths
    assert "raw_text" in field_paths


def test_ontology_pipeline_trigger_signals_are_stable():
    signals = OntologyRuntimePipeline.detect_trigger_signals(
        '请审核合同 ```json\n{"contract": {"id": "C-1"}}\n```',
        input_payload={"contract": {"id": "C-1"}},
        mode="auto",
    )

    assert signals[0] == "auto 模式"
    assert "检测到结构化/可映射输入" in signals
    assert "检测到 JSON 输入" in signals
    assert "命中本体/审核/风控关键词" in signals


def test_mapping_execute_request_graph_persistence_defaults_off():
    req = MappingExecuteRequest(space_id="space-1", input_payload={"item": {"id": "1"}})
    assert req.persist_graph is False
    assert req.source == "manual"
    assert req.session_id is None


def test_ontology_action_planner_recommends_data_source_for_missing_required_field():
    planner = OntologyActionPlanner()
    graph = InstanceGraph(
        entities=[EntityInstance(id="customer:1", entity_type="Customer", attributes={"id": "1"})],
        relations=[],
    )
    data_source = OntologyDataSourceRecord(
        id="ds-1",
        space_id="space-1",
        name="Customer CRM API",
        kind=DataSourceKind.api,
        protocol="openapi",
        config={"resource": "customer", "fields": ["credit_score"]},
        status=DataSourceStatus.active,
        created_by="u1",
        created_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
    )
    plan = planner.build_plan(
        query="审核客户风险",
        graph=graph,
        decision=None,
        mapping_trace=[MappingTraceItem(code="MAPPING_REQUIRED_MISSING", message="missing", target="Customer.credit_score", source_path="credit_score")],
        schema_payload={
            "entity_types": [
                {"name": "Customer", "attributes": {"credit_score": {"data_type": "number", "required": True}}},
            ]
        },
        data_sources=[data_source],
        tool_catalog=[{"name": "crm_lookup", "label": "CRM 查询", "description": "查询 customer credit_score", "category": "api"}],
    )
    plan_dict = plan.to_dict()
    assert plan_dict["missing_fields"][0]["field"] == "credit_score"
    assert plan_dict["suggested_data_sources"][0]["id"] == "ds-1"
    assert plan_dict["suggested_tools"][0]["name"] == "crm_lookup"
    assert plan_dict["steps"][0]["kind"] == "data_source"


def test_ontology_action_executor_applies_fixture_patch_to_graph():
    graph = InstanceGraph(
        entities=[EntityInstance(id="customer:c-1", entity_type="Customer", attributes={"id": "c-1"})],
        relations=[],
    )
    source = OntologyDataSourceRecord(
        id="ds-1",
        space_id="space-1",
        name="Customer fixture",
        kind=DataSourceKind.api,
        protocol="fixture",
        config={
            "runtime": {
                "mode": "fixture",
                "key_field": "id",
                "entity_type": "Customer",
                "records": [{"id": "c-1", "credit_score": 720}],
            }
        },
        status=DataSourceStatus.active,
        created_by="u1",
        created_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
    )
    action_plan = {
        "missing_fields": [{"entity_type": "Customer", "entity_id": "customer:c-1", "field": "credit_score"}],
        "steps": [{"step_id": "complete_required_fields", "kind": "data_source", "data_source_id": "ds-1"}],
    }
    result = OntologyActionExecutor().execute_safe(graph=graph, action_plan=action_plan, data_sources=[source])
    assert result.status == "applied"
    assert result.applied_patch_count == 1
    assert result.graph.entities[0].attributes["credit_score"] == 720


def test_ontology_action_executor_skips_live_sources_by_default():
    graph = InstanceGraph(
        entities=[EntityInstance(id="customer:c-1", entity_type="Customer", attributes={"id": "c-1"})],
        relations=[],
    )
    source = OntologyDataSourceRecord(
        id="ds-live",
        space_id="space-1",
        name="Live API",
        kind=DataSourceKind.api,
        protocol="openapi",
        config={"base_url": "https://example.com", "runtime": {"mode": "live_http"}},
        status=DataSourceStatus.active,
        created_by="u1",
        created_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
    )
    result = OntologyActionExecutor().execute_safe(
        graph=graph,
        action_plan={
            "missing_fields": [{"entity_type": "Customer", "entity_id": "customer:c-1", "field": "credit_score"}],
            "steps": [{"step_id": "complete_required_fields", "kind": "data_source", "data_source_id": "ds-live"}],
        },
        data_sources=[source],
    )
    assert result.status == "skipped"
    assert result.applied_patch_count == 0
    assert "live execution is disabled" in result.executions[0]["reason"]


def test_live_sql_policy_allows_only_readonly_single_statement():
    executor = OntologyActionExecutor()
    assert executor._validate_readonly_sql("select id, name from customers where id = $1") is None
    assert executor._validate_readonly_sql("with x as (select 1) select * from x") is None
    assert "only SELECT" in executor._validate_readonly_sql("update customers set name = 'x'")
    assert "only one SQL" in executor._validate_readonly_sql("select * from users; drop table users")


def test_live_api_ssrf_guard_blocks_private_addresses():
    executor = OntologyActionExecutor()
    try:
        executor._assert_safe_url("http://127.0.0.1/internal", ["127.0.0.1"])
    except ValueError as exc:
        assert "private or reserved" in str(exc)
    else:
        assert False, "expected localhost SSRF target to be blocked"


def test_data_source_upsert_cannot_forge_runtime_approval():
    config = {
        "runtime": {
            "mode": "live_api",
            "live_approved": True,
            "approved_by": "attacker",
            "approved_at": "now",
            "approval_reason": "forged",
        }
    }
    PersistentOntologyService._strip_runtime_approval_fields(config)
    assert "live_approved" not in config["runtime"]
    assert "approved_by" not in config["runtime"]


async def test_governed_executor_blocks_unapproved_live_source(monkeypatch):
    monkeypatch.setattr("app.ontology.action_executor.settings.ONTOLOGY_ENABLE_LIVE_DATA_SOURCE_EXECUTION", True)
    graph = InstanceGraph(
        entities=[EntityInstance(id="customer:c-1", entity_type="Customer", attributes={"id": "c-1"})],
        relations=[],
    )
    source = OntologyDataSourceRecord(
        id="ds-live",
        space_id="space-1",
        name="Live API",
        kind=DataSourceKind.api,
        protocol="rest",
        config={"base_url": "https://api.example.com", "runtime": {"mode": "live_api", "allowed_hosts": ["api.example.com"]}},
        status=DataSourceStatus.active,
        created_by="u1",
        created_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
    )
    result = await OntologyActionExecutor().execute(
        graph=graph,
        action_plan={
            "missing_fields": [{"entity_type": "Customer", "entity_id": "customer:c-1", "field": "credit_score"}],
            "steps": [{"step_id": "complete_required_fields", "kind": "data_source", "data_source_id": "ds-live"}],
        },
        data_sources=[source],
    )
    assert result.mode == "governed_runtime"
    assert result.applied_patch_count == 0
    assert result.executions[0]["status"] == "skipped"
    assert "approval" in result.executions[0]["reason"]
