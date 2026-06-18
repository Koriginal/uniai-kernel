from __future__ import annotations

import hashlib
import re
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology_assets import RuleSourceDocumentModel
from app.models.review import (
    NormClauseModel,
    PolicyArticleModel,
    PolicyDocumentModel,
    ReviewCheckModel,
    ReviewPackModel,
    ReviewRunModel,
)
from app.ontology.asset_service import ontology_asset_service
from app.ontology.domain_models import utc_now
from app.ontology.persistent_service import persistent_ontology_service
from app.review.models import (
    NormClausePatch,
    NormClauseRecord,
    PolicyArticleRecord,
    PolicyDocumentRecord,
    ReviewCheckPatch,
    ReviewCheckRecord,
    ReviewPackCreate,
    ReviewPackRecord,
    ReviewRunCreate,
    ReviewRunRecord,
    ReviewTargetExtractResult,
)
from app.services.application_service import ensure_application_access


class ReviewKnowledgeService:
    def extract_target_document(
        self,
        *,
        title: Optional[str],
        file_name: str,
        content_type: Optional[str],
        content: bytes,
    ) -> ReviewTargetExtractResult:
        if not content:
            raise HTTPException(status_code=400, detail="uploaded target file is empty")
        if len(content) > ontology_asset_service.MAX_SOURCE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="uploaded target file exceeds 8MB limit")
        text, warnings = ontology_asset_service._extract_uploaded_text(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        if not text.strip():
            raise HTTPException(status_code=400, detail={"message": "target document text is empty", "warnings": warnings})
        return ReviewTargetExtractResult(
            title=(title or file_name).strip(),
            file_name=file_name,
            content_type=content_type,
            text=text,
            metadata={
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "text_length": len(text),
            },
            warnings=warnings,
        )

    async def upload_policy_document(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        title: Optional[str],
        business_domain: Optional[str],
        document_type: str,
        version: str,
        file_name: str,
        content_type: Optional[str],
        content: bytes,
        actor_user_id: str,
        is_admin: bool,
    ) -> PolicyDocumentRecord:
        source_result = await ontology_asset_service.upload_source_document(
            db,
            space_id=space_id,
            title=title,
            source_type="review_manual" if document_type in {"contract_rule", "tender_rule"} else "policy_doc",
            file_name=file_name,
            content_type=content_type,
            content=content,
            actor_user_id=actor_user_id,
            is_admin=is_admin,
        )
        source = source_result.source
        model = await self._get_policy_document_by_source(db, space_id, source.id, version)
        if model:
            return self._policy_document_to_record(model)

        now = utc_now()
        model = PolicyDocumentModel(
            id=f"policy-doc-{uuid.uuid4().hex[:10]}",
            space_id=space_id,
            user_id=actor_user_id,
            source_document_id=source.id,
            title=(title or source.title).strip(),
            business_domain=(business_domain or "legal").strip() or None,
            document_type=document_type,
            version=version.strip() or "1",
            raw_text_hash=hashlib.sha256((source.raw_text or "").encode("utf-8")).hexdigest(),
            metadata_json={"source_upload_warnings": source_result.warnings, "file_name": source.file_name},
            status="draft",
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return self._policy_document_to_record(model)

    async def list_policy_documents(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[PolicyDocumentRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        result = await db.execute(
            select(PolicyDocumentModel)
            .where(PolicyDocumentModel.space_id == space_id)
            .order_by(desc(PolicyDocumentModel.created_at))
        )
        return [self._policy_document_to_record(item) for item in result.scalars().all()]

    async def segment_policy_document(
        self,
        db: AsyncSession,
        policy_document_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[PolicyArticleRecord]:
        document = await self._get_policy_document(db, policy_document_id)
        if not document:
            raise HTTPException(status_code=404, detail="policy document not found")
        await persistent_ontology_service._ensure_space_access(db, document.space_id, actor_user_id, is_admin, action="write")
        source = await self._get_source(db, document.source_document_id)
        raw_text = (source.raw_text if source else "") or ""
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="policy document raw_text is empty")

        result = await db.execute(select(PolicyArticleModel).where(PolicyArticleModel.policy_document_id == document.id))
        existing = list(result.scalars().all())
        if existing:
            return [self._policy_article_to_record(item) for item in existing]

        articles = self.segment_policy_text(raw_text)
        now = utc_now()
        models: List[PolicyArticleModel] = []
        for item in articles:
            model = PolicyArticleModel(
                id=f"policy-art-{uuid.uuid4().hex[:10]}",
                space_id=document.space_id,
                policy_document_id=document.id,
                article_no=item["article_no"],
                chapter_path=item["chapter_path"],
                paragraph_path=item["paragraph_path"],
                locator=item["locator"],
                text=item["text"],
                quote=item["quote"][:2000],
                text_hash=hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
                metadata_json=item["metadata"],
                created_at=now,
            )
            db.add(model)
            models.append(model)
        document.status = "segmented"
        document.updated_at = now
        await db.commit()
        for item in models:
            await db.refresh(item)
        return [self._policy_article_to_record(item) for item in models]

    async def list_articles(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        policy_document_id: Optional[str],
        actor_user_id: str,
        is_admin: bool,
    ) -> List[PolicyArticleRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [PolicyArticleModel.space_id == space_id]
        if policy_document_id:
            conds.append(PolicyArticleModel.policy_document_id == policy_document_id)
        result = await db.execute(select(PolicyArticleModel).where(and_(*conds)).order_by(PolicyArticleModel.created_at))
        return [self._policy_article_to_record(item) for item in result.scalars().all()]

    async def extract_norms(
        self,
        db: AsyncSession,
        policy_document_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> Dict[str, Any]:
        document = await self._get_policy_document(db, policy_document_id)
        if not document:
            raise HTTPException(status_code=404, detail="policy document not found")
        await persistent_ontology_service._ensure_space_access(db, document.space_id, actor_user_id, is_admin, action="write")
        articles_result = await db.execute(select(PolicyArticleModel).where(PolicyArticleModel.policy_document_id == document.id))
        articles = list(articles_result.scalars().all())
        if not articles:
            articles = [self._record_to_article_model(item) for item in await self.segment_policy_document(db, document.id, actor_user_id=actor_user_id, is_admin=is_admin)]

        created_norms: List[NormClauseModel] = []
        created_checks: List[ReviewCheckModel] = []
        warnings: List[str] = []
        for article in articles:
            candidate = self.infer_norm_candidate(article, document)
            if not candidate:
                warnings.append(f"{article.locator} 未抽取出规范语义")
                continue
            if await self._get_norm_by_code(db, document.space_id, candidate["norm_code"]):
                continue
            now = utc_now()
            norm = NormClauseModel(
                id=f"norm-{uuid.uuid4().hex[:10]}",
                space_id=document.space_id,
                policy_document_id=document.id,
                policy_article_id=article.id,
                norm_code=candidate["norm_code"],
                norm_type=candidate["norm_type"],
                subject=candidate["subject"],
                action=candidate["action"],
                object=candidate["object"],
                condition_text=candidate["condition_text"],
                exception_text=candidate["exception_text"],
                consequence_text=candidate["consequence_text"],
                evidence_required=candidate["evidence_required"],
                domain_tags=candidate["domain_tags"],
                scenario_tags=candidate["scenario_tags"],
                confidence=candidate["confidence"],
                metadata_json={"article_locator": article.locator, "article_quote": article.quote},
                status="draft",
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(norm)
            created_norms.append(norm)

            check_code = self._normalize_code(f"CHECK_{candidate['norm_code']}")
            if not await self._get_check_by_code(db, document.space_id, check_code):
                check = ReviewCheckModel(
                    id=f"review-check-{uuid.uuid4().hex[:10]}",
                    space_id=document.space_id,
                    check_code=check_code[:120],
                    name=candidate["check_name"],
                    scenario_type=candidate["scenario_tags"][0] if candidate["scenario_tags"] else "custom",
                    description=f"依据 {document.title} {article.locator} 生成的审查点，发布前需要人工确认。",
                    norm_clause_ids=[norm.id],
                    input_schema=candidate["input_schema"],
                    evidence_schema={"required_fields": candidate["evidence_required"]},
                    check_type="semantic",
                    severity=candidate["severity"],
                    fail_template=candidate["fail_template"],
                    pass_template="未发现与该审查点冲突的内容。",
                    metadata_json={"article_id": article.id, "article_locator": article.locator},
                    status="draft",
                    created_by=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(check)
                created_checks.append(check)
        document.status = "norms_extracted" if created_norms else document.status
        document.updated_at = utc_now()
        await db.commit()
        for item in [*created_norms, *created_checks]:
            await db.refresh(item)
        return {
            "norm_clauses": [self._norm_to_record(item) for item in created_norms],
            "review_checks": [self._check_to_record(item) for item in created_checks],
            "warnings": warnings,
        }

    async def list_norms(self, db: AsyncSession, *, space_id: str, status: Optional[str], actor_user_id: str, is_admin: bool) -> List[NormClauseRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [NormClauseModel.space_id == space_id]
        if status:
            conds.append(NormClauseModel.status == status)
        result = await db.execute(select(NormClauseModel).where(and_(*conds)).order_by(desc(NormClauseModel.created_at)))
        return [self._norm_to_record(item) for item in result.scalars().all()]

    async def update_norm(self, db: AsyncSession, norm_id: str, payload: NormClausePatch, *, actor_user_id: str, is_admin: bool) -> NormClauseRecord:
        norm = await db.get(NormClauseModel, norm_id)
        if not norm:
            raise HTTPException(status_code=404, detail="norm clause not found")
        await persistent_ontology_service._ensure_space_access(db, norm.space_id, actor_user_id, is_admin, action="write")
        if norm.status in {"released", "deprecated"}:
            raise HTTPException(status_code=400, detail="released/deprecated norm clauses cannot be edited")
        data = payload.model_dump(exclude_unset=True)
        for field in ["norm_type", "subject", "action", "object", "condition_text", "exception_text", "consequence_text", "confidence", "status", "review_note"]:
            if field in data:
                setattr(norm, field, data[field])
        for field, target in [("evidence_required", "evidence_required"), ("domain_tags", "domain_tags"), ("scenario_tags", "scenario_tags"), ("metadata", "metadata_json")]:
            if field in data:
                setattr(norm, target, deepcopy(data[field] or ([] if field != "metadata" else {})))
        if data.get("status") in {"approved", "rejected"}:
            norm.reviewed_by = actor_user_id
        norm.updated_at = utc_now()
        await db.commit()
        await db.refresh(norm)
        return self._norm_to_record(norm)

    async def list_checks(self, db: AsyncSession, *, space_id: str, status: Optional[str], actor_user_id: str, is_admin: bool) -> List[ReviewCheckRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [ReviewCheckModel.space_id == space_id]
        if status:
            conds.append(ReviewCheckModel.status == status)
        result = await db.execute(select(ReviewCheckModel).where(and_(*conds)).order_by(ReviewCheckModel.scenario_type, ReviewCheckModel.check_code))
        return [self._check_to_record(item) for item in result.scalars().all()]

    async def update_check(self, db: AsyncSession, check_id: str, payload: ReviewCheckPatch, *, actor_user_id: str, is_admin: bool) -> ReviewCheckRecord:
        check = await db.get(ReviewCheckModel, check_id)
        if not check:
            raise HTTPException(status_code=404, detail="review check not found")
        await persistent_ontology_service._ensure_space_access(db, check.space_id, actor_user_id, is_admin, action="write")
        if check.status in {"released", "deprecated"}:
            raise HTTPException(status_code=400, detail="released/deprecated review checks cannot be edited")
        data = payload.model_dump(exclude_unset=True)
        for field in ["name", "scenario_type", "description", "check_type", "severity", "fail_template", "pass_template", "status", "review_note"]:
            if field in data:
                setattr(check, field, data[field])
        for field, target in [("norm_clause_ids", "norm_clause_ids"), ("input_schema", "input_schema"), ("evidence_schema", "evidence_schema"), ("metadata", "metadata_json")]:
            if field in data:
                setattr(check, target, deepcopy(data[field] or ([] if field == "norm_clause_ids" else {})))
        if data.get("status") in {"approved", "rejected"}:
            check.reviewed_by = actor_user_id
        check.updated_at = utc_now()
        await db.commit()
        await db.refresh(check)
        return self._check_to_record(check)

    async def create_pack(self, db: AsyncSession, payload: ReviewPackCreate, *, actor_user_id: str, is_admin: bool) -> ReviewPackRecord:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        if await self._get_pack_by_name_version(db, payload.space_id, payload.name, payload.version):
            raise HTTPException(status_code=409, detail="review pack name/version already exists")
        norm_ids = payload.norm_clause_ids or await self._approved_norm_ids(db, payload.space_id, payload.policy_document_ids)
        check_ids = payload.review_check_ids or await self._approved_check_ids(db, payload.space_id, norm_ids, payload.scenario_type)
        if not norm_ids:
            raise HTTPException(status_code=400, detail="review pack requires approved norm clauses")
        if not check_ids:
            raise HTTPException(status_code=400, detail="review pack requires approved review checks")
        now = utc_now()
        model = ReviewPackModel(
            id=f"review-pack-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            name=payload.name.strip(),
            business_domain=(payload.business_domain or "").strip() or None,
            scenario_type=payload.scenario_type,
            version=payload.version.strip(),
            policy_document_ids=payload.policy_document_ids,
            norm_clause_ids=norm_ids,
            review_check_ids=check_ids,
            metadata_json=deepcopy(payload.metadata),
            status="draft",
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return self._pack_to_record(model)

    async def list_packs(self, db: AsyncSession, *, space_id: str, status: Optional[str], actor_user_id: str, is_admin: bool) -> List[ReviewPackRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [ReviewPackModel.space_id == space_id]
        if status:
            conds.append(ReviewPackModel.status == status)
        result = await db.execute(select(ReviewPackModel).where(and_(*conds)).order_by(desc(ReviewPackModel.created_at)))
        return [self._pack_to_record(item) for item in result.scalars().all()]

    async def release_pack(self, db: AsyncSession, pack_id: str, *, actor_user_id: str, is_admin: bool) -> ReviewPackRecord:
        pack = await db.get(ReviewPackModel, pack_id)
        if not pack:
            raise HTTPException(status_code=404, detail="review pack not found")
        await persistent_ontology_service._ensure_space_access(db, pack.space_id, actor_user_id, is_admin, action="governance")
        norms = await self._get_norms_by_ids(db, pack.norm_clause_ids or [])
        checks = await self._get_checks_by_ids(db, pack.review_check_ids or [])
        bad_norms = [item.norm_code for item in norms if item.status != "approved"]
        bad_checks = [item.check_code for item in checks if item.status != "approved"]
        if bad_norms or bad_checks:
            raise HTTPException(status_code=400, detail={"message": "only approved norms/checks can be released", "norms": bad_norms, "checks": bad_checks})
        now = utc_now()
        pack.status = "released"
        pack.released_by = actor_user_id
        pack.released_at = now
        pack.updated_at = now
        for item in norms:
            item.status = "released"
            item.updated_at = now
        for item in checks:
            item.status = "released"
            item.updated_at = now
        await db.commit()
        await db.refresh(pack)
        return self._pack_to_record(pack)

    async def run_review(self, db: AsyncSession, payload: ReviewRunCreate, *, actor_user_id: str, is_admin: bool) -> ReviewRunRecord:
        pack = await self._resolve_run_pack(db, payload, actor_user_id=actor_user_id, is_admin=is_admin)
        if pack.status != "released":
            raise HTTPException(status_code=400, detail="review runtime only accepts released review packs")
        checks = await self._get_checks_by_ids(db, pack.review_check_ids or [])
        norms = {item.id: item for item in await self._get_norms_by_ids(db, pack.norm_clause_ids or [])}
        articles = {item.id: item for item in await self._get_articles_by_ids(db, [norm.policy_article_id for norm in norms.values()])}
        findings, citations = self.evaluate_text(payload.target_text, checks, norms, articles)
        summary = {
            "total": len(findings),
            "failed": len([item for item in findings if item["status"] == "fail"]),
            "warnings": len([item for item in findings if item["status"] == "warning"]),
            "passed": len([item for item in findings if item["status"] == "pass"]),
            "review_pack": {"id": pack.id, "name": pack.name, "version": pack.version, "scenario_type": pack.scenario_type},
        }
        now = utc_now()
        model = ReviewRunModel(
            id=f"review-run-{uuid.uuid4().hex[:10]}",
            user_id=actor_user_id,
            application_id=payload.application_id,
            review_pack_id=pack.id,
            target_document_ids=payload.target_document_ids,
            target_snapshot={"title": payload.target_title, "text_hash": hashlib.sha256(payload.target_text.encode("utf-8")).hexdigest()},
            extracted_facts=self.extract_target_facts(payload.target_text),
            findings=findings,
            citations=citations,
            summary=summary,
            status="completed",
            created_at=now,
        )
        db.add(model)
        await db.commit()
        return self._run_to_record(model)

    async def get_run(self, db: AsyncSession, run_id: str, *, actor_user_id: str, is_admin: bool) -> ReviewRunRecord:
        model = await db.get(ReviewRunModel, run_id)
        if not model:
            raise HTTPException(status_code=404, detail="review run not found")
        if model.user_id != actor_user_id and not is_admin:
            raise HTTPException(status_code=403, detail="not allowed to access this review run")
        return self._run_to_record(model)

    def segment_policy_text(self, raw_text: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        chapter_path: List[str] = []
        current: Optional[Dict[str, Any]] = None
        for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
            text = raw_line.strip()
            if not text:
                continue
            chapter = re.match(r"^(第\s*[一二三四五六七八九十百千万0-9]+\s*章)\s*(.*)$", text)
            if chapter:
                chapter_path = [" ".join(part for part in chapter.groups() if part).strip()]
                continue
            marker = re.match(r"^(第\s*[一二三四五六七八九十百千万0-9.]+\s*条)\s*(.*)$", text)
            numbered = re.match(r"^([0-9]+[.、])\s*(.*)$", text)
            if marker or numbered:
                if current:
                    articles.append(current)
                article_no = marker.group(1) if marker else numbered.group(1)
                body = (marker.group(2) if marker else numbered.group(2)).strip() or text
                current = {
                    "article_no": article_no,
                    "chapter_path": list(chapter_path),
                    "paragraph_path": [f"line:{line_no}"],
                    "locator": article_no,
                    "text": body,
                    "quote": text,
                    "metadata": {"start_line": line_no},
                }
                continue
            if current:
                current["text"] = f"{current['text']} {text}".strip()
                current["quote"] = f"{current['quote']}\n{text}".strip()
            else:
                current = {
                    "article_no": f"line-{line_no}",
                    "chapter_path": list(chapter_path),
                    "paragraph_path": [f"line:{line_no}"],
                    "locator": f"第 {line_no} 行",
                    "text": text,
                    "quote": text,
                    "metadata": {"start_line": line_no},
                }
        if current:
            articles.append(current)
        return [item for item in articles if len(item["text"]) >= 4]

    def infer_norm_candidate(self, article: PolicyArticleModel, document: PolicyDocumentModel) -> Optional[Dict[str, Any]]:
        text = article.text.strip()
        if not re.search(r"(应当|必须|须|需要|不得|禁止|严禁|需|应|可以|评分|标准|资格|保证金|付款|违约|验收|审批|备案|材料|证明|资质)", text):
            return None
        norm_type = "obligation"
        if re.search(r"(不得|禁止|严禁|不予|不得要求|不得设置)", text):
            norm_type = "prohibition"
        elif re.search(r"(审批|报批|批准|备案)", text):
            norm_type = "approval_required"
        elif re.search(r"(材料|证明|凭证|票据|资质|资格|证书)", text):
            norm_type = "evidence_required"
        elif re.search(r"(评分|分值|评审标准|技术标准|商务标准)", text):
            norm_type = "scoring"
        elif re.search(r"(违约|赔偿|责任|追究)", text):
            norm_type = "liability"
        scenario = self._infer_scenario(document, text)
        field = self._infer_target_field(text, scenario)
        code = self._normalize_code(f"{scenario}_{norm_type}_{field}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6]}")
        severity = "critical" if norm_type == "prohibition" else ("high" if norm_type in {"approval_required", "liability"} else "medium")
        return {
            "norm_code": code[:120],
            "norm_type": norm_type,
            "subject": self._infer_subject(text, scenario),
            "action": self._infer_action(text),
            "object": field,
            "condition_text": text,
            "exception_text": self._extract_after(text, r"(但|除|例外)") if re.search(r"(但|除|例外)", text) else None,
            "consequence_text": self._extract_after(text, r"(否则|违者|不予|承担)") if re.search(r"(否则|违者|不予|承担)", text) else None,
            "evidence_required": self._infer_evidence_required(text, field),
            "domain_tags": [document.business_domain or "legal"],
            "scenario_tags": [scenario],
            "confidence": "high" if re.search(r"(应当|必须|不得|禁止|严禁|须)", text) else "medium",
            "check_name": self._build_check_name(text, field),
            "input_schema": {"target_field": field, "source_locator": article.locator},
            "severity": severity,
            "fail_template": f"目标文件未满足规则要求：{text[:180]}",
        }

    def evaluate_text(
        self,
        target_text: str,
        checks: Sequence[ReviewCheckModel],
        norms: Dict[str, NormClauseModel],
        articles: Dict[str, PolicyArticleModel],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        target = re.sub(r"\s+", " ", target_text)
        for check in checks:
            linked_norms = [norms[item] for item in (check.norm_clause_ids or []) if item in norms]
            check_citations = []
            for norm in linked_norms:
                article = articles.get(norm.policy_article_id)
                if article:
                    citation = {
                        "policy_article_id": article.id,
                        "locator": article.locator,
                        "quote": article.quote,
                        "norm_clause_id": norm.id,
                        "norm_code": norm.norm_code,
                    }
                    check_citations.append(citation)
                    citations.append(citation)
            keywords = self._keywords_for_check(check, linked_norms)
            matched = [word for word in keywords if word and word in target]
            status = "pass" if matched else ("fail" if check.severity in {"high", "critical"} else "warning")
            findings.append(
                {
                    "check_id": check.id,
                    "check_code": check.check_code,
                    "status": status,
                    "severity": check.severity,
                    "issue": check.pass_template if status == "pass" else (check.fail_template or check.description or check.name),
                    "target_evidence": {"matched_keywords": matched, "snippet": self._target_snippet(target, matched[0] if matched else None)},
                    "policy_citations": check_citations,
                    "suggestion": "请补充或修改目标文件，使其明确满足引用条款要求。" if status != "pass" else "无需处理。",
                }
            )
        return findings, self._dedupe_citations(citations)

    def extract_target_facts(self, text: str) -> Dict[str, Any]:
        return {
            "has_payment": bool(re.search(r"付款|支付|账期", text)),
            "has_liability": bool(re.search(r"违约|赔偿|责任", text)),
            "has_qualification": bool(re.search(r"资质|资格|证书", text)),
            "has_scoring": bool(re.search(r"评分|分值|评审标准", text)),
            "amounts": re.findall(r"\d+(?:\.\d+)?\s*(?:万元|元|%)", text)[:20],
        }

    async def _resolve_run_pack(self, db: AsyncSession, payload: ReviewRunCreate, *, actor_user_id: str, is_admin: bool) -> ReviewPackModel:
        if payload.review_pack_id:
            pack = await db.get(ReviewPackModel, payload.review_pack_id)
            if not pack:
                raise HTTPException(status_code=404, detail="review pack not found")
            await persistent_ontology_service._ensure_space_access(db, pack.space_id, actor_user_id, is_admin, action="read")
            return pack
        if not payload.application_id:
            raise HTTPException(status_code=400, detail="review_pack_id or application_id is required")
        application = await ensure_application_access(db, payload.application_id, user_id=actor_user_id, is_admin=is_admin)
        policy = dict(application.runtime_policy or {})
        review_pack_id = policy.get("review_pack_id")
        if not review_pack_id:
            raise HTTPException(status_code=400, detail="application runtime_policy.review_pack_id is required for review run")
        pack = await db.get(ReviewPackModel, review_pack_id)
        if not pack:
            raise HTTPException(status_code=404, detail="application review pack not found")
        return pack

    @staticmethod
    def _infer_scenario(document: PolicyDocumentModel, text: str) -> str:
        if document.document_type == "tender_rule" or re.search(r"招标|投标|评标|供应商|保证金|废标", text):
            return "tender_review"
        if document.document_type == "contract_rule" or re.search(r"合同|付款|违约|验收|甲方|乙方", text):
            return "contract_review"
        return "custom"

    @staticmethod
    def _infer_target_field(text: str, scenario: str) -> str:
        mapping = [
            ("payment_terms", r"付款|支付|账期|结算"),
            ("liability_terms", r"违约|赔偿|责任"),
            ("acceptance_terms", r"验收|交付"),
            ("qualification", r"资质|资格|证书|业绩"),
            ("bid_bond", r"保证金"),
            ("scoring_method", r"评分|分值|评审标准"),
            ("reject_bid_condition", r"废标|否决投标"),
            ("approval_materials", r"审批|报批|备案|材料|证明|凭证"),
        ]
        for field, pattern in mapping:
            if re.search(pattern, text):
                return field
        return "document_clause" if scenario == "contract_review" else "tender_clause"

    @staticmethod
    def _infer_subject(text: str, scenario: str) -> str:
        if "供应商" in text or "投标人" in text:
            return "投标人"
        if "采购人" in text or "招标人" in text:
            return "招标人"
        if "甲方" in text:
            return "甲方"
        if "乙方" in text:
            return "乙方"
        return "合同当事人" if scenario == "contract_review" else "审查对象"

    @staticmethod
    def _infer_action(text: str) -> str:
        for word in ["不得", "禁止", "严禁", "应当", "必须", "须", "需要", "可以"]:
            if word in text:
                return word
        return "审查"

    @staticmethod
    def _infer_evidence_required(text: str, field: str) -> List[str]:
        required = [field]
        for label, pattern in [("amount", r"金额|费用|保证金"), ("date_or_days", r"期限|天|日|时间"), ("certificate", r"证书|资质|资格"), ("approval_record", r"审批|报批|备案"), ("scoring_table", r"评分|分值")]:
            if re.search(pattern, text):
                required.append(label)
        return list(dict.fromkeys(required))

    @staticmethod
    def _build_check_name(text: str, field: str) -> str:
        compact = re.sub(r"\s+", "", text)
        return f"{field} 审查：{compact[:36]}"

    @staticmethod
    def _extract_after(text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text)
        return text[match.start():] if match else None

    @staticmethod
    def _normalize_code(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]+", "_", value.upper()).strip("_")

    @staticmethod
    def _keywords_for_check(check: ReviewCheckModel, linked_norms: Sequence[NormClauseModel]) -> List[str]:
        values = [check.name, check.description or "", check.fail_template or ""]
        values.extend([norm.object or "" for norm in linked_norms])
        mapping = {
            "payment_terms": ["付款", "支付", "账期", "结算"],
            "liability_terms": ["违约", "赔偿", "责任"],
            "acceptance_terms": ["验收", "交付"],
            "qualification": ["资质", "资格", "证书", "业绩"],
            "bid_bond": ["保证金"],
            "scoring_method": ["评分", "分值", "评审标准"],
            "reject_bid_condition": ["废标", "否决投标"],
            "approval_materials": ["审批", "备案", "材料", "证明"],
        }
        keywords: List[str] = []
        for value in values:
            for field, words in mapping.items():
                if field in value or any(word in value for word in words):
                    keywords.extend(words)
        return list(dict.fromkeys(keywords))

    @staticmethod
    def _target_snippet(text: str, keyword: Optional[str]) -> Optional[str]:
        if not keyword:
            return None
        idx = text.find(keyword)
        if idx < 0:
            return None
        return text[max(0, idx - 60): idx + 120]

    @staticmethod
    def _dedupe_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for item in citations:
            key = (item.get("policy_article_id"), item.get("norm_clause_id"))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    async def _get_policy_document(self, db: AsyncSession, policy_document_id: str) -> Optional[PolicyDocumentModel]:
        return await db.get(PolicyDocumentModel, policy_document_id)

    async def _get_policy_document_by_source(self, db: AsyncSession, space_id: str, source_document_id: str, version: str) -> Optional[PolicyDocumentModel]:
        result = await db.execute(
            select(PolicyDocumentModel).where(
                and_(
                    PolicyDocumentModel.space_id == space_id,
                    PolicyDocumentModel.source_document_id == source_document_id,
                    PolicyDocumentModel.version == version,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_source(self, db: AsyncSession, source_document_id: Optional[str]) -> Optional[RuleSourceDocumentModel]:
        if not source_document_id:
            return None
        return await db.get(RuleSourceDocumentModel, source_document_id)

    async def _get_norm_by_code(self, db: AsyncSession, space_id: str, norm_code: str) -> Optional[NormClauseModel]:
        result = await db.execute(select(NormClauseModel).where(and_(NormClauseModel.space_id == space_id, NormClauseModel.norm_code == norm_code)))
        return result.scalar_one_or_none()

    async def _get_check_by_code(self, db: AsyncSession, space_id: str, check_code: str) -> Optional[ReviewCheckModel]:
        result = await db.execute(select(ReviewCheckModel).where(and_(ReviewCheckModel.space_id == space_id, ReviewCheckModel.check_code == check_code)))
        return result.scalar_one_or_none()

    async def _get_pack_by_name_version(self, db: AsyncSession, space_id: str, name: str, version: str) -> Optional[ReviewPackModel]:
        result = await db.execute(select(ReviewPackModel).where(and_(ReviewPackModel.space_id == space_id, ReviewPackModel.name == name.strip(), ReviewPackModel.version == version.strip())))
        return result.scalar_one_or_none()

    async def _approved_norm_ids(self, db: AsyncSession, space_id: str, policy_document_ids: List[str]) -> List[str]:
        conds = [NormClauseModel.space_id == space_id, NormClauseModel.status == "approved"]
        if policy_document_ids:
            conds.append(NormClauseModel.policy_document_id.in_(policy_document_ids))
        result = await db.execute(select(NormClauseModel.id).where(and_(*conds)).order_by(NormClauseModel.norm_code))
        return list(result.scalars().all())

    async def _approved_check_ids(self, db: AsyncSession, space_id: str, norm_ids: List[str], scenario_type: str) -> List[str]:
        result = await db.execute(select(ReviewCheckModel).where(and_(ReviewCheckModel.space_id == space_id, ReviewCheckModel.status == "approved", ReviewCheckModel.scenario_type == scenario_type)).order_by(ReviewCheckModel.check_code))
        return [item.id for item in result.scalars().all() if set(item.norm_clause_ids or []).intersection(norm_ids)]

    async def _get_norms_by_ids(self, db: AsyncSession, ids: List[str]) -> List[NormClauseModel]:
        if not ids:
            return []
        result = await db.execute(select(NormClauseModel).where(NormClauseModel.id.in_(ids)))
        return list(result.scalars().all())

    async def _get_checks_by_ids(self, db: AsyncSession, ids: List[str]) -> List[ReviewCheckModel]:
        if not ids:
            return []
        result = await db.execute(select(ReviewCheckModel).where(ReviewCheckModel.id.in_(ids)).order_by(ReviewCheckModel.check_code))
        return list(result.scalars().all())

    async def _get_articles_by_ids(self, db: AsyncSession, ids: List[str]) -> List[PolicyArticleModel]:
        if not ids:
            return []
        result = await db.execute(select(PolicyArticleModel).where(PolicyArticleModel.id.in_(ids)))
        return list(result.scalars().all())

    @staticmethod
    def _record_to_article_model(record: PolicyArticleRecord) -> PolicyArticleModel:
        return PolicyArticleModel(**record.model_dump(exclude={"metadata"}), metadata_json=record.metadata)

    @staticmethod
    def _policy_document_to_record(model: PolicyDocumentModel) -> PolicyDocumentRecord:
        return PolicyDocumentRecord(
            id=model.id,
            space_id=model.space_id,
            user_id=model.user_id,
            source_document_id=model.source_document_id,
            title=model.title,
            business_domain=model.business_domain,
            document_type=model.document_type,
            version=model.version,
            raw_text_hash=model.raw_text_hash,
            metadata=model.metadata_json or {},
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _policy_article_to_record(model: PolicyArticleModel) -> PolicyArticleRecord:
        return PolicyArticleRecord(
            id=model.id,
            space_id=model.space_id,
            policy_document_id=model.policy_document_id,
            article_no=model.article_no,
            chapter_path=model.chapter_path or [],
            paragraph_path=model.paragraph_path or [],
            locator=model.locator,
            text=model.text,
            quote=model.quote,
            text_hash=model.text_hash,
            metadata=model.metadata_json or {},
            created_at=model.created_at,
        )

    @staticmethod
    def _norm_to_record(model: NormClauseModel) -> NormClauseRecord:
        return NormClauseRecord(
            id=model.id,
            space_id=model.space_id,
            policy_document_id=model.policy_document_id,
            policy_article_id=model.policy_article_id,
            norm_code=model.norm_code,
            norm_type=model.norm_type,
            subject=model.subject,
            action=model.action,
            object=model.object,
            condition_text=model.condition_text,
            exception_text=model.exception_text,
            consequence_text=model.consequence_text,
            evidence_required=model.evidence_required or [],
            domain_tags=model.domain_tags or [],
            scenario_tags=model.scenario_tags or [],
            confidence=model.confidence,
            metadata=model.metadata_json or {},
            status=model.status,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            review_note=model.review_note,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _check_to_record(model: ReviewCheckModel) -> ReviewCheckRecord:
        return ReviewCheckRecord(
            id=model.id,
            space_id=model.space_id,
            check_code=model.check_code,
            name=model.name,
            scenario_type=model.scenario_type,
            description=model.description,
            norm_clause_ids=model.norm_clause_ids or [],
            input_schema=model.input_schema or {},
            evidence_schema=model.evidence_schema or {},
            check_type=model.check_type,
            severity=model.severity,
            fail_template=model.fail_template,
            pass_template=model.pass_template,
            metadata=model.metadata_json or {},
            status=model.status,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            review_note=model.review_note,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _pack_to_record(model: ReviewPackModel) -> ReviewPackRecord:
        return ReviewPackRecord(
            id=model.id,
            space_id=model.space_id,
            name=model.name,
            business_domain=model.business_domain,
            scenario_type=model.scenario_type,
            version=model.version,
            policy_document_ids=model.policy_document_ids or [],
            norm_clause_ids=model.norm_clause_ids or [],
            review_check_ids=model.review_check_ids or [],
            metadata=model.metadata_json or {},
            status=model.status,
            created_by=model.created_by,
            released_by=model.released_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            released_at=model.released_at,
        )

    @staticmethod
    def _run_to_record(model: ReviewRunModel) -> ReviewRunRecord:
        return ReviewRunRecord(
            run_id=model.id,
            application_id=model.application_id,
            review_pack_id=model.review_pack_id,
            target_document_ids=model.target_document_ids or [],
            summary=model.summary or {},
            findings=model.findings or [],
            citations=model.citations or [],
            generated_at=model.created_at,
        )


review_knowledge_service = ReviewKnowledgeService()
