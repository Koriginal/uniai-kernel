from app.agents.task_runtime import (
    advance_execution_plan,
    build_repair_message,
    build_execution_plan,
    build_runtime_prompt_block,
    build_task_frame,
    classify_task,
    evaluate_task_completion,
    get_runtime_capability_catalog,
    get_runtime_provider_catalog,
    reopen_plan_for_repair,
    record_execution_artifact,
    register_runtime_capability_provider,
    should_repair_task,
    unregister_runtime_capability_provider,
    validate_tool_against_plan,
)
from app.agents.runtime_capabilities import RuntimeCapabilityContext
from app.agents.nodes.tools import _is_tool_allowed_by_application


def test_classify_realtime_task():
    assert classify_task("今天美元兑人民币汇率是多少？") == "realtime_research"


def test_classify_business_review_task():
    query = "请审查这份合同的付款条款和违约责任，识别合规风险。"
    assert classify_task(query) == "business_review"


def test_build_engineering_plan_can_delegate_when_swarm_enabled():
    frame = build_task_frame(
        query="帮我修复这个接口报错并补测试",
        semantic_frame={},
        semantic_slots={},
        agent_profile={"runtime_policy": {"allow_tools": True}},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search", "upsert_canvas"],
        enable_swarm=True,
    )
    step_ids = [step["id"] for step in plan["steps"]]
    assert frame["kind"] == "engineering"
    assert "inspect" in step_ids
    assert "delegate" in step_ids
    assert "verify" in step_ids


def test_runtime_prompt_block_contains_plan_and_acceptance():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={"runtime_policy": {"allow_web_search": True}},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )
    prompt = build_runtime_prompt_block(frame, plan)
    assert "[TASK RUNTIME CONTRACT]" in prompt
    assert "retrieve" in prompt
    assert "web_search" in prompt
    assert "包含可核查来源" in prompt


def test_advance_execution_plan_marks_tool_step_by_candidate():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )

    plan = advance_execution_plan(plan, event_type="agent_start", payload={"agent_id": "root"})
    assert plan["steps"][0]["status"] == "in_progress"

    plan = advance_execution_plan(plan, event_type="agent_complete", payload={"agent_id": "root"})
    assert plan["steps"][0]["status"] == "completed"
    assert plan["current_step"] == "retrieve"
    assert plan["steps"][1]["status"] == "in_progress"

    plan = advance_execution_plan(
        plan,
        event_type="tool_success",
        payload={"tool_name": "web_search", "status": "success", "tool_call_id": "call_1"},
    )
    assert plan["steps"][1]["status"] == "completed"
    assert plan["current_step"] == "synthesize"


def test_record_execution_artifact_keeps_tool_preview():
    artifacts = record_execution_artifact(
        [],
        artifact_type="tool_result",
        payload={
            "status": "success",
            "tool_name": "web_search",
            "tool_call_id": "call_1",
            "result": {"preview": "source summary"},
            "duration_ms": 12.5,
        },
    )

    assert artifacts[0]["type"] == "tool_result"
    assert artifacts[0]["tool_name"] == "web_search"
    assert artifacts[0]["preview"] == "source summary"
    assert artifacts[0]["metadata"]["duration_ms"] == 12.5


def test_validate_tool_against_plan_allows_current_candidate():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )
    plan = advance_execution_plan(plan, event_type="agent_complete", payload={"agent_id": "root"})

    decision = validate_tool_against_plan(
        tool_name="web_search",
        tool_metadata={"category": "search"},
        task_frame=frame,
        execution_plan=plan,
    )

    assert decision["allowed"]
    assert decision["decision"] == "allow"
    assert decision["plan_step_id"] == "retrieve"


def test_validate_tool_against_plan_blocks_off_plan_tool_when_candidates_exist():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )
    plan = advance_execution_plan(plan, event_type="agent_complete", payload={"agent_id": "root"})

    decision = validate_tool_against_plan(
        tool_name="upsert_canvas",
        tool_metadata={"category": "canvas"},
        task_frame=frame,
        execution_plan=plan,
    )

    assert not decision["allowed"]
    assert decision["decision"] == "deny"
    assert "candidate" in decision["reason"]


