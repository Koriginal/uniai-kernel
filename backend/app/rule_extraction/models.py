from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RuleExtractionRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    source_type: str = Field(default="policy_doc", max_length=80)
    text: str = Field(..., min_length=1, max_length=200000)
    max_rules: int = Field(default=100, ge=1, le=500)


class ExtractedClause(BaseModel):
    locator: str
    text: str
    chapter_path: List[str] = Field(default_factory=list)
    line_start: int
    line_end: int
    is_rule_like: bool = False


class ExtractedRuleCandidate(BaseModel):
    rule_code: str
    name: str
    description: str
    target_entity_type: Optional[str] = None
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    severity: str
    action: str
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    extraction: Dict[str, Any] = Field(default_factory=dict)


class RuleExtractionResult(BaseModel):
    title: Optional[str] = None
    source_type: str
    text_hash: str
    clause_count: int
    rule_count: int
    clauses: List[ExtractedClause] = Field(default_factory=list)
    rules: List[ExtractedRuleCandidate] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RuleExtractionUploadResult(RuleExtractionResult):
    file_name: str
    content_type: Optional[str] = None
    upload_metadata: Dict[str, Any] = Field(default_factory=dict)
