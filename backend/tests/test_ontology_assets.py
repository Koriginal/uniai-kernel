import pytest
from fastapi import HTTPException

from app.models.ontology_assets import OntologyTermModel, RuleEntryModel, RuleSourceDocumentModel
from app.ontology.asset_models import RuleSourceParseRequest, SchemaPackageCompileRequest, RulePackageCompileRequest
from app.ontology.asset_service import OntologyAssetService
from app.ontology.domain_models import PackageKind, utc_now


class _FakeDB:
    def __init__(self):
        self.commits = 0
        self.added = []

    def add(self, model):
        self.added.append(model)

    async def commit(self):
        self.commits += 1

    async def refresh(self, model):
        return None


@pytest.mark.asyncio
async def test_compile_rules_builds_package_from_approved_entries(monkeypatch):
    service = OntologyAssetService()
    db = _FakeDB()
    entry = RuleEntryModel(
        id="rule-entry-1",
        space_id="space-1",
        source_document_id="source-1",
        rule_code="CONTRACT_PAYMENT_TERM_GT_90D",
        name="付款周期超过 90 天",
        target_entity_type="Contract",
        conditions=[{"path": "entity.payment_term_days", "operator": "gt", "value": 90}],
        severity="high",
        action="flag",
        evidence_refs=[{"source_document_id": "source-1", "locator": "第 3.2 条"}],
        test_cases=[{"name": "命中样例", "graph": {}, "expected_hit": True}],
        tags=["contract"],
        status="approved",
        version="1",
        created_by="author-1",
    )

    async def fake_access(*args, **kwargs):
        return object()

    async def fake_select(*args, **kwargs):
        return [entry]

    captured = {}

    async def fake_upsert(**kwargs):
        captured.update(kwargs)

        class _Pkg:
            def model_dump(self):
                return {
                    "kind": PackageKind.rule,
                    "space_id": kwargs["space_id"],
                    "version": kwargs["version"],
                    "payload": kwargs["payload"],
                }

        return _Pkg()

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._ensure_space_access", fake_access)
    monkeypatch.setattr(service, "_select_rule_entries_for_compile", fake_select)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._upsert_package", fake_upsert)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._try_audit", fake_audit)

    result = await service.compile_rules(
        db,
        RulePackageCompileRequest(space_id="space-1", version="1.0.0", description="contract rules"),
        actor_user_id="compiler-1",
        is_admin=False,
    )

    assert result.rule_entry_ids == ["rule-entry-1"]
    assert entry.status == "packaged"
    assert captured["kind"] == PackageKind.rule
    assert captured["payload"]["rules"][0]["rule_id"] == "CONTRACT_PAYMENT_TERM_GT_90D"
    assert captured["payload"]["metadata"]["compiled_from_rule_entry_ids"] == ["rule-entry-1"]
    assert captured["payload"]["metadata"]["source_document_ids"] == ["source-1"]


def test_high_risk_rule_requires_test_cases_before_review():
    service = OntologyAssetService()

    with pytest.raises(HTTPException) as exc:
        service._validate_rule_payload(
            {
                "rule_code": "CONTRACT_PAYMENT_TERM_GT_90D",
                "conditions": [{"path": "entity.payment_term_days", "operator": "gt", "value": 90}],
                "evidence_refs": [{"source_document_id": "source-1", "locator": "第 3.2 条"}],
                "severity": "high",
                "test_cases": [],
            },
            require_approved_quality=True,
        )

    assert exc.value.status_code == 400
    assert "test_cases" in str(exc.value.detail)


def test_draft_rule_can_enter_review_queue_before_release_quality_gate():
    service = OntologyAssetService()

    service._validate_rule_payload(
        {
            "rule_code": "POLICY_TEXT_RULE",
            "conditions": [],
            "evidence_refs": [{"source_document_id": "source-1", "locator": "第 1 条"}],
            "severity": "critical",
            "test_cases": [],
        },
        require_approved_quality=False,
    )


def test_rule_quality_report_is_authoritative_for_approval_and_packaging():
    service = OntologyAssetService()
    entry = RuleEntryModel(
        id="rule-entry-quality",
        space_id="space-1",
        rule_code="CONTRACT_PAYMENT_TERM",
        name="付款规则",
        conditions=[],
        severity="high",
        action="flag",
        evidence_refs=[{"source_document_id": "source-1", "locator": "第三条"}],
        test_cases=[],
        tags=[],
        status="reviewing",
        version="1",
        created_by="author-1",
    )

    report = service._rule_quality_report(entry)

    assert report.can_submit_review is False
    assert report.can_approve is False
    assert report.can_package is False
    assert {issue.code for issue in report.blockers} == {
        "missing_conditions",
        "missing_high_risk_test_cases",
    }
    assert {issue.code for issue in report.warnings} == {"missing_target_entity_type"}


