from app.agents.nodes.agent import _has_tool_result_after_latest_user


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
