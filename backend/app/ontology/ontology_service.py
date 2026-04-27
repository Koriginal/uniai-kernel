from __future__ import annotations

import re
import threading
import uuid
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException

from app.core.config import settings
from app.ontology.domain_models import (
    DecisionResult,
    EntityInstance,
    EntityMappingRule,
    ExplanationResponse,
    InstanceGraph,
    MappingExecuteRequest,
    MappingExecuteResponse,
    MappingTraceItem,
    PackageKind,
    PackageRecord,
    ReleaseRequest,
    ReleaseResult,
    RelationInstance,
    RuleDef,
    RuleEvaluateRequest,
    RuleHit,
    RuleMiss,
    VersionStage,
    utc_now,
    OntologySpace,
    OntologySpaceCreate,
    SchemaPackageCreate,
    MappingPackageCreate,
    RulePackageCreate,
)

_SEVERITY_WEIGHTS = {
    "low": 5,
    "medium": 10,
    "high": 20,
    "critical": 40,
}


class OntologyService:
    """
    In-memory ontology engine.

    该实现先把“本体能力层”补齐为可运行服务：
    - 映射（mapping）
    - 规则执行（rule evaluate）
    - 版本治理（release stage）
    - 可解释（explain decision）

    后续可通过 repository 接口替换为 DB 持久化。
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._spaces: Dict[str, OntologySpace] = {}
        self._packages: Dict[Tuple[str, PackageKind, str], PackageRecord] = {}
        self._active_versions: Dict[Tuple[str, PackageKind], str] = {}
        self._decisions: Dict[str, ExplanationResponse] = {}

    # -----------------------------
    # Space
    # -----------------------------
    def create_space(self, payload: OntologySpaceCreate, owner_user_id: str) -> OntologySpace:
        with self._lock:
            code = self._normalize_code(payload.code or payload.name)
            existed = next((s for s in self._spaces.values() if s.code == code), None)
            if existed:
                return existed

            space = OntologySpace(
                id=f"onto-space-{uuid.uuid4().hex[:10]}",
                name=payload.name.strip(),
                code=code,
                description=(payload.description or "").strip() or None,
                owner_user_id=owner_user_id,
                created_at=utc_now(),
            )
            self._spaces[space.id] = space
            return space

    def list_spaces(self, owner_user_id: str, include_admin_owned: bool = True) -> List[OntologySpace]:
        with self._lock:
            out: List[OntologySpace] = []
            for item in self._spaces.values():
                if item.owner_user_id == owner_user_id:
                    out.append(item)
                elif include_admin_owned and item.owner_user_id == "admin":
                    out.append(item)
            out.sort(key=lambda x: x.created_at, reverse=True)
            return out

    # -----------------------------
    # Package Upsert
    # -----------------------------
    def upsert_schema(self, payload: SchemaPackageCreate, actor_user_id: str) -> PackageRecord:
        self._ensure_space_access(payload.space_id, actor_user_id)
        data = payload.model_dump()

        # 基础结构校验：实体类型名唯一
        names = [e["name"] for e in data.get("entity_types", [])]
        if len(names) != len(set(names)):
            raise HTTPException(status_code=400, detail="schema entity_types contains duplicate names")

        return self._upsert_package(
            space_id=payload.space_id,
            kind=PackageKind.schema,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    def upsert_mapping(self, payload: MappingPackageCreate, actor_user_id: str) -> PackageRecord:
        self._ensure_space_access(payload.space_id, actor_user_id)
        data = payload.model_dump()

        # 快速校验：entity_type + id_template 存在
        for item in data.get("entity_mappings", []):
            if not item.get("entity_type") or not item.get("id_template"):
                raise HTTPException(status_code=400, detail="entity mapping requires entity_type and id_template")

        return self._upsert_package(
            space_id=payload.space_id,
            kind=PackageKind.mapping,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    def upsert_rule(self, payload: RulePackageCreate, actor_user_id: str) -> PackageRecord:
        self._ensure_space_access(payload.space_id, actor_user_id)
        data = payload.model_dump()

        rule_ids = [r["rule_id"] for r in data.get("rules", [])]
        if len(rule_ids) != len(set(rule_ids)):
            raise HTTPException(status_code=400, detail="rule package contains duplicate rule_id")

        return self._upsert_package(
            space_id=payload.space_id,
            kind=PackageKind.rule,
            version=payload.version,
            payload=data,
            actor_user_id=actor_user_id,
        )

    def list_packages(self, space_id: str, kind: PackageKind, actor_user_id: str) -> List[PackageRecord]:
        self._ensure_space_access(space_id, actor_user_id)
        with self._lock:
            rows = [
                deepcopy(v)
                for (sid, pk, _), v in self._packages.items()
                if sid == space_id and pk == kind
            ]
            rows.sort(key=lambda x: (x.updated_at, x.version), reverse=True)
            return rows

    # -----------------------------
    # Governance / Release
    # -----------------------------
    def release(self, payload: ReleaseRequest, actor_user_id: str) -> ReleaseResult:
        self._ensure_space_access(payload.space_id, actor_user_id)

        key = (payload.space_id, payload.kind, payload.version)
        with self._lock:
            record = self._packages.get(key)
            if not record:
                raise HTTPException(status_code=404, detail="package version not found")
            if payload.target_stage == VersionStage.draft:
                raise HTTPException(status_code=400, detail="release target_stage cannot be draft")

            warnings: List[str] = []
            self._validate_stage_transition(record.stage, payload.target_stage)

            # GA 发布时，做最小兼容性检查 + 自动处理现行 GA
            if payload.target_stage == VersionStage.ga:
                warnings.extend(self._collect_release_warnings(record))
                if payload.strict_compatibility and warnings:
                    raise HTTPException(
                        status_code=409,
                        detail={"message": "compatibility checks failed", "warnings": warnings},
                    )
                active_key = (payload.space_id, payload.kind)
                prev_ga = self._active_versions.get(active_key)
                if prev_ga and prev_ga != payload.version:
                    prev = self._packages.get((payload.space_id, payload.kind, prev_ga))
                    if prev:
                        prev.stage = VersionStage.deprecated
                        prev.updated_at = utc_now()
                self._active_versions[active_key] = payload.version

            record.stage = payload.target_stage
            record.notes = payload.notes
            record.updated_at = utc_now()

            return ReleaseResult(
                ok=True,
                space_id=payload.space_id,
                kind=payload.kind,
                version=payload.version,
                stage=payload.target_stage,
                warnings=warnings,
            )

    # -----------------------------
    # Mapping Execution
    # -----------------------------
    def execute_mapping(self, req: MappingExecuteRequest, actor_user_id: str) -> MappingExecuteResponse:
        self._ensure_space_access(req.space_id, actor_user_id)

        mapping_record = self._resolve_package(
            req.space_id,
            PackageKind.mapping,
            req.mapping_version,
            actor_user_id,
        )
        schema_record: Optional[PackageRecord] = None
        if req.schema_version or (req.space_id, PackageKind.schema) in self._active_versions:
            schema_record = self._resolve_package(
                req.space_id,
                PackageKind.schema,
                req.schema_version,
                actor_user_id,
            )

        payload = mapping_record.payload
        entity_rules = [EntityMappingRule.model_validate(x) for x in payload.get("entity_mappings", [])]
        relation_rules = payload.get("relation_mappings", [])

        entities: Dict[str, EntityInstance] = {}
        relations: List[RelationInstance] = []
        trace: List[MappingTraceItem] = []

        for rule in entity_rules:
            rows = self._resolve_source_rows(req.input_payload, rule.source_path)
            if not rows:
                trace.append(MappingTraceItem(code="MAPPING_SOURCE_EMPTY", message=f"entity source has no rows: {rule.entity_type}", source_path=rule.source_path))
                continue

            for idx, row in enumerate(rows):
                ctx = {"row": row, "root": req.input_payload, "index": idx}
                entity_id = self._render_template(rule.id_template, ctx)
                if not entity_id:
                    trace.append(MappingTraceItem(code="MAPPING_ENTITY_ID_EMPTY", message=f"entity id_template rendered empty for {rule.entity_type}", target=rule.entity_type))
                    continue

                attrs: Dict[str, Any] = {}
                for fm in rule.field_mappings:
                    raw = self._pick_value(row, req.input_payload, fm.source_path)
                    if raw is None:
                        raw = fm.default_value
                    if raw is None and fm.required:
                        trace.append(MappingTraceItem(code="MAPPING_REQUIRED_MISSING", message=f"required source missing: {fm.source_path}", source_path=fm.source_path, target=f"{rule.entity_type}.{fm.target_attr}"))
                        continue
                    attrs[fm.target_attr] = self._apply_transform(raw, fm.transform)

                entities[entity_id] = EntityInstance(id=entity_id, entity_type=rule.entity_type, attributes=attrs)

        for rel in relation_rules:
            source_path = rel.get("source_path")
            rows = self._resolve_source_rows(req.input_payload, source_path)
            if not rows:
                rows = [req.input_payload]

            for idx, row in enumerate(rows):
                ctx = {"row": row, "root": req.input_payload, "index": idx}
                source_id = self._render_template(rel.get("source_entity_template", ""), ctx)
                target_id = self._render_template(rel.get("target_entity_template", ""), ctx)

                if source_id not in entities or target_id not in entities:
                    trace.append(
                        MappingTraceItem(
                            code="MAPPING_RELATION_SKIPPED",
                            message="relation skipped because source or target entity not found",
                            target=f"{rel.get('relation_type')}:{source_id}->{target_id}",
                            source_path=source_path,
                        )
                    )
                    continue

                relations.append(
                    RelationInstance(
                        relation_type=rel.get("relation_type", "related_to"),
                        source_id=source_id,
                        target_id=target_id,
                        attributes=rel.get("attributes", {}) or {},
                    )
                )

        if schema_record:
            trace.extend(self._validate_graph_against_schema(list(entities.values()), schema_record.payload))

        if len(trace) > settings.ONTOLOGY_MAX_TRACE_ITEMS:
            trace = trace[: settings.ONTOLOGY_MAX_TRACE_ITEMS]
            trace.append(
                MappingTraceItem(
                    code="TRACE_TRUNCATED",
                    message=f"trace truncated to {settings.ONTOLOGY_MAX_TRACE_ITEMS} items",
                )
            )

        graph = InstanceGraph(
            entities=list(entities.values()),
            relations=relations,
            metadata={
                "space_id": req.space_id,
                "mapping_version": mapping_record.version,
                "schema_version": schema_record.version if schema_record else None,
            },
        )

        return MappingExecuteResponse(
            graph=graph,
            mapping_version=mapping_record.version,
            schema_version=schema_record.version if schema_record else None,
            trace=trace,
        )

    # -----------------------------
    # Rules + Explain
    # -----------------------------
    def evaluate_rules(self, req: RuleEvaluateRequest, actor_user_id: str) -> DecisionResult:
        self._ensure_space_access(req.space_id, actor_user_id)
        rule_record = self._resolve_package(req.space_id, PackageKind.rule, req.rule_version, actor_user_id)

        rules = [RuleDef.model_validate(item) for item in rule_record.payload.get("rules", [])]
        hits: List[RuleHit] = []
        misses: List[RuleMiss] = []

        by_type: Dict[str, List[EntityInstance]] = defaultdict(list)
        for entity in req.graph.entities:
            by_type[entity.entity_type].append(entity)

        for rule in rules:
            scope_entities: Iterable[Optional[EntityInstance]]
            if rule.target_entity_type:
                scope_entities = by_type.get(rule.target_entity_type, [])
                if not scope_entities:
                    misses.append(RuleMiss(rule_id=rule.rule_id, reason=f"no entity for target type {rule.target_entity_type}"))
                    continue
            else:
                scope_entities = [None]

            rule_hit = False
            for entity in scope_entities:
                ok, reason = self._evaluate_conditions(rule.conditions, entity, req.graph, req.context)
                if ok:
                    hits.append(
                        RuleHit(
                            rule_id=rule.rule_id,
                            name=rule.name,
                            severity=rule.severity,
                            action=rule.action,
                            entity_id=entity.id if entity else None,
                            reason=reason,
                        )
                    )
                    rule_hit = True
            if not rule_hit:
                misses.append(RuleMiss(rule_id=rule.rule_id, reason="conditions not met"))

        risk_score = sum(_SEVERITY_WEIGHTS.get(hit.severity, 0) for hit in hits)
        risk_level = self._to_risk_level(risk_score)

        decision = DecisionResult(
            decision_id=f"decision-{uuid.uuid4().hex[:10]}",
            space_id=req.space_id,
            rule_version=rule_record.version,
            risk_score=risk_score,
            risk_level=risk_level,
            hits=hits,
            misses=misses,
            created_at=utc_now(),
        )

        explanation = self._build_explanation(decision, req)
        with self._lock:
            self._decisions[decision.decision_id] = explanation

        return decision

    def explain(self, decision_id: str, actor_user_id: str) -> ExplanationResponse:
        # decision 结果按当前内存存储，不做 owner 校验，避免中途协作读不到
        _ = actor_user_id
        with self._lock:
            item = self._decisions.get(decision_id)
            if not item:
                raise HTTPException(status_code=404, detail="decision not found")
            return item

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _upsert_package(
        self,
        *,
        space_id: str,
        kind: PackageKind,
        version: str,
        payload: Dict[str, Any],
        actor_user_id: str,
    ) -> PackageRecord:
        self._assert_version(version)

        now = utc_now()
        key = (space_id, kind, version)
        with self._lock:
            existed = self._packages.get(key)
            stage = existed.stage if existed else VersionStage.draft
            record = PackageRecord(
                kind=kind,
                space_id=space_id,
                version=version,
                stage=stage,
                created_by=existed.created_by if existed else actor_user_id,
                created_at=existed.created_at if existed else now,
                updated_at=now,
                notes=existed.notes if existed else None,
                payload=payload,
            )
            self._packages[key] = record
            return deepcopy(record)

    def _resolve_package(
        self,
        space_id: str,
        kind: PackageKind,
        version: Optional[str],
        actor_user_id: str,
    ) -> PackageRecord:
        self._ensure_space_access(space_id, actor_user_id)
        with self._lock:
            resolved_version = version
            if not resolved_version:
                resolved_version = self._active_versions.get((space_id, kind))
            if not resolved_version:
                raise HTTPException(status_code=404, detail=f"no active {kind.value} package version")

            record = self._packages.get((space_id, kind, resolved_version))
            if not record:
                raise HTTPException(status_code=404, detail=f"{kind.value} package version not found")
            return deepcopy(record)

    def _ensure_space_access(self, space_id: str, actor_user_id: str) -> None:
        with self._lock:
            space = self._spaces.get(space_id)
            if not space:
                raise HTTPException(status_code=404, detail="ontology space not found")
            if actor_user_id != "admin" and space.owner_user_id not in {actor_user_id, "admin"}:
                raise HTTPException(status_code=403, detail="forbidden to access this ontology space")

    @staticmethod
    def _normalize_code(value: str) -> str:
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_\-]", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text[:64] or f"space-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _assert_version(version: str) -> None:
        if not re.match(r"^\d+\.\d+\.\d+$", version or ""):
            raise HTTPException(status_code=400, detail="version must follow semver like 1.0.0")

    @staticmethod
    def _validate_stage_transition(current: VersionStage, target: VersionStage) -> None:
        allowed = {
            VersionStage.draft: {VersionStage.review, VersionStage.staging, VersionStage.ga, VersionStage.deprecated},
            VersionStage.review: {VersionStage.staging, VersionStage.ga, VersionStage.deprecated},
            VersionStage.staging: {VersionStage.ga, VersionStage.deprecated},
            VersionStage.ga: {VersionStage.deprecated},
            VersionStage.deprecated: set(),
        }
        if target == current:
            return
        if target not in allowed[current]:
            raise HTTPException(status_code=400, detail=f"invalid stage transition: {current.value} -> {target.value}")

    def _collect_release_warnings(self, candidate: PackageRecord) -> List[str]:
        warnings: List[str] = []
        active_version = self._active_versions.get((candidate.space_id, candidate.kind))
        if not active_version:
            return warnings

        prev = self._packages.get((candidate.space_id, candidate.kind, active_version))
        if not prev:
            return warnings

        old_major = int(prev.version.split(".")[0])
        new_major = int(candidate.version.split(".")[0])

        if candidate.kind == PackageKind.schema and new_major == old_major:
            old_entities = {e.get("name") for e in prev.payload.get("entity_types", [])}
            new_entities = {e.get("name") for e in candidate.payload.get("entity_types", [])}
            removed = sorted(old_entities - new_entities)
            if removed:
                warnings.append(
                    f"schema removes entity types without major bump: {', '.join(removed)}"
                )

        if candidate.kind == PackageKind.rule and new_major == old_major:
            old_rules = {r.get("rule_id") for r in prev.payload.get("rules", [])}
            new_rules = {r.get("rule_id") for r in candidate.payload.get("rules", [])}
            removed = sorted(old_rules - new_rules)
            if removed:
                warnings.append(
                    f"rule package removes rules without major bump: {', '.join(removed)}"
                )

        return warnings

    @staticmethod
    def _resolve_source_rows(payload: Dict[str, Any], source_path: Optional[str]) -> List[Dict[str, Any]]:
        if not source_path:
            return [payload]
        value = OntologyService._get_path(payload, source_path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _get_path(data: Any, path: str) -> Any:
        cur = data
        for part in (path or "").split("."):
            if part == "":
                continue
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @staticmethod
    def _pick_value(row: Dict[str, Any], root: Dict[str, Any], path: str) -> Any:
        value = OntologyService._get_path(row, path)
        if value is None:
            value = OntologyService._get_path(root, path)
        return value

    @staticmethod
    def _render_template(template: str, ctx: Dict[str, Any]) -> str:
        if not template:
            return ""

        def replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if expr.startswith("row."):
                return str(OntologyService._get_path(ctx.get("row", {}), expr[4:]) or "")
            if expr.startswith("root."):
                return str(OntologyService._get_path(ctx.get("root", {}), expr[5:]) or "")
            if expr == "index":
                return str(ctx.get("index", ""))
            return str(OntologyService._get_path(ctx.get("row", {}), expr) or "")

        rendered = re.sub(r"\{\{\s*([^}]+)\s*\}\}", replace, template)
        return rendered.strip()

    @staticmethod
    def _apply_transform(value: Any, transform: Any) -> Any:
        if value is None or transform is None:
            return value

        name = getattr(transform, "value", transform)
        try:
            if name == "trim":
                return str(value).strip()
            if name == "lower":
                return str(value).lower()
            if name == "upper":
                return str(value).upper()
            if name == "to_int":
                return int(value)
            if name == "to_float":
                return float(value)
            if name == "to_bool":
                text = str(value).strip().lower()
                return text in {"1", "true", "yes", "y", "on"}
        except Exception:
            return value
        return value

    def _validate_graph_against_schema(
        self,
        entities: List[EntityInstance],
        schema_payload: Dict[str, Any],
    ) -> List[MappingTraceItem]:
        trace: List[MappingTraceItem] = []
        schema_entities = {item.get("name"): item for item in schema_payload.get("entity_types", [])}

        for entity in entities:
            schema = schema_entities.get(entity.entity_type)
            if not schema:
                trace.append(
                    MappingTraceItem(
                        code="SCHEMA_ENTITY_UNKNOWN",
                        message=f"entity type not found in schema: {entity.entity_type}",
                        target=entity.entity_type,
                    )
                )
                continue

            attrs = schema.get("attributes", {})
            for name, item in attrs.items():
                if item.get("required") and entity.attributes.get(name) is None:
                    trace.append(
                        MappingTraceItem(
                            code="SCHEMA_REQUIRED_MISSING",
                            message=f"required attribute missing: {name}",
                            target=f"{entity.id}.{name}",
                        )
                    )

        return trace

    def _evaluate_conditions(
        self,
        conditions: List[Any],
        entity: Optional[EntityInstance],
        graph: InstanceGraph,
        context: Dict[str, Any],
    ) -> Tuple[bool, str]:
        for cond in conditions:
            left = self._resolve_condition_path(cond.path, entity, graph, context)
            ok = self._compare(left, cond.operator, cond.value)
            if not ok:
                return False, f"condition failed: {cond.path} {cond.operator}"
        return True, "all conditions matched"

    @staticmethod
    def _resolve_condition_path(path: str, entity: Optional[EntityInstance], graph: InstanceGraph, context: Dict[str, Any]) -> Any:
        if path.startswith("entity."):
            if not entity:
                return None
            key = path[len("entity."):]
            if key == "id":
                return entity.id
            if key == "type":
                return entity.entity_type
            return entity.attributes.get(key)

        if path.startswith("context."):
            key = path[len("context."):]
            return OntologyService._get_path(context, key)

        if path.startswith("graph."):
            key = path[len("graph."):]
            if key == "entity_count":
                return len(graph.entities)
            if key == "relation_count":
                return len(graph.relations)

        return None

    @staticmethod
    def _compare(left: Any, operator: str, right: Any) -> bool:
        if operator == "exists":
            return left is not None and left != ""
        if operator == "eq":
            return left == right
        if operator == "neq":
            return left != right
        if operator == "gt":
            return left is not None and right is not None and left > right
        if operator == "gte":
            return left is not None and right is not None and left >= right
        if operator == "lt":
            return left is not None and right is not None and left < right
        if operator == "lte":
            return left is not None and right is not None and left <= right
        if operator == "contains":
            if left is None:
                return False
            if isinstance(left, list):
                return right in left
            return str(right) in str(left)
        if operator == "in":
            if right is None:
                return False
            try:
                return left in right
            except TypeError:
                return False
        return False

    @staticmethod
    def _to_risk_level(score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 40:
            return "high"
        if score >= 20:
            return "medium"
        return "low"

    @staticmethod
    def _build_explanation(decision: DecisionResult, req: RuleEvaluateRequest) -> ExplanationResponse:
        why = [f"hit rule {h.rule_id} ({h.severity}) on entity {h.entity_id or 'global'}" for h in decision.hits[:12]]
        why_not = [f"rule {m.rule_id} not triggered: {m.reason}" for m in decision.misses[:12]]

        evidence = {
            "graph_entity_count": len(req.graph.entities),
            "graph_relation_count": len(req.graph.relations),
            "rule_version": decision.rule_version,
            "risk_score": decision.risk_score,
            "risk_level": decision.risk_level,
        }

        return ExplanationResponse(
            decision=decision,
            why=why,
            why_not=why_not,
            evidence=evidence,
        )


ontology_service = OntologyService()
