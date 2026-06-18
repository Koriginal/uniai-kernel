from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PolicyDocumentRecord(BaseModel):
    id: str
    space_id: str
    user_id: str
    source_document_id: Optional[str] = None
    title: str
    business_domain: Optional[str] = None
    document_type: str
    version: str
    raw_text_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class PolicyArticleRecord(BaseModel):
    id: str
    space_id: str
    policy_document_id: str
    article_no: str
    chapter_path: List[str] = Field(default_factory=list)
    paragraph_path: List[str] = Field(default_factory=list)
    locator: str
    text: str
    quote: str
    text_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NormClausePatch(BaseModel):
    norm_type: Optional[str] = Field(default=None, pattern="^(obligation|prohibition|permission|exception|approval_required|evidence_required|liability|standard|scoring)$")
    subject: Optional[str] = Field(default=None, max_length=200)
    action: Optional[str] = Field(default=None, max_length=200)
    object: Optional[str] = Field(default=None, max_length=200)
    condition_text: Optional[str] = Field(default=None, max_length=2000)
    exception_text: Optional[str] = Field(default=None, max_length=2000)
    consequence_text: Optional[str] = Field(default=None, max_length=2000)
    evidence_required: Optional[List[str]] = None
    domain_tags: Optional[List[str]] = None
    scenario_tags: Optional[List[str]] = None
    confidence: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|approved|rejected|released|deprecated)$")
    review_note: Optional[str] = Field(default=None, max_length=1000)


class NormClauseRecord(BaseModel):
    id: str
    space_id: str
    policy_document_id: str
    policy_article_id: str
    norm_code: str
    norm_type: str
    subject: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    condition_text: Optional[str] = None
    exception_text: Optional[str] = None
    consequence_text: Optional[str] = None
    evidence_required: List[str] = Field(default_factory=list)
    domain_tags: List[str] = Field(default_factory=list)
    scenario_tags: List[str] = Field(default_factory=list)
    confidence: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_by: str
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReviewCheckPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    scenario_type: Optional[str] = Field(default=None, pattern="^(contract_review|tender_review|custom)$")
    description: Optional[str] = Field(default=None, max_length=2000)
    norm_clause_ids: Optional[List[str]] = None
    input_schema: Optional[Dict[str, Any]] = None
    evidence_schema: Optional[Dict[str, Any]] = None
    check_type: Optional[str] = Field(default=None, pattern="^(deterministic|semantic|manual)$")
    severity: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    fail_template: Optional[str] = Field(default=None, max_length=2000)
    pass_template: Optional[str] = Field(default=None, max_length=2000)
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|approved|rejected|released|deprecated)$")
    review_note: Optional[str] = Field(default=None, max_length=1000)


class ReviewCheckRecord(BaseModel):
    id: str
    space_id: str
    check_code: str
    name: str
    scenario_type: str
    description: Optional[str] = None
    norm_clause_ids: List[str] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    evidence_schema: Dict[str, Any] = Field(default_factory=dict)
    check_type: str
    severity: str
    fail_template: Optional[str] = None
    pass_template: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_by: str
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReviewPackCreate(BaseModel):
    space_id: str
    name: str = Field(..., min_length=1, max_length=200)
    business_domain: Optional[str] = Field(default="legal", max_length=120)
    scenario_type: str = Field(default="contract_review", pattern="^(contract_review|tender_review|custom)$")
    version: str = Field(default="1.0.0", min_length=1, max_length=80)
    policy_document_ids: List[str] = Field(default_factory=list)
    norm_clause_ids: List[str] = Field(default_factory=list)
    review_check_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewPackRecord(BaseModel):
    id: str
    space_id: str
    name: str
    business_domain: Optional[str] = None
    scenario_type: str
    version: str
    policy_document_ids: List[str] = Field(default_factory=list)
    norm_clause_ids: List[str] = Field(default_factory=list)
    review_check_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_by: str
    released_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    released_at: Optional[datetime] = None


class ReviewRunCreate(BaseModel):
    application_id: Optional[str] = None
    review_pack_id: Optional[str] = None
    target_title: Optional[str] = Field(default=None, max_length=200)
    target_text: str = Field(..., min_length=1, max_length=200000)
    target_document_ids: List[str] = Field(default_factory=list)


class ReviewTargetExtractResult(BaseModel):
    title: str
    file_name: str
    content_type: Optional[str] = None
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class ReviewRunRecord(BaseModel):
    run_id: str
    application_id: Optional[str] = None
    review_pack_id: Optional[str] = None
    target_document_ids: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime
