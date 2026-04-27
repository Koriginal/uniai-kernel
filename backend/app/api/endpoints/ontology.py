from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from app.api import deps
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from app.ontology.domain_models import (
    OrganizationCreate,
    OrganizationMemberAdd,
    OrganizationMemberRecord,
    OrganizationRecord,
    ApprovalRecord,
    ApprovalReviewRequest,
    ApprovalStatus,
    ApprovalSubmitRequest,
    DecisionResult,
    ExplanationResponse,
    MappingExecuteRequest,
    MappingExecuteResponse,
    MappingPackageCreate,
    OntologyDataSourceCreate,
    OntologyDataSourceRecord,
    DataSourceDiscoveryResult,
    DataSourceTestResult,
    OntologySecretCreate,
    OntologySecretRecord,
    PackageDiffResponse,
    OntologySpace,
    OntologySpaceCreate,
    PackageKind,
    PackageRecord,
    ReleaseRequest,
    ReleaseResult,
    RollbackRequest,
    RuleEvaluateRequest,
    RulePackageCreate,
    SchemaPackageCreate,
)
from app.ontology.persistent_service import persistent_ontology_service

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


def _ensure_ontology_enabled() -> None:
    if not settings.ENABLE_ONTOLOGY_ENGINE:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Ontology engine is disabled by configuration")


@router.post("/spaces", response_model=OntologySpace)
async def create_space(
    payload: OntologySpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.create_space(db, payload, owner_user_id=current_user.id)


@router.post("/orgs", response_model=OrganizationRecord)
async def create_org(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.create_org(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/orgs", response_model=List[OrganizationRecord])
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_orgs(
        db,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/orgs/{org_id}/members", response_model=OrganizationMemberRecord)
async def add_org_member(
    org_id: str,
    payload: OrganizationMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.add_org_member(
        db,
        org_id=org_id,
        payload=payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/orgs/{org_id}/members", response_model=List[OrganizationMemberRecord])
async def list_org_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_org_members(
        db,
        org_id=org_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/spaces", response_model=List[OntologySpace])
async def list_spaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_spaces(db, owner_user_id=current_user.id, is_admin=current_user.is_admin)


@router.post("/data-sources", response_model=OntologyDataSourceRecord)
async def upsert_data_source(
    payload: OntologyDataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.upsert_data_source(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/data-sources/{space_id}", response_model=List[OntologyDataSourceRecord])
async def list_data_sources(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_data_sources(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/data-sources/{data_source_id}/test", response_model=DataSourceTestResult)
async def test_data_source(
    data_source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.test_data_source(
        db,
        data_source_id=data_source_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/data-sources/{data_source_id}/discover", response_model=DataSourceDiscoveryResult)
async def discover_data_source(
    data_source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.discover_data_source(
        db,
        data_source_id=data_source_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/secrets", response_model=OntologySecretRecord)
async def upsert_secret(
    payload: OntologySecretCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.upsert_secret(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/secrets/{space_id}", response_model=List[OntologySecretRecord])
async def list_secrets(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_secrets(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/schema", response_model=PackageRecord)
async def upsert_schema(
    payload: SchemaPackageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.upsert_schema(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/mapping", response_model=PackageRecord)
async def upsert_mapping(
    payload: MappingPackageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.upsert_mapping(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rules", response_model=PackageRecord)
async def upsert_rules(
    payload: RulePackageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.upsert_rule(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/packages/{space_id}/{kind}", response_model=List[PackageRecord])
async def list_packages(
    space_id: str,
    kind: PackageKind,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_packages(
        db,
        space_id=space_id,
        kind=kind,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/governance/releases/{space_id}", response_model=List[Dict[str, Any]])
async def list_release_events(
    space_id: str,
    kind: Optional[PackageKind] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_release_events(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
        kind=kind,
    )


@router.get("/governance/diff", response_model=PackageDiffResponse)
async def diff_packages(
    space_id: str,
    kind: PackageKind,
    from_version: str,
    to_version: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.diff_packages(
        db,
        space_id=space_id,
        kind=kind,
        from_version=from_version,
        to_version=to_version,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/governance/release", response_model=ReleaseResult)
async def release_package(
    payload: ReleaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.release(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/governance/approvals/submit", response_model=ApprovalRecord)
async def submit_approval(
    payload: ApprovalSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.submit_approval(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/governance/approvals/{space_id}", response_model=List[ApprovalRecord])
async def list_approvals(
    space_id: str,
    kind: Optional[PackageKind] = None,
    status: Optional[ApprovalStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.list_approvals(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
        kind=kind,
        status=status,
    )


@router.post("/governance/approvals/review", response_model=ApprovalRecord)
async def review_approval(
    payload: ApprovalReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.review_approval(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/governance/rollback", response_model=ReleaseResult)
async def rollback_package(
    payload: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.rollback(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/mapping/execute", response_model=MappingExecuteResponse)
async def execute_mapping(
    payload: MappingExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.execute_mapping(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rules/evaluate", response_model=DecisionResult)
async def evaluate_rules(
    payload: RuleEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.evaluate_rules(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/explain/{decision_id}", response_model=ExplanationResponse)
async def explain_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await persistent_ontology_service.explain(
        db,
        decision_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
