from app.agents.nodes.tools import _estimate_json_size, _json_safe
from app.api.endpoints.audit import _runtime_trace_summary
from app.models.tool_artifact import ToolArtifact


class NonJsonValue:
    def __str__(self):
        return "non-json-value"


def test_json_safe_keeps_shape_and_stringifies_unknown_values():
    value = {"ok": True, "items": [NonJsonValue()]}

    safe = _json_safe(value)

    assert safe == {"ok": True, "items": ["non-json-value"]}
    assert _estimate_json_size(safe) > 0


def test_tool_artifact_model_table_name():
    assert ToolArtifact.__tablename__ == "tool_artifacts"
    assert "artifact_metadata" in ToolArtifact.__table__.columns


def test_runtime_trace_summary_counts_task_runtime_and_artifacts():
    summary = _runtime_trace_summary(
        {
            "task_runtime": {
                "task_frame": {"kind": "realtime_research"},
                "execution_plan": {"status": "completed"},
                "task_repair_count": 1,
                "task_evaluation": {
                    "status": "passed",
                    "checks": [
                        {"id": "response_present", "status": "passed"},
                        {"id": "external_facts", "status": "warning"},
                    ],
                    "missing_requirements": ["source_timestamp"],
                },
            },
            "tool_runtime_events": [
                {
                    "phase": "end",
                    "status": "success",
                    "tool_name": "web_search",
                    "artifact_id": "artifact_1",
                }
            ],
        }
    )

    assert summary["has_task_runtime"] is True
    assert summary["task_kind"] == "realtime_research"
    assert summary["task_status"] == "passed"
    assert summary["artifact_count"] == 1
    assert summary["repair_count"] == 1
    assert summary["evaluation_check_count"] == 2
    assert summary["warning_check_count"] == 1
    assert summary["missing_requirement_count"] == 1
