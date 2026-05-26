from app.agents.nodes.agent import (
    _has_tool_result_after_latest_user,
    _is_active_ontology_pipeline,
    _looks_like_ontology_runtime_task,
)


def test_has_tool_result_after_latest_user_false_for_old_turn_result():
    messages = [
        {"role": "user", "content": "搜索一下今日金价"},
        {"role": "tool", "name": "web_search", "content": "gold result"},
        {"role": "assistant", "content": "根据检索结果..."},
        {"role": "user", "content": "搜索一下全新超级小爱音箱pro最低价格"},
    ]
    assert _has_tool_result_after_latest_user(messages, "web_search") is False


def test_has_tool_result_after_latest_user_true_when_current_turn_has_tool_result():
    messages = [
        {"role": "user", "content": "搜索一下今日金价"},
        {"role": "tool", "name": "web_search", "content": "gold result"},
        {"role": "assistant", "content": "根据检索结果..."},
        {"role": "user", "content": "搜索一下全新超级小爱音箱pro最低价格"},
        {"role": "tool", "name": "web_search", "content": "speaker result"},
    ]
    assert _has_tool_result_after_latest_user(messages, "web_search") is True


def test_contract_text_is_treated_as_ontology_runtime_task():
    assert _looks_like_ontology_runtime_task("Contract No.: C-1\nParty A: A\nPayment terms: 50%") is True
    assert _looks_like_ontology_runtime_task("帮我翻译合同") is False
    assert _looks_like_ontology_runtime_task("你好，帮我写一个欢迎语") is False


def test_non_idle_ontology_pipeline_locks_routing():
    assert _is_active_ontology_pipeline({"event": {"status": "success"}}) is True
    assert _is_active_ontology_pipeline({"event": {"status": "waiting_for_input"}}) is True
    assert _is_active_ontology_pipeline({"event": {"status": "idle"}}) is False
