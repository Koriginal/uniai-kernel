import pytest
from fastapi import HTTPException

from app.models.review import NormClauseModel, PolicyArticleModel, PolicyDocumentModel, ReviewCheckModel, ReviewPackModel
from app.review.models import NormClausePatch
from app.review.service import ReviewKnowledgeService
from app.ontology.domain_models import utc_now


class _FakeDB:
    def __init__(self, by_id=None):
        self.by_id = by_id or {}
        self.added = []
        self.commits = 0

    def add(self, model):
        self.added.append(model)

    async def commit(self):
        self.commits += 1

    async def refresh(self, model):
        return None

    async def get(self, model_cls, item_id):
        return self.by_id.get(item_id)


def test_segment_policy_text_keeps_chapter_and_article_locator():
    service = ReviewKnowledgeService()

    articles = service.segment_policy_text(
        "\n".join(
            [
                "第一章 总则",
                "第一条 合同付款周期不得超过90日。",
                "第二条 招标文件应当明确评分标准和废标条件。",
            ]
        )
    )

    assert len(articles) == 2
    assert articles[0]["locator"] == "第一条"
    assert articles[0]["chapter_path"] == ["第一章 总则"]
    assert "付款周期不得超过90日" in articles[0]["text"]


def test_infer_norm_candidate_for_contract_and_tender_rules():
    service = ReviewKnowledgeService()
    contract_doc = PolicyDocumentModel(
        id="policy-doc-1",
        space_id="space-1",
        user_id="user-1",
        title="合同评审规则",
        business_domain="legal",
        document_type="contract_rule",
        version="1",
        raw_text_hash="hash",
        status="segmented",
    )
    tender_doc = PolicyDocumentModel(
        id="policy-doc-2",
        space_id="space-1",
        user_id="user-1",
        title="招标文件评审规则",
        business_domain="procurement",
        document_type="tender_rule",
        version="1",
        raw_text_hash="hash",
        status="segmented",
    )
    article = PolicyArticleModel(
        id="article-1",
        space_id="space-1",
        policy_document_id="policy-doc-1",
        article_no="第一条",
        chapter_path=[],
        paragraph_path=["line:1"],
        locator="第一条",
        text="合同付款周期不得超过90日，违约责任必须明确。",
        quote="第一条 合同付款周期不得超过90日，违约责任必须明确。",
        text_hash="hash",
        created_at=utc_now(),
    )
    tender_article = PolicyArticleModel(
        id="article-2",
        space_id="space-1",
        policy_document_id="policy-doc-2",
        article_no="第二条",
        chapter_path=[],
        paragraph_path=["line:2"],
        locator="第二条",
        text="招标文件应当明确供应商资格、评分标准和废标条件。",
        quote="第二条 招标文件应当明确供应商资格、评分标准和废标条件。",
        text_hash="hash",
        created_at=utc_now(),
    )

    contract_candidate = service.infer_norm_candidate(article, contract_doc)
    tender_candidate = service.infer_norm_candidate(tender_article, tender_doc)

    assert contract_candidate["norm_type"] == "prohibition"
    assert contract_candidate["scenario_tags"] == ["contract_review"]
    assert contract_candidate["object"] == "payment_terms"
    assert tender_candidate["scenario_tags"] == ["tender_review"]
    assert tender_candidate["object"] in {"qualification", "scoring_method"}