def test_validate_tool_against_plan_warns_when_no_step_requests_tool():
    frame = build_task_frame(
        query="帮我写一段说明",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=[],
        enable_swarm=False,
    )

    decision = validate_tool_against_plan(
        tool_name="upsert_canvas",
        tool_metadata={"category": "canvas"},
        task_frame=frame,
        execution_plan=plan,
    )

    assert decision["allowed"]
    assert decision["decision"] == "warn"


def test_application_tool_whitelist_blocks_unlisted_tool():
    allowed, reason = _is_tool_allowed_by_application("upsert_canvas", ["web_search"])

    assert not allowed
    assert "业务应用" in reason


def test_evaluate_realtime_task_requires_retrieval():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )

    evaluation = evaluate_task_completion(
        task_frame=frame,
        execution_plan=plan,
        execution_artifacts=[],
        messages=[],
        assistant_text="今天金价上涨。",
    )

    assert evaluation["status"] == "failed"
    assert "web_search_result" in evaluation["missing_requirements"]


def test_evaluate_realtime_task_passes_with_web_search_artifact():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )
    plan = advance_execution_plan(plan, event_type="agent_start", payload={"agent_id": "root"})
    plan = advance_execution_plan(plan, event_type="agent_complete", payload={"agent_id": "root"})
    plan = advance_execution_plan(
        plan,
        event_type="tool_success",
        payload={"tool_name": "web_search", "status": "success", "tool_call_id": "call_1"},
    )
    plan = advance_execution_plan(plan, event_type="agent_complete", payload={"agent_id": "root"})
    artifacts = record_execution_artifact(
        [],
        artifact_type="tool_result",
        payload={
            "status": "success",
            "tool_name": "web_search",
            "tool_call_id": "call_1",
            "result": {"preview": "source summary"},
        },
    )

    evaluation = evaluate_task_completion(
        task_frame=frame,
        execution_plan=plan,
        execution_artifacts=artifacts,
        messages=[],
        assistant_text="根据来源，今天金价上涨。",
    )

    assert evaluation["status"] == "passed"


def test_should_repair_failed_task_once():
    evaluation = {"status": "failed", "missing_requirements": ["web_search_result"]}
    assert should_repair_task(evaluation, repair_count=0, max_repairs=1)
    assert not should_repair_task(evaluation, repair_count=1, max_repairs=1)


def test_reopen_plan_for_repair_targets_web_search_step():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    plan = build_execution_plan(
        task_frame=frame,
        available_tools=["web_search"],
        enable_swarm=False,
    )
    evaluation = {"status": "failed", "missing_requirements": ["web_search_result"]}

    repaired = reopen_plan_for_repair(plan, evaluation)

    assert repaired["status"] == "repairing"
    assert repaired["current_step"] == "retrieve"
    assert repaired["steps"][1]["status"] == "pending"


def test_build_repair_message_keeps_original_goal_and_missing_items():
    frame = build_task_frame(
        query="今天金价有什么变化？",
        semantic_frame={},
        semantic_slots={},
        agent_profile={},
    )
    message = build_repair_message(
        task_frame=frame,
        task_evaluation={
            "status": "failed",
            "missing_requirements": ["web_search_result"],
            "checks": [{"id": "external_facts", "status": "failed"}],
        },
    )

    assert message["role"] == "user"
    assert "今天金价有什么变化" in message["content"]
    assert "web_search_result" in message["content"]
    assert "external_facts" in message["content"]


def test_runtime_capability_catalog_exposes_framework_nodes():
    catalog = get_runtime_capability_catalog()
    ids = {item["id"] for item in catalog}

    assert "task_understanding" in ids
    assert "execution_planning" in ids
    assert "execution_ledger" in ids
    assert "task_evaluation" in ids
    assert "runtime_repair" in ids
    assert "runtime_capability_provider" in ids
    assert "plan_aware_tool_policy" in ids


def test_runtime_provider_catalog_exposes_default_provider():
    providers = get_runtime_provider_catalog()
    names = {item["name"] for item in providers}

    assert "default_task_runtime" in names


