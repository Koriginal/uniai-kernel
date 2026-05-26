from app.agents.task_runtime import (
    build_execution_plan,
    build_runtime_prompt_block,
    build_task_frame,
    classify_task,
)


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
