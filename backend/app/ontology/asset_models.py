from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.ontology.domain_models import RuleCondition


class RuleSourceType(str, Enum):
    policy_doc = "policy_doc"
    contract_template = "contract_template"
    review_manual = "review_manual"
    regulation = "regulation"
    historical_case = "historical_case"
    database_schema = "database_schema"
    api_schema = "api_schema"
    custom_note = "custom_note"


class RuleSourceStatus(str, Enum):
    uploaded = "uploaded"
    parsed = "parsed"
    parse_failed = "parse_failed"
    reviewed = "reviewed"
    archived = "archived"


class RuleEntryStatus(str, Enum):
    draft = "draft"
    reviewing = "reviewing"
    approved = "approved"
    rejected = "rejected"
    packaged = "packaged"
    released = "released"
    deprecated = "deprecated"


class OntologyTermKind(str, Enum):
    entity = "entity"
    attribute = "attribute"
    relation = "relation"
    enum = "enum"
    taxonomy = "taxonomy"
    vocabulary = "vocabulary"


class RuleSourceDocumentCreate(BaseModel):
    space_id: str
    title: str = Field(..., min_length=1, max_length=200)
    source_type: RuleSourceType = RuleSourceType.custom_note
    file_name: Optional[str] = Field(default=None, max_length=300)
    content_type: Optional[str] = Field(default=None, max_length=120)
    raw_text: Optional[str] = Field(default=None, max_length=200000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuleSourceDocumentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[RuleSourceStatus] = None
    metadata: Optional[Dict[str, Any]] = None


class RuleSourceDocumentRecord(BaseModel):
    id: str
    space_id: str
    user_id: str
    title: str
    source_type: RuleSourceType
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    content_hash: str
    raw_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: RuleSourceStatus
    created_at: datetime
    updated_at: Optional[datetime] = None


class RuleSourceUploadResult(BaseModel):
    source: RuleSourceDocumentRecord
    warnings: List[str] = Field(default_factory=list)


class RuleSourceParseRequest(BaseModel):
    max_rules: int = Field(default=30, ge=1, le=200)
    overwrite_existing: bool = False


class EvidenceRef(BaseModel):
    source_document_id: Optional[str] = None
    locator: str = Field(..., min_length=1, max_length=500)
    quote: Optional[str] = Field(default=None, max_length=2000)


class RuleTestCase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    graph: Dict[str, Any] = Field(default_factory=dict)
    expected_hit: bool = True


class RuleEntryCreate(BaseModel):
    space_id: str
    source_document_id: Optional[str] = None
    rule_code: str = Field(..., min_length=2, max_length=120)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    target_entity_type: Optional[str] = Field(default=None, max_length=120)
    conditions: List[RuleCondition] = Field(default_factory=list)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    action: str = Field(default="flag", pattern="^(flag|block|recommend)$")
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    test_cases: List[RuleTestCase] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    version: str = Field(default="1", max_length=40)


class RuleEntryUpdate(BaseModel):
    source_document_id: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    target_entity_type: Optional[str] = Field(default=None, max_length=120)
    conditions: Optional[List[RuleCondition]] = None
    severity: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    action: Optional[str] = Field(default=None, pattern="^(flag|block|recommend)$")
    evidence_refs: Optional[List[EvidenceRef]] = None
    test_cases: Optional[List[RuleTestCase]] = None
    tags: Optional[List[str]] = None
    version: Optional[str] = Field(default=None, max_length=40)


class RuleEntryReviewRequest(BaseModel):
    approve: bool
    review_note: Optional[str] = Field(default=None, max_length=1000)


class RuleQualityIssue(BaseModel):
    code: str
    field: str
    message: str


class RuleQualityReport(BaseModel):
    rule_entry_id: str
    status: RuleEntryStatus
    blockers: List[RuleQualityIssue] = Field(default_factory=list)
    warnings: List[RuleQualityIssue] = Field(default_factory=list)
    can_submit_review: bool = False
    can_approve: bool = False
    can_package: bool = False


class RuleBatchSubmitRequest(BaseModel):
    rule_entry_ids: List[str] = Field(..., min_length=1, max_length=200)


class RuleBatchSubmitResult(BaseModel):
    submitted_ids: List[str] = Field(default_factory=list)
    skipped: Dict[str, str] = Field(default_factory=dict)


class RuleEntryRecord(BaseModel):
    id: str
    space_id: str
    source_document_id: Optional[str] = None
    rule_code: str
    name: str
    description: Optional[str] = None
    target_entity_type: Optional[str] = None
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    severity: str
    action: str
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    status: RuleEntryStatus
    version: str
    created_by: str
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class RuleSourceParseResult(BaseModel):
    source: RuleSourceDocumentRecord
    rule_entries: List[RuleEntryRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RulePackageCompileRequest(BaseModel):
    space_id: str
    version: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1000)
    rule_entry_ids: Optional[List[str]] = None
    include_tags: Optional[List[str]] = None


class RulePackageCompileResult(BaseModel):
    package: Dict[str, Any]
    rule_entry_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class OntologyTermCreate(BaseModel):
    space_id: str
    source_document_id: Optional[str] = None
    term_code: str = Field(..., min_length=2, max_length=120)
    name: str = Field(..., min_length=1, max_length=160)
    kind: OntologyTermKind
    description: Optional[str] = Field(default=None, max_length=2000)
    entity_type: Optional[str] = Field(default=None, max_length=120)
    data_type: Optional[str] = Field(default=None, pattern="^(string|number|integer|boolean|array|object)$")
    required: bool = False
    enum_values: List[str] = Field(default_factory=list)
    relation_target_type: Optional[str] = Field(default=None, max_length=120)
    relation_cardinality: Optional[str] = Field(default=None, pattern="^(one|many)$")
    aliases: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="1", max_length=40)


class OntologyTermUpdate(BaseModel):
    source_document_id: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    entity_type: Optional[str] = Field(default=None, max_length=120)
    data_type: Optional[str] = Field(default=None, pattern="^(string|number|integer|boolean|array|object)$")
    required: Optional[bool] = None
    enum_values: Optional[List[str]] = None
    relation_target_type: Optional[str] = Field(default=None, max_length=120)
    relation_cardinality: Optional[str] = Field(default=None, pattern="^(one|many)$")
    aliases: Optional[List[str]] = None
    evidence_refs: Optional[List[EvidenceRef]] = None
    metadata: Optional[Dict[str, Any]] = None
    version: Optional[str] = Field(default=None, max_length=40)


class OntologyTermRecord(BaseModel):
    id: str
    space_id: str
    source_document_id: Optional[str] = None
    term_code: str
    name: str
    kind: OntologyTermKind
    description: Optional[str] = None
    entity_type: Optional[str] = None
    data_type: Optional[str] = None
    required: bool = False
    enum_values: List[str] = Field(default_factory=list)
    relation_target_type: Optional[str] = None
    relation_cardinality: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: RuleEntryStatus
    version: str
    created_by: str
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SchemaPackageCompileRequest(BaseModel):
    space_id: str
    version: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1000)
    term_ids: Optional[List[str]] = None


class SchemaPackageCompileResult(BaseModel):
    package: Dict[str, Any]
    term_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
