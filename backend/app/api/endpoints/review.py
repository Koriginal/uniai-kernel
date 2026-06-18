from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.db import get_db
from app.models.user import User
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
from app.review.service import review_knowledge_service

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


@router.post("/policy-documents/upload", response_model=PolicyDocumentRecord)
async def upload_policy_document(
    space_id: str = Form(...),
    document_type: str = Form("contract_rule"),
    version: str = Form("1"),
    title: Optional[str] = Form(None),
    business_domain: Optional[str] = Form("legal"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    content = await file.read()
    return await review_knowledge_service.upload_policy_document(
        db,
        space_id=space_id,
        title=title,
        business_domain=business_domain,
        document_type=document_type,
        version=version,
        file_name=file.filename or "policy-document",
        content_type=file.content_type,
        content=content,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/policy-documents", response_model=List[PolicyDocumentRecord])
async def list_policy_documents(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.list_policy_documents(
        db,
        space_id=space_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/policy-documents/{policy_document_id}/segment", response_model=List[PolicyArticleRecord])
async def segment_policy_document(
    policy_document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.segment_policy_document(
        db,
        policy_document_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/policy-documents/{policy_document_id}/extract-norms")
async def extract_norms(
    policy_document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.extract_norms(
        db,
        policy_document_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/articles", response_model=List[PolicyArticleRecord])
async def list_articles(
    space_id: str,
    policy_document_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.list_articles(
        db,
        space_id=space_id,
        policy_document_id=policy_document_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/norm-clauses", response_model=List[NormClauseRecord])
async def list_norm_clauses(
    space_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.list_norms(
        db,
        space_id=space_id,
        status=status,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.patch("/norm-clauses/{norm_clause_id}", response_model=NormClauseRecord)
async def update_norm_clause(
    norm_clause_id: str,
    payload: NormClausePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.update_norm(
        db,
        norm_clause_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/checks", response_model=List[ReviewCheckRecord])
async def list_review_checks(
    space_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.list_checks(
        db,
        space_id=space_id,
        status=status,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.patch("/checks/{check_id}", response_model=ReviewCheckRecord)
async def update_review_check(
    check_id: str,
    payload: ReviewCheckPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.update_check(
        db,
        check_id,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/packs", response_model=ReviewPackRecord)
async def create_review_pack(
    payload: ReviewPackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.create_pack(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.get("/packs", response_model=List[ReviewPackRecord])
async def list_review_packs(
    space_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.list_packs(
        db,
        space_id=space_id,
        status=status,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/packs/{pack_id}/release", response_model=ReviewPackRecord)
async def release_review_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.release_pack(
        db,
        pack_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/runs", response_model=ReviewRunRecord)
async def create_review_run(
    payload: ReviewRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.run_review(
        db,
        payload,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )


@router.post("/target-documents/extract", response_model=ReviewTargetExtractResult)
async def extract_target_document(
    title: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    content = await file.read()
    return review_knowledge_service.extract_target_document(
        title=title,
        file_name=file.filename or "review-target",
        content_type=file.content_type,
        content=content,
    )


@router.get("/runs/{run_id}", response_model=ReviewRunRecord)
async def get_review_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await review_knowledge_service.get_run(
        db,
        run_id,
        actor_user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
