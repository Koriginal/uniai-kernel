from __future__ import annotations

import re
import uuid
import os
import base64
import hashlib
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ontology.repository import ontology_repo
from app.services.audit_service import audit_service
from app.models.ontology import (
    OntologyApprovalModel,
    OntologyDecisionModel,
    OntologyDataSourceModel,
    OntologyExplanationModel,
    OntologySecretModel,
    OntologyPackageModel,
    OntologyReleaseEventModel,
    OntologySpaceModel,
)
from app.models.user import Organization as OrganizationModel
from app.ontology.domain_models import (
    OrganizationCreate,
    OrganizationMemberAdd,
    OrganizationMemberRecord,
    OrganizationRecord,
    DecisionResult,
    DataSourceKind,
    DataSourceStatus,
    DataSourceDiscoveryResult,
    DataSourceTestResult,
    DiscoveredColumn,
    DiscoveredEntity,
    EntityInstance,
    EntityMappingRule,
    ExplanationResponse,
    InstanceGraph,
    MappingExecuteRequest,
    MappingExecuteResponse,
    MappingPackageCreate,
    MappingTraceItem,
    PackageDiffResponse,
    ApprovalRecord,
    ApprovalReviewRequest,
    ApprovalStatus,
    ApprovalSubmitRequest,
    OntologySpace,
    OntologySpaceCreate,
    OntologyDataSourceCreate,
    OntologyDataSourceRecord,
    OntologySecretCreate,
    OntologySecretRecord,
    PackageKind,
    PackageRecord,
    ReleaseRequest,
    ReleaseResult,
    RollbackRequest,
    RelationInstance,
    RuleDef,
    RuleEvaluateRequest,
    RuleHit,
    RuleMiss,
    RulePackageCreate,
    SchemaPackageCreate,
    VersionStage,
    utc_now,
)

_SEVERITY_WEIGHTS = {
    "low": 5,
    "medium": 10,
    "high": 20,
    "critical": 40,
}


