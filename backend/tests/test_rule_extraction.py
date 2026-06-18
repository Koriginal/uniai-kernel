from fastapi import HTTPException
import pytest

from app.rule_extraction.models import RuleExtractionRequest
from app.rule_extraction.service import RuleExtractionService


def test_rule_extraction_segments_chinese_policy_and_builds_candidates():
    service = RuleExtractionService()

    result = service.extract_from_text(
        RuleExtractionRequest(
            title="合同审查规则",
            source_type="contract_rule",
            text="\n".join(
                [
                    "第一章 总则",
                    "第一条 合同付款周期不得超过90日。",
                    "第二条 合同必须明确违约责任。",
                ]
            ),
        )
    )

    assert result.clause_count == 2
    assert result.rule_count == 2
    assert result.rules[0].rule_code.startswith("CONTRACT_RULE_PAYMENT_TERM_DAYS")
    assert result.rules[0].conditions[0]["path"] == "entity.payment_term_days"
    assert result.rules[0].evidence_refs[0]["locator"] == "第一条"


def test_rule_extraction_upload_supports_plain_text():
    service = RuleExtractionService()

    result = service.extract_from_upload(
        title="招标规则",
        source_type="tender_rule",
        max_rules=10,
        file_name="tender.md",
        content_type="text/markdown",
        content="第一条 招标文件应当明确供应商资质和评分标准。".encode("utf-8"),
    )

    assert result.file_name == "tender.md"
    assert result.rule_count == 1
    assert result.rules[0].target_entity_type == "TenderDocument"
    assert result.upload_metadata["sha256"]


def test_rule_extraction_rejects_empty_text():
    service = RuleExtractionService()

    with pytest.raises(HTTPException) as exc:
        service.extract_from_text(RuleExtractionRequest(text="   "))

    assert exc.value.status_code == 400
