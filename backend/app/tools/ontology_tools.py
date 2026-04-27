from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.core.db import SessionLocal
from app.ontology.domain_models import (
    InstanceGraph,
    MappingExecuteRequest,
    RuleEvaluateRequest,
)
from app.ontology.persistent_service import persistent_ontology_service
from app.ontology.runtime import ontology_runtime
from app.tools.base import BaseTool


def _jsonable(obj: Any) -> str:
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json(indent=2)
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


class OntologyListSpacesTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="ontology_list_spaces",
            label="本体空间列表",
            description="列出当前用户可访问的本体空间，用于选择业务语义空间。",
            category="ontology",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, user_id: str = "", **_kwargs) -> str:
        if not user_id:
            return "Ontology Error: missing trusted runtime user_id"
        async with SessionLocal() as db:
            spaces = await persistent_ontology_service.list_spaces(db, owner_user_id=user_id, is_admin=False)
            return _jsonable({"spaces": [space.model_dump(mode="json") for space in spaces]})


class OntologyRuntimeContractTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="ontology_get_runtime_contract",
            label="本体运行契约",
            description="获取指定本体空间的 GA 版本摘要，包括实体、映射、规则和可用版本。",
            category="ontology",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "本体空间 ID。"},
            },
            "required": ["space_id"],
        }

    async def execute(self, space_id: str, user_id: str = "", **_kwargs) -> str:
        if not user_id:
            return "Ontology Error: missing trusted runtime user_id"
        async with SessionLocal() as db:
            contract = await ontology_runtime.build_contract(db, space_id=space_id, user_id=user_id, is_admin=False)
            return _jsonable(contract)


class OntologyMapInputTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="ontology_map_input",
            label="本体映射执行",
            description="把业务输入数据映射成本体图，适用于结构化抽取、审核、规则判断前置步骤。",
            category="ontology",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "本体空间 ID。"},
                "input_payload": {"type": "object", "description": "待映射的业务输入 JSON。"},
                "mapping_version": {"type": "string", "description": "可选，指定 mapping 版本；不填使用当前 GA。"},
                "schema_version": {"type": "string", "description": "可选，指定 schema 版本；不填使用当前 GA。"},
            },
            "required": ["space_id", "input_payload"],
        }

    async def execute(
        self,
        space_id: str,
        input_payload: Dict[str, Any],
        user_id: str = "",
        mapping_version: Optional[str] = None,
        schema_version: Optional[str] = None,
        **_kwargs,
    ) -> str:
        if not user_id:
            return "Ontology Error: missing trusted runtime user_id"
        async with SessionLocal() as db:
            result = await persistent_ontology_service.execute_mapping(
                db,
                MappingExecuteRequest(
                    space_id=space_id,
                    input_payload=input_payload,
                    mapping_version=mapping_version,
                    schema_version=schema_version,
                ),
                actor_user_id=user_id,
                is_admin=False,
            )
            return _jsonable(result)


class OntologyEvaluateRulesTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="ontology_evaluate_rules",
            label="本体规则执行",
            description="基于本体图执行规则，返回风险等级、命中规则、未命中规则和 decision_id。",
            category="ontology",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "本体空间 ID。"},
                "graph": {"type": "object", "description": "本体图，通常来自 ontology_map_input 的 graph。"},
                "rule_version": {"type": "string", "description": "可选，指定 rule 版本；不填使用当前 GA。"},
                "context": {"type": "object", "description": "可选，规则执行上下文。"},
            },
            "required": ["space_id", "graph"],
        }

    async def execute(
        self,
        space_id: str,
        graph: Dict[str, Any],
        user_id: str = "",
        rule_version: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **_kwargs,
    ) -> str:
        if not user_id:
            return "Ontology Error: missing trusted runtime user_id"
        async with SessionLocal() as db:
            result = await persistent_ontology_service.evaluate_rules(
                db,
                RuleEvaluateRequest(
                    space_id=space_id,
                    graph=InstanceGraph.model_validate(graph),
                    rule_version=rule_version,
                    context=context or {},
                ),
                actor_user_id=user_id,
                is_admin=False,
            )
            return _jsonable(result)


class OntologyExplainDecisionTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="ontology_explain_decision",
            label="本体决策解释",
            description="根据 decision_id 获取本体规则决策解释，包括 why、why_not 和 evidence。",
            category="ontology",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string", "description": "规则执行返回的 decision_id。"},
            },
            "required": ["decision_id"],
        }

    async def execute(self, decision_id: str, user_id: str = "", **_kwargs) -> str:
        if not user_id:
            return "Ontology Error: missing trusted runtime user_id"
        async with SessionLocal() as db:
            result = await persistent_ontology_service.explain(
                db,
                decision_id=decision_id,
                actor_user_id=user_id,
                is_admin=False,
            )
            return _jsonable(result)


def register(registry):
    registry.register_action(OntologyListSpacesTool())
    registry.register_action(OntologyRuntimeContractTool())
    registry.register_action(OntologyMapInputTool())
    registry.register_action(OntologyEvaluateRulesTool())
    registry.register_action(OntologyExplainDecisionTool())
