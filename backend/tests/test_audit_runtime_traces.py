from app.api.endpoints.audit import _content_preview, _runtime_trace_summary
from app.api.endpoints.sessions import _build_runtime_report_markdown, _summarize_runtime_trace_items
from app.models.session import ChatSession


def test_runtime_trace_summary_handles_empty_events():
    summary = _runtime_trace_summary(None)

    assert summary["has_ontology"] is False
    assert summary["tool_count"] == 0
    assert summary["blocked_tool_count"] == 0
    assert summary["failed_tool_count"] == 0


def test_runtime_trace_summary_extracts_ontology_and_tool_counts():
    summary = _runtime_trace_summary({
        "ontology_runtime": {
            "status": "success",
            "space_id": "space-1",
            "space_name": "合同审核",
            "space_code": "contract-review",
            "decision": {"risk_level": "high", "risk_score": 0.82},
        },
        "tool_runtime_events": [
            {"phase": "start", "tool_name": "web_search", "status": "running"},
            {"phase": "end", "tool_name": "web_search", "status": "blocked"},
            {"phase": "end", "tool_name": "ontology_evaluate", "status": "success"},
            {"phase": "end", "tool_name": "api_query", "status": "error"},
        ],
    })

    assert summary["has_ontology"] is True
    assert summary["ontology_status"] == "success"
    assert summary["ontology_space_name"] == "合同审核"
    assert summary["risk_level"] == "high"
    assert summary["tool_count"] == 3
    assert summary["successful_tool_count"] == 1
    assert summary["blocked_tool_count"] == 1
    assert summary["failed_tool_count"] == 1


def test_content_preview_compacts_whitespace_and_truncates():
    preview = _content_preview("第一行\n\n第二行   第三行", limit=8)

    assert preview == "第一行 第二行 ..."


def test_runtime_report_markdown_contains_operational_fields():
    session = ChatSession(id="session-1", title="合同审核会话")
    report = _build_runtime_report_markdown(
        session,
        [
            {
                "message_id": "msg-1",
                "agent_id": "agent-1",
                "created_at": None,
                "content_preview": "发现一个高风险条款。",
                "ontology_runtime": {
                    "trigger_reason": "检测到合同文本",
                    "trigger_signals": ["auto 模式", "检测到合同/协议文本"],
                },
                "summary": {
                    "has_ontology": True,
                    "ontology_status": "success",
                    "ontology_space_name": "合同审核",
                    "risk_level": "high",
                    "tool_count": 2,
                    "successful_tool_count": 1,
                    "blocked_tool_count": 1,
                    "failed_tool_count": 0,
                },
            }
        ],
        {"total": 1, "with_ontology": 1, "with_tools": 1, "blocked_tools": 1, "failed_tools": 0},
    )

    assert "# 会话运行轨迹报告" in report
    assert "会话：合同审核会话" in report
    assert "本体空间：合同审核" in report
    assert "触发判断：检测到合同文本" in report
    assert "触发信号：auto 模式，检测到合同/协议文本" in report
    assert "风险等级：high" in report
    assert "工具：2 次，成功 1，拦截 1，失败 0" in report


def test_summarize_runtime_trace_items_keeps_export_and_list_counts_aligned():
    summary = _summarize_runtime_trace_items([
        {
            "summary": {
                "has_ontology": True,
                "tool_count": 2,
                "blocked_tool_count": 1,
                "failed_tool_count": 0,
            }
        },
        {
            "summary": {
                "has_ontology": False,
                "tool_count": 1,
                "blocked_tool_count": 0,
                "failed_tool_count": 1,
            }
        },
    ])

    assert summary == {
        "total": 2,
        "with_ontology": 1,
        "with_tools": 2,
        "blocked_tools": 1,
        "failed_tools": 1,
    }
