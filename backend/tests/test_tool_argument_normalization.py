from app.agents.nodes.agent import _normalize_tool_arguments, _sanitize_message_tool_calls


def test_normalize_tool_arguments_keeps_json_object_string():
    assert _normalize_tool_arguments('{"query":"today gold price"}') == '{"query": "today gold price"}'


def test_normalize_tool_arguments_wraps_non_json_text():
    assert _normalize_tool_arguments("not json") == '{"input": "not json"}'


def test_normalize_tool_arguments_wraps_array():
    assert _normalize_tool_arguments('["a","b"]') == '{"input": ["a", "b"]}'


def test_sanitize_message_tool_calls_rewrites_assistant_tool_arguments():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "code_tool", "arguments": "class Contract: pass"},
                }
            ],
        }
    ]

    result = _sanitize_message_tool_calls(messages)

    assert result[0]["tool_calls"][0]["function"]["arguments"] == '{"input": "class Contract: pass"}'
