from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.ontology.domain_models import DecisionResult, InstanceGraph, MappingTraceItem, OntologyDataSourceRecord


@dataclass
class OntologyActionStep:
    step_id: str
    kind: str
    title: str
    reason: str
    priority: int = 50
    status: str = "suggested"
    tool_name: Optional[str] = None
    data_source_id: Optional[str] = None
    data_source_name: Optional[str] = None
    fields: List[str] = field(default_factory=list)
    entity_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "title": self.title,
            "reason": self.reason,
            "priority": self.priority,
            "status": self.status,
            "tool_name": self.tool_name,
            "data_source_id": self.data_source_id,
            "data_source_name": self.data_source_name,
            "fields": self.fields,
            "entity_types": self.entity_types,
        }


@dataclass
class OntologyActionPlan:
    summary: str
    missing_fields: List[Dict[str, Any]] = field(default_factory=list)
    suggested_data_sources: List[Dict[str, Any]] = field(default_factory=list)
    suggested_tools: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[OntologyActionStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "missing_fields": self.missing_fields,
            "suggested_data_sources": self.suggested_data_sources,
            "suggested_tools": self.suggested_tools,
            "steps": [step.to_dict() for step in sorted(self.steps, key=lambda item: item.priority)],
        }


class OntologyActionPlanner:
    """Builds a safe, explainable plan from ontology runtime outputs.

    This planner intentionally recommends actions instead of executing arbitrary tools.
    Production systems can later attach approval gates or deterministic executors to
    the generated steps.
    """

    def build_plan(
        self,
        *,
        query: str,
        graph: Optional[InstanceGraph],
        decision: Optional[DecisionResult],
        mapping_trace: Sequence[MappingTraceItem] = (),
        schema_payload: Optional[Dict[str, Any]] = None,
        data_sources: Sequence[OntologyDataSourceRecord] = (),
        tool_catalog: Sequence[Dict[str, Any]] = (),
    ) -> OntologyActionPlan:
        missing_fields = self._collect_missing_fields(graph, mapping_trace, schema_payload or {})
        entity_types = sorted({entity.entity_type for entity in (graph.entities if graph else [])})
        data_source_matches = self._rank_data_sources(query, missing_fields, entity_types, data_sources)
        tool_matches = self._rank_tools(query, missing_fields, entity_types, tool_catalog)

        steps: List[OntologyActionStep] = []
        if missing_fields:
            top_source = data_source_matches[0] if data_source_matches else None
            steps.append(
                OntologyActionStep(
                    step_id="complete_required_fields",
                    kind="data_source",
                    title="补齐本体缺失字段",
                    reason="映射或 schema 校验发现必填字段缺失，继续决策前应优先补数。",
                    priority=10,
                    status="required",
                    data_source_id=top_source.get("id") if top_source else None,
                    data_source_name=top_source.get("name") if top_source else None,
                    fields=[item["field"] for item in missing_fields[:20]],
                    entity_types=sorted({item["entity_type"] for item in missing_fields if item.get("entity_type")}),
                )
            )
        if tool_matches:
            top_tool = tool_matches[0]
            steps.append(
                OntologyActionStep(
                    step_id="use_relevant_tool",
                    kind="tool",
                    title=f"优先考虑工具：{top_tool.get('name')}",
                    reason=top_tool.get("reason") or "工具描述与当前本体实体、字段或用户任务匹配。",
                    priority=30,
                    status="suggested",
                    tool_name=top_tool.get("name"),
                    fields=[item["field"] for item in missing_fields[:10]],
                    entity_types=entity_types,
                )
            )
        if decision and (decision.risk_level in {"high", "critical"} or any(hit.action == "block" for hit in decision.hits)):
            steps.append(
                OntologyActionStep(
                    step_id="human_review",
                    kind="human_review",
                    title="进入人工复核",
                    reason="本体规则产生高风险/严重风险或命中阻断动作，生产场景应进入人工确认。",
                    priority=40,
                    status="required",
                    entity_types=entity_types,
                )
            )
        steps.append(
            OntologyActionStep(
                step_id="answer_with_explanation",
                kind="respond",
                title="基于本体结果回答",
                reason="回答应引用已识别实体、命中规则、证据和缺失数据，不编造未执行的动作。",
                priority=90,
                status="required",
                entity_types=entity_types,
            )
        )

        summary_parts = []
        if missing_fields:
            summary_parts.append(f"发现 {len(missing_fields)} 个缺失字段")
        if data_source_matches:
            summary_parts.append(f"匹配 {len(data_source_matches)} 个候选数据源")
        if tool_matches:
            summary_parts.append(f"匹配 {len(tool_matches)} 个候选工具")
        if decision:
            summary_parts.append(f"规则风险等级 {decision.risk_level}")
        summary = "；".join(summary_parts) if summary_parts else "未发现额外工具路由需求，可直接基于本体结果回答"

        return OntologyActionPlan(
            summary=summary,
            missing_fields=missing_fields,
            suggested_data_sources=data_source_matches[:5],
            suggested_tools=tool_matches[:5],
            steps=steps,
        )

    def _collect_missing_fields(
        self,
        graph: Optional[InstanceGraph],
        mapping_trace: Sequence[MappingTraceItem],
        schema_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        missing: List[Dict[str, Any]] = []
        seen = set()

        for item in mapping_trace:
            if item.code != "MAPPING_REQUIRED_MISSING":
                continue
            entity_type, field = self._split_target(item.target or "")
            key = (entity_type, field, item.source_path)
            if key in seen:
                continue
            seen.add(key)
            missing.append({
                "entity_type": entity_type,
                "field": field,
                "source_path": item.source_path,
                "reason": item.message,
                "source": "mapping_trace",
            })

        if not graph:
            return missing

        required_by_type: Dict[str, List[str]] = {}
        for entity_def in schema_payload.get("entity_types", []) or []:
            entity_name = entity_def.get("name")
            attrs = entity_def.get("attributes", {}) or {}
            required = [name for name, meta in attrs.items() if isinstance(meta, dict) and meta.get("required")]
            if entity_name and required:
                required_by_type[entity_name] = required

        for entity in graph.entities:
            required_fields = required_by_type.get(entity.entity_type, [])
            for field_name in required_fields:
                value = (entity.attributes or {}).get(field_name)
                if value not in (None, "", []):
                    continue
                key = (entity.entity_type, field_name, entity.id)
                if key in seen:
                    continue
                seen.add(key)
                missing.append({
                    "entity_type": entity.entity_type,
                    "entity_id": entity.id,
                    "field": field_name,
                    "source_path": None,
                    "reason": "schema required attribute is missing on mapped entity",
                    "source": "schema_validation",
                })
        return missing

    def _rank_data_sources(
        self,
        query: str,
        missing_fields: Sequence[Dict[str, Any]],
        entity_types: Sequence[str],
        data_sources: Sequence[OntologyDataSourceRecord],
    ) -> List[Dict[str, Any]]:
        terms = self._terms([query, *entity_types, *[item.get("field", "") for item in missing_fields]])
        ranked = []
        for source in data_sources:
            kind_value = source.kind.value if hasattr(source.kind, "value") else str(source.kind)
            status_value = source.status.value if hasattr(source.status, "value") else str(source.status)
            searchable = " ".join([
                source.name,
                kind_value,
                source.protocol,
                json.dumps(source.config or {}, ensure_ascii=False),
            ])
            score = self._overlap_score(terms, searchable)
            if status_value == "active":
                score += 2
            if score <= 0 and not missing_fields:
                continue
            ranked.append({
                "id": source.id,
                "name": source.name,
                "kind": kind_value,
                "protocol": source.protocol,
                "status": status_value,
                "score": score,
                "reason": "名称、协议或配置与本体实体/缺失字段匹配" if score > 0 else "存在缺失字段，可作为候选补数来源",
            })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    def _rank_tools(
        self,
        query: str,
        missing_fields: Sequence[Dict[str, Any]],
        entity_types: Sequence[str],
        tool_catalog: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        terms = self._terms([query, *entity_types, *[item.get("field", "") for item in missing_fields]])
        ranked = []
        for tool in tool_catalog:
            name = str(tool.get("name") or "")
            if name.startswith("ontology_") or name in {"transfer_to_agent", "invoke_orchestrator", "upsert_canvas"}:
                continue
            searchable = " ".join([name, str(tool.get("label") or ""), str(tool.get("description") or ""), str(tool.get("category") or "")])
            score = self._overlap_score(terms, searchable)
            category = str(tool.get("category") or "")
            if category in {"api", "mcp", "knowledge", "memory"}:
                score += 1
            if score <= 0:
                continue
            ranked.append({
                "name": name,
                "label": tool.get("label"),
                "category": category,
                "score": score,
                "reason": "工具描述与当前任务、本体实体或缺失字段匹配",
            })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    @staticmethod
    def _split_target(target: str) -> tuple[str, str]:
        if "." in target:
            entity_type, field = target.split(".", 1)
            return entity_type, field
        return "", target or "unknown"

    @staticmethod
    def _terms(values: Iterable[str]) -> List[str]:
        terms = set()
        for value in values:
            for part in re.split(r"[^A-Za-z0-9_\u4e00-\u9fff]+", str(value or "").lower()):
                if len(part) >= 2:
                    terms.add(part)
        return sorted(terms)

    @staticmethod
    def _overlap_score(terms: Sequence[str], text: str) -> int:
        lowered = (text or "").lower()
        return sum(1 for term in terms if term and term in lowered)


ontology_action_planner = OntologyActionPlanner()
