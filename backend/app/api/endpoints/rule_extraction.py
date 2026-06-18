from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api import deps
from app.rule_extraction.models import RuleExtractionRequest, RuleExtractionResult, RuleExtractionUploadResult
from app.rule_extraction.service import rule_extraction_service

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


@router.post("/extract", response_model=RuleExtractionResult)
async def extract_rules(payload: RuleExtractionRequest):
    return rule_extraction_service.extract_from_text(payload)


@router.post("/upload", response_model=RuleExtractionUploadResult)
async def upload_and_extract_rules(
    title: Optional[str] = Form(None),
    source_type: str = Form("policy_doc"),
    max_rules: int = Form(100),
    file: UploadFile = File(...),
):
    content = await file.read()
    return rule_extraction_service.extract_from_upload(
        title=title,
        source_type=source_type,
        max_rules=max_rules,
        file_name=file.filename or "rule-source",
        content_type=file.content_type,
        content=content,
    )