class PersistentOntologyService:
    """Database-backed ontology service."""
    def __init__(self):
        self.repo = ontology_repo
        self._org_role_permissions = {
            "viewer": {"read"},
            "member": {"read", "execute", "approve_request"},
            "admin": {"read", "execute", "approve_request", "review_approval", "write", "space_create", "governance", "member_manage"},
            "owner": {"read", "execute", "approve_request", "review_approval", "write", "space_create", "governance", "member_manage"},
        }
        digest = hashlib.sha256((settings.ENCRYPTION_KEY or settings.SECRET_KEY).encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    async def create_org(self, db: AsyncSession, payload: OrganizationCreate, actor_user_id: str, is_admin: bool) -> OrganizationRecord:
        if not settings.ENABLE_ORG_TENANCY:
            raise HTTPException(status_code=400, detail="org tenancy is disabled by configuration")
        code = self._normalize_code(payload.code)
        existed = await self.repo.get_org_by_code(db, code)
        if existed:
            if is_admin or existed.owner_user_id == actor_user_id or await self.repo.is_org_member(db, org_id=existed.id, user_id=actor_user_id):
                return self._org_to_domain(existed)
            raise HTTPException(status_code=403, detail="organization code already exists")

        model = OrganizationModel(
            code=code,
            name=payload.name.strip(),
            description=(payload.description or "").strip() or None,
            owner_user_id=actor_user_id,
            is_active=True,
            created_at=utc_now(),
        )
        model = await self.repo.create_org(db, model)
        await self.repo.add_or_update_org_member(db, org_id=model.id, user_id=actor_user_id, role="owner")
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.org.create", output_result=model.id)
        return self._org_to_domain(model)

    async def list_orgs(self, db: AsyncSession, actor_user_id: str, is_admin: bool) -> List[OrganizationRecord]:
        rows = await self.repo.list_orgs_for_user(db, user_id=actor_user_id, is_admin=is_admin)
        return [self._org_to_domain(item) for item in rows]

    async def add_org_member(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        payload: OrganizationMemberAdd,
        actor_user_id: str,
        is_admin: bool,
    ) -> OrganizationMemberRecord:
        if not settings.ENABLE_ORG_TENANCY:
            raise HTTPException(status_code=400, detail="org tenancy is disabled by configuration")
        org = await self.repo.get_org_by_id(db, org_id)
        if not org:
            raise HTTPException(status_code=404, detail="organization not found")
        if not is_admin:
            if org.owner_user_id == actor_user_id:
                pass
            else:
                role = await self._resolve_org_membership_role(db, org_id=org_id, user_id=actor_user_id)
                if not role or not self._org_action_allowed(role, "member_manage"):
                    raise HTTPException(status_code=403, detail="only org owner/admin can add members")
        member = await self.repo.add_or_update_org_member(
            db,
            org_id=org_id,
            user_id=payload.user_id,
            role=payload.role.value,
        )
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.org.member.upsert", output_result=f"{org_id}:{payload.user_id}")
        return self._org_member_to_domain(member)

    async def list_org_members(self, db: AsyncSession, *, org_id: str, actor_user_id: str, is_admin: bool) -> List[OrganizationMemberRecord]:
        org = await self.repo.get_org_by_id(db, org_id)
        if not org:
            raise HTTPException(status_code=404, detail="organization not found")
        if not is_admin and org.owner_user_id != actor_user_id:
            role = await self._resolve_org_membership_role(db, org_id=org_id, user_id=actor_user_id)
            if not role or not self._org_action_allowed(role, "read"):
                raise HTTPException(status_code=403, detail="forbidden to access this organization")
        rows = await self.repo.list_org_members(db, org_id=org_id)
        return [self._org_member_to_domain(item) for item in rows]

    async def create_space(self, db: AsyncSession, payload: OntologySpaceCreate, owner_user_id: str) -> OntologySpace:
        code = self._normalize_code(payload.code or payload.name)
        org_id = (payload.org_id or "").strip() or None
        if org_id:
            if not settings.ENABLE_ORG_TENANCY:
                raise HTTPException(status_code=400, detail="org scope is disabled by configuration")
            role = await self._resolve_org_membership_role(db, org_id=org_id, user_id=owner_user_id)
            if not role:
                raise HTTPException(status_code=403, detail="forbidden to create ontology space in this organization")
            if not self._org_action_allowed(role, "space_create"):
                raise HTTPException(status_code=403, detail="insufficient org permissions to create ontology space")

        existed = await self.repo.get_space_by_owner_code(db, owner_user_id, code)
        if existed:
            return self._space_to_domain(existed)

        now = utc_now()
        model = OntologySpaceModel(
            id=f"onto-space-{uuid.uuid4().hex[:10]}",
            name=payload.name.strip(),
            code=code,
            description=(payload.description or "").strip() or None,
            owner_user_id=owner_user_id,
            org_id=org_id,
            created_at=now,
            updated_at=now,
        )
        model = await self.repo.create_space(db, model)
        await self._try_audit(db, user_id=owner_user_id, action_name="ontology.space.create", output_result=model.id)
        return self._space_to_domain(model)

    async def list_spaces(self, db: AsyncSession, owner_user_id: str, is_admin: bool) -> List[OntologySpace]:
        rows = await self.repo.list_spaces_for_user(
            db,
            user_id=owner_user_id,
            is_admin=is_admin,
            enable_org_tenancy=settings.ENABLE_ORG_TENANCY,
        )
        return [self._space_to_domain(item) for item in rows]

    async def upsert_data_source(
        self,
        db: AsyncSession,
        payload: OntologyDataSourceCreate,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologyDataSourceRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        self._validate_data_source_config(payload)
        existed = await self.repo.get_data_source_by_name(db, space_id=payload.space_id, name=payload.name.strip())
        now = utc_now()
        model = OntologyDataSourceModel(
            id=existed.id if existed else f"onto-ds-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            name=payload.name.strip(),
            kind=payload.kind.value,
            protocol=payload.protocol.strip().lower(),
            config=self._sanitize_data_source_config(payload.config),
            secret_ref=(payload.secret_ref or "").strip() or None,
            status=payload.status.value,
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        saved = await self.repo.upsert_data_source(db, existed=existed, new_model=model)
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.datasource.upsert", output_result=saved.id)
        return self._data_source_to_domain(saved)

    async def list_data_sources(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[OntologyDataSourceRecord]:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin)
        rows = await self.repo.list_data_sources(db, space_id=space_id)
        return [self._data_source_to_domain(item) for item in rows]

    async def test_data_source(
        self,
        db: AsyncSession,
        *,
        data_source_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> DataSourceTestResult:
        model = await self.repo.get_data_source(db, data_source_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology data source not found")
        await self._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="execute")
        result = self._dry_run_data_source(model)
        await self.repo.update_data_source_test_result(
            db,
            model=model,
            status=result.status,
            message=result.message,
        )
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.datasource.test", output_result=model.id)
        return result

    async def upsert_secret(
        self,
        db: AsyncSession,
        payload: OntologySecretCreate,
        actor_user_id: str,
        is_admin: bool,
    ) -> OntologySecretRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        scope = self._normalize_secret_part(payload.scope)
        name = self._normalize_secret_part(payload.name)
        existed = await self.repo.get_secret_by_ref(db, space_id=payload.space_id, scope=scope, name=name)
        now = utc_now()
        model = OntologySecretModel(
            id=existed.id if existed else f"onto-sec-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            scope=scope,
            name=name,
            encrypted_value=self._encrypt_secret(payload.value),
            description=(payload.description or "").strip() or None,
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        saved = await self.repo.upsert_secret(db, existed=existed, new_model=model)
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.secret.upsert", output_result=f"secret://{scope}/{name}")
        return self._secret_to_domain(saved)

    async def list_secrets(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[OntologySecretRecord]:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin, action="read")
        rows = await self.repo.list_secrets(db, space_id=space_id)
        return [self._secret_to_domain(item) for item in rows]

    async def discover_data_source(
        self,
        db: AsyncSession,
        *,
        data_source_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> DataSourceDiscoveryResult:
        model = await self.repo.get_data_source(db, data_source_id)
        if not model:
            raise HTTPException(status_code=404, detail="ontology data source not found")
        await self._ensure_space_access(db, model.space_id, actor_user_id, is_admin, action="execute")

        if model.kind == DataSourceKind.database.value:
            result = await self._discover_database(db, model)
        elif model.kind == DataSourceKind.api.value:
            result = await self._discover_api(db, model)
        else:
            result = DataSourceDiscoveryResult(
                ok=False,
                status="unsupported",
                message=f"{model.kind}:{model.protocol} discovery adapter is not installed yet",
                source_id=model.id,
                protocol=model.protocol,
                entities=[],
                warnings=["当前协议已注册，但还没有启用对应的 schema discovery 适配器。"],
            )
        await self._try_audit(db, user_id=actor_user_id, action_name="ontology.datasource.discover", output_result=f"{model.id}:{result.status}")
        return result

    async def upsert_schema(self, db: AsyncSession, payload: SchemaPackageCreate, actor_user_id: str, is_admin: bool) -> PackageRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        data = payload.model_dump()
        names = [e["name"] for e in data.get("entity_types", [])]
        if len(names) != len(set(names)):
            raise HTTPException(status_code=400, detail="schema entity_types contains duplicate names")
        return await self._upsert_package(
            db=db,
            space_id=payload.space_id,
            kind=PackageKind.schema,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    async def upsert_mapping(self, db: AsyncSession, payload: MappingPackageCreate, actor_user_id: str, is_admin: bool) -> PackageRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        data = payload.model_dump()
        for item in data.get("entity_mappings", []):
            if not item.get("entity_type") or not item.get("id_template"):
                raise HTTPException(status_code=400, detail="entity mapping requires entity_type and id_template")
        return await self._upsert_package(
            db=db,
            space_id=payload.space_id,
            kind=PackageKind.mapping,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    async def upsert_rule(self, db: AsyncSession, payload: RulePackageCreate, actor_user_id: str, is_admin: bool) -> PackageRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="write")
        data = payload.model_dump()
        rule_ids = [r["rule_id"] for r in data.get("rules", [])]
        if len(rule_ids) != len(set(rule_ids)):
            raise HTTPException(status_code=400, detail="rule package contains duplicate rule_id")
        return await self._upsert_package(
            db=db,
            space_id=payload.space_id,
            kind=PackageKind.rule,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    async def list_packages(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: PackageKind,
        actor_user_id: str,
        is_admin: bool,
    ) -> List[PackageRecord]:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin)
        rows = await self.repo.list_packages(db, space_id=space_id, kind=kind.value)
        return [self._pkg_to_domain(x) for x in rows]

    async def diff_packages(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: PackageKind,
        from_version: str,
        to_version: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> PackageDiffResponse:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin)
        from_pkg = await self.repo.get_package(db, space_id, kind.value, from_version)
        to_pkg = await self.repo.get_package(db, space_id, kind.value, to_version)
        if not from_pkg or not to_pkg:
            raise HTTPException(status_code=404, detail="from/to package version not found")

        summary: Dict[str, Any] = {}
        breaking_changes: List[str] = []

        if kind == PackageKind.schema:
            old_entities = {e.get("name") for e in (from_pkg.payload or {}).get("entity_types", [])}
            new_entities = {e.get("name") for e in (to_pkg.payload or {}).get("entity_types", [])}
            added = sorted(x for x in (new_entities - old_entities) if x)
            removed = sorted(x for x in (old_entities - new_entities) if x)
            summary = {
                "added_entity_types": added,
                "removed_entity_types": removed,
                "entity_type_count_from": len(old_entities),
                "entity_type_count_to": len(new_entities),
            }
            if removed:
                breaking_changes.append(f"removed entity types: {', '.join(removed)}")
        elif kind == PackageKind.rule:
            old_rules = {r.get("rule_id") for r in (from_pkg.payload or {}).get("rules", [])}
            new_rules = {r.get("rule_id") for r in (to_pkg.payload or {}).get("rules", [])}
            added = sorted(x for x in (new_rules - old_rules) if x)
            removed = sorted(x for x in (old_rules - new_rules) if x)
            summary = {
                "added_rules": added,
                "removed_rules": removed,
                "rule_count_from": len(old_rules),
                "rule_count_to": len(new_rules),
            }
            if removed:
                breaking_changes.append(f"removed rules: {', '.join(removed)}")
        else:
            old_map = (from_pkg.payload or {}).get("entity_mappings", [])
            new_map = (to_pkg.payload or {}).get("entity_mappings", [])
            old_rel = (from_pkg.payload or {}).get("relation_mappings", [])
            new_rel = (to_pkg.payload or {}).get("relation_mappings", [])
            summary = {
                "entity_mapping_count_from": len(old_map),
                "entity_mapping_count_to": len(new_map),
                "relation_mapping_count_from": len(old_rel),
                "relation_mapping_count_to": len(new_rel),
                "entity_mapping_delta": len(new_map) - len(old_map),
                "relation_mapping_delta": len(new_rel) - len(old_rel),
            }

        return PackageDiffResponse(
            space_id=space_id,
            kind=kind,
            from_version=from_version,
            to_version=to_version,
            summary=summary,
            breaking_changes=breaking_changes,
        )

    async def release(
        self,
        db: AsyncSession,
        payload: ReleaseRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> ReleaseResult:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="governance")

        record = await self.repo.get_package(db, payload.space_id, payload.kind.value, payload.version)
        if not record:
            raise HTTPException(status_code=404, detail="package version not found")
        if payload.target_stage == VersionStage.draft:
            raise HTTPException(status_code=400, detail="release target_stage cannot be draft")

        current_stage = VersionStage(record.stage)
        self._validate_stage_transition(current_stage, payload.target_stage)
        await self._require_approval_for_release(
            db,
            space_id=payload.space_id,
            kind=payload.kind,
            version=payload.version,
            target_stage=payload.target_stage,
        )

        warnings: List[str] = []
        if payload.target_stage == VersionStage.ga:
            previous_active = await self.repo.find_other_active_package(
                db,
                space_id=payload.space_id,
                kind=payload.kind.value,
                exclude_id=record.id,
            )
            warnings.extend(self._collect_release_warnings(previous_active, record))
            if payload.strict_compatibility and warnings:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "compatibility checks failed", "warnings": warnings},
                )
            await self.repo.switch_active_package(
                db,
                space_id=payload.space_id,
                kind=payload.kind.value,
                target=record,
                deprecate_previous=True,
            )
        else:
            # 只在 GA 时标记 active；其余阶段保持 false
            if payload.target_stage != VersionStage.ga:
                record.is_active = False

        record.stage = payload.target_stage.value
        record.notes = payload.notes
        record.updated_at = utc_now()

        release_event = OntologyReleaseEventModel(
            id=f"onto-release-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            package_id=record.id,
            kind=payload.kind.value,
            version=payload.version,
            from_stage=current_stage.value,
            to_stage=payload.target_stage.value,
            actor_user_id=actor_user_id,
            notes=payload.notes,
            warnings=warnings,
            created_at=utc_now(),
        )
        db.add(release_event)

        await db.commit()
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.package.release",
            output_result=f"{payload.kind.value}:{payload.version}:{payload.target_stage.value}",
        )
        return ReleaseResult(
            ok=True,
            space_id=payload.space_id,
            kind=payload.kind,
            version=payload.version,
            stage=payload.target_stage,
            warnings=warnings,
        )

    async def submit_approval(
        self,
        db: AsyncSession,
        payload: ApprovalSubmitRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> ApprovalRecord:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="approve_request")
        pkg = await self.repo.get_package(db, payload.space_id, payload.kind.value, payload.version)
        if not pkg:
            raise HTTPException(status_code=404, detail="package version not found")
        if payload.target_stage == VersionStage.draft:
            raise HTTPException(status_code=400, detail="approval target_stage cannot be draft")
        self._validate_stage_transition(VersionStage(pkg.stage), payload.target_stage)

        pending = await self.repo.get_pending_release_gate(
            db,
            space_id=payload.space_id,
            kind=payload.kind.value,
            version=payload.version,
            requested_stage=payload.target_stage.value,
        )
        if pending:
            raise HTTPException(status_code=409, detail="a pending approval already exists for this release gate")

        approval = OntologyApprovalModel(
            id=f"onto-appr-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            package_id=pkg.id,
            kind=payload.kind.value,
            version=payload.version,
            requested_stage=payload.target_stage.value,
            status=ApprovalStatus.pending.value,
            requester_user_id=actor_user_id,
            request_note=payload.note,
            created_at=utc_now(),
        )
        approval = await self.repo.create_approval(db, approval)
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.approval.submit",
            output_result=approval.id,
        )
        return self._approval_to_domain(approval)

    async def list_approvals(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
        kind: Optional[PackageKind] = None,
        status: Optional[ApprovalStatus] = None,
    ) -> List[ApprovalRecord]:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin)
        rows = await self.repo.list_approvals(
            db,
            space_id=space_id,
            kind=kind.value if kind else None,
            status=status.value if status else None,
        )
        return [self._approval_to_domain(item) for item in rows]

    async def review_approval(
        self,
        db: AsyncSession,
        payload: ApprovalReviewRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> ApprovalRecord:
        approval = await self.repo.get_approval(db, payload.approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="approval not found")

        await self._ensure_space_access(db, approval.space_id, actor_user_id, is_admin, action="review_approval")
        if actor_user_id == approval.requester_user_id:
            raise HTTPException(status_code=403, detail="requester cannot review own approval")

        if approval.status != ApprovalStatus.pending.value:
            raise HTTPException(status_code=409, detail="approval already reviewed")

        approval.status = ApprovalStatus.approved.value if payload.approve else ApprovalStatus.rejected.value
        approval.reviewer_user_id = actor_user_id
        approval.review_note = payload.review_note
        approval.reviewed_at = utc_now()
        await db.commit()
        await db.refresh(approval)
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.approval.review",
            output_result=approval.id,
        )
        return self._approval_to_domain(approval)

    async def rollback(
        self,
        db: AsyncSession,
        payload: RollbackRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> ReleaseResult:
        await self._ensure_space_access(db, payload.space_id, actor_user_id, is_admin, action="governance")

        target = await self.repo.get_package(db, payload.space_id, payload.kind.value, payload.target_version)
        if not target:
            raise HTTPException(status_code=404, detail="target version not found")

        previous_active = await self.repo.get_active_package(db, payload.space_id, payload.kind.value)
        current_stage = VersionStage(target.stage)
        warnings = self._collect_release_warnings(previous_active, target)

        await self.repo.switch_active_package(
            db,
            space_id=payload.space_id,
            kind=payload.kind.value,
            target=target,
            deprecate_previous=True,
        )
        target.notes = payload.notes

        event = OntologyReleaseEventModel(
            id=f"onto-release-{uuid.uuid4().hex[:10]}",
            space_id=payload.space_id,
            package_id=target.id,
            kind=payload.kind.value,
            version=payload.target_version,
            from_stage=current_stage.value,
            to_stage=VersionStage.ga.value,
            actor_user_id=actor_user_id,
            notes=payload.notes or "rollback to target version",
            warnings=warnings,
            created_at=utc_now(),
        )
        db.add(event)
        await db.commit()
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.package.rollback",
            output_result=f"{payload.kind.value}:{payload.target_version}",
        )
        return ReleaseResult(
            ok=True,
            space_id=payload.space_id,
            kind=payload.kind,
            version=payload.target_version,
            stage=VersionStage.ga,
            warnings=warnings,
        )

    async def list_release_events(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
        kind: Optional[PackageKind] = None,
    ) -> List[Dict[str, Any]]:
        await self._ensure_space_access(db, space_id, actor_user_id, is_admin)
        rows = await self.repo.list_release_events(db, space_id=space_id, kind=kind.value if kind else None)
        return [
            {
                "id": r.id,
                "space_id": r.space_id,
                "package_id": r.package_id,
                "kind": r.kind,
                "version": r.version,
                "from_stage": r.from_stage,
                "to_stage": r.to_stage,
                "actor_user_id": r.actor_user_id,
                "notes": r.notes,
                "warnings": r.warnings or [],
                "created_at": r.created_at,
            }
            for r in rows
        ]

    async def execute_mapping(
        self,
        db: AsyncSession,
        req: MappingExecuteRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> MappingExecuteResponse:
        await self._ensure_space_access(db, req.space_id, actor_user_id, is_admin, action="execute")

        mapping_record = await self._resolve_package(db, req.space_id, PackageKind.mapping, req.mapping_version)
        schema_record: Optional[OntologyPackageModel] = None
        try:
            schema_record = await self._resolve_package(db, req.space_id, PackageKind.schema, req.schema_version, required=False)
        except HTTPException:
            schema_record = None

        payload = mapping_record.payload or {}
        entity_rules = [EntityMappingRule.model_validate(x) for x in payload.get("entity_mappings", [])]
        relation_rules = payload.get("relation_mappings", [])

        entities: Dict[str, EntityInstance] = {}
        relations: List[RelationInstance] = []
        trace: List[MappingTraceItem] = []

        for rule in entity_rules:
            rows = self._resolve_source_rows(req.input_payload, rule.source_path)
            if not rows:
                trace.append(MappingTraceItem(code="MAPPING_SOURCE_EMPTY", message=f"entity source has no rows: {rule.entity_type}", source_path=rule.source_path))
                continue

            for idx, row in enumerate(rows):
                ctx = {"row": row, "root": req.input_payload, "index": idx}
                entity_id = self._render_template(rule.id_template, ctx)
                if not entity_id:
                    trace.append(MappingTraceItem(code="MAPPING_ENTITY_ID_EMPTY", message=f"entity id_template rendered empty for {rule.entity_type}", target=rule.entity_type))
                    continue

                attrs: Dict[str, Any] = {}
                for fm in rule.field_mappings:
                    raw = self._pick_value(row, req.input_payload, fm.source_path)
                    if raw is None:
                        raw = fm.default_value
                    if raw is None and fm.required:
                        trace.append(MappingTraceItem(code="MAPPING_REQUIRED_MISSING", message=f"required source missing: {fm.source_path}", source_path=fm.source_path, target=f"{rule.entity_type}.{fm.target_attr}"))
                        continue
                    attrs[fm.target_attr] = self._apply_transform(raw, fm.transform)

                entities[entity_id] = EntityInstance(id=entity_id, entity_type=rule.entity_type, attributes=attrs)

        for rel in relation_rules:
            source_path = rel.get("source_path")
            rows = self._resolve_source_rows(req.input_payload, source_path)
            if not rows:
                rows = [req.input_payload]

            for idx, row in enumerate(rows):
                ctx = {"row": row, "root": req.input_payload, "index": idx}
                source_id = self._render_template(rel.get("source_entity_template", ""), ctx)
                target_id = self._render_template(rel.get("target_entity_template", ""), ctx)

                if source_id not in entities or target_id not in entities:
                    trace.append(
                        MappingTraceItem(
                            code="MAPPING_RELATION_SKIPPED",
                            message="relation skipped because source or target entity not found",
                            target=f"{rel.get('relation_type')}:{source_id}->{target_id}",
                            source_path=source_path,
                        )
                    )
                    continue

                relations.append(
                    RelationInstance(
                        relation_type=rel.get("relation_type", "related_to"),
                        source_id=source_id,
                        target_id=target_id,
                        attributes=rel.get("attributes", {}) or {},
                    )
                )

        if schema_record:
            trace.extend(self._validate_graph_against_schema(list(entities.values()), schema_record.payload or {}))

        if len(trace) > settings.ONTOLOGY_MAX_TRACE_ITEMS:
            trace = trace[: settings.ONTOLOGY_MAX_TRACE_ITEMS]
            trace.append(
                MappingTraceItem(
                    code="TRACE_TRUNCATED",
                    message=f"trace truncated to {settings.ONTOLOGY_MAX_TRACE_ITEMS} items",
                )
            )

        graph = InstanceGraph(
            entities=list(entities.values()),
            relations=relations,
            metadata={
                "space_id": req.space_id,
                "mapping_version": mapping_record.version,
                "schema_version": schema_record.version if schema_record else None,
            },
        )

        response = MappingExecuteResponse(
            graph=graph,
            mapping_version=mapping_record.version,
            schema_version=schema_record.version if schema_record else None,
            trace=trace,
        )
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.mapping.execute",
            output_result=f"{req.space_id}:{mapping_record.version}",
        )
        return response

    async def evaluate_rules(
        self,
        db: AsyncSession,
        req: RuleEvaluateRequest,
        actor_user_id: str,
        is_admin: bool,
    ) -> DecisionResult:
        await self._ensure_space_access(db, req.space_id, actor_user_id, is_admin, action="execute")
        rule_record = await self._resolve_package(db, req.space_id, PackageKind.rule, req.rule_version)

        rules = [RuleDef.model_validate(item) for item in (rule_record.payload or {}).get("rules", [])]
        hits: List[RuleHit] = []
        misses: List[RuleMiss] = []

        by_type: Dict[str, List[EntityInstance]] = defaultdict(list)
        for entity in req.graph.entities:
            by_type[entity.entity_type].append(entity)

        for rule in rules:
            scope_entities: Iterable[Optional[EntityInstance]]
            if rule.target_entity_type:
                scope_entities = by_type.get(rule.target_entity_type, [])
                if not scope_entities:
                    misses.append(RuleMiss(rule_id=rule.rule_id, reason=f"no entity for target type {rule.target_entity_type}"))
                    continue
            else:
                scope_entities = [None]

            rule_hit = False
            for entity in scope_entities:
                ok, reason = self._evaluate_conditions(rule.conditions, entity, req.graph, req.context)
                if ok:
                    hits.append(
                        RuleHit(
                            rule_id=rule.rule_id,
                            name=rule.name,
                            severity=rule.severity,
                            action=rule.action,
                            entity_id=entity.id if entity else None,
                            reason=reason,
                        )
                    )
                    rule_hit = True
            if not rule_hit:
                misses.append(RuleMiss(rule_id=rule.rule_id, reason="conditions not met"))

        risk_score = sum(_SEVERITY_WEIGHTS.get(hit.severity, 0) for hit in hits)
        risk_level = self._to_risk_level(risk_score)

        decision = DecisionResult(
            decision_id=f"decision-{uuid.uuid4().hex[:10]}",
            space_id=req.space_id,
            rule_version=rule_record.version,
            risk_score=risk_score,
            risk_level=risk_level,
            hits=hits,
            misses=misses,
            created_at=utc_now(),
        )

        explanation = self._build_explanation(decision, req)

        decision_model = OntologyDecisionModel(
            id=decision.decision_id,
            space_id=decision.space_id,
            rule_version=decision.rule_version,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            hits=[h.model_dump() for h in decision.hits],
            misses=[m.model_dump() for m in decision.misses],
            graph_snapshot=req.graph.model_dump(),
            context=req.context,
            created_by=actor_user_id,
            created_at=decision.created_at,
        )
        explanation_model = OntologyExplanationModel(
            decision_id=decision.decision_id,
            why=explanation.why,
            why_not=explanation.why_not,
            evidence=explanation.evidence,
            created_at=utc_now(),
        )
        await self.repo.create_decision_with_explanation(
            db,
            decision_model=decision_model,
            explanation_model=explanation_model,
        )
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.rules.evaluate",
            output_result=decision.decision_id,
        )
        return decision

    async def explain(
        self,
        db: AsyncSession,
        decision_id: str,
        actor_user_id: str,
        is_admin: bool,
    ) -> ExplanationResponse:
        decision = await self.repo.get_decision(db, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="decision not found")

        await self._ensure_space_access(db, decision.space_id, actor_user_id, is_admin)

        exp = await self.repo.get_explanation(db, decision_id)
        if not exp:
            raise HTTPException(status_code=404, detail="explanation not found")

        decision_domain = DecisionResult(
            decision_id=decision.id,
            space_id=decision.space_id,
            rule_version=decision.rule_version,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            hits=[RuleHit.model_validate(x) for x in (decision.hits or [])],
            misses=[RuleMiss.model_validate(x) for x in (decision.misses or [])],
            created_at=decision.created_at,
        )
        return ExplanationResponse(
            decision=decision_domain,
            why=(exp.why or []),
            why_not=(exp.why_not or []),
            evidence=(exp.evidence or {}),
        )

    async def _upsert_package(
        self,
        *,
        db: AsyncSession,
        space_id: str,
        kind: PackageKind,
        version: str,
        payload: Dict[str, Any],
        actor_user_id: str,
    ) -> PackageRecord:
        self._assert_version(version)

        existed = await self.repo.get_package(db, space_id, kind.value, version)
        now = utc_now()

        if existed:
            existed.payload = payload
            existed.updated_at = now
            model = existed
        else:
            model = OntologyPackageModel(
                id=f"onto-pkg-{uuid.uuid4().hex[:10]}",
                space_id=space_id,
                kind=kind.value,
                version=version,
                stage=VersionStage.draft.value,
                is_active=False,
                payload=payload,
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
        model = await self.repo.upsert_package(db, existed=existed, new_model=model)
        await self._try_audit(
            db,
            user_id=actor_user_id,
            action_name="ontology.package.upsert",
            output_result=f"{kind.value}:{version}",
        )
        return self._pkg_to_domain(model)

    async def _resolve_package(
        self,
        db: AsyncSession,
        space_id: str,
        kind: PackageKind,
        version: Optional[str],
        *,
        required: bool = True,
    ) -> Optional[OntologyPackageModel]:
        if version:
            row = await self.repo.get_package(db, space_id, kind.value, version)
            if row:
                return row
            if required:
                raise HTTPException(status_code=404, detail=f"{kind.value} package version not found")
            return None

        active = await self.repo.get_active_package(db, space_id, kind.value)
        if active:
            return active

        if required:
            raise HTTPException(status_code=404, detail=f"no active {kind.value} package version")
        return None

    async def _ensure_space_access(
        self,
        db: AsyncSession,
        space_id: str,
        actor_user_id: str,
        is_admin: bool,
        *,
        action: str = "read",
    ) -> OntologySpaceModel:
        space = await self.repo.get_space_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="ontology space not found")

        if is_admin or space.owner_user_id == actor_user_id:
            return space
        if settings.ENABLE_ORG_TENANCY and space.org_id:
            role = await self._resolve_org_membership_role(db, org_id=space.org_id, user_id=actor_user_id)
            if role and self._org_action_allowed(role, action):
                return space
        raise HTTPException(status_code=403, detail="forbidden to access this ontology space")

    async def _resolve_org_membership_role(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        user_id: str,
    ) -> Optional[str]:
        """Backward-compatible membership lookup across repo implementations."""
        get_membership = getattr(self.repo, "get_org_membership", None)
        if callable(get_membership):
            membership = await get_membership(db, org_id=org_id, user_id=user_id)
            if membership:
                return (getattr(membership, "role", None) or "member").lower()

        is_member = getattr(self.repo, "is_org_member", None)
        if callable(is_member):
            ok = await is_member(db, org_id=org_id, user_id=user_id)
            if ok:
                return "member"
        return None

    def _org_action_allowed(self, role: str, action: str) -> bool:
        granted = self._org_role_permissions.get((role or "").lower(), set())
        return action in granted

    @staticmethod
    def _sanitize_data_source_config(config: Dict[str, Any]) -> Dict[str, Any]:
        blocked = {"password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "access_token", "refresh_token"}
        sanitized = deepcopy(config or {})
        for key in list(sanitized.keys()):
            if key.lower() in blocked:
                sanitized.pop(key, None)
        return sanitized

    def _validate_data_source_config(self, payload: OntologyDataSourceCreate) -> None:
        protocol = payload.protocol.strip().lower()
        config = payload.config or {}
        if payload.kind == DataSourceKind.database:
            if protocol not in {"postgresql", "mysql", "sqlite", "mssql", "oracle"}:
                raise HTTPException(status_code=400, detail="unsupported database protocol")
            if protocol != "sqlite":
                for field in ("host", "database"):
                    if not str(config.get(field, "")).strip():
                        raise HTTPException(status_code=400, detail=f"database config requires {field}")
                if "password" in config or "token" in config:
                    raise HTTPException(status_code=400, detail="do not store database secrets in config; use secret_ref")
        elif payload.kind == DataSourceKind.api:
            if protocol not in {"rest", "graphql", "openapi", "webhook"}:
                raise HTTPException(status_code=400, detail="unsupported api protocol")
            if not str(config.get("base_url", "")).strip():
                raise HTTPException(status_code=400, detail="api config requires base_url")
            if "token" in config or "api_key" in config or "authorization" in config:
                raise HTTPException(status_code=400, detail="do not store api secrets in config; use secret_ref")
        elif payload.kind == DataSourceKind.protocol:
            if protocol not in {"mcp", "s3", "oss", "kafka", "mqtt", "amqp", "ftp", "sftp"}:
                raise HTTPException(status_code=400, detail="unsupported protocol")
        elif payload.kind not in {DataSourceKind.file, DataSourceKind.stream}:
            raise HTTPException(status_code=400, detail="unsupported data source kind")

    @staticmethod
    def _dry_run_data_source(model: OntologyDataSourceModel) -> DataSourceTestResult:
        config = model.config or {}
        capabilities: Dict[str, Any] = {"protocol": model.protocol, "kind": model.kind, "dry_run": True}
        if model.kind == DataSourceKind.database.value:
            required = ["host", "database"] if model.protocol != "sqlite" else ["path"]
            missing = [item for item in required if not str(config.get(item, "")).strip()]
            if missing:
                return DataSourceTestResult(ok=False, status="invalid", message=f"missing config: {', '.join(missing)}", capabilities=capabilities)
            capabilities["supports_schema_introspection"] = True
            return DataSourceTestResult(ok=True, status="ready", message="database connector config is valid; live probe requires connector runtime", capabilities=capabilities)
        if model.kind == DataSourceKind.api.value:
            if not str(config.get("base_url", "")).strip():
                return DataSourceTestResult(ok=False, status="invalid", message="missing config: base_url", capabilities=capabilities)
            capabilities["supports_openapi"] = model.protocol == "openapi"
            return DataSourceTestResult(ok=True, status="ready", message="api connector config is valid; live probe is disabled by default for SSRF safety", capabilities=capabilities)
        return DataSourceTestResult(ok=True, status="ready", message="connector config is registered; runtime adapter can be attached later", capabilities=capabilities)

    @staticmethod
    def _normalize_secret_part(value: str) -> str:
        text = (value or "").strip()
        if not re.match(r"^[A-Za-z0-9_.-]{1,120}$", text):
            raise HTTPException(status_code=400, detail="secret scope/name only supports letters, digits, dot, underscore and dash")
        return text

    def _encrypt_secret(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt_secret(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise HTTPException(status_code=500, detail="failed to decrypt ontology secret; check ENCRYPTION_KEY/SECRET_KEY") from exc

    async def _resolve_secret_value(self, secret_ref: Optional[str], db: Optional[AsyncSession] = None, space_id: Optional[str] = None) -> Optional[str]:
        if not secret_ref:
            return None
        ref = secret_ref.strip()
        if ref.startswith("env:"):
            return os.getenv(ref.removeprefix("env:").strip())
        if ref.startswith("ENV:"):
            return os.getenv(ref.removeprefix("ENV:").strip())
        if ref.startswith("secret://"):
            if not db or not space_id:
                raise HTTPException(status_code=400, detail="secret:// requires ontology space context")
            parts = ref.removeprefix("secret://").split("/", 1)
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail="secret ref must be secret://scope/name")
            scope = self._normalize_secret_part(parts[0])
            name = self._normalize_secret_part(parts[1])
            secret = await self.repo.get_secret_by_ref(db, space_id=space_id, scope=scope, name=name)
            if not secret:
                raise HTTPException(status_code=404, detail=f"secret not found: secret://{scope}/{name}")
            return self._decrypt_secret(secret.encrypted_value)
        return None

    @staticmethod
    def _normalize_discovered_type(raw_type: str) -> str:
        text = (raw_type or "").lower()
        if text in {"integer", "int"} or any(token in text for token in ("serial", "bigint", "smallint")):
            return "integer"
        if text == "number" or any(token in text for token in ("numeric", "decimal", "double", "real", "float", "money")):
            return "number"
        if text == "boolean" or any(token in text for token in ("bool",)):
            return "boolean"
        if any(token in text for token in ("json", "object", "record")):
            return "object"
        if any(token in text for token in ("array", "list")):
            return "array"
        return "string"

    async def _discover_database(self, db: AsyncSession, model: OntologyDataSourceModel) -> DataSourceDiscoveryResult:
        protocol = (model.protocol or "").lower()
        if protocol == "postgresql":
            return await self._discover_postgresql(db, model)
        if protocol == "mysql":
            return DataSourceDiscoveryResult(
                ok=False,
                status="driver_missing",
                message="MySQL discovery requires an async MySQL adapter; PostgreSQL is available now",
                source_id=model.id,
                protocol=model.protocol,
                warnings=["后续可接 aiomysql/asyncmy 适配器；当前不在 pyproject 中强行新增驱动，避免影响现有部署。"],
            )
        return DataSourceDiscoveryResult(
            ok=False,
            status="unsupported",
            message=f"database protocol {model.protocol} discovery is not supported yet",
            source_id=model.id,
            protocol=model.protocol,
        )

    async def _discover_postgresql(self, db: AsyncSession, model: OntologyDataSourceModel) -> DataSourceDiscoveryResult:
        try:
            import asyncpg
        except Exception as exc:  # pragma: no cover - dependency exists in normal backend install
            raise HTTPException(status_code=500, detail=f"asyncpg is not available: {exc}") from exc

        config = model.config or {}
        schema = str(config.get("schema") or "public").strip() or "public"
        max_tables = min(max(int(config.get("max_tables") or 50), 1), 200)
        password = await self._resolve_secret_value(model.secret_ref, db=db, space_id=model.space_id)
        conn = None
        try:
            conn = await asyncpg.connect(
                host=str(config.get("host") or "127.0.0.1"),
                port=int(config.get("port") or 5432),
                user=str(config.get("user") or config.get("username") or "postgres"),
                password=password,
                database=str(config.get("database")),
                timeout=float(config.get("connect_timeout") or 5),
                ssl=config.get("ssl") if isinstance(config.get("ssl"), bool) else None,
            )
            rows = await conn.fetch(
                """
                WITH limited_tables AS (
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema = $1
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    LIMIT $2
                ),
                pk_cols AS (
                    SELECT
                        kcu.table_schema,
                        kcu.table_name,
                        kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                     AND tc.table_name = kcu.table_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_schema = $1
                )
                SELECT
                    c.table_schema,
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.udt_name,
                    c.is_nullable,
                    c.ordinal_position,
                    COALESCE(pk_cols.column_name IS NOT NULL, false) AS is_primary_key
                FROM information_schema.columns c
                JOIN limited_tables lt
                  ON lt.table_schema = c.table_schema
                 AND lt.table_name = c.table_name
                LEFT JOIN pk_cols
                  ON pk_cols.table_schema = c.table_schema
                 AND pk_cols.table_name = c.table_name
                 AND pk_cols.column_name = c.column_name
                ORDER BY c.table_name, c.ordinal_position
                """,
                schema,
                max_tables,
            )
        except Exception as exc:
            return DataSourceDiscoveryResult(
                ok=False,
                status="failed",
                message=f"PostgreSQL discovery failed: {exc}",
                source_id=model.id,
                protocol=model.protocol,
                entities=[],
            )
        finally:
            if conn:
                await conn.close()

        grouped: Dict[str, List[Any]] = defaultdict(list)
        for row in rows:
            grouped[str(row["table_name"])].append(row)

        entities: List[DiscoveredEntity] = []
        for table_name, table_rows in grouped.items():
            columns = [
                DiscoveredColumn(
                    name=str(row["column_name"]),
                    data_type=self._normalize_discovered_type(str(row["data_type"] or row["udt_name"])),
                    nullable=str(row["is_nullable"]).upper() == "YES",
                    primary_key=bool(row["is_primary_key"]),
                    source_path=f"{table_name}.{row['column_name']}",
                )
                for row in table_rows
            ]
            entities.append(
                DiscoveredEntity(
                    name=self._to_pascal_name(table_name),
                    source=f"{schema}.{table_name}",
                    columns=columns,
                    primary_keys=[col.name for col in columns if col.primary_key],
                )
            )

        return DataSourceDiscoveryResult(
            ok=True,
            status="ready",
            message=f"discovered {len(entities)} PostgreSQL tables",
            source_id=model.id,
            protocol=model.protocol,
            entities=entities,
            warnings=[] if len(entities) < max_tables else [f"结果已按 max_tables={max_tables} 截断"],
        )

    async def _discover_api(self, db: AsyncSession, model: OntologyDataSourceModel) -> DataSourceDiscoveryResult:
        config = model.config or {}
        spec = config.get("openapi") or config.get("openapi_json") or config.get("schema")
        warnings: List[str] = []
        if not spec:
            url = str(config.get("openapi_url") or "").strip()
            base_url = str(config.get("base_url") or "").rstrip("/")
            if not url and base_url:
                url = f"{base_url}/openapi.json"
            if not url:
                return DataSourceDiscoveryResult(
                    ok=False,
                    status="invalid",
                    message="api discovery requires config.openapi, config.schema, config.openapi_url, or base_url/openapi.json",
                    source_id=model.id,
                    protocol=model.protocol,
                )
            headers = {}
            token = await self._resolve_secret_value(model.secret_ref, db=db, space_id=model.space_id)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                async with httpx.AsyncClient(timeout=float(config.get("timeout") or 8), follow_redirects=False) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type or response.text.strip().startswith("{"):
                        spec = response.json()
                    else:
                        try:
                            import yaml
                        except Exception as exc:
                            raise HTTPException(status_code=500, detail="PyYAML is required to parse non-JSON OpenAPI specs") from exc
                        spec = yaml.safe_load(response.text)
            except HTTPException:
                raise
            except Exception as exc:
                return DataSourceDiscoveryResult(
                    ok=False,
                    status="failed",
                    message=f"OpenAPI discovery failed: {exc}",
                    source_id=model.id,
                    protocol=model.protocol,
                )

        entities = self._discover_entities_from_openapi(spec if isinstance(spec, dict) else {})
        if not entities:
            warnings.append("未从 OpenAPI components.schemas 中识别到对象；请确认接口暴露了 schema。")
        return DataSourceDiscoveryResult(
            ok=bool(entities),
            status="ready" if entities else "empty",
            message=f"discovered {len(entities)} API schemas",
            source_id=model.id,
            protocol=model.protocol,
            entities=entities,
            warnings=warnings,
        )

    @staticmethod
    def _to_pascal_name(value: str) -> str:
        parts = re.split(r"[^A-Za-z0-9]+", value or "")
        return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Entity"

    def _discover_entities_from_openapi(self, spec: Dict[str, Any]) -> List[DiscoveredEntity]:
        schemas = (((spec or {}).get("components") or {}).get("schemas") or {})
        if not isinstance(schemas, dict) and isinstance(spec.get("properties"), dict):
            schemas = {"Entity": spec}
        entities: List[DiscoveredEntity] = []
        for raw_name, schema in schemas.items():
            if not isinstance(schema, dict):
                continue
            resolved = self._resolve_json_schema_ref(schema, schemas)
            properties = resolved.get("properties") if isinstance(resolved, dict) else None
            if not isinstance(properties, dict):
                continue
            required = set(resolved.get("required") or [])
            columns: List[DiscoveredColumn] = []
            for prop_name, prop_schema in properties.items():
                prop = self._resolve_json_schema_ref(prop_schema, schemas) if isinstance(prop_schema, dict) else {}
                raw_type = str(prop.get("type") or prop.get("format") or "object")
                columns.append(
                    DiscoveredColumn(
                        name=str(prop_name),
                        data_type=self._normalize_discovered_type(raw_type),
                        nullable=str(prop_name) not in required,
                        primary_key=str(prop_name).lower() in {"id", f"{str(raw_name).lower()}_id"},
                        description=prop.get("description") if isinstance(prop.get("description"), str) else None,
                        source_path=str(prop_name),
                    )
                )
            entities.append(
                DiscoveredEntity(
                    name=self._to_pascal_name(str(raw_name)),
                    source=f"components.schemas.{raw_name}",
                    columns=columns,
                    primary_keys=[col.name for col in columns if col.primary_key],
                    description=resolved.get("description") if isinstance(resolved.get("description"), str) else None,
                )
            )
        return entities

    @staticmethod
    def _resolve_json_schema_ref(schema: Dict[str, Any], schemas: Dict[str, Any]) -> Dict[str, Any]:
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            target = ref.rsplit("/", 1)[-1]
            value = schemas.get(target)
            if isinstance(value, dict):
                return value
        return schema

    async def _require_approval_for_release(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: PackageKind,
        version: str,
        target_stage: VersionStage,
    ) -> None:
        require_staging = settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_STAGING
        require_ga = settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA
        must_require = (
            (target_stage == VersionStage.staging and require_staging)
            or (target_stage == VersionStage.ga and require_ga)
        )
        if not must_require:
            return

        gate = await self.repo.get_approved_release_gate(
            db,
            space_id=space_id,
            kind=kind.value,
            version=version,
            requested_stage=target_stage.value,
        )
        if not gate:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "release approval required",
                    "required_stage": target_stage.value,
                    "kind": kind.value,
                    "version": version,
                },
            )

    @staticmethod
    def _approval_to_domain(model: OntologyApprovalModel) -> ApprovalRecord:
        return ApprovalRecord(
            id=model.id,
            space_id=model.space_id,
            package_id=model.package_id,
            kind=PackageKind(model.kind),
            version=model.version,
            requested_stage=VersionStage(model.requested_stage),
            status=ApprovalStatus(model.status),
            requester_user_id=model.requester_user_id,
            reviewer_user_id=model.reviewer_user_id,
            request_note=model.request_note,
            review_note=model.review_note,
            reviewed_at=model.reviewed_at,
            created_at=model.created_at,
        )

    @staticmethod
    def _data_source_to_domain(model: OntologyDataSourceModel) -> OntologyDataSourceRecord:
        return OntologyDataSourceRecord(
            id=model.id,
            space_id=model.space_id,
            name=model.name,
            kind=DataSourceKind(model.kind),
            protocol=model.protocol,
            config=model.config or {},
            secret_ref=model.secret_ref,
            status=DataSourceStatus(model.status),
            last_test_status=model.last_test_status,
            last_test_message=model.last_test_message,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _secret_to_domain(model: OntologySecretModel) -> OntologySecretRecord:
        return OntologySecretRecord(
            id=model.id,
            space_id=model.space_id,
            scope=model.scope,
            name=model.name,
            ref=f"secret://{model.scope}/{model.name}",
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def _try_audit(self, db: AsyncSession, *, user_id: str, action_name: str, output_result: str) -> None:
        try:
            await audit_service.log_action(
                db,
                user_id=user_id,
                action_name=action_name,
                status="success",
                output_result=output_result,
            )
        except Exception:
            # 审计失败不影响主流程
            pass

    @staticmethod
    def _space_to_domain(space: OntologySpaceModel) -> OntologySpace:
        return OntologySpace(
            id=space.id,
            name=space.name,
            code=space.code,
            description=space.description,
            owner_user_id=space.owner_user_id,
            org_id=space.org_id,
            created_at=space.created_at,
        )

    @staticmethod
    def _org_to_domain(model: OrganizationModel) -> OrganizationRecord:
        return OrganizationRecord(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            owner_user_id=model.owner_user_id,
            is_active=bool(model.is_active),
            created_at=model.created_at,
        )

    @staticmethod
    def _org_member_to_domain(model) -> OrganizationMemberRecord:
        return OrganizationMemberRecord(
            id=model.id,
            org_id=model.org_id,
            user_id=model.user_id,
            role=model.role,
            is_active=bool(model.is_active),
            created_at=model.created_at,
        )

    @staticmethod
    def _pkg_to_domain(pkg: OntologyPackageModel) -> PackageRecord:
        return PackageRecord(
            kind=PackageKind(pkg.kind),
            space_id=pkg.space_id,
            version=pkg.version,
            stage=VersionStage(pkg.stage),
            created_by=pkg.created_by,
            created_at=pkg.created_at,
            updated_at=pkg.updated_at or pkg.created_at,
            notes=pkg.notes,
            payload=deepcopy(pkg.payload or {}),
        )

    @staticmethod
    def _normalize_code(value: str) -> str:
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_\-]", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text[:64] or f"space-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _assert_version(version: str) -> None:
        if not re.match(r"^\d+\.\d+\.\d+$", version or ""):
            raise HTTPException(status_code=400, detail="version must follow semver like 1.0.0")

    @staticmethod
    def _validate_stage_transition(current: VersionStage, target: VersionStage) -> None:
        allowed = {
            VersionStage.draft: {VersionStage.review, VersionStage.deprecated},
            VersionStage.review: {VersionStage.staging, VersionStage.deprecated},
            VersionStage.staging: {VersionStage.ga, VersionStage.deprecated},
            VersionStage.ga: {VersionStage.deprecated},
            VersionStage.deprecated: set(),
        }
        if target == current:
            return
        if target not in allowed[current]:
            raise HTTPException(status_code=400, detail=f"invalid stage transition: {current.value} -> {target.value}")

    def _collect_release_warnings(
        self,
        previous_active: Optional[OntologyPackageModel],
        candidate: OntologyPackageModel,
    ) -> List[str]:
        warnings: List[str] = []
        if not previous_active:
            return warnings

        old_major = int((previous_active.version or "0.0.0").split(".")[0])
        new_major = int((candidate.version or "0.0.0").split(".")[0])
        if new_major != old_major:
            return warnings

        if candidate.kind == PackageKind.schema.value:
            old_entities = {e.get("name") for e in (previous_active.payload or {}).get("entity_types", [])}
            new_entities = {e.get("name") for e in (candidate.payload or {}).get("entity_types", [])}
            removed = sorted(old_entities - new_entities)
            if removed:
                warnings.append(
                    f"schema removes entity types without major bump: {', '.join(removed)}"
                )

        if candidate.kind == PackageKind.rule.value:
            old_rules = {r.get("rule_id") for r in (previous_active.payload or {}).get("rules", [])}
            new_rules = {r.get("rule_id") for r in (candidate.payload or {}).get("rules", [])}
            removed = sorted(old_rules - new_rules)
            if removed:
                warnings.append(
                    f"rule package removes rules without major bump: {', '.join(removed)}"
                )

        return warnings

    @staticmethod
    def _resolve_source_rows(payload: Dict[str, Any], source_path: Optional[str]) -> List[Dict[str, Any]]:
        if not source_path:
            return [payload]
        value = PersistentOntologyService._get_path(payload, source_path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _get_path(data: Any, path: str) -> Any:
        cur = data
        for part in (path or "").split("."):
            if part == "":
                continue
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @staticmethod
    def _pick_value(row: Dict[str, Any], root: Dict[str, Any], path: str) -> Any:
        value = PersistentOntologyService._get_path(row, path)
        if value is None:
            value = PersistentOntologyService._get_path(root, path)
        return value

    @staticmethod
    def _render_template(template: str, ctx: Dict[str, Any]) -> str:
        if not template:
            return ""

        def replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if expr.startswith("row."):
                return str(PersistentOntologyService._get_path(ctx.get("row", {}), expr[4:]) or "")
            if expr.startswith("root."):
                return str(PersistentOntologyService._get_path(ctx.get("root", {}), expr[5:]) or "")
            if expr == "index":
                return str(ctx.get("index", ""))
            return str(PersistentOntologyService._get_path(ctx.get("row", {}), expr) or "")

        rendered = re.sub(r"\{\{\s*([^}]+)\s*\}\}", replace, template)
        return rendered.strip()

    @staticmethod
    def _apply_transform(value: Any, transform: Any) -> Any:
        if value is None or transform is None:
            return value

        name = getattr(transform, "value", transform)
        try:
            if name == "trim":
                return str(value).strip()
            if name == "lower":
                return str(value).lower()
            if name == "upper":
                return str(value).upper()
            if name == "to_int":
                return int(value)
            if name == "to_float":
                return float(value)
            if name == "to_bool":
                text = str(value).strip().lower()
                return text in {"1", "true", "yes", "y", "on"}
        except Exception:
            return value
        return value

    def _validate_graph_against_schema(
        self,
        entities: List[EntityInstance],
        schema_payload: Dict[str, Any],
    ) -> List[MappingTraceItem]:
        trace: List[MappingTraceItem] = []
        schema_entities = {item.get("name"): item for item in schema_payload.get("entity_types", [])}

        for entity in entities:
            schema = schema_entities.get(entity.entity_type)
            if not schema:
                trace.append(
                    MappingTraceItem(
                        code="SCHEMA_ENTITY_UNKNOWN",
                        message=f"entity type not found in schema: {entity.entity_type}",
                        target=entity.entity_type,
                    )
                )
                continue

            attrs = schema.get("attributes", {})
            for name, item in attrs.items():
                if item.get("required") and entity.attributes.get(name) is None:
                    trace.append(
                        MappingTraceItem(
                            code="SCHEMA_REQUIRED_MISSING",
                            message=f"required attribute missing: {name}",
                            target=f"{entity.id}.{name}",
                        )
                    )

        return trace

    def _evaluate_conditions(
        self,
        conditions: List[Any],
        entity: Optional[EntityInstance],
        graph: InstanceGraph,
        context: Dict[str, Any],
    ) -> Tuple[bool, str]:
        for cond in conditions:
            left = self._resolve_condition_path(cond.path, entity, graph, context)
            ok = self._compare(left, cond.operator, cond.value)
            if not ok:
                return False, f"condition failed: {cond.path} {cond.operator}"
        return True, "all conditions matched"

    @staticmethod
    def _resolve_condition_path(path: str, entity: Optional[EntityInstance], graph: InstanceGraph, context: Dict[str, Any]) -> Any:
        if path.startswith("entity."):
            if not entity:
                return None
            key = path[len("entity."):]
            if key == "id":
                return entity.id
            if key == "type":
                return entity.entity_type
            return entity.attributes.get(key)

        if path.startswith("context."):
            key = path[len("context."):]
            return PersistentOntologyService._get_path(context, key)

        if path.startswith("graph."):
            key = path[len("graph."):]
            if key == "entity_count":
                return len(graph.entities)
            if key == "relation_count":
                return len(graph.relations)

        return None

    @staticmethod
    def _compare(left: Any, operator: str, right: Any) -> bool:
        if operator == "exists":
            return left is not None and left != ""
        if operator == "eq":
            return left == right
        if operator == "neq":
            return left != right
        if operator == "gt":
            return left is not None and right is not None and left > right
        if operator == "gte":
            return left is not None and right is not None and left >= right
        if operator == "lt":
            return left is not None and right is not None and left < right
        if operator == "lte":
            return left is not None and right is not None and left <= right
        if operator == "contains":
            if left is None:
                return False
            if isinstance(left, list):
                return right in left
            return str(right) in str(left)
        if operator == "in":
            if right is None:
                return False
            try:
                return left in right
            except TypeError:
                return False
        return False

    @staticmethod
    def _to_risk_level(score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 40:
            return "high"
        if score >= 20:
            return "medium"
        return "low"

    @staticmethod
    def _build_explanation(decision: DecisionResult, req: RuleEvaluateRequest) -> ExplanationResponse:
        why = [f"hit rule {h.rule_id} ({h.severity}) on entity {h.entity_id or 'global'}" for h in decision.hits[:12]]
        why_not = [f"rule {m.rule_id} not triggered: {m.reason}" for m in decision.misses[:12]]

        evidence = {
            "graph_entity_count": len(req.graph.entities),
            "graph_relation_count": len(req.graph.relations),
            "rule_version": decision.rule_version,
            "risk_score": decision.risk_score,
            "risk_level": decision.risk_level,
        }

        return ExplanationResponse(
            decision=decision,
            why=why,
            why_not=why_not,
            evidence=evidence,
        )


persistent_ontology_service = PersistentOntologyService()
