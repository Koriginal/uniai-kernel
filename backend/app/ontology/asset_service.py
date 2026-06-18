from __future__ import annotations

import hashlib
import re
import uuid
import zipfile
from copy import deepcopy
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology_assets import OntologyTermModel, RuleEntryModel, RuleSourceDocumentModel
from app.ontology.asset_models import (
    OntologyTermCreate,
    OntologyTermKind,
    OntologyTermRecord,
    OntologyTermUpdate,
    RuleEntryCreate,
    RuleBatchSubmitResult,
    RuleEntryRecord,
    RuleEntryReviewRequest,
    RuleEntryStatus,
    RuleEntryUpdate,
    RuleQualityIssue,
    RuleQualityReport,
    RulePackageCompileRequest,
    RulePackageCompileResult,
    RuleSourceParseRequest,
    RuleSourceParseResult,
    RuleSourceDocumentCreate,
    RuleSourceDocumentRecord,
    RuleSourceDocumentUpdate,
    RuleSourceUploadResult,
    SchemaPackageCompileRequest,
    SchemaPackageCompileResult,
)
from app.ontology.domain_models import AttributeDef, EntityTypeDef, PackageKind, RelationDef, RuleDef, RulePackageCreate, SchemaPackageCreate, utc_now
from app.ontology.persistent_service import persistent_ontology_service


