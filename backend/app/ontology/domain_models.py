from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PackageKind(str, Enum):
    schema = "schema"
    mapping = "mapping"
    rule = "rule"


class VersionStage(str, Enum):
    draft = "draft"
    review = "review"
    staging = "staging"
    ga = "ga"
    deprecated = "deprecated"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class OrgRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class DataSourceKind(str, Enum):
    database = "database"
    api = "api"
    protocol = "protocol"
    file = "file"
    stream = "stream"


class DataSourceStatus(str, Enum):
    draft = "draft"
    active = "active"
    disabled = "disabled"


class OntologySpaceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    code: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    org_id: Optional[str] = Field(default=None, max_length=64)


class OrganizationCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class OrganizationMemberAdd(BaseModel):
    user_id: str
    role: OrgRole = OrgRole.member


class OrganizationMemberRecord(BaseModel):
    id: str
    org_id: str
    user_id: str
    role: OrgRole
    is_active: bool
    created_at: datetime


class OrganizationRecord(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    owner_user_id: str
    is_active: bool
    created_at: datetime


class OntologySpace(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    owner_user_id: str
    org_id: Optional[str] = None
    created_at: datetime


class OntologyDataSourceCreate(BaseModel):
    space_id: str
    name: str = Field(..., min_length=2, max_length=120)
    kind: DataSourceKind
    protocol: str = Field(..., min_length=2, max_length=64)
    config: Dict[str, Any] = Field(default_factory=dict)
    secret_ref: Optional[str] = Field(default=None, max_length=256)
    status: DataSourceStatus = DataSourceStatus.draft


class OntologyDataSourceRecord(BaseModel):
    id: str
    space_id: str
    name: str
    kind: DataSourceKind
    protocol: str
    config: Dict[str, Any] = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    status: DataSourceStatus
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class DataSourceTestResult(BaseModel):
    ok: bool
    status: str
    message: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class DiscoveredColumn(BaseModel):
    name: str
    data_type: str = "string"
    nullable: bool = True
    primary_key: bool = False
    description: Optional[str] = None
    source_path: Optional[str] = None


class DiscoveredEntity(BaseModel):
    name: str
    source: str
    columns: List[DiscoveredColumn] = Field(default_factory=list)
    primary_keys: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class DataSourceDiscoveryResult(BaseModel):
    ok: bool
    status: str
    message: str
    source_id: str
    protocol: str
    entities: List[DiscoveredEntity] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


class OntologySecretCreate(BaseModel):
    space_id: str
    scope: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1, max_length=4096)
    description: Optional[str] = Field(default=None, max_length=500)


class OntologySecretRecord(BaseModel):
    id: str
    space_id: str
    scope: str
    name: str
    ref: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class AttributeDef(BaseModel):
    data_type: Literal["string", "number", "integer", "boolean", "array", "object"] = "string"
    required: bool = False
    description: Optional[str] = None
    enum_values: Optional[List[str]] = None


class RelationDef(BaseModel):
    name: str
    target_type: str
    cardinality: Literal["one", "many"] = "many"
    description: Optional[str] = None


class EntityTypeDef(BaseModel):
    name: str
    description: Optional[str] = None
    attributes: Dict[str, AttributeDef] = Field(default_factory=dict)
    relations: List[RelationDef] = Field(default_factory=list)


class SchemaPackageCreate(BaseModel):
    space_id: str
    version: str
    description: Optional[str] = None
    entity_types: List[EntityTypeDef] = Field(default_factory=list)
    taxonomy: Dict[str, List[str]] = Field(default_factory=dict)
    vocabulary: Dict[str, List[str]] = Field(default_factory=dict)


class TransformKind(str, Enum):
    trim = "trim"
    lower = "lower"
    upper = "upper"
    to_int = "to_int"
    to_float = "to_float"
    to_bool = "to_bool"


class FieldMappingRule(BaseModel):
    source_path: str
    target_attr: str
    required: bool = False
    default_value: Optional[Any] = None
    transform: Optional[TransformKind] = None


class EntityMappingRule(BaseModel):
    entity_type: str
    id_template: str
    source_path: Optional[str] = None
    field_mappings: List[FieldMappingRule] = Field(default_factory=list)


class RelationMappingRule(BaseModel):
    relation_type: str
    source_entity_template: str
    target_entity_template: str
    source_path: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class MappingPackageCreate(BaseModel):
    space_id: str
    version: str
    description: Optional[str] = None
    entity_mappings: List[EntityMappingRule] = Field(default_factory=list)
    relation_mappings: List[RelationMappingRule] = Field(default_factory=list)


class RuleCondition(BaseModel):
    path: str
    operator: Literal[
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "in",
        "exists",
    ]
    value: Optional[Any] = None


class RuleDef(BaseModel):
    rule_id: str
    name: str
    description: Optional[str] = None
    target_entity_type: Optional[str] = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    action: Literal["flag", "block", "recommend"] = "flag"
    conditions: List[RuleCondition] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RulePackageCreate(BaseModel):
    space_id: str
    version: str
    description: Optional[str] = None
    rules: List[RuleDef] = Field(default_factory=list)


class PackageRecord(BaseModel):
    kind: PackageKind
    space_id: str
    version: str
    stage: VersionStage = VersionStage.draft
    created_by: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    payload: Dict[str, Any]


class ReleaseRequest(BaseModel):
    space_id: str
    kind: PackageKind
    version: str
    target_stage: VersionStage
    notes: Optional[str] = None
    strict_compatibility: bool = False


class ReleaseResult(BaseModel):
    ok: bool
    space_id: str
    kind: PackageKind
    version: str
    stage: VersionStage
    warnings: List[str] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    space_id: str
    kind: PackageKind
    target_version: str
    notes: Optional[str] = None


class ApprovalSubmitRequest(BaseModel):
    space_id: str
    kind: PackageKind
    version: str
    target_stage: VersionStage
    note: Optional[str] = None


class ApprovalReviewRequest(BaseModel):
    approval_id: str
    approve: bool
    review_note: Optional[str] = None


class ApprovalRecord(BaseModel):
    id: str
    space_id: str
    package_id: str
    kind: PackageKind
    version: str
    requested_stage: VersionStage
    status: ApprovalStatus
    requester_user_id: str
    reviewer_user_id: Optional[str] = None
    request_note: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class PackageDiffRequest(BaseModel):
    space_id: str
    kind: PackageKind
    from_version: str
    to_version: str


class PackageDiffResponse(BaseModel):
    space_id: str
    kind: PackageKind
    from_version: str
    to_version: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    breaking_changes: List[str] = Field(default_factory=list)


class EntityInstance(BaseModel):
    id: str
    entity_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class RelationInstance(BaseModel):
    relation_type: str
    source_id: str
    target_id: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class InstanceGraph(BaseModel):
    entities: List[EntityInstance] = Field(default_factory=list)
    relations: List[RelationInstance] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MappingTraceItem(BaseModel):
    code: str
    message: str
    source_path: Optional[str] = None
    target: Optional[str] = None


class MappingExecuteRequest(BaseModel):
    space_id: str
    input_payload: Dict[str, Any]
    mapping_version: Optional[str] = None
    schema_version: Optional[str] = None


class MappingExecuteResponse(BaseModel):
    graph: InstanceGraph
    mapping_version: str
    schema_version: Optional[str] = None
    trace: List[MappingTraceItem] = Field(default_factory=list)


class RuleEvaluateRequest(BaseModel):
    space_id: str
    graph: InstanceGraph
    rule_version: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class RuleHit(BaseModel):
    rule_id: str
    name: str
    severity: str
    action: str
    entity_id: Optional[str] = None
    reason: str


class RuleMiss(BaseModel):
    rule_id: str
    reason: str


class DecisionResult(BaseModel):
    decision_id: str
    space_id: str
    rule_version: str
    risk_score: int
    risk_level: Literal["low", "medium", "high", "critical"]
    hits: List[RuleHit] = Field(default_factory=list)
    misses: List[RuleMiss] = Field(default_factory=list)
    created_at: datetime


class ExplanationResponse(BaseModel):
    decision: DecisionResult
    why: List[str] = Field(default_factory=list)
    why_not: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