@pytest.mark.asyncio
async def test_release_pack_rejects_unapproved_assets(monkeypatch):
    service = ReviewKnowledgeService()
    pack = ReviewPackModel(
        id="pack-1",
        space_id="space-1",
        name="合同审查包",
        scenario_type="contract_review",
        version="1.0.0",
        norm_clause_ids=["norm-1"],
        review_check_ids=["check-1"],
        status="draft",
        created_by="user-1",
    )
    norm = NormClauseModel(
        id="norm-1",
        space_id="space-1",
        policy_document_id="policy-doc-1",
        policy_article_id="article-1",
        norm_code="NORM_1",
        norm_type="obligation",
        status="draft",
        confidence="high",
        created_by="user-1",
    )
    check = ReviewCheckModel(
        id="check-1",
        space_id="space-1",
        check_code="CHECK_1",
        name="付款条款审查",
        scenario_type="contract_review",
        norm_clause_ids=["norm-1"],
        check_type="semantic",
        severity="high",
        status="approved",
        created_by="user-1",
    )
    db = _FakeDB({"pack-1": pack})

    async def fake_access(*args, **kwargs):
        return object()

    async def fake_norms(*args, **kwargs):
        return [norm]

    async def fake_checks(*args, **kwargs):
        return [check]

    monkeypatch.setattr("app.review.service.persistent_ontology_service._ensure_space_access", fake_access)
    monkeypatch.setattr(service, "_get_norms_by_ids", fake_norms)
    monkeypatch.setattr(service, "_get_checks_by_ids", fake_checks)

    with pytest.raises(HTTPException) as exc:
        await service.release_pack(db, "pack-1", actor_user_id="reviewer-1", is_admin=True)

    assert exc.value.status_code == 400
    assert "only approved" in str(exc.value.detail)


def test_review_runtime_returns_findings_with_policy_citations():
    service = ReviewKnowledgeService()
    article = PolicyArticleModel(
        id="article-1",
        space_id="space-1",
        policy_document_id="policy-doc-1",
        article_no="第一条",
        chapter_path=[],
        paragraph_path=["line:1"],
        locator="第一条",
        text="合同应当明确违约责任。",
        quote="第一条 合同应当明确违约责任。",
        text_hash="hash",
        created_at=utc_now(),
    )
    norm = NormClauseModel(
        id="norm-1",
        space_id="space-1",
        policy_document_id="policy-doc-1",
        policy_article_id="article-1",
        norm_code="NORM_LIABILITY",
        norm_type="obligation",
        object="liability_terms",
        status="released",
        confidence="high",
        created_by="user-1",
    )
    check = ReviewCheckModel(
        id="check-1",
        space_id="space-1",
        check_code="CHECK_LIABILITY",
        name="违约责任审查",
        scenario_type="contract_review",
        norm_clause_ids=["norm-1"],
        check_type="semantic",
        severity="high",
        fail_template="合同未明确违约责任。",
        pass_template="合同已包含违约责任。",
        status="released",
        created_by="user-1",
    )

    findings, citations = service.evaluate_text("本合同约定付款方式，但未写赔偿责任。", [check], {"norm-1": norm}, {"article-1": article})

    assert findings[0]["status"] == "pass"
    assert findings[0]["policy_citations"][0]["locator"] == "第一条"
    assert citations[0]["quote"] == "第一条 合同应当明确违约责任。"


def test_extract_target_document_returns_text_and_metadata():
    service = ReviewKnowledgeService()

    result = service.extract_target_document(
        title="待审合同",
        file_name="contract.txt",
        content_type="text/plain",
        content="合同约定付款方式和违约责任。".encode("utf-8"),
    )

    assert result.title == "待审合同"
    assert "违约责任" in result.text
    assert result.metadata["text_length"] == len(result.text)
    assert result.metadata["sha256"]


def test_extract_target_document_rejects_empty_file():
    service = ReviewKnowledgeService()

    with pytest.raises(HTTPException) as exc:
        service.extract_target_document(
            title=None,
            file_name="empty.txt",
            content_type="text/plain",
            content=b"",
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_released_norm_clause_cannot_be_edited(monkeypatch):
    service = ReviewKnowledgeService()
    norm = NormClauseModel(
        id="norm-released",
        space_id="space-1",
        policy_document_id="policy-doc-1",
        policy_article_id="article-1",
        norm_code="NORM_RELEASED",
        norm_type="obligation",
        status="released",
        confidence="high",
        created_by="user-1",
    )
    db = _FakeDB({"norm-released": norm})

    async def fake_access(*args, **kwargs):
        return object()

    monkeypatch.setattr("app.review.service.persistent_ontology_service._ensure_space_access", fake_access)

    with pytest.raises(HTTPException) as exc:
        await service.update_norm(
            db,
            "norm-released",
            NormClausePatch(condition_text="尝试修改发布规则"),
            actor_user_id="user-1",
            is_admin=True,
        )

    assert exc.value.status_code == 400
    assert "cannot be edited" in str(exc.value.detail)
