from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ontology.domain_models import (
    ExplanationResponse,
    InstanceGraph,
    MappingExecuteRequest,
    MappingExecuteResponse,
    PackageKind,
    RuleEvaluateRequest,
    DecisionResult,
)
from app.ontology.persistent_service import persistent_ontology_service
from app.ontology.runtime import ontology_runtime
from app.ontology.action_planner import ontology_action_planner
from app.ontology.action_executor import ontology_action_executor


@dataclass
class OntologyPipelineResult:
    """Runtime snapshot produced before the LLM answers a turn."""

    enabled: bool
    status: str
    space_id: Optional[str] = None
    space_name: Optional[str] = None
    space_code: Optional[str] = None
    message: str = ""
    active_versions: Dict[str, str] = field(default_factory=dict)
    missing_active_packages: List[str] = field(default_factory=list)
    input_payload: Optional[Dict[str, Any]] = None
    graph_id: Optional[str] = None
    mapping: Optional[MappingExecuteResponse] = None
    decision: Optional[DecisionResult] = None
    explanation: Optional[ExplanationResponse] = None
    action_plan: Optional[Dict[str, Any]] = None
    action_execution: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    should_block: bool = False
    trigger_reason: str = ""
    trigger_signals: List[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        if not self.enabled:
            return ""

        payload: Dict[str, Any] = {
            "status": self.status,
            "space_id": self.space_id,
            "space_name": self.space_name,
            "space_code": self.space_code,
            "message": self.message,
            "active_versions": self.active_versions,
            "missing_active_packages": self.missing_active_packages,
            "warnings": self.warnings,
            "should_block": self.should_block,
            "trigger_reason": self.trigger_reason,
            "trigger_signals": self.trigger_signals,
        }
        if self.graph_id:
            payload["graph_id"] = self.graph_id
        if self.mapping:
            payload["mapping"] = {
                "entity_count": len(self.mapping.graph.entities),
                "relation_count": len(self.mapping.graph.relations),
                "mapping_version": self.mapping.mapping_version,
                "schema_version": self.mapping.schema_version,
                "trace": [item.model_dump(mode="json") for item in self.mapping.trace[:20]],
                "graph": self.mapping.graph.model_dump(mode="json"),
            }
        if self.decision:
            payload["decision"] = self.decision.model_dump(mode="json")
        if self.explanation:
            payload["explanation"] = {
                "why": self.explanation.why[:20],
                "why_not": self.explanation.why_not[:20],
                "evidence": self.explanation.evidence,
            }
        if self.action_plan:
            payload["action_plan"] = self.action_plan
        if self.action_execution:
            payload["action_execution"] = self.action_execution

        return (
            "\n\n[ONTOLOGY PIPELINE SNAPSHOT]\n"
            "系统已在回答前尝试执行本体运行时流水线。你必须基于该快照回答，"
            "不要编造未出现的规则、实体或数据源。若用户询问本体空间，优先使用 space_name，可括号补充 space_code，不要只复述 space_id。"
            "若 status 不是 success，请说明本体未完整执行的原因。\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        )

    def to_event(self) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "type": "ontology_runtime",
            "status": self.status,
            "space_id": self.space_id,
            "space_name": self.space_name,
            "space_code": self.space_code,
            "message": self.message,
            "active_versions": self.active_versions,
            "missing_active_packages": self.missing_active_packages,
            "warnings": self.warnings,
            "should_block": self.should_block,
            "trigger_reason": self.trigger_reason,
            "trigger_signals": self.trigger_signals,
        }
        if self.graph_id:
            event["graph_id"] = self.graph_id
        if self.mapping:
            event["mapping"] = {
                "entity_count": len(self.mapping.graph.entities),
                "relation_count": len(self.mapping.graph.relations),
                "trace_count": len(self.mapping.trace),
            }
        if self.decision:
            event["decision"] = {
                "decision_id": self.decision.decision_id,
                "risk_level": self.decision.risk_level,
                "risk_score": self.decision.risk_score,
                "hit_count": len(self.decision.hits),
                "miss_count": len(self.decision.misses),
            }
        if self.explanation:
            event["explanation"] = {
                "why_count": len(self.explanation.why),
                "why_not_count": len(self.explanation.why_not),
                "evidence_count": len(self.explanation.evidence or []),
            }
        if self.action_plan:
            event["action_plan"] = {
                "summary": self.action_plan.get("summary"),
                "step_count": len(self.action_plan.get("steps") or []),
                "missing_field_count": len(self.action_plan.get("missing_fields") or []),
                "suggested_tool_count": len(self.action_plan.get("suggested_tools") or []),
                "suggested_data_source_count": len(self.action_plan.get("suggested_data_sources") or []),
            }
        if self.action_execution:
            event["action_execution"] = {
                "status": self.action_execution.get("status"),
                "applied_patch_count": self.action_execution.get("applied_patch_count", 0),
                "execution_count": len(self.action_execution.get("executions") or []),
            }
        return event

    def to_response(self) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "enabled": self.enabled,
            "status": self.status,
            "space_id": self.space_id,
            "space_name": self.space_name,
            "space_code": self.space_code,
            "message": self.message,
            "active_versions": self.active_versions,
            "missing_active_packages": self.missing_active_packages,
            "graph_id": self.graph_id,
            "warnings": self.warnings,
            "should_block": self.should_block,
            "trigger_reason": self.trigger_reason,
            "trigger_signals": self.trigger_signals,
            "action_plan": self.action_plan,
            "action_execution": self.action_execution,
        }
        if self.mapping:
            response["mapping"] = {
                "graph": self.mapping.graph.model_dump(mode="json"),
                "mapping_version": self.mapping.mapping_version,
                "schema_version": self.mapping.schema_version,
                "trace": [item.model_dump(mode="json") for item in self.mapping.trace],
            }
        if self.decision:
            response["decision"] = self.decision.model_dump(mode="json")
        if self.explanation:
            response["explanation"] = {
                "decision": self.explanation.decision.model_dump(mode="json"),
                "why": self.explanation.why,
                "why_not": self.explanation.why_not,
                "evidence": self.explanation.evidence,
            }
        return response