class OntologyAssetService:
    MAX_SOURCE_UPLOAD_BYTES = 8 * 1024 * 1024

    async def create_source_document(
        self,
        db: AsyncSession,
        payload: RuleSourceDocumentCreate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleSourceDocumentRecord:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        content_hash = self._hash_source(payload)
        existed = await self._get_source_by_hash(db, payload.space_id, content_hash)
        if existed:
            return self._source_to_record(existed)

        now = utc_now()
        model = RuleSourceDocumentModel(
            id=f"rule-src-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            user_id=actor_user_id,
            title=payload.title.strip(),
            source_type=payload.source_type.value,
            file_name=(payload.file_name or "").strip() or None,
            content_type=(payload.content_type or "").strip() or None,
            content_hash=content_hash,
            raw_text=payload.raw_text,
            metadata_json=deepcopy(payload.metadata or {}),
            status="uploaded",
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        await persistent_ontology_service._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.asset.source.create",
            output_result=model.id,
        )
        return self._source_to_record(model)

    async def upload_source_document(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        title: Optional[str],
        source_type: str,
        file_name: str,
        content_type: Optional[str],
        content: bytes,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleSourceUploadResult:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="write")
        if not content:
            raise HTTPException(status_code=400, detail="uploaded file is empty")
        if len(content) > self.MAX_SOURCE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="uploaded file exceeds 8MB limit")
        raw_text, warnings = self._extract_uploaded_text(file_name=file_name, content_type=content_type, content=content)
        payload = RuleSourceDocumentCreate(
            space_id=space_id,
            title=(title or file_name).strip(),
            source_type=source_type,
            file_name=file_name,
            content_type=content_type or "application/octet-stream",
            raw_text=raw_text,
            metadata={
                "upload": {
                    "file_name": file_name,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "text_extracted": bool(raw_text),
                    "warnings": warnings,
                }
            },
        )
        source = await self.create_source_document(db, payload, actor_user_id=actor_user_id, is_admin=is_admin)
        return RuleSourceUploadResult(source=source, warnings=warnings)

    async def list_source_documents(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[RuleSourceDocumentRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        result = await db.execute(
            select(RuleSourceDocumentModel)
            .where(RuleSourceDocumentModel.space_id == space_id)
            .order_by(desc(RuleSourceDocumentModel.created_at))
        )
        return [self._source_to_record(row) for row in result.scalars().all()]

    async def get_source_document(
        self,
        db: AsyncSession,
        source_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleSourceDocumentRecord:
        model = await self._get_source(db, source_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule source document not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="read")
        return self._source_to_record(model)

    async def update_source_document(
        self,
        db: AsyncSession,
        source_id: str,
        payload: RuleSourceDocumentUpdate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleSourceDocumentRecord:
        model = await self._get_source(db, source_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule source document not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="write")
        if payload.title is not None:
            model.title = payload.title.strip()
        if payload.status is not None:
            model.status = payload.status.value
        if payload.metadata is not None:
            model.metadata_json = deepcopy(payload.metadata)
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._source_to_record(model)

    async def parse_source_document(
        self,
        db: AsyncSession,
        source_id: str,
        payload: RuleSourceParseRequest,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleSourceParseResult:
        source = await self._get_source(db, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="rule source document not found")
        await persistent_ontology_service._ensure_space_access(db, source.space_id, actor_user_id, is_admin, action="write")
        raw_text = (source.raw_text or "").strip()
        if not raw_text:
            source.status = "parse_failed"
            source.metadata_json = {**(source.metadata_json or {}), "parse_error": "raw_text is empty"}
            source.updated_at = utc_now()
            await db.commit()
            raise HTTPException(status_code=400, detail="source document raw_text is empty")

        from app.rule_extraction.models import RuleExtractionRequest
        from app.rule_extraction.service import rule_extraction_service

        extraction = rule_extraction_service.extract_from_text(
            RuleExtractionRequest(
                title=source.title,
                source_type=source.source_type,
                text=raw_text,
                max_rules=payload.max_rules,
            )
        )
        created: List[RuleEntryModel] = []
        warnings: List[str] = list(extraction.warnings)
        for candidate in extraction.rules:
            rule_code = candidate.rule_code
            if await self._get_rule_by_code(db, source.space_id, rule_code):
                if not payload.overwrite_existing:
                    warnings.append(f"{rule_code} 已存在，已跳过")
                    continue
                rule_code = f"{rule_code}_{hashlib.sha1(candidate.evidence_refs[0].get('quote', rule_code).encode('utf-8')).hexdigest()[:6].upper()}"
            evidence_refs = [
                {
                    **ref,
                    "source_document_id": source.id,
                }
                for ref in candidate.evidence_refs
            ]
            now = utc_now()
            model = RuleEntryModel(
                id=f"rule-entry-{uuid.uuid4().hex[:10]}",
                space_id=source.space_id,
                source_document_id=source.id,
                rule_code=rule_code,
                name=candidate.name,
                description=candidate.description,
                target_entity_type=candidate.target_entity_type,
                conditions=candidate.conditions,
                severity=candidate.severity,
                action=candidate.action,
                evidence_refs=evidence_refs,
                test_cases=[],
                tags=candidate.tags,
                status=RuleEntryStatus.draft.value,
                version="1",
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(model)
            created.append(model)

        has_existing_rules = bool(created) or await self._source_has_rules(db, source.id)
        source.status = "parsed" if has_existing_rules else "parse_failed"
        source.metadata_json = {
            **(source.metadata_json or {}),
            "last_parse": {
                "parsed_at": utc_now().isoformat(),
                "created_rule_count": len(created),
                "warning_count": len(warnings),
            },
        }
        source.updated_at = utc_now()
        await db.commit()
        for item in created:
            await db.refresh(item)
        await db.refresh(source)
        await persistent_ontology_service._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.asset.source.parse",
            output_result=f"{source.id}:{len(created)}",
        )
        return RuleSourceParseResult(
            source=self._source_to_record(source),
            rule_entries=[self._rule_to_record(item) for item in created],
            warnings=warnings,
        )

    async def create_rule_entry(
        self,
        db: AsyncSession,
        payload: RuleEntryCreate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        await self._ensure_source_in_space(db, payload.space_id, payload.source_document_id)
        existed = await self._get_rule_by_code(db, payload.space_id, payload.rule_code)
        if existed:
            raise HTTPException(status_code=409, detail="rule_code already exists in this ontology space")
        self._validate_rule_payload(payload.model_dump(), require_approved_quality=False)
        now = utc_now()
        model = RuleEntryModel(
            id=f"rule-entry-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            source_document_id=payload.source_document_id,
            rule_code=self._normalize_rule_code(payload.rule_code),
            name=payload.name.strip(),
            description=(payload.description or "").strip() or None,
            target_entity_type=(payload.target_entity_type or "").strip() or None,
            conditions=[item.model_dump() for item in payload.conditions],
            severity=payload.severity,
            action=payload.action,
            evidence_refs=[item.model_dump() for item in payload.evidence_refs],
            test_cases=[item.model_dump() for item in payload.test_cases],
            tags=self._normalize_tags(payload.tags),
            status=RuleEntryStatus.draft.value,
            version=payload.version.strip() or "1",
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        await persistent_ontology_service._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.asset.rule.create",
            output_result=model.id,
        )
        return self._rule_to_record(model)

    async def list_rule_entries(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        status: Optional[RuleEntryStatus],
        actor_user_id: str,
        is_admin: bool,
    ) -> List[RuleEntryRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [RuleEntryModel.space_id == space_id]
        if status:
            conds.append(RuleEntryModel.status == status.value)
        result = await db.execute(
            select(RuleEntryModel)
            .where(and_(*conds))
            .order_by(desc(RuleEntryModel.updated_at), desc(RuleEntryModel.created_at))
        )
        return [self._rule_to_record(row) for row in result.scalars().all()]

    async def get_rule_entry(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="read")
        return self._rule_to_record(model)

    async def get_rule_quality(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleQualityReport:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="read")
        return self._rule_quality_report(model)

    async def list_rule_quality(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[RuleQualityReport]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        result = await db.execute(
            select(RuleEntryModel)
            .where(RuleEntryModel.space_id == space_id)
            .order_by(desc(RuleEntryModel.updated_at), desc(RuleEntryModel.created_at))
        )
        return [self._rule_quality_report(row) for row in result.scalars().all()]

    async def update_rule_entry(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        payload: RuleEntryUpdate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="write")
        if model.status in {RuleEntryStatus.packaged.value, RuleEntryStatus.released.value, RuleEntryStatus.deprecated.value}:
            raise HTTPException(status_code=400, detail="packaged/released/deprecated rule entries cannot be edited")
        data = payload.model_dump(exclude_unset=True)
        if "source_document_id" in data:
            await self._ensure_source_in_space(db, model.space_id, data["source_document_id"])
            model.source_document_id = data["source_document_id"]
        for field in ["name", "description", "target_entity_type", "severity", "action", "version"]:
            if field in data:
                value = data[field]
                setattr(model, field, value.strip() if isinstance(value, str) else value)
        if "conditions" in data:
            model.conditions = [item.model_dump() for item in payload.conditions or []]
        if "evidence_refs" in data:
            model.evidence_refs = [item.model_dump() for item in payload.evidence_refs or []]
        if "test_cases" in data:
            model.test_cases = [item.model_dump() for item in payload.test_cases or []]
        if "tags" in data:
            model.tags = self._normalize_tags(payload.tags or [])
        if model.status in {RuleEntryStatus.reviewing.value, RuleEntryStatus.approved.value, RuleEntryStatus.rejected.value}:
            model.status = RuleEntryStatus.draft.value
            model.reviewed_by = None
            model.review_note = None
        self._validate_rule_payload(self._rule_payload(model), require_approved_quality=False)
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._rule_to_record(model)

    async def submit_rule_entry_review(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="approve_request")
        if model.status not in {RuleEntryStatus.draft.value, RuleEntryStatus.rejected.value}:
            raise HTTPException(status_code=400, detail="only draft/rejected rule entries can be submitted")
        self._validate_rule_payload(self._rule_payload(model), require_approved_quality=False)
        model.status = RuleEntryStatus.reviewing.value
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._rule_to_record(model)

    async def batch_submit_rule_entry_review(
        self,
        db: AsyncSession,
        rule_entry_ids: List[str],
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleBatchSubmitResult:
        unique_ids = list(dict.fromkeys(rule_entry_ids))
        result = await db.execute(select(RuleEntryModel).where(RuleEntryModel.id.in_(unique_ids)))
        models = {row.id: row for row in result.scalars().all()}
        submitted_ids: List[str] = []
        skipped: Dict[str, str] = {}
        now = utc_now()
        checked_spaces: set[str] = set()
        for rule_entry_id in unique_ids:
            model = models.get(rule_entry_id)
            if not model:
                skipped[rule_entry_id] = "rule entry not found"
                continue
            if model.space_id not in checked_spaces:
                await persistent_ontology_service._ensure_space_access(
                    db,
                    model.space_id,
                    actor_user_id,
                    is_admin,
                    action="approve_request",
                )
                checked_spaces.add(model.space_id)
            report = self._rule_quality_report(model)
            if not report.can_submit_review:
                skipped[rule_entry_id] = f"status {model.status} cannot be submitted"
                continue
            model.status = RuleEntryStatus.reviewing.value
            model.updated_at = now
            submitted_ids.append(rule_entry_id)
        if submitted_ids:
            await db.commit()
        return RuleBatchSubmitResult(submitted_ids=submitted_ids, skipped=skipped)

    async def review_rule_entry(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        payload: RuleEntryReviewRequest,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="review_approval")
        if model.created_by == actor_user_id and not is_admin:
            raise HTTPException(status_code=403, detail="requester cannot review own rule entry")
        if model.status != RuleEntryStatus.reviewing.value:
            raise HTTPException(status_code=400, detail="only reviewing rule entries can be reviewed")
        if payload.approve:
            self._validate_rule_payload(self._rule_payload(model), require_approved_quality=True)
            model.status = RuleEntryStatus.approved.value
        else:
            model.status = RuleEntryStatus.rejected.value
        model.reviewed_by = actor_user_id
        model.review_note = (payload.review_note or "").strip() or None
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        await persistent_ontology_service._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.asset.rule.review",
            output_result=f"{model.id}:{model.status}",
        )
        return self._rule_to_record(model)

    async def deprecate_rule_entry(
        self,
        db: AsyncSession,
        rule_entry_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RuleEntryRecord:
        model = await self._get_rule(db, rule_entry_id)
        if not model:
            raise HTTPException(status_code=404, detail="rule entry not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="governance")
        model.status = RuleEntryStatus.deprecated.value
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._rule_to_record(model)

    async def compile_rules(
        self,
        db: AsyncSession,
        payload: RulePackageCompileRequest,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> RulePackageCompileResult:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        entries = await self._select_rule_entries_for_compile(db, payload)
        if not entries:
            raise HTTPException(status_code=400, detail="no approved rule entries matched compile request")

        rule_ids = [item.rule_code for item in entries]
        if len(rule_ids) != len(set(rule_ids)):
            raise HTTPException(status_code=400, detail="approved rule entries contain duplicate rule_code")

        rules: List[RuleDef] = []
        warnings: List[str] = []
        source_document_ids: List[str] = []
        for entry in entries:
            self._validate_rule_payload(self._rule_payload(entry), require_approved_quality=True)
            source_document_ids.extend(
                ref.get("source_document_id")
                for ref in (entry.evidence_refs or [])
                if isinstance(ref, dict) and ref.get("source_document_id")
            )
            if not entry.test_cases:
                warnings.append(f"{entry.rule_code} has no test cases")
            rules.append(
                RuleDef(
                    rule_id=entry.rule_code,
                    name=entry.name,
                    description=entry.description,
                    target_entity_type=entry.target_entity_type,
                    severity=entry.severity,
                    action=entry.action,
                    conditions=entry.conditions or [],
                    tags=entry.tags or [],
                )
            )

        rule_package = RulePackageCreate(
            space_id=payload.space_id,
            version=payload.version,
            description=payload.description,
            rules=rules,
        )
        package_payload = rule_package.model_dump()
        package_payload["metadata"] = {
            "compiled_from": "rule_entries",
            "compiled_from_rule_entry_ids": [entry.id for entry in entries],
            "source_document_ids": sorted(set(source_document_ids)),
            "compiled_by": actor_user_id,
            "compiled_at": utc_now().isoformat(),
        }
        package_record = await persistent_ontology_service._upsert_package(
            db=db,
            space_id=payload.space_id,
            kind=PackageKind.rule,
            version=payload.version,
            payload=package_payload,
            actor_user_id=actor_user_id,
        )

        now = utc_now()
        for entry in entries:
            entry.status = RuleEntryStatus.packaged.value
            entry.updated_at = now
        await db.commit()
        await persistent_ontology_service._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.asset.rules.compile",
            output_result=f"{payload.space_id}:rule:{payload.version}:{len(entries)}",
        )
        return RulePackageCompileResult(
            package=package_record.model_dump(),
            rule_entry_ids=[entry.id for entry in entries],
            warnings=warnings,
        )

    async def create_term(
        self,
        db: AsyncSession,
        payload: OntologyTermCreate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologyTermRecord:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        await self._ensure_source_in_space(db, payload.space_id, payload.source_document_id)
        if await self._get_term_by_code(db, payload.space_id, payload.term_code):
            raise HTTPException(status_code=409, detail="term_code already exists in this ontology space")
        self._validate_term_payload(payload.model_dump(), require_approved_quality=False)
        now = utc_now()
        model = OntologyTermModel(
            id=f"onto-term-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            source_document_id=payload.source_document_id,
            term_code=self._normalize_term_code(payload.term_code),
            name=payload.name.strip(),
            kind=payload.kind.value,
            description=(payload.description or "").strip() or None,
            entity_type=(payload.entity_type or "").strip() or None,
            data_type=payload.data_type,
            required=payload.required,
            enum_values=self._normalize_tags(payload.enum_values),
            relation_target_type=(payload.relation_target_type or "").strip() or None,
            relation_cardinality=payload.relation_cardinality,
            aliases=self._normalize_tags(payload.aliases),
            evidence_refs=[item.model_dump() for item in payload.evidence_refs],
            metadata_json=deepcopy(payload.metadata or {}),
            status=RuleEntryStatus.draft.value,
            version=payload.version.strip() or "1",
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return self._term_to_record(model)

    async def list_terms(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        status: Optional[RuleEntryStatus],
        kind: Optional[OntologyTermKind],
        actor_user_id: str,
        is_admin: bool,
    ) -> List[OntologyTermRecord]:
        await persistent_ontology_service._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        conds = [OntologyTermModel.space_id == space_id]
        if status:
            conds.append(OntologyTermModel.status == status.value)
        if kind:
            conds.append(OntologyTermModel.kind == kind.value)
        result = await db.execute(
            select(OntologyTermModel)
            .where(and_(*conds))
            .order_by(OntologyTermModel.kind, OntologyTermModel.entity_type, OntologyTermModel.name)
        )
        return [self._term_to_record(row) for row in result.scalars().all()]

    async def get_term(
        self,
        db: AsyncSession,
        term_id: str,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologyTermRecord:
        model = await self._get_term(db, term_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology term not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="read")
        return self._term_to_record(model)

    async def update_term(
        self,
        db: AsyncSession,
        term_id: str,
        payload: OntologyTermUpdate,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologyTermRecord:
        model = await self._get_term(db, term_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology term not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="write")
        if model.status in {RuleEntryStatus.packaged.value, RuleEntryStatus.released.value, RuleEntryStatus.deprecated.value}:
            raise HTTPException(status_code=400, detail="packaged/released/deprecated ontology terms cannot be edited")
        data = payload.model_dump(exclude_unset=True)
        if "source_document_id" in data:
            await self._ensure_source_in_space(db, model.space_id, data["source_document_id"])
            model.source_document_id = data["source_document_id"]
        for field in ["name", "description", "entity_type", "data_type", "required", "relation_target_type", "relation_cardinality", "version"]:
            if field in data:
                value = data[field]
                setattr(model, field, value.strip() if isinstance(value, str) else value)
        if "enum_values" in data:
            model.enum_values = self._normalize_tags(payload.enum_values or [])
        if "aliases" in data:
            model.aliases = self._normalize_tags(payload.aliases or [])
        if "evidence_refs" in data:
            model.evidence_refs = [item.model_dump() for item in payload.evidence_refs or []]
        if "metadata" in data:
            model.metadata_json = deepcopy(payload.metadata or {})
        if model.status in {RuleEntryStatus.reviewing.value, RuleEntryStatus.approved.value, RuleEntryStatus.rejected.value}:
            model.status = RuleEntryStatus.draft.value
            model.reviewed_by = None
            model.review_note = None
        self._validate_term_payload(self._term_payload(model), require_approved_quality=False)
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._term_to_record(model)

    async def submit_term_review(self, db: AsyncSession, term_id: str, *, actor_user_id: str, is_admin: bool) -> OntologyTermRecord:
        model = await self._get_term(db, term_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology term not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="approve_request")
        if model.status not in {RuleEntryStatus.draft.value, RuleEntryStatus.rejected.value}:
            raise HTTPException(status_code=400, detail="only draft/rejected ontology terms can be submitted")
        self._validate_term_payload(self._term_payload(model), require_approved_quality=True)
        model.status = RuleEntryStatus.reviewing.value
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._term_to_record(model)

    async def review_term(
        self,
        db: AsyncSession,
        term_id: str,
        payload: RuleEntryReviewRequest,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologyTermRecord:
        model = await self._get_term(db, term_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology term not found")
        await persistent_ontology_service._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="review_approval")
        if model.created_by == actor_user_id and not is_admin:
            raise HTTPException(status_code=403, detail="requester cannot review own ontology term")
        if model.status != RuleEntryStatus.reviewing.value:
            raise HTTPException(status_code=400, detail="only reviewing ontology terms can be reviewed")
        if payload.approve:
            self._validate_term_payload(self._term_payload(model), require_approved_quality=True)
            model.status = RuleEntryStatus.approved.value
        else:
            model.status = RuleEntryStatus.rejected.value
        model.reviewed_by = actor_user_id
        model.review_note = (payload.review_note or "").strip() or None
        model.updated_at = utc_now()
        await db.commit()
        await db.refresh(model)
        return self._term_to_record(model)

    async def compile_schema(
        self,
        db: AsyncSession,
        payload: SchemaPackageCompileRequest,
        *,
        actor_user_id: str,
        is_admin: bool,
    ) -> SchemaPackageCompileResult:
        await persistent_ontology_service._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        terms = await self._select_terms_for_compile(db, payload)
        if not terms:
            raise HTTPException(status_code=400, detail="no approved ontology terms matched compile request")
        for term in terms:
            self._validate_term_payload(self._term_payload(term), require_approved_quality=True)

        entities = {term.name: {"name": term.name, "description": term.description, "attributes": {}, "relations": []} for term in terms if term.kind == OntologyTermKind.entity.value}
        taxonomy: Dict[str, List[str]] = {}
        vocabulary: Dict[str, List[str]] = {}
        warnings: List[str] = []
        source_document_ids: List[str] = []
        for term in terms:
            source_document_ids.extend(ref.get("source_document_id") for ref in (term.evidence_refs or []) if isinstance(ref, dict) and ref.get("source_document_id"))
            if term.kind == OntologyTermKind.attribute.value:
                if term.entity_type not in entities:
                    raise HTTPException(status_code=400, detail=f"attribute {term.term_code} references missing entity {term.entity_type}")
                entities[term.entity_type]["attributes"][term.name] = AttributeDef(
                    data_type=term.data_type or "string",
                    required=term.required,
                    description=term.description,
                    enum_values=term.enum_values or None,
                ).model_dump()
            elif term.kind == OntologyTermKind.relation.value:
                if term.entity_type not in entities:
                    raise HTTPException(status_code=400, detail=f"relation {term.term_code} references missing source entity {term.entity_type}")
                if term.relation_target_type not in entities:
                    raise HTTPException(status_code=400, detail=f"relation {term.term_code} references missing target entity {term.relation_target_type}")
                entities[term.entity_type]["relations"].append(
                    RelationDef(
                        name=term.name,
                        target_type=term.relation_target_type or "",
                        cardinality=term.relation_cardinality or "many",
                        description=term.description,
                    ).model_dump()
                )
            elif term.kind == OntologyTermKind.taxonomy.value:
                taxonomy[term.name] = term.enum_values or []
            elif term.kind == OntologyTermKind.vocabulary.value:
                vocabulary[term.name] = term.enum_values or term.aliases or []
            elif term.kind == OntologyTermKind.enum.value:
                warnings.append(f"enum {term.term_code} is compiled only when referenced by an attribute")

        schema_package = SchemaPackageCreate(
            space_id=payload.space_id,
            version=payload.version,
            description=payload.description,
            entity_types=[EntityTypeDef.model_validate(item) for item in entities.values()],
            taxonomy=taxonomy,
            vocabulary=vocabulary,
        )
        package_payload = schema_package.model_dump()
        package_payload["metadata"] = {
            "compiled_from": "ontology_terms",
            "compiled_from_term_ids": [term.id for term in terms],
            "source_document_ids": sorted(set(source_document_ids)),
            "compiled_by": actor_user_id,
            "compiled_at": utc_now().isoformat(),
        }
        package_record = await persistent_ontology_service._upsert_package(
            db=db,
            space_id=payload.space_id,
            kind=PackageKind.schema,
            version=payload.version,
            payload=package_payload,
            actor_user_id=actor_user_id,
        )
        now = utc_now()
        for term in terms:
            term.status = RuleEntryStatus.packaged.value
            term.updated_at = now
        await db.commit()
        return SchemaPackageCompileResult(
            package=package_record.model_dump(),
            term_ids=[term.id for term in terms],
            warnings=warnings,
        )

    async def _select_rule_entries_for_compile(self, db: AsyncSession, payload: RulePackageCompileRequest) -> List[RuleEntryModel]:
        conds = [RuleEntryModel.space_id == payload.space_id, RuleEntryModel.status == RuleEntryStatus.approved.value]
        if payload.rule_entry_ids:
            conds.append(RuleEntryModel.id.in_(payload.rule_entry_ids))
        if payload.include_tags:
            tags = set(self._normalize_tags(payload.include_tags))
            result = await db.execute(select(RuleEntryModel).where(and_(*conds)).order_by(RuleEntryModel.rule_code))
            return [
                row for row in result.scalars().all()
                if tags.intersection(set(row.tags or []))
            ]
        result = await db.execute(select(RuleEntryModel).where(and_(*conds)).order_by(RuleEntryModel.rule_code))
        return result.scalars().all()

    async def _select_terms_for_compile(self, db: AsyncSession, payload: SchemaPackageCompileRequest) -> List[OntologyTermModel]:
        conds = [OntologyTermModel.space_id == payload.space_id, OntologyTermModel.status == RuleEntryStatus.approved.value]
        if payload.term_ids:
            conds.append(OntologyTermModel.id.in_(payload.term_ids))
        result = await db.execute(
            select(OntologyTermModel)
            .where(and_(*conds))
            .order_by(OntologyTermModel.kind, OntologyTermModel.entity_type, OntologyTermModel.name)
        )
        return result.scalars().all()

    async def _get_source(self, db: AsyncSession, source_id: str) -> Optional[RuleSourceDocumentModel]:
        result = await db.execute(select(RuleSourceDocumentModel).where(RuleSourceDocumentModel.id == source_id))
        return result.scalar_one_or_none()

    async def _source_has_rules(self, db: AsyncSession, source_id: str) -> bool:
        result = await db.execute(
            select(RuleEntryModel.id)
            .where(RuleEntryModel.source_document_id == source_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_source_by_hash(self, db: AsyncSession, space_id: str, content_hash: str) -> Optional[RuleSourceDocumentModel]:
        result = await db.execute(
            select(RuleSourceDocumentModel).where(
                and_(RuleSourceDocumentModel.space_id == space_id, RuleSourceDocumentModel.content_hash == content_hash)
            )
        )
        return result.scalar_one_or_none()

    async def _get_rule(self, db: AsyncSession, rule_entry_id: str) -> Optional[RuleEntryModel]:
        result = await db.execute(select(RuleEntryModel).where(RuleEntryModel.id == rule_entry_id))
        return result.scalar_one_or_none()

    async def _get_rule_by_code(self, db: AsyncSession, space_id: str, rule_code: str) -> Optional[RuleEntryModel]:
        result = await db.execute(
            select(RuleEntryModel).where(
                and_(RuleEntryModel.space_id == space_id, RuleEntryModel.rule_code == self._normalize_rule_code(rule_code))
            )
        )
        return result.scalar_one_or_none()

    async def _get_term(self, db: AsyncSession, term_id: str) -> Optional[OntologyTermModel]:
        result = await db.execute(select(OntologyTermModel).where(OntologyTermModel.id == term_id))
        return result.scalar_one_or_none()

    async def _get_term_by_code(self, db: AsyncSession, space_id: str, term_code: str) -> Optional[OntologyTermModel]:
        result = await db.execute(
            select(OntologyTermModel).where(
                and_(OntologyTermModel.space_id == space_id, OntologyTermModel.term_code == self._normalize_term_code(term_code))
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_source_in_space(self, db: AsyncSession, space_id: str, source_document_id: Optional[str]) -> None:
        if not source_document_id:
            return
        source = await self._get_source(db, source_document_id)
        if not source or source.space_id != space_id:
            raise HTTPException(status_code=400, detail="source_document_id does not belong to this ontology space")

    def _split_source_clauses(self, raw_text: str) -> List[Dict[str, str]]:
        clauses: List[Dict[str, str]] = []
        current_locator = ""
        current_lines: List[str] = []
        for idx, line in enumerate(raw_text.splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            marker = re.match(r"^(第\s*[一二三四五六七八九十百千0-9.]+\s*[条章节款]|[0-9]+[.、])\s*(.*)$", text)
            if marker and current_lines:
                clauses.append({"locator": current_locator or f"第 {idx - len(current_lines)} 行", "quote": " ".join(current_lines)})
                current_lines = []
            if marker:
                current_locator = marker.group(1)
                rest = marker.group(2).strip()
                current_lines.append(rest or text)
            else:
                current_locator = current_locator or f"第 {idx} 行"
                current_lines.append(text)
        if current_lines:
            clauses.append({"locator": current_locator or "全文", "quote": " ".join(current_lines)})
        has_clause_marker = any(re.match(r"^第\s*[一二三四五六七八九十百千0-9.]+\s*[条章节款]$", item["locator"]) for item in clauses)
        if len(clauses) <= 1 and not has_clause_marker:
            sentences = re.split(r"(?<=[。；;])", raw_text)
            clauses = [
                {"locator": f"句 {idx}", "quote": item.strip()}
                for idx, item in enumerate(sentences, start=1)
                if item.strip()
            ]
        return clauses

    def _infer_rule_candidate(self, source: RuleSourceDocumentModel, clause: Dict[str, str]) -> Optional[Dict[str, Any]]:
        text = clause["quote"].strip()
        if not text:
            return None
        if self._is_non_rule_clause(clause):
            return None
        if self._is_non_rule_heading(text):
            return None

        if not re.search(
            r"(超过|大于|高于|低于|少于|不得|严禁|禁止|必须|应当|需要|需|须|按照|执行|报批|审批|备案|报销|核销|公开|监督|检查|追究|适用|废止|施行|标准|预算|计划|票据|凭证|责任|原则|范围|高风险|风险|提示|预警|拦截|拒绝)",
            text,
        ):
            return None

        field, field_label = self._infer_policy_field(text)
        target_entity_type = self._infer_target_entity_type(source, text, field)
        threshold = self._extract_threshold(text)
        operator = self._infer_operator(text)
        conditions: List[Dict[str, Any]] = []
        if field and threshold is not None and operator:
            value = threshold["value"]
            if field == "amount" and threshold["unit"] in {"万元", "万"}:
                value = value * 10000
            conditions.append({"path": f"entity.{field}", "operator": operator, "value": value})
        elif field and "自动续约" in text:
            conditions.append({"path": "entity.auto_renewal", "operator": "eq", "value": True})
        elif field and re.search(r"(不得|严禁|禁止|不予|不得以|不得安排|不得核销)", text):
            conditions.append({"path": f"entity.{field}", "operator": "exists"})

        severity = "medium"
        if re.search(r"(重大|严重|关键|禁止|不得|严禁|拒绝|拦截|追究|处罚|处分|废止)", text):
            severity = "critical"
        elif re.search(r"(高风险|高危|超过|大于|高于)", text):
            severity = "high"
        elif re.search(r"(提示|关注|建议)", text):
            severity = "low"

        action = "flag"
        if re.search(r"(禁止|不得|严禁|拒绝|拦截|不予|不得核销)", text):
            action = "block"
        elif re.search(r"(建议|推荐|参照)", text):
            action = "recommend"

        stem = field.upper() if field else self._infer_rule_stem(text)
        if threshold and operator:
            stem = f"{stem}_{operator.upper()}_{str(threshold['value']).replace('.', '_')}"
        stem = f"{stem}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6].upper()}"
        rule_code = self._normalize_rule_code(f"{source.source_type}_{stem}")
        name = self._build_rule_name(text, field_label)
        return {
            "rule_code": rule_code[:120],
            "name": name,
            "description": f"从 {source.title} {clause['locator']} 抽取的候选规则。审核时需确认条件是否完整。",
            "target_entity_type": target_entity_type,
            "conditions": conditions,
            "severity": severity,
            "action": action,
        }

    @staticmethod
    def _infer_policy_field(text: str) -> tuple[Optional[str], Optional[str]]:
        mapping = [
            ("budget_amount", "预算金额", r"预算|经费预算|超预算|无预算"),
            ("travel_plan", "出国计划", r"出国计划|出访计划|计划报批|计划审批"),
            ("delegation_size", "团组人数", r"团组人数|人数"),
            ("country_count", "国家数", r"国家数|出访国家"),
            ("stay_days", "在外停留天数", r"停留天数|在外停留|天数"),
            ("travel_route", "出访路线", r"路线|绕道|过境"),
            ("airline_choice", "航线选择", r"航空公司|国际航线|外国航空公司"),
            ("ticket_payment_method", "机票支付方式", r"机票款|公务卡|银行转账|现金支付"),
            ("transport_class", "交通工具舱位", r"头等舱|公务舱|经济舱|软卧|硬卧|舱位|交通工具"),
            ("city_transport_plan", "城市间交通", r"城市间|国外城市间交通"),
            ("hotel_standard", "住宿标准", r"住宿费|住宿标准|标准间|普通套房|酒店"),
            ("meal_misc_allowance", "伙食费和公杂费", r"伙食费|公杂费|包干"),
            ("banquet_expense", "宴请费用", r"宴请|用餐|公款相互宴请"),
            ("gift_expense", "礼品费用", r"礼品|纪念品|赠送"),
            ("insurance_expense", "保险费用", r"保险|签证费用|防疫费用|会议注册费用"),
            ("reimbursement_document", "报销凭证", r"报销|票据|凭证|发票|护照|签证|费用明细"),
            ("expense_audit", "经费核销审核", r"核销|审核|开支标准|开支内容"),
            ("information_disclosure", "预决算公开", r"公开|预决算信息"),
            ("supervision_check", "监督检查", r"监督检查|审计|绩效评价"),
            ("record_filing", "备案", r"备案|报送财政部"),
            ("payment_term_days", "付款周期", r"(付款|账期|支付).{0,8}(周期|期限|天|日)"),
            ("amount", "合同金额", r"(合同)?金额|标的额|交易额|授信额度"),
            ("term_days", "合同期限", r"(合同)?期限|有效期"),
            ("liability_cap", "责任上限", r"责任上限|赔偿上限|责任限制"),
            ("auto_renewal", "自动续约", r"自动续约|自动延续"),
        ]
        for field, label, pattern in mapping:
            if re.search(pattern, text):
                return field, label
        return None, None

    @staticmethod
    def _infer_target_entity_type(source: RuleSourceDocumentModel, text: str, field: Optional[str]) -> Optional[str]:
        title = f"{source.title or ''} {text}"
        if re.search(r"因公临时出国|出国|出访|团组", title):
            if field in {"reimbursement_document", "expense_audit", "budget_amount", "insurance_expense", "meal_misc_allowance", "hotel_standard"}:
                return "AbroadExpenseClaim"
            return "TemporaryAbroadTrip"
        if re.search(r"合同|付款|自动续约|责任上限", title):
            return "Contract"
        return "PolicySubject"

    @staticmethod
    def _infer_rule_stem(text: str) -> str:
        keywords = [
            ("PROHIBITED", r"不得|严禁|禁止"),
            ("APPROVAL_REQUIRED", r"报批|审批|批准|审签"),
            ("REIMBURSEMENT", r"报销|核销|票据|凭证"),
            ("BUDGET_CONTROL", r"预算|经费"),
            ("STANDARD_CONTROL", r"标准|不得擅自突破"),
            ("SUPERVISION", r"监督|检查|审计"),
            ("FILING", r"备案|报送"),
            ("DISCLOSURE", r"公开"),
            ("SCOPE", r"适用|范围"),
        ]
        for stem, pattern in keywords:
            if re.search(pattern, text):
                return stem
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8].upper()

    @staticmethod
    def _is_non_rule_heading(text: str) -> bool:
        compact = re.sub(r"\s+", "", text or "")
        if not compact:
            return True
        if re.match(r"^第[一二三四五六七八九十百千0-9.]+章", compact):
            return True
        if compact in {"附件:", "附件", "总则", "附则"}:
            return True
        if len(compact) <= 24 and re.search(r"(管理办法|通知)$", compact) and not re.search(r"(应当|不得|须|按照|执行|适用|施行)", compact):
            return True
        return False

    def _is_non_rule_clause(self, clause: Dict[str, str]) -> bool:
        text = clause.get("quote") or ""
        locator = clause.get("locator") or ""
        if self._is_non_rule_heading(text):
            return True
        if re.match(r"^第\s*[一二三四五六七八九十百千0-9.]+\s*章$", locator) and len(re.sub(r"\s+", "", text)) <= 30:
            return True
        if re.match(r"^第\s*[0-9]+\s*行$", locator) and re.search(r"(发布时间|关于印发|通知|财政部|外交部)", text):
            return True
        return False

    @staticmethod
    def _extract_threshold(text: str) -> Optional[Dict[str, Any]]:
        body = re.sub(r"^第\s*[一二三四五六七八九十百千0-9.]+\s*[条章节款]\s*", "", text.strip())
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(万元|万|元|天|日|个月|月|年|%)?", body)
        if not match:
            return None
        raw = match.group(1)
        value: Any = float(raw) if "." in raw else int(raw)
        return {"value": value, "unit": match.group(2) or ""}

    @staticmethod
    def _infer_operator(text: str) -> Optional[str]:
        if re.search(r"(超过|大于|高于|多于)", text):
            return "gt"
        if re.search(r"(不低于|不少于|至少|大于等于)", text):
            return "gte"
        if re.search(r"(低于|少于|小于)", text):
            return "lt"
        if re.search(r"(不超过|不高于|最多|小于等于)", text):
            return "lte"
        return None

    @staticmethod
    def _build_rule_name(text: str, field_label: Optional[str]) -> str:
        compact = re.sub(r"\s+", "", text)
        if len(compact) <= 36:
            return compact
        prefix = f"{field_label}：" if field_label else ""
        return f"{prefix}{compact[:34]}"

    def _extract_uploaded_text(self, *, file_name: str, content_type: Optional[str], content: bytes) -> tuple[str, List[str]]:
        warnings: List[str] = []
        lower_name = (file_name or "").lower()
        mime = (content_type or "").lower()
        if lower_name.endswith((".txt", ".md", ".markdown", ".json", ".csv", ".tsv")) or mime.startswith("text/") or mime in {"application/json"}:
            return self._decode_text_bytes(content), warnings
        if lower_name.endswith(".docx") or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            try:
                return self._extract_docx_text(content), warnings
            except Exception as exc:
                warnings.append(f"DOCX text extraction failed: {exc}")
                return "", warnings
        if lower_name.endswith(".pdf") or mime == "application/pdf":
            warnings.append("PDF text extraction is not enabled yet; install a PDF parser before using PDF sources.")
            return "", warnings
        warnings.append("unsupported file type; stored metadata but no text was extracted")
        return "", warnings

    @staticmethod
    def _decode_text_bytes(content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_docx_text(content: bytes) -> str:
        paragraphs: List[str] = []
        with zipfile.ZipFile(BytesIO(content)) as docx:
            xml_bytes = docx.read("word/document.xml")
        root = ElementTree.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for paragraph in root.findall(".//w:p", ns):
            parts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
            text = "".join(parts).strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)

    def _validate_rule_payload(self, data: Dict[str, Any], *, require_approved_quality: bool) -> None:
        if not self._normalize_rule_code(data.get("rule_code") or ""):
            raise HTTPException(status_code=400, detail="rule_code is required")
        conditions = data.get("conditions") or []
        for condition in conditions:
            if not condition.get("path") or not condition.get("operator"):
                raise HTTPException(status_code=400, detail="rule condition requires path and operator")
        if require_approved_quality:
            blockers, _ = self._assess_rule_payload(data)
            if blockers:
                raise HTTPException(status_code=400, detail=blockers[0].message)

    def _assess_rule_payload(self, data: Dict[str, Any]) -> tuple[List[RuleQualityIssue], List[RuleQualityIssue]]:
        blockers: List[RuleQualityIssue] = []
        warnings: List[RuleQualityIssue] = []
        conditions = data.get("conditions") or []
        evidence_refs = data.get("evidence_refs") or []
        test_cases = data.get("test_cases") or []
        if not conditions:
            blockers.append(RuleQualityIssue(
                code="missing_conditions",
                field="conditions",
                message="rule entry requires structured conditions before review",
            ))
        if not evidence_refs:
            blockers.append(RuleQualityIssue(
                code="missing_evidence_refs",
                field="evidence_refs",
                message="rule entry requires evidence_refs before review",
            ))
        for index, ref in enumerate(evidence_refs):
            if not isinstance(ref, dict) or not ref.get("locator"):
                blockers.append(RuleQualityIssue(
                    code="missing_evidence_locator",
                    field=f"evidence_refs.{index}.locator",
                    message="each evidence ref requires locator",
                ))
        if data.get("severity") in {"high", "critical"} and not test_cases:
            blockers.append(RuleQualityIssue(
                code="missing_high_risk_test_cases",
                field="test_cases",
                message="high/critical rule entries require test_cases",
            ))
        elif not test_cases:
            warnings.append(RuleQualityIssue(
                code="missing_test_cases",
                field="test_cases",
                message="rule entry has no test cases",
            ))
        if not data.get("target_entity_type"):
            warnings.append(RuleQualityIssue(
                code="missing_target_entity_type",
                field="target_entity_type",
                message="rule entry has no target_entity_type",
            ))
        return blockers, warnings

    def _rule_quality_report(self, model: RuleEntryModel) -> RuleQualityReport:
        blockers, warnings = self._assess_rule_payload({
            **self._rule_payload(model),
            "target_entity_type": model.target_entity_type,
        })
        return RuleQualityReport(
            rule_entry_id=model.id,
            status=RuleEntryStatus(model.status),
            blockers=blockers,
            warnings=warnings,
            can_submit_review=model.status in {RuleEntryStatus.draft.value, RuleEntryStatus.rejected.value},
            can_approve=model.status == RuleEntryStatus.reviewing.value and not blockers,
            can_package=model.status == RuleEntryStatus.approved.value and not blockers,
        )

    def _rule_payload(self, model: RuleEntryModel) -> Dict[str, Any]:
        return {
            "rule_code": model.rule_code,
            "conditions": deepcopy(model.conditions or []),
            "evidence_refs": deepcopy(model.evidence_refs or []),
            "severity": model.severity,
            "test_cases": deepcopy(model.test_cases or []),
        }

    def _validate_term_payload(self, data: Dict[str, Any], *, require_approved_quality: bool) -> None:
        kind = data.get("kind")
        if not self._normalize_term_code(data.get("term_code") or ""):
            raise HTTPException(status_code=400, detail="term_code is required")
        if require_approved_quality:
            if not data.get("description"):
                raise HTTPException(status_code=400, detail="ontology term requires description before review")
            if not data.get("evidence_refs"):
                raise HTTPException(status_code=400, detail="ontology term requires evidence_refs before review")
        if kind == OntologyTermKind.attribute.value:
            if not data.get("entity_type") or not data.get("data_type"):
                raise HTTPException(status_code=400, detail="attribute term requires entity_type and data_type")
        elif kind == OntologyTermKind.relation.value:
            if not data.get("entity_type") or not data.get("relation_target_type"):
                raise HTTPException(status_code=400, detail="relation term requires entity_type and relation_target_type")
        elif kind == OntologyTermKind.enum.value:
            if not data.get("enum_values"):
                raise HTTPException(status_code=400, detail="enum term requires enum_values")

    def _term_payload(self, model: OntologyTermModel) -> Dict[str, Any]:
        return {
            "term_code": model.term_code,
            "kind": model.kind,
            "description": model.description,
            "entity_type": model.entity_type,
            "data_type": model.data_type,
            "enum_values": deepcopy(model.enum_values or []),
            "relation_target_type": model.relation_target_type,
            "evidence_refs": deepcopy(model.evidence_refs or []),
        }

    def _source_to_record(self, model: RuleSourceDocumentModel) -> RuleSourceDocumentRecord:
        return RuleSourceDocumentRecord(
            id=model.id,
            space_id=model.space_id,
            user_id=model.user_id,
            title=model.title,
            source_type=model.source_type,
            file_name=model.file_name,
            content_type=model.content_type,
            content_hash=model.content_hash,
            raw_text=model.raw_text,
            metadata=deepcopy(model.metadata_json or {}),
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _rule_to_record(self, model: RuleEntryModel) -> RuleEntryRecord:
        return RuleEntryRecord(
            id=model.id,
            space_id=model.space_id,
            source_document_id=model.source_document_id,
            rule_code=model.rule_code,
            name=model.name,
            description=model.description,
            target_entity_type=model.target_entity_type,
            conditions=deepcopy(model.conditions or []),
            severity=model.severity,
            action=model.action,
            evidence_refs=deepcopy(model.evidence_refs or []),
            test_cases=deepcopy(model.test_cases or []),
            tags=deepcopy(model.tags or []),
            status=model.status,
            version=model.version,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            review_note=model.review_note,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _term_to_record(self, model: OntologyTermModel) -> OntologyTermRecord:
        return OntologyTermRecord(
            id=model.id,
            space_id=model.space_id,
            source_document_id=model.source_document_id,
            term_code=model.term_code,
            name=model.name,
            kind=model.kind,
            description=model.description,
            entity_type=model.entity_type,
            data_type=model.data_type,
            required=bool(model.required),
            enum_values=deepcopy(model.enum_values or []),
            relation_target_type=model.relation_target_type,
            relation_cardinality=model.relation_cardinality,
            aliases=deepcopy(model.aliases or []),
            evidence_refs=deepcopy(model.evidence_refs or []),
            metadata=deepcopy(model.metadata_json or {}),
            status=model.status,
            version=model.version,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            review_note=model.review_note,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _hash_source(payload: RuleSourceDocumentCreate) -> str:
        text = payload.raw_text or ""
        parts = [
            payload.title.strip(),
            payload.source_type.value,
            payload.file_name or "",
            payload.content_type or "",
            text,
        ]
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_rule_code(value: str) -> str:
        return (value or "").strip().upper().replace(" ", "_")

    @staticmethod
    def _normalize_term_code(value: str) -> str:
        return (value or "").strip().upper().replace(" ", "_")

    @staticmethod
    def _normalize_tags(tags: List[str]) -> List[str]:
        result = []
        seen = set()
        for tag in tags or []:
            value = (tag or "").strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result


ontology_asset_service = OntologyAssetService()