def test_registered_runtime_provider_can_own_custom_task_kind():
    class InvoiceRuntimeProvider:
        name = "invoice_runtime_test"
        version = "0.1"
        task_kinds = ["invoice_review"]
        priority = 20

        def catalog(self):
            return {
                "name": self.name,
                "version": self.version,
                "task_kinds": self.task_kinds,
                "description": "test provider",
            }

        def match(self, context: RuntimeCapabilityContext) -> float:
            if "发票" in context.query:
                return 0.9
            if context.task_frame.get("kind") == "invoice_review":
                return 0.9
            return 0.0

        def classify_task(self, context: RuntimeCapabilityContext) -> str:
            return "invoice_review"

        def build_frame(self, context: RuntimeCapabilityContext) -> dict:
            return {
                "task_id": "task_invoice_test",
                "kind": "invoice_review",
                "user_goal": context.query,
                "constraints": {"requires_governance": True},
                "acceptance": ["核对发票字段"],
                "runtime_provider": {"name": self.name, "version": self.version},
            }

        def build_plan(self, context: RuntimeCapabilityContext) -> dict:
            return {
                "plan_id": "plan_invoice_test",
                "task_id": context.task_frame.get("task_id"),
                "status": "planned",
                "steps": [
                    {
                        "id": "check_invoice",
                        "title": "核对发票抬头、金额和税号",
                        "owner": "orchestrator",
                        "status": "pending",
                        "tool_candidates": [],
                        "depends_on": [],
                    }
                ],
                "current_step": "check_invoice",
                "done_criteria": ["核对发票字段"],
                "runtime_provider": {"name": self.name, "version": self.version},
            }

        def evaluate(self, context: RuntimeCapabilityContext) -> dict:
            return {
                "status": "passed" if context.assistant_text else "failed",
                "checks": [{"id": "invoice_response", "status": "passed" if context.assistant_text else "failed"}],
                "missing_requirements": [] if context.assistant_text else ["invoice_response"],
                "acceptance": context.task_frame.get("acceptance") or [],
                "runtime_provider": {"name": self.name, "version": self.version},
            }

    register_runtime_capability_provider(InvoiceRuntimeProvider())
    try:
        frame = build_task_frame(
            query="请核对这张发票的抬头和金额",
            semantic_frame={},
            semantic_slots={},
            agent_profile={},
        )
        plan = build_execution_plan(task_frame=frame, available_tools=[], enable_swarm=False)
        evaluation = evaluate_task_completion(
            task_frame=frame,
            execution_plan=plan,
            execution_artifacts=[],
            messages=[],
            assistant_text="抬头和金额已核对。",
        )

        assert frame["kind"] == "invoice_review"
        assert frame["runtime_provider"]["name"] == "invoice_runtime_test"
        assert plan["steps"][0]["id"] == "check_invoice"
        assert evaluation["runtime_provider"]["name"] == "invoice_runtime_test"
    finally:
        unregister_runtime_capability_provider("invoice_runtime_test")


def test_runtime_provider_selection_respects_application_allowlist():
    class HighPriorityProvider:
        name = "high_priority_test"
        version = "0.1"
        task_kinds = ["high_priority"]
        priority = 50

        def catalog(self):
            return {"name": self.name, "version": self.version, "task_kinds": self.task_kinds}

        def match(self, context: RuntimeCapabilityContext) -> float:
            return 1.0

        def classify_task(self, context: RuntimeCapabilityContext) -> str:
            return "high_priority"

        def build_frame(self, context: RuntimeCapabilityContext) -> dict:
            return {"task_id": "task_high", "kind": "high_priority", "allowed_runtime_provider_names": context.allowed_provider_names}

        def build_plan(self, context: RuntimeCapabilityContext) -> dict:
            return {"plan_id": "plan_high", "steps": [], "runtime_provider": {"name": self.name}}

        def evaluate(self, context: RuntimeCapabilityContext) -> dict:
            return {"status": "passed", "checks": [], "missing_requirements": []}

    register_runtime_capability_provider(HighPriorityProvider())
    try:
        frame = build_task_frame(
            query="今天金价有什么变化？",
            semantic_frame={},
            semantic_slots={},
            agent_profile={"allowed_runtime_provider_names": ["default_task_runtime"]},
        )

        assert frame["kind"] == "realtime_research"
        assert frame["runtime_provider"]["name"] == "default_task_runtime"
    finally:
        unregister_runtime_capability_provider("high_priority_test")
