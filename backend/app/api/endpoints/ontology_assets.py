from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.ontology.asset_models import (
    OntologyTermCreate,
    OntologyTermKind,
    OntologyTermRecord,
    OntologyTermUpdate,
    RuleBatchSubmitRequest,
    RuleBatchSubmitResult,
    RuleEntryCreate,
    RuleEntryRecord,
    RuleEntryReviewRequest,
    RuleEntryStatus,
    RuleEntryUpdate,
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
from app.ontology.asset_service import ontology_asset_service

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


def _ensure_ontology_enabled() -> None:
    if not settings.ENABLE_ONTOLOGY_ENGINE:
        raise HTTPException(status_code=503, detail="Ontology engine is disabled by configuration")


@router.post("/asset-sources", response_model=RuleSourceDocumentRecord)
async def create_source_document(
    payload: RuleSourceDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.create_source_document(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/asset-sources/upload", response_model=RuleSourceUploadResult)
async def upload_source_document(
    space_id: str = Form(...),
    source_type: str = Form("custom_note"),
    title: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    content = await file.read()
    return await ontology_asset_service.upload_source_document(
        db,
        space_id=space_id,
        title=title,
        source_type=source_type,
        file_name=file.filename or "uploaded-source",
        content_type=file.content_type,
        content=content,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/asset-sources/{space_id}", response_model=List[RuleSourceDocumentRecord])
async def list_source_documents(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.list_source_documents(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/asset-sources/detail/{source_id}", response_model=RuleSourceDocumentRecord)
async def get_source_document(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.get_source_document(
        db,
        source_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.patch("/asset-sources/{source_id}", response_model=RuleSourceDocumentRecord)
async def update_source_document(
    source_id: str,
    payload: RuleSourceDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.update_source_document(
        db,
        source_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/asset-sources/{source_id}/parse", response_model=RuleSourceParseResult)
async def parse_source_document(
    source_id: str,
    payload: RuleSourceParseRequest = RuleSourceParseRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.parse_source_document(
        db,
        source_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rule-entries", response_model=RuleEntryRecord)
async def create_rule_entry(
    payload: RuleEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.create_rule_entry(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/rule-entries/{space_id}", response_model=List[RuleEntryRecord])
async def list_rule_entries(
    space_id: str,
    status: Optional[RuleEntryStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.list_rule_entries(
        db,
        space_id=space_id,
        status=status,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/rule-entries/detail/{rule_entry_id}", response_model=RuleEntryRecord)
async def get_rule_entry(
    rule_entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.get_rule_entry(
        db,
        rule_entry_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/rule-quality/{space_id}", response_model=List[RuleQualityReport])
async def list_rule_quality(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.list_rule_quality(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/rule-quality/detail/{rule_entry_id}", response_model=RuleQualityReport)
async def get_rule_quality(
    rule_entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.get_rule_quality(
        db,
        rule_entry_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.patch("/rule-entries/{rule_entry_id}", response_model=RuleEntryRecord)
async def update_rule_entry(
    rule_entry_id: str,
    payload: RuleEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.update_rule_entry(
        db,
        rule_entry_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rule-entries/batch-submit-review", response_model=RuleBatchSubmitResult)
async def batch_submit_rule_entry_review(
    payload: RuleBatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.batch_submit_rule_entry_review(
        db,
        payload.rule_entry_ids,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rule-entries/{rule_entry_id}/submit-review", response_model=RuleEntryRecord)
async def submit_rule_entry_review(
    rule_entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.submit_rule_entry_review(
        db,
        rule_entry_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rule-entries/{rule_entry_id}/review", response_model=RuleEntryRecord)
async def review_rule_entry(
    rule_entry_id: str,
    payload: RuleEntryReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.review_rule_entry(
        db,
        rule_entry_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/rule-entries/{rule_entry_id}/deprecate", response_model=RuleEntryRecord)
async def deprecate_rule_entry(
    rule_entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.deprecate_rule_entry(
        db,
        rule_entry_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/assets/compile-rules", response_model=RulePackageCompileResult)
async def compile_rules(
    payload: RulePackageCompileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.compile_rules(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/terms", response_model=OntologyTermRecord)
async def create_term(
    payload: OntologyTermCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.create_term(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/terms/{space_id}", response_model=List[OntologyTermRecord])
async def list_terms(
    space_id: str,
    status: Optional[RuleEntryStatus] = None,
    kind: Optional[OntologyTermKind] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.list_terms(
        db,
        space_id=space_id,
        status=status,
        kind=kind,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/terms/detail/{term_id}", response_model=OntologyTermRecord)
async def get_term(
    term_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.get_term(
        db,
        term_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.patch("/terms/{term_id}", response_model=OntologyTermRecord)
async def update_term(
    term_id: str,
    payload: OntologyTermUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.update_term(
        db,
        term_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/terms/{term_id}/submit-review", response_model=OntologyTermRecord)
async def submit_term_review(
    term_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.submit_term_review(
        db,
        term_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/terms/{term_id}/review", response_model=OntologyTermRecord)
async def review_term(
    term_id: str,
    payload: RuleEntryReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.review_term(
        db,
        term_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/assets/compile-schema", response_model=SchemaPackageCompileResult)
async def compile_schema(
    payload: SchemaPackageCompileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ensure_ontology_enabled()
    return await ontology_asset_service.compile_schema(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
