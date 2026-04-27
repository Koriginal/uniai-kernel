from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.models.ontology import (
    OntologyApprovalModel,
    OntologyDecisionModel,
    OntologyExplanationModel,
    OntologyPackageModel,
    OntologyReleaseEventModel,
    OntologySpaceModel,
    OntologyDataSourceModel,
    OntologySecretModel,
)
from app.models.user import UserOrganizationMembership
from app.models.user import Organization


class SQLAlchemyOntologyRepository:
    async def create_org(self, db: AsyncSession, model: Organization) -> Organization:
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    async def get_org_by_code(self, db: AsyncSession, code: str) -> Optional[Organization]:
        result = await db.execute(select(Organization).where(Organization.code == code))
        return result.scalar_one_or_none()

    async def get_org_by_id(self, db: AsyncSession, org_id: str) -> Optional[Organization]:
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def list_orgs_for_user(self, db: AsyncSession, *, user_id: str, is_admin: bool) -> List[Organization]:
        if is_admin:
            result = await db.execute(select(Organization).order_by(desc(Organization.created_at)))
            return result.scalars().all()
        member_subq = select(UserOrganizationMembership.org_id).where(
            and_(
                UserOrganizationMembership.user_id == user_id,
                UserOrganizationMembership.is_active == True,
            )
        )
        result = await db.execute(
            select(Organization)
            .where(
                and_(
                    Organization.is_active == True,
                    Organization.id.in_(member_subq),
                )
            )
            .order_by(desc(Organization.created_at))
        )
        return result.scalars().all()

    async def add_or_update_org_member(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        user_id: str,
        role: str,
    ) -> UserOrganizationMembership:
        result = await db.execute(
            select(UserOrganizationMembership).where(
                and_(
                    UserOrganizationMembership.org_id == org_id,
                    UserOrganizationMembership.user_id == user_id,
                )
            )
        )
        membership = result.scalar_one_or_none()
        if membership:
            membership.role = role
            membership.is_active = True
        else:
            membership = UserOrganizationMembership(org_id=org_id, user_id=user_id, role=role, is_active=True)
            db.add(membership)
        await db.commit()
        await db.refresh(membership)
        return membership

    async def list_org_members(self, db: AsyncSession, *, org_id: str) -> List[UserOrganizationMembership]:
        result = await db.execute(
            select(UserOrganizationMembership)
            .where(UserOrganizationMembership.org_id == org_id)
            .order_by(desc(UserOrganizationMembership.created_at))
        )
        return result.scalars().all()

    async def get_space_by_owner_code(self, db: AsyncSession, owner_user_id: str, code: str) -> Optional[OntologySpaceModel]:
        result = await db.execute(
            select(OntologySpaceModel).where(
                and_(OntologySpaceModel.owner_user_id == owner_user_id, OntologySpaceModel.code == code)
            )
        )
        return result.scalar_one_or_none()

    async def create_space(self, db: AsyncSession, model: OntologySpaceModel) -> OntologySpaceModel:
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    async def get_space_by_id(self, db: AsyncSession, space_id: str) -> Optional[OntologySpaceModel]:
        result = await db.execute(select(OntologySpaceModel).where(OntologySpaceModel.id == space_id))
        return result.scalar_one_or_none()

    async def list_spaces(self, db: AsyncSession, owner_user_id: Optional[str] = None) -> List[OntologySpaceModel]:
        stmt = select(OntologySpaceModel)
        if owner_user_id:
            stmt = stmt.where(OntologySpaceModel.owner_user_id == owner_user_id)
        stmt = stmt.order_by(desc(OntologySpaceModel.created_at))
        result = await db.execute(stmt)
        return result.scalars().all()

    async def list_spaces_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        is_admin: bool,
        enable_org_tenancy: bool,
    ) -> List[OntologySpaceModel]:
        if is_admin:
            result = await db.execute(select(OntologySpaceModel).order_by(desc(OntologySpaceModel.created_at)))
            return result.scalars().all()

        owned_res = await db.execute(
            select(OntologySpaceModel)
            .where(OntologySpaceModel.owner_user_id == user_id)
            .order_by(desc(OntologySpaceModel.created_at))
        )
        rows = owned_res.scalars().all()
        if not enable_org_tenancy:
            return rows

        org_subq = select(UserOrganizationMembership.org_id).where(
            and_(
                UserOrganizationMembership.user_id == user_id,
                UserOrganizationMembership.is_active == True,
            )
        )
        org_res = await db.execute(
            select(OntologySpaceModel)
            .where(
                and_(
                    OntologySpaceModel.org_id.is_not(None),
                    OntologySpaceModel.org_id.in_(org_subq),
                )
            )
            .order_by(desc(OntologySpaceModel.created_at))
        )
        rows.extend(org_res.scalars().all())
        dedup = {}
        for item in rows:
            dedup[item.id] = item
        return sorted(dedup.values(), key=lambda x: x.created_at, reverse=True)

    async def get_package(self, db: AsyncSession, space_id: str, kind: str, version: str) -> Optional[OntologyPackageModel]:
        result = await db.execute(
            select(OntologyPackageModel).where(
                and_(
                    OntologyPackageModel.space_id == space_id,
                    OntologyPackageModel.kind == kind,
                    OntologyPackageModel.version == version,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_active_package(self, db: AsyncSession, space_id: str, kind: str) -> Optional[OntologyPackageModel]:
        result = await db.execute(
            select(OntologyPackageModel).where(
                and_(
                    OntologyPackageModel.space_id == space_id,
                    OntologyPackageModel.kind == kind,
                    OntologyPackageModel.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_packages(self, db: AsyncSession, space_id: str, kind: str) -> List[OntologyPackageModel]:
        result = await db.execute(
            select(OntologyPackageModel)
            .where(and_(OntologyPackageModel.space_id == space_id, OntologyPackageModel.kind == kind))
            .order_by(desc(OntologyPackageModel.updated_at), desc(OntologyPackageModel.created_at))
        )
        return result.scalars().all()

    async def upsert_package(
        self,
        db: AsyncSession,
        *,
        existed: Optional[OntologyPackageModel],
        new_model: OntologyPackageModel,
    ) -> OntologyPackageModel:
        if existed:
            existed.payload = new_model.payload
            existed.updated_at = new_model.updated_at
            model = existed
        else:
            db.add(new_model)
            model = new_model
        await db.commit()
        await db.refresh(model)
        return model

    async def list_release_events(self, db: AsyncSession, space_id: str, kind: Optional[str] = None) -> List[OntologyReleaseEventModel]:
        conds = [OntologyReleaseEventModel.space_id == space_id]
        if kind:
            conds.append(OntologyReleaseEventModel.kind == kind)
        result = await db.execute(
            select(OntologyReleaseEventModel)
            .where(and_(*conds))
            .order_by(desc(OntologyReleaseEventModel.created_at))
            .limit(200)
        )
        return result.scalars().all()

    async def find_other_active_package(self, db: AsyncSession, space_id: str, kind: str, exclude_id: str) -> Optional[OntologyPackageModel]:
        result = await db.execute(
            select(OntologyPackageModel).where(
                and_(
                    OntologyPackageModel.space_id == space_id,
                    OntologyPackageModel.kind == kind,
                    OntologyPackageModel.is_active == True,
                    OntologyPackageModel.id != exclude_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def save_release_transition(
        self,
        db: AsyncSession,
        *,
        package_model: OntologyPackageModel,
        previous_active: Optional[OntologyPackageModel],
        release_event: OntologyReleaseEventModel,
    ) -> None:
        if previous_active:
            previous_active.is_active = False
        db.add(release_event)
        await db.commit()

    async def create_decision_with_explanation(
        self,
        db: AsyncSession,
        *,
        decision_model: OntologyDecisionModel,
        explanation_model: OntologyExplanationModel,
    ) -> None:
        db.add(decision_model)
        db.add(explanation_model)
        await db.commit()

    async def get_decision(self, db: AsyncSession, decision_id: str) -> Optional[OntologyDecisionModel]:
        result = await db.execute(select(OntologyDecisionModel).where(OntologyDecisionModel.id == decision_id))
        return result.scalar_one_or_none()

    async def get_explanation(self, db: AsyncSession, decision_id: str) -> Optional[OntologyExplanationModel]:
        result = await db.execute(select(OntologyExplanationModel).where(OntologyExplanationModel.decision_id == decision_id))
        return result.scalar_one_or_none()

    async def create_approval(self, db: AsyncSession, approval: OntologyApprovalModel) -> OntologyApprovalModel:
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval

    async def list_approvals(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[OntologyApprovalModel]:
        conds = [OntologyApprovalModel.space_id == space_id]
        if kind:
            conds.append(OntologyApprovalModel.kind == kind)
        if status:
            conds.append(OntologyApprovalModel.status == status)
        result = await db.execute(
            select(OntologyApprovalModel)
            .where(and_(*conds))
            .order_by(desc(OntologyApprovalModel.created_at))
            .limit(200)
        )
        return result.scalars().all()

    async def get_approval(self, db: AsyncSession, approval_id: str) -> Optional[OntologyApprovalModel]:
        result = await db.execute(select(OntologyApprovalModel).where(OntologyApprovalModel.id == approval_id))
        return result.scalar_one_or_none()

    async def get_approved_release_gate(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: str,
        version: str,
        requested_stage: str,
    ) -> Optional[OntologyApprovalModel]:
        result = await db.execute(
            select(OntologyApprovalModel)
            .where(
                and_(
                    OntologyApprovalModel.space_id == space_id,
                    OntologyApprovalModel.kind == kind,
                    OntologyApprovalModel.version == version,
                    OntologyApprovalModel.requested_stage == requested_stage,
                    OntologyApprovalModel.status == "approved",
                )
            )
            .order_by(desc(OntologyApprovalModel.reviewed_at), desc(OntologyApprovalModel.created_at))
        )
        return result.scalars().first()

    async def get_pending_release_gate(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: str,
        version: str,
        requested_stage: str,
    ) -> Optional[OntologyApprovalModel]:
        result = await db.execute(
            select(OntologyApprovalModel)
            .where(
                and_(
                    OntologyApprovalModel.space_id == space_id,
                    OntologyApprovalModel.kind == kind,
                    OntologyApprovalModel.version == version,
                    OntologyApprovalModel.requested_stage == requested_stage,
                    OntologyApprovalModel.status == "pending",
                )
            )
            .order_by(desc(OntologyApprovalModel.created_at))
        )
        return result.scalars().first()

    async def is_org_member(self, db: AsyncSession, *, org_id: str, user_id: str) -> bool:
        result = await db.execute(
            select(UserOrganizationMembership.id).where(
                and_(
                    UserOrganizationMembership.org_id == org_id,
                    UserOrganizationMembership.user_id == user_id,
                    UserOrganizationMembership.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_data_source(self, db: AsyncSession, data_source_id: str) -> Optional[OntologyDataSourceModel]:
        result = await db.execute(select(OntologyDataSourceModel).where(OntologyDataSourceModel.id == data_source_id))
        return result.scalar_one_or_none()

    async def get_data_source_by_name(self, db: AsyncSession, *, space_id: str, name: str) -> Optional[OntologyDataSourceModel]:
        result = await db.execute(
            select(OntologyDataSourceModel).where(
                and_(
                    OntologyDataSourceModel.space_id == space_id,
                    OntologyDataSourceModel.name == name,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_data_sources(self, db: AsyncSession, *, space_id: str) -> List[OntologyDataSourceModel]:
        result = await db.execute(
            select(OntologyDataSourceModel)
            .where(OntologyDataSourceModel.space_id == space_id)
            .order_by(desc(OntologyDataSourceModel.updated_at), desc(OntologyDataSourceModel.created_at))
        )
        return result.scalars().all()

    async def upsert_data_source(
        self,
        db: AsyncSession,
        *,
        existed: Optional[OntologyDataSourceModel],
        new_model: OntologyDataSourceModel,
    ) -> OntologyDataSourceModel:
        if existed:
            existed.kind = new_model.kind
            existed.protocol = new_model.protocol
            existed.config = new_model.config
            existed.secret_ref = new_model.secret_ref
            existed.status = new_model.status
            existed.updated_at = new_model.updated_at
            model = existed
        else:
            db.add(new_model)
            model = new_model
        await db.commit()
        await db.refresh(model)
        return model

    async def update_data_source_test_result(
        self,
        db: AsyncSession,
        *,
        model: OntologyDataSourceModel,
        status: str,
        message: str,
    ) -> OntologyDataSourceModel:
        model.last_test_status = status
        model.last_test_message = message
        await db.commit()
        await db.refresh(model)
        return model

    async def get_secret_by_ref(self, db: AsyncSession, *, space_id: str, scope: str, name: str) -> Optional[OntologySecretModel]:
        result = await db.execute(
            select(OntologySecretModel).where(
                and_(
                    OntologySecretModel.space_id == space_id,
                    OntologySecretModel.scope == scope,
                    OntologySecretModel.name == name,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_secrets(self, db: AsyncSession, *, space_id: str) -> List[OntologySecretModel]:
        result = await db.execute(
            select(OntologySecretModel)
            .where(OntologySecretModel.space_id == space_id)
            .order_by(desc(OntologySecretModel.updated_at), desc(OntologySecretModel.created_at))
        )
        return result.scalars().all()

    async def upsert_secret(
        self,
        db: AsyncSession,
        *,
        existed: Optional[OntologySecretModel],
        new_model: OntologySecretModel,
    ) -> OntologySecretModel:
        if existed:
            existed.encrypted_value = new_model.encrypted_value
            existed.description = new_model.description
            existed.updated_at = new_model.updated_at
            model = existed
        else:
            db.add(new_model)
            model = new_model
        await db.commit()
        await db.refresh(model)
        return model

    async def get_org_membership(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        user_id: str,
    ) -> Optional[UserOrganizationMembership]:
        result = await db.execute(
            select(UserOrganizationMembership).where(
                and_(
                    UserOrganizationMembership.org_id == org_id,
                    UserOrganizationMembership.user_id == user_id,
                    UserOrganizationMembership.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def set_package_active_state(
        self,
        db: AsyncSession,
        *,
        target: OntologyPackageModel,
        previous_active: Optional[OntologyPackageModel],
        deprecate_previous: bool,
    ) -> None:
        if previous_active and previous_active.id != target.id:
            previous_active.is_active = False
            if deprecate_previous:
                previous_active.stage = "deprecated"
        target.is_active = True
        target.stage = "ga"
        await db.commit()

    async def switch_active_package(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        kind: str,
        target: OntologyPackageModel,
        deprecate_previous: bool,
    ) -> None:
        """
        先下线旧 active，再激活 target，避免部分唯一索引 (space_id, kind, is_active=true) 冲突。
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(OntologyPackageModel).where(
                and_(
                    OntologyPackageModel.space_id == space_id,
                    OntologyPackageModel.kind == kind,
                    OntologyPackageModel.is_active == True,
                    OntologyPackageModel.id != target.id,
                )
            )
        )
        previous_rows = result.scalars().all()
        for row in previous_rows:
            row.is_active = False
            if deprecate_previous:
                row.stage = "deprecated"
            row.updated_at = now
        await db.flush()

        target.is_active = True
        target.stage = "ga"
        target.updated_at = now
        await db.flush()


ontology_repo = SQLAlchemyOntologyRepository()