class OntologyRuntimePipeline:
    """Best-effort ontology runtime pipeline used by agents before LLM reasoning."""

    async def run(
        self,
        db: AsyncSession,
        *,
        raw_config: Optional[Dict[str, Any]],
        user_id: str,
        is_admin: bool = False,
        query: str = "",
        explicit_payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> OntologyPipelineResult:
        config = ontology_runtime.normalize_config(raw_config)
        if not config.get("enabled"):
            return OntologyPipelineResult(
                enabled=False,
                status="disabled",
                message="ontology disabled",
                trigger_reason="本体配置未启用",
            )

        mode = config.get("mode") or "auto"
        fallback = config.get("fallback_when_unavailable") or "continue_without_ontology"
        required = mode == "required" or fallback == "stop_and_ask"

        try:
            input_payload = (
                explicit_payload
                or self.extract_json_payload(query)
                or self.extract_domain_text_payload(query)
            )
            trigger_signals = self.detect_trigger_signals(query, input_payload=input_payload, mode=mode)
            if mode == "auto" and not input_payload and not self.looks_like_ontology_task(query):
                return OntologyPipelineResult(
                    enabled=True,
                    status="idle",
                    message="当前请求不像本体任务，未执行本体流水线",
                    trigger_reason="auto 模式未发现结构化输入、合同文本或审核/风控类关键词",
                    trigger_signals=trigger_signals,
                )

            space_id = await ontology_runtime.resolve_space(
                db,
                config=config,
                user_id=user_id,
                is_admin=is_admin,
                query=query,
            )
            if not space_id:
                return OntologyPipelineResult(
                    enabled=True,
                    status="unavailable",
                    message="没有可用本体空间",
                    should_block=required,
                    trigger_reason="已触发本体，但没有解析到可访问的本体空间",
                    trigger_signals=trigger_signals,
                )

            contract = await ontology_runtime.build_contract(
                db,
                space_id=space_id,
                user_id=user_id,
                is_admin=is_admin,
            )
            active_versions = contract.get("active_versions") or {}
            missing = contract.get("missing_active_packages") or []
            space_name = contract.get("space_name")
            space_code = contract.get("space_code")

            if not input_payload:
                return OntologyPipelineResult(
                    enabled=True,
                    status="waiting_for_input",
                    space_id=space_id,
                    space_name=space_name,
                    space_code=space_code,
                    message="未检测到可映射的业务输入，本轮仅注入本体契约",
                    active_versions=active_versions,
                    missing_active_packages=missing,
                    warnings=["需要 JSON 或可识别的业务文本后才能自动执行 mapping/rule/explain"],
                    should_block=False,
                    trigger_reason="已触发本体契约注入，但未检测到可映射业务输入",
                    trigger_signals=trigger_signals,
                )

            if "mapping" in missing:
                return OntologyPipelineResult(
                    enabled=True,
                    status="missing_mapping",
                    space_id=space_id,
                    space_name=space_name,
                    space_code=space_code,
                    message="当前空间没有正式 mapping 包，无法自动生成实例图",
                    active_versions=active_versions,
                    missing_active_packages=missing,
                    input_payload=input_payload,
                    should_block=required,
                    trigger_reason="检测到业务输入，但当前空间缺少正式 mapping 包",
                    trigger_signals=trigger_signals,
                )

            mapping = await persistent_ontology_service.execute_mapping(
                db,
                MappingExecuteRequest(
                    space_id=space_id,
                    input_payload=input_payload,
                    persist_graph=True,
                    source="agent_runtime",
                    session_id=session_id,
                    request_id=request_id,
                ),
                actor_user_id=user_id,
                is_admin=is_admin,
            )
            graph_id = mapping.graph_id

            decision: Optional[DecisionResult] = None
            explanation: Optional[ExplanationResponse] = None
            warnings: List[str] = []

            if "rule" in missing:
                warnings.append("当前空间没有正式 rule 包，已完成映射但无法执行规则")
            else:
                decision = await persistent_ontology_service.evaluate_rules(
                    db,
                    RuleEvaluateRequest(
                        space_id=space_id,
                        graph=InstanceGraph.model_validate(mapping.graph),
                        context={"source": "agent_runtime_pipeline"},
                    ),
                    actor_user_id=user_id,
                    is_admin=is_admin,
                )
                if graph_id:
                    await persistent_ontology_service.link_instance_graph_decision(
                        db,
                        graph_id=graph_id,
                        decision_id=decision.decision_id,
                        actor_user_id=user_id,
                        is_admin=is_admin,
                    )
                if config.get("explain_required", True):
                    explanation = await persistent_ontology_service.explain(
                        db,
                        decision_id=decision.decision_id,
                        actor_user_id=user_id,
                        is_admin=is_admin,
                    )

            action_plan = await self._build_action_plan(
                db,
                space_id=space_id,
                user_id=user_id,
                is_admin=is_admin,
                query=query,
                graph=mapping.graph,
                decision=decision,
                mapping_trace=mapping.trace,
            )
            action_execution = await self._execute_action_plan_safe(
                db,
                space_id=space_id,
                user_id=user_id,
                is_admin=is_admin,
                graph=mapping.graph,
                action_plan=action_plan,
            )
            if action_execution.get("_graph") is not None:
                mapping.graph = action_execution.pop("_graph")
                if graph_id:
                    await persistent_ontology_service.update_instance_graph_snapshot(
                        db,
                        graph_id=graph_id,
                        graph=mapping.graph,
                        actor_user_id=user_id,
                        is_admin=is_admin,
                        metadata_patch={"action_execution": action_execution},
                    )

            should_block = False
            if decision:
                should_block = any(hit.action == "block" for hit in decision.hits) or decision.risk_level == "critical"
                if config.get("strict_rules") and decision.risk_level in {"high", "critical"}:
                    should_block = True

            return OntologyPipelineResult(
                enabled=True,
                status="success" if decision else "mapped_only",
                space_id=space_id,
                space_name=space_name,
                space_code=space_code,
                message="本体运行时流水线已执行",
                active_versions=active_versions,
                missing_active_packages=missing,
                input_payload=input_payload,
                graph_id=graph_id,
                mapping=mapping,
                decision=decision,
                explanation=explanation,
                action_plan=action_plan,
                action_execution=action_execution,
                warnings=warnings,
                should_block=should_block,
                trigger_reason=self.build_trigger_reason(mode=mode, input_payload=input_payload, query=query),
                trigger_signals=trigger_signals,
            )
        except Exception as exc:
            return OntologyPipelineResult(
                enabled=True,
                status="error",
                message=f"本体运行时执行失败：{exc}",
                should_block=required,
                trigger_reason="本体已触发，但运行时执行异常",
                trigger_signals=self.detect_trigger_signals(query, input_payload=None, mode=mode),
            )

    @staticmethod
    def extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from a user message without trusting arbitrary code."""
        if not text:
            return None

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        candidates = [fenced.group(1)] if fenced else []

        start = text.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape = False
            for idx in range(start, len(text)):
                char = text[idx]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : idx + 1])
                        break

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @classmethod
    def extract_domain_text_payload(cls, text: str) -> Optional[Dict[str, Any]]:
        """Best-effort conversion from business prose to ontology input.

        This is intentionally conservative: it only activates for obvious domain
        documents and preserves raw text so downstream mapping/rules can still be
        explained even when not every field is parsed.
        """
        return cls.extract_contract_text_payload(text)

    @staticmethod
    def extract_contract_text_payload(text: str) -> Optional[Dict[str, Any]]:
        if not text or not OntologyRuntimePipeline.looks_like_contract_document(text):
            return None

        raw_text = text.strip()
        normalized = re.sub(r"\r\n?", "\n", raw_text)
        compact = re.sub(r"[ \t]+", " ", normalized)
        lower = compact.lower()

        def find_line(patterns: List[str]) -> Optional[str]:
            for pattern in patterns:
                match = re.search(pattern, compact, flags=re.IGNORECASE | re.MULTILINE)
                if match:
                    value = (match.group(1) or "").strip(" ：:\t\r\n")
                    if value:
                        return value[:300]
            return None

        def first_meaningful_line() -> Optional[str]:
            for line in normalized.splitlines():
                value = line.strip(" #\t")
                if len(value) >= 4 and not value.lower().startswith(("party ", "address:", "phone:", "email:")):
                    return value[:300]
            return None

        def parse_amount() -> Optional[float]:
            patterns = [
                r"(?:total\s+(?:contract\s+)?amount|contract\s+amount|amount|合同金额|总金额|价款)[^\d¥￥]{0,20}(?:rmb|cny|¥|￥|人民币)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
                r"(?:rmb|cny|¥|￥|人民币)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
                r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:rmb|cny|元|人民币)",
            ]
            for pattern in patterns:
                match = re.search(pattern, compact, flags=re.IGNORECASE)
                if not match:
                    continue
                try:
                    return float(match.group(1).replace(",", ""))
                except Exception:
                    continue
            return None

        contract_id = find_line([
            r"(?:Contract\s+No\.?|Contract\s+Number|合同编号|合同号)\s*[:：]\s*([^\n]+)",
        ])
        title = find_line([
            r"(?:Project\s+Name|项目名称|Contract\s+Name|合同名称)\s*[:：]\s*([^\n]+)",
        ]) or first_meaningful_line()
        party_a = find_line([
            r"(?:Party\s+A\s*(?:\([^)]*\))?|甲方|Client)\s*[:：]\s*([^\n]+)",
        ])
        party_b = find_line([
            r"(?:Party\s+B\s*(?:\([^)]*\))?|乙方|Consultant|Contractor|Service\s+Provider)\s*[:：]\s*([^\n]+)",
        ])
        effective_date = find_line([
            r"(?:Effective\s+Date|生效日期|合同生效日)\s*[:：]\s*([0-9]{4}[-/.年][0-9]{1,2}[-/.月][0-9]{1,2}日?)",
        ])
        expiry_date = find_line([
            r"(?:Expiry\s+Date|Expiration\s+Date|End\s+Date|终止日期|到期日)\s*[:：]\s*([0-9]{4}[-/.年][0-9]{1,2}[-/.月][0-9]{1,2}日?)",
        ])
        liability_cap = find_line([
            r"(?:liability\s+cap|limitation\s+of\s+liability|责任上限|赔偿上限)\s*[:：]?\s*([^\n。；;]+)",
        ])
        governing_law = find_line([
            r"(?:governing\s+law|applicable\s+law|适用法律|管辖法律)\s*[:：]?\s*([^\n。；;]+)",
        ])

        auto_renewal = bool(re.search(r"automatic\s+renewal|auto[-\s]?renew|自动续约|自动延展|期满自动", lower))
        amount = parse_amount()

        contract: Dict[str, Any] = {
            "raw_text": raw_text[:12000],
            "source_type": "text",
        }
        if contract_id:
            contract["contract_id"] = contract_id
            contract["id"] = contract_id
        if title:
            contract["title"] = title
            contract["name"] = title
        if party_a:
            contract["party_a"] = party_a
        if party_b:
            contract["party_b"] = party_b
            contract["counterparty_name"] = party_b
        elif party_a:
            contract["counterparty_name"] = party_a
        if amount is not None:
            contract["amount"] = amount
            contract["total_amount"] = amount
            contract["currency"] = "CNY" if re.search(r"rmb|cny|¥|￥|人民币|元", compact, re.IGNORECASE) else ""
        if effective_date:
            contract["effective_date"] = effective_date
        if expiry_date:
            contract["expiry_date"] = expiry_date
        if liability_cap:
            contract["liability_cap"] = liability_cap
        if governing_law:
            contract["governing_law"] = governing_law
        if auto_renewal:
            contract["auto_renewal"] = True

        return {"contract": contract}

    async def _build_action_plan(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        user_id: str,
        is_admin: bool,
        query: str,
        graph: InstanceGraph,
        decision: Optional[DecisionResult],
        mapping_trace: List[Any],
    ) -> Dict[str, Any]:
        schema_payload: Dict[str, Any] = {}
        try:
            schema_pkg = await persistent_ontology_service._resolve_package(db, space_id, PackageKind.schema, None, required=False)
            schema_payload = schema_pkg.payload or {} if schema_pkg else {}
        except Exception:
            schema_payload = {}

        try:
            data_sources = await persistent_ontology_service.list_data_sources(
                db,
                space_id=space_id,
                actor_user_id=user_id,
                is_admin=is_admin,
            )
        except Exception:
            data_sources = []

        try:
            from app.core.plugins import registry

            tool_catalog = registry.get_action_catalog()
        except Exception:
            tool_catalog = []

        plan = ontology_action_planner.build_plan(
            query=query,
            graph=graph,
            decision=decision,
            mapping_trace=mapping_trace,
            schema_payload=schema_payload,
            data_sources=data_sources,
            tool_catalog=tool_catalog,
        )
        return plan.to_dict()

    async def _execute_action_plan_safe(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        user_id: str,
        is_admin: bool,
        graph: InstanceGraph,
        action_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            data_sources = await persistent_ontology_service.list_data_sources(
                db,
                space_id=space_id,
                actor_user_id=user_id,
                is_admin=is_admin,
            )
        except Exception:
            data_sources = []
        async def secret_resolver(secret_ref: Optional[str], source_space_id: str) -> Optional[str]:
            return await persistent_ontology_service.resolve_runtime_secret(
                db,
                secret_ref=secret_ref,
                space_id=source_space_id,
            )

        async def audit_logger(action_name: str, status: str, payload: Dict[str, Any]) -> None:
            await persistent_ontology_service.audit_runtime_execution(
                db,
                user_id=user_id,
                action_name=action_name,
                status=status,
                payload=payload,
            )

        result = await ontology_action_executor.execute(
            graph=graph,
            action_plan=action_plan,
            data_sources=data_sources,
            secret_resolver=secret_resolver,
            audit_logger=audit_logger,
        )
        output = result.to_dict()
        if result.graph is not None and result.applied_patch_count > 0:
            output["_graph"] = result.graph
        return output

    @staticmethod
    def looks_like_ontology_task(text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        keywords = [
            "本体",
            "映射",
            "规则",
            "解释",
            "审核",
            "审查",
            "风控",
            "风险",
            "合规",
            "校验",
            "验证",
            "结构化",
            "抽取",
            "实体",
            "关系",
            "ontology",
            "mapping",
            "schema",
            "rule",
            "risk",
            "compliance",
            "review",
            "validate",
            "extract",
            "entity",
        ]
        return any(item in lowered for item in keywords) or OntologyRuntimePipeline.looks_like_contract_document(text)

    @staticmethod
    def detect_trigger_signals(text: str, *, input_payload: Optional[Dict[str, Any]], mode: str) -> List[str]:
        signals: List[str] = []
        if mode == "required":
            signals.append("required 模式")
        elif mode == "auto":
            signals.append("auto 模式")
        if input_payload:
            signals.append("检测到结构化/可映射输入")
        if OntologyRuntimePipeline.extract_json_payload(text):
            signals.append("检测到 JSON 输入")
        if OntologyRuntimePipeline.looks_like_contract_document(text):
            signals.append("检测到合同/协议文本")
        if OntologyRuntimePipeline.looks_like_ontology_task(text):
            signals.append("命中本体/审核/风控关键词")
        # 保持顺序并去重，方便前端稳定展示。
        unique: List[str] = []
        for item in signals:
            if item not in unique:
                unique.append(item)
        return unique

    @staticmethod
    def build_trigger_reason(*, mode: str, input_payload: Optional[Dict[str, Any]], query: str) -> str:
        if mode == "required":
            return "required 模式要求每轮优先执行本体"
        if input_payload:
            return "检测到结构化输入或可识别业务文本，已执行本体映射和规则流水线"
        if OntologyRuntimePipeline.looks_like_ontology_task(query):
            return "命中审核/风控/本体相关意图，已注入本体契约"
        return "auto 模式未发现明确本体任务信号"

    @staticmethod
    def looks_like_contract_document(text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return False
        contract_keywords = [
            "合同",
            "协议",
            "甲方",
            "乙方",
            "合同编号",
            "合同金额",
            "付款",
            "违约",
            "责任上限",
            "自动续约",
            "technical consulting contract",
            "contract no",
            "contract number",
            "party a",
            "party b",
            "client",
            "consultant",
            "contractor",
            "payment terms",
            "liability",
            "governing law",
            "breach",
            "termination",
        ]
        hit_count = sum(1 for item in contract_keywords if item in lowered)
        return hit_count >= 2 or ("contract" in lowered and len(lowered) > 120)


ontology_runtime_pipeline = OntologyRuntimePipeline()