def test_low_risk_rule_without_tests_returns_warning_not_blocker():
    service = OntologyAssetService()
    entry = RuleEntryModel(
        id="rule-entry-low",
        space_id="space-1",
        rule_code="CONTRACT_NOTICE",
        name="提示规则",
        target_entity_type="Contract",
        conditions=[{"path": "entity.notice", "operator": "exists"}],
        severity="low",
        action="recommend",
        evidence_refs=[{"source_document_id": "source-1", "locator": "第四条"}],
        test_cases=[],
        tags=[],
        status="approved",
        version="1",
        created_by="author-1",
    )

    report = service._rule_quality_report(entry)

    assert report.blockers == []
    assert report.can_package is True
    assert [issue.code for issue in report.warnings] == ["missing_test_cases"]


def test_rule_code_and_tags_are_normalized():
    service = OntologyAssetService()

    assert service._normalize_rule_code(" contract payment term ") == "CONTRACT_PAYMENT_TERM"
    assert service._normalize_tags(["contract", " contract ", "", "risk"]) == ["contract", "risk"]


def test_extract_uploaded_text_supports_plain_text():
    service = OntologyAssetService()

    text, warnings = service._extract_uploaded_text(
        file_name="review.md",
        content_type="text/markdown",
        content="第 1 条 合同金额超过 100 万元，应标记高风险。".encode("utf-8"),
    )

    assert "合同金额超过 100 万元" in text
    assert warnings == []


def test_extract_uploaded_text_warns_for_pdf_without_parser():
    service = OntologyAssetService()

    text, warnings = service._extract_uploaded_text(
        file_name="policy.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7",
    )

    assert text == ""
    assert warnings
    assert "PDF text extraction is not enabled" in warnings[0]


def test_policy_document_clauses_are_recognized_as_rule_candidates():
    service = OntologyAssetService()
    source = RuleSourceDocumentModel(
        id="source-policy",
        space_id="space-1",
        user_id="author-1",
        title="因公临时出国经费管理办法",
        source_type="policy_doc",
        content_hash="hash-policy",
        raw_text="",
        metadata_json={},
        status="uploaded",
        created_at=utc_now(),
    )

    budget = service._infer_rule_candidate(source, {"locator": "第四条", "quote": "各地区各部门各单位因公组派临时出国团组应当加强预算硬约束，不得超预算或无预算安排出访团组。"})
    approval = service._infer_rule_candidate(source, {"locator": "第五条", "quote": "因公临时出国应当认真履行因公临时出国计划报批制度，严格控制团组人数、国家数和在外停留天数。"})
    reimbursement = service._infer_rule_candidate(source, {"locator": "第十六条", "quote": "出国人员回国报销费用时，须凭有效票据填报国外费用报销单。"})

    assert budget is not None
    assert budget["target_entity_type"] == "AbroadExpenseClaim"
    assert budget["action"] == "block"
    assert budget["severity"] == "critical"
    assert approval is not None
    assert approval["target_entity_type"] == "TemporaryAbroadTrip"
    assert reimbursement is not None
    assert reimbursement["target_entity_type"] == "AbroadExpenseClaim"


@pytest.mark.asyncio
async def test_parse_source_document_creates_rule_entries_with_quote(monkeypatch):
    service = OntologyAssetService()
    db = _FakeDB()
    source = RuleSourceDocumentModel(
        id="source-1",
        space_id="space-1",
        user_id="author-1",
        title="合同审核手册",
        source_type="review_manual",
        content_hash="hash-1",
        raw_text="第 3.2 条 付款周期超过 90 天，应标记为高风险并要求业务负责人确认。",
        metadata_json={},
        status="uploaded",
        created_at=utc_now(),
    )

    async def fake_get_source(*args, **kwargs):
        return source

    async def fake_access(*args, **kwargs):
        return object()

    async def fake_get_rule_by_code(*args, **kwargs):
        return None

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_get_source", fake_get_source)
    monkeypatch.setattr(service, "_get_rule_by_code", fake_get_rule_by_code)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._ensure_space_access", fake_access)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._try_audit", fake_audit)

    result = await service.parse_source_document(
        db,
        "source-1",
        RuleSourceParseRequest(),
        actor_user_id="author-1",
        is_admin=False,
    )

    assert source.status == "parsed"
    assert len(result.rule_entries) == 1
    rule = result.rule_entries[0]
    assert rule.source_document_id == "source-1"
    assert rule.target_entity_type == "Contract"
    assert rule.conditions == [{"path": "entity.payment_term_days", "operator": "gt", "value": 90}]
    assert rule.evidence_refs[0]["locator"] == "第 3.2 条"
    assert "付款周期超过 90 天" in rule.evidence_refs[0]["quote"]


