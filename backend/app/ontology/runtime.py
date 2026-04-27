from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ontology.domain_models import PackageKind
from app.ontology.persistent_service import persistent_ontology_service


ONTOLOGY_AGENT_TOOL_NAMES = [
    "ontology_list_spaces",
    "ontology_get_runtime_contract",
    "ontology_map_input",
    "ontology_evaluate_rules",
    "ontology_explain_decision",
]


class OntologyRuntime:
    """Runtime adapter that lets agents use ontology packages without coupling to storage."""

    def normalize_config(self, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = dict(raw or {})
        mode = str(data.get("mode") or ("auto" if data.get("enabled") else "off")).lower()
        if mode not in {"off", "auto", "required"}:
            mode = "off"
        return {
            "enabled": mode != "off",
            "mode": mode,
            "space_id": (data.get("space_id") or "").strip() or None,
            "strict_rules": bool(data.get("strict_rules", False)),
            "explain_required": bool(data.get("explain_required", True)),
            "fallback_when_unavailable": data.get("fallback_when_unavailable") or "continue_without_ontology",
        }

    def is_enabled(self, raw: Optional[Dict[str, Any]]) -> bool:
        return bool(self.normalize_config(raw).get("enabled"))

    async def resolve_space(
        self,
        db: AsyncSession,
        *,
        config: Dict[str, Any],
        user_id: str,
        is_admin: bool = False,
        query: str = "",
    ) -> Optional[str]:
        if config.get("space_id"):
            return str(config["space_id"])
        if config.get("mode") != "auto":
            return None

        spaces = await persistent_ontology_service.list_spaces(db, owner_user_id=user_id, is_admin=is_admin)
        if not spaces:
            return None
        q = (query or "").lower()
        for space in spaces:
            haystack = " ".join([space.name or "", space.code or "", space.description or ""]).lower()
            if q and any(token for token in q.split() if token and token in haystack):
                return space.id
        return spaces[0].id

    async def build_contract(
        self,
        db: AsyncSession,
        *,
        space_id: str,
        user_id: str,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        await persistent_ontology_service._ensure_space_access(db, space_id, user_id, is_admin)
        packages = {}
        missing = []
        for kind in [PackageKind.schema, PackageKind.mapping, PackageKind.rule]:
            pkg = await persistent_ontology_service._resolve_package(db, space_id, kind, None, required=False)
            if not pkg:
                missing.append(kind.value)
                packages[kind.value] = None
                continue
            packages[kind.value] = {
                "version": pkg.version,
                "stage": pkg.stage,
                "is_active": bool(pkg.is_active),
                "summary": self._summarize_package(kind, pkg.payload or {}),
            }

        return {
            "ontology_enabled": True,
            "space_id": space_id,
            "active_versions": {
                kind: data["version"] for kind, data in packages.items() if data
            },
            "missing_active_packages": missing,
            "packages": packages,
            "agent_tools": ONTOLOGY_AGENT_TOOL_NAMES,
        }

    async def build_agent_prompt(
        self,
        db: AsyncSession,
        *,
        raw_config: Optional[Dict[str, Any]],
        user_id: str,
        query: str = "",
        is_admin: bool = False,
    ) -> str:
        config = self.normalize_config(raw_config)
        if not config["enabled"]:
            return ""

        space_id = await self.resolve_space(db, config=config, user_id=user_id, is_admin=is_admin, query=query)
        if not space_id:
            if config["mode"] == "required":
                return (
                    "\n\n[ONTOLOGY RUNTIME]: REQUIRED BUT UNAVAILABLE\n"
                    "本智能体必须使用本体，但当前没有可用本体空间。请要求用户先配置本体空间。\n"
                )
            return ""

        try:
            contract = await self.build_contract(db, space_id=space_id, user_id=user_id, is_admin=is_admin)
        except Exception as exc:
            if config["mode"] == "required":
                return (
                    "\n\n[ONTOLOGY RUNTIME]: REQUIRED BUT FAILED\n"
                    f"本体运行时初始化失败：{exc}。请停止业务判断并提示用户修复本体配置。\n"
                )
            return ""

        return (
            "\n\n[ONTOLOGY RUNTIME]: ENABLED\n"
            f"current_user_id: {user_id}\n"
            f"space_id: {space_id}\n"
            f"active_versions: {contract.get('active_versions', {})}\n"
            f"missing_active_packages: {contract.get('missing_active_packages', [])}\n"
            "可用本体工具: ontology_get_runtime_contract, ontology_map_input, "
            "ontology_evaluate_rules, ontology_explain_decision, ontology_list_spaces。\n"
            "使用规则：\n"
            "1. 当任务涉及业务审核、合规判断、结构化抽取、风险识别或可解释决策时，优先调用本体工具。\n"
            "2. user_id 由系统运行时自动注入，调用工具时不要填写、猜测或复述用户 ID。\n"
            "3. space_id 默认由系统运行时自动补齐；只有用户明确指定其他可访问空间时才传入 space_id。\n"
            "4. 不要把完整本体 JSON 直接复述给用户；应输出结论、命中规则、证据和建议。\n"
        )

    def _summarize_package(self, kind: PackageKind, payload: Dict[str, Any]) -> Dict[str, Any]:
        if kind == PackageKind.schema:
            entities = []
            for item in payload.get("entity_types", []) or []:
                attrs = item.get("attributes", {}) or {}
                entities.append({
                    "name": item.get("name"),
                    "attributes": list(attrs.keys())[:30],
                    "relations": [rel.get("name") for rel in item.get("relations", []) or []][:20],
                })
            return {"entity_types": entities, "entity_count": len(entities)}
        if kind == PackageKind.mapping:
            mappings = payload.get("entity_mappings", []) or []
            return {
                "entity_mappings": [
                    {
                        "entity_type": item.get("entity_type"),
                        "source_path": item.get("source_path"),
                        "fields": [f.get("target_attr") for f in item.get("field_mappings", []) or []][:30],
                    }
                    for item in mappings[:20]
                ],
                "mapping_count": len(mappings),
            }
        rules = payload.get("rules", []) or []
        return {
            "rules": [
                {
                    "rule_id": item.get("rule_id"),
                    "name": item.get("name"),
                    "severity": item.get("severity"),
                    "action": item.get("action"),
                    "target_entity_type": item.get("target_entity_type"),
                }
                for item in rules[:30]
            ],
            "rule_count": len(rules),
        }


ontology_runtime = OntologyRuntime()
