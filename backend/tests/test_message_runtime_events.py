from app.api.endpoints.messages import _message_runtime_payload
from app.models.message import ChatMessage


def test_message_runtime_payload_defaults_to_empty_events():
    message = ChatMessage(
        id="msg-1",
        session_id="session-1",
        role="assistant",
        content="hello",
        user_id="user-1",
        agent_id="agent-1",
        runtime_events=None,
    )

    payload = _message_runtime_payload(message)

    assert payload["message_id"] == "msg-1"
    assert payload["session_id"] == "session-1"
    assert payload["agent_id"] == "agent-1"
    assert payload["runtime_events"] == {}
    assert payload["ontology_runtime"] is None
    assert payload["tool_runtime_events"] == []


def test_message_runtime_payload_returns_replay_snapshots():
    ontology_event = {"type": "ontology_runtime", "status": "success", "space_name": "合同审核"}
    tool_events = [
        {"tool_call_id": "call-1", "tool_name": "web_search", "status": "blocked"},
    ]
    message = ChatMessage(
        id="msg-2",
        session_id="session-2",
        role="assistant",
        content="done",
        user_id="user-1",
        agent_id="agent-2",
        runtime_events={
            "ontology_runtime": ontology_event,
            "tool_runtime_events": tool_events,
        },
    )

    payload = _message_runtime_payload(message)

    assert payload["ontology_runtime"] == ontology_event
    assert payload["tool_runtime_events"] == tool_events
