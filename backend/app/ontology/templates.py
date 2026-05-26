from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OntologyTemplateApplyRequest(BaseModel):
    space_id: Optional[str] = Field(default=None, max_length=128)
    space_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    space_code: Optional[str] = Field(default=None, max_length=64)
    publish_ga: bool = False


class OntologyTemplateSummary(BaseModel):
    id: str
    title: str
    scenario: str
    description: str
    version: str
    package_counts: Dict[str, int]
    sample: Dict[str, Any]


class OntologyTemplateApplyResult(BaseModel):
    template_id: str
    space_id: str
    created_space: bool = False
    versions: Dict[str, str]
    published: bool = False
    warnings: List[str] = Field(default_factory=list)


CONTRACT_REVIEW_TEMPLATE: Dict[str, Any] = {
    "id": "contract-review",
    "title": "合同审核",
    "scenario": "法务 / 销售合同 / 采购合同",
    "description": "识别合同主体、金额、期限、自动续约和责任上限，输出规则命中和缺失字段。",
    "sample": {
        "contract": {
            "id": "CTR-2026-001",
            "title": "年度服务采购合同",
            "counterparty_name": "星河科技有限公司",
            "amount": 250000,
            "currency": "CNY",
            "effective_date": "2026-05-01",
            "expiry_date": "2027-04-30",
            "governing_law": "中国法律",
            "auto_renewal": True,
            "liability_cap": "",
        },
    },
    "schema": {
        "version": "1.0.0",
        "description": "合同审核本体：合同主体、金额、期限与关键风险字段",
        "entity_types": [
            {
                "name": "Contract",
                "attributes": {
                    "id": {"data_type": "string", "required": True},
                    "title": {"data_type": "string", "required": True},
                    "counterparty_name": {"data_type": "string", "required": True},
                    "amount": {"data_type": "number", "required": True},
                    "currency": {"data_type": "string", "required": False},
                    "effective_date": {"data_type": "string", "required": False},
                    "expiry_date": {"data_type": "string", "required": True},
                    "governing_law": {"data_type": "string", "required": False},
                    "auto_renewal": {"data_type": "boolean", "required": False},
                    "liability_cap": {"data_type": "string", "required": False},
                    "raw_text": {"data_type": "string", "required": False},
                },
                "relations": [],
            },
        ],
        "taxonomy": {},
        "vocabulary": {
            "risk_terms": ["自动续约", "责任上限", "高金额", "到期日", "管辖法律"],
        },
    },
    "mapping": {
        "version": "1.0.0",
        "description": "合同样本到 Contract 对象的默认映射",
        "entity_mappings": [
            {
                "entity_type": "Contract",
                "source_path": "contract",
                "id_template": "contract:{{row.id}}",
                "field_mappings": [
                    {"source_path": "id", "target_attr": "id", "required": True, "transform": "trim"},
                    {"source_path": "title", "target_attr": "title", "required": True, "transform": "trim"},
                    {"source_path": "counterparty_name", "target_attr": "counterparty_name", "required": True, "transform": "trim"},
                    {"source_path": "amount", "target_attr": "amount", "required": True, "transform": "to_float"},
                    {"source_path": "currency", "target_attr": "currency", "transform": "trim"},
                    {"source_path": "effective_date", "target_attr": "effective_date", "transform": "trim"},
                    {"source_path": "expiry_date", "target_attr": "expiry_date", "required": True, "transform": "trim"},
                    {"source_path": "governing_law", "target_attr": "governing_law", "transform": "trim"},
                    {"source_path": "auto_renewal", "target_attr": "auto_renewal", "transform": "to_bool"},
                    {"source_path": "liability_cap", "target_attr": "liability_cap", "transform": "trim"},
                    {"source_path": "raw_text", "target_attr": "raw_text", "transform": "trim"},
                ],
            },
        ],
        "relation_mappings": [],
    },
    "rule": {
        "version": "1.0.0",
        "description": "合同审核默认风险规则",
        "rules": [
            {
                "rule_id": "CONTRACT_HIGH_VALUE",
                "name": "合同金额较高",
                "target_entity_type": "Contract",
                "severity": "high",
                "action": "flag",
                "conditions": [{"path": "entity.amount", "operator": "gt", "value": 100000}],
                "tags": ["amount", "review"],
            },
            {
                "rule_id": "CONTRACT_AUTO_RENEWAL",
                "name": "存在自动续约条款",
                "target_entity_type": "Contract",
                "severity": "medium",
                "action": "recommend",
                "conditions": [{"path": "entity.auto_renewal", "operator": "eq", "value": True}],
                "tags": ["renewal"],
            },
            {
                "rule_id": "CONTRACT_MISSING_LIABILITY_CAP",
                "name": "责任上限缺失",
                "target_entity_type": "Contract",
                "severity": "medium",
                "action": "recommend",
                "conditions": [{"path": "entity.liability_cap", "operator": "eq", "value": ""}],
                "tags": ["liability"],
            },
        ],
    },
}


TEMPLATES: Dict[str, Dict[str, Any]] = {
    CONTRACT_REVIEW_TEMPLATE["id"]: CONTRACT_REVIEW_TEMPLATE,
}


def list_template_summaries() -> List[OntologyTemplateSummary]:
    summaries: List[OntologyTemplateSummary] = []
    for item in TEMPLATES.values():
        summaries.append(
            OntologyTemplateSummary(
                id=item["id"],
                title=item["title"],
                scenario=item["scenario"],
                description=item["description"],
                version=str(item["schema"]["version"]),
                package_counts={
                    "schema": len(item["schema"].get("entity_types", [])),
                    "mapping": len(item["mapping"].get("entity_mappings", [])),
                    "rule": len(item["rule"].get("rules", [])),
                },
                sample=deepcopy(item["sample"]),
            )
        )
    return summaries


def get_template(template_id: str) -> Dict[str, Any]:
    if template_id not in TEMPLATES:
        raise KeyError(template_id)
    return deepcopy(TEMPLATES[template_id])
