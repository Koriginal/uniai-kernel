import re
from typing import List

from app.ontology.schema import SemanticContext, SemanticFrame, SemanticSlots


class OntologyResolver:
    """
    Lightweight semantic resolver.
    This is intentionally heuristic-first so we can iterate quickly while
    keeping a stable schema contract for future ontology engines.
    """

    _interaction_keywords = {
        "workflow": ["workflow", "pipeline", "自动化", "流程", "审批", "编排"],
        "builder": ["架构", "框架", "搭建", "设计", "方案"],
        "analysis": ["分析", "诊断", "评估", "审计", "排查", "review"],
    }

    def resolve(self, query: str, preferred_mode: str = "chat") -> SemanticContext:
        text = (query or "").strip()
        lower_text = text.lower()

        interaction_mode = preferred_mode or "chat"
        intent = "qa"
        domain = "general"
        confidence = 0.35

        if self._match_any(text, lower_text, self._interaction_keywords["workflow"]):
            interaction_mode = "workflow"
            intent = "orchestrate"
            confidence = 0.72
        elif self._match_any(text, lower_text, self._interaction_keywords["builder"]):
            interaction_mode = "builder"
            intent = "design"
            confidence = 0.68
        elif self._match_any(text, lower_text, self._interaction_keywords["analysis"]):
            interaction_mode = "analysis"
            intent = "analyze"
            confidence = 0.66

        if self._match_any(text, lower_text, ["代码", "python", "javascript", "typescript", "c++", "java", "bug"]):
            domain = "software_engineering"
        elif self._match_any(text, lower_text, ["翻译", "英文", "中文", "language"]):
            domain = "translation"
        elif self._match_any(text, lower_text, ["联网", "搜索", "调研", "research", "web"]):
            domain = "research"

        entities = self._extract_entities(text)

        frame = SemanticFrame(
            intent=intent,
            domain=domain,
            interaction_mode=interaction_mode,
            confidence=confidence,
        )
        slots = SemanticSlots(
            raw_query=text,
            entities=entities,
            constraints=[],
            desired_artifacts=[],
            delegated_task=None,
        )
        return SemanticContext(interaction_mode=interaction_mode, frame=frame, slots=slots)

    @staticmethod
    def _match_any(text: str, lower_text: str, keywords: List[str]) -> bool:
        return any((k in text) or (k in lower_text) for k in keywords)

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        entities = [m.group(0) for m in re.finditer(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text)]
        if len(entities) > 8:
            entities = entities[:8]
        return entities
