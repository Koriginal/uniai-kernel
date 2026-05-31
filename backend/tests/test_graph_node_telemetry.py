from app.agents.graph_builder import _node_input_summary, _node_output_summary


def test_node_input_summary_exposes_runtime_state_without_message_content():
    summary = _node_input_summary(
        {
            "messages": [{"role": "user", "content": "secret content"}],
            "pending_tool_calls": [{"id": "call_1"}],
            "current_agent_id": "agent_1",
            "iteration_count": 2,
            "task_frame": {"kind": "engineering", "user_goal": "do work"},
            "execution_plan": {
                "status": "running",
                "current_step": "verify",
                "steps": [
                    {"id": "inspect", "status": "completed"},
                    {"id": "verify", "status": "pending"},
                ],
            },
            "execution_artifacts": [{"type": "tool_result"}],
            "task_repair_count": 1,
            "pending_repair": True,
        }
    )

    assert summary["message_count"] == 1
    assert summary["pending_tool_calls"] == 1
    assert summary["task_kind"] == "engineering"
    assert summary["plan"]["current_step"] == "verify"
    assert summary["plan"]["completed_steps"] == 1
    assert summary["artifact_count"] == 1
    assert "secret content" not in str(summary)


def test_node_output_summary_reports_state_deltas():
    before = {
        "messages": [{"role": "user", "content": "hello"}],
        "pending_tool_calls": [],
        "execution_plan": {"status": "running", "current_step": "solve", "steps": []},
        "execution_artifacts": [],
    }
    result = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "done"},
        ],
        "iter_text": "done",
        "execution_artifacts": [{"type": "answer"}],
        "task_evaluation": {"status": "passed"},
    }

    summary = _node_output_summary(before, result)

    assert summary["message_count"] == 2
    assert summary["message_delta"] == 1
    assert summary["iter_text_chars"] == 4
    assert summary["artifact_count"] == 1
    assert summary["task_evaluation_status"] == "passed"
    assert "task_evaluation" in summary["updated_keys"]