@pytest.mark.asyncio
async def test_reparse_keeps_source_parsed_when_rules_already_exist(monkeypatch):
    service = OntologyAssetService()
    db = _FakeDB()
    source = RuleSourceDocumentModel(
        id="source-1",
        space_id="space-1",
        user_id="author-1",
        title="合同审核手册",
        source_type="review_manual",
        content_hash="hash-1",
        raw_text="第 3.2 条 付款周期超过 90 天，应标记为高风险并要求业务负责人确认。",
        metadata_json={},
        status="parsed",
        created_at=utc_now(),
    )

    async def fake_get_source(*args, **kwargs):
        return source

    async def fake_access(*args, **kwargs):
        return object()

    async def fake_get_rule_by_code(*args, **kwargs):
        return object()

    async def fake_source_has_rules(*args, **kwargs):
        return True

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_get_source", fake_get_source)
    monkeypatch.setattr(service, "_get_rule_by_code", fake_get_rule_by_code)
    monkeypatch.setattr(service, "_source_has_rules", fake_source_has_rules)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._ensure_space_access", fake_access)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._try_audit", fake_audit)

    result = await service.parse_source_document(
        db,
        "source-1",
        RuleSourceParseRequest(),
        actor_user_id="author-1",
        is_admin=False,
    )

    assert source.status == "parsed"
    assert result.rule_entries == []
    assert any("已存在" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_compile_schema_builds_package_from_approved_terms(monkeypatch):
    service = OntologyAssetService()
    db = _FakeDB()
    terms = [
        OntologyTermModel(
            id="term-entity-contract",
            space_id="space-1",
            term_code="ENTITY_CONTRACT",
            name="Contract",
            kind="entity",
            description="合同主体",
            evidence_refs=[{"source_document_id": "source-1", "locator": "术语表"}],
            status="approved",
            version="1",
            created_by="author-1",
        ),
        OntologyTermModel(
            id="term-attr-amount",
            space_id="space-1",
            term_code="ATTR_CONTRACT_AMOUNT",
            name="amount",
            kind="attribute",
            description="合同金额",
            entity_type="Contract",
            data_type="number",
            required=True,
            evidence_refs=[{"source_document_id": "source-1", "locator": "字段表"}],
            status="approved",
            version="1",
            created_by="author-1",
        ),
        OntologyTermModel(
            id="term-entity-party",
            space_id="space-1",
            term_code="ENTITY_PARTY",
            name="Party",
            kind="entity",
            description="合同相对方",
            evidence_refs=[{"source_document_id": "source-1", "locator": "术语表"}],
            status="approved",
            version="1",
            created_by="author-1",
        ),
        OntologyTermModel(
            id="term-rel-party",
            space_id="space-1",
            term_code="REL_CONTRACT_PARTY",
            name="counterparty",
            kind="relation",
            description="合同相对方关系",
            entity_type="Contract",
            relation_target_type="Party",
            relation_cardinality="many",
            evidence_refs=[{"source_document_id": "source-1", "locator": "关系表"}],
            status="approved",
            version="1",
            created_by="author-1",
        ),
    ]

    async def fake_access(*args, **kwargs):
        return object()

    async def fake_select(*args, **kwargs):
        return terms

    captured = {}

    async def fake_upsert(**kwargs):
        captured.update(kwargs)

        class _Pkg:
            def model_dump(self):
                return {
                    "kind": PackageKind.schema,
                    "space_id": kwargs["space_id"],
                    "version": kwargs["version"],
                    "payload": kwargs["payload"],
                }

        return _Pkg()

    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._ensure_space_access", fake_access)
    monkeypatch.setattr(service, "_select_terms_for_compile", fake_select)
    monkeypatch.setattr("app.ontology.asset_service.persistent_ontology_service._upsert_package", fake_upsert)

    result = await service.compile_schema(
        db,
        SchemaPackageCompileRequest(space_id="space-1", version="1.0.0", description="contract schema"),
        actor_user_id="compiler-1",
        is_admin=False,
    )

    assert result.term_ids == [term.id for term in terms]
    assert all(term.status == "packaged" for term in terms)
    assert captured["kind"] == PackageKind.schema
    entity_map = {item["name"]: item for item in captured["payload"]["entity_types"]}
    assert entity_map["Contract"]["attributes"]["amount"]["data_type"] == "number"
    assert entity_map["Contract"]["relations"][0]["target_type"] == "Party"
    assert captured["payload"]["metadata"]["compiled_from_term_ids"] == [term.id for term in terms]


def test_attribute_term_requires_entity_and_data_type():
    service = OntologyAssetService()

    with pytest.raises(HTTPException) as exc:
        service._validate_term_payload(
            {
                "term_code": "ATTR_AMOUNT",
                "kind": "attribute",
                "description": "合同金额",
                "entity_type": "Contract",
                "data_type": None,
                "evidence_refs": [{"locator": "字段表"}],
            },
            require_approved_quality=True,
        )

    assert exc.value.status_code == 400
    assert "entity_type and data_type" in str(exc.value.detail)
