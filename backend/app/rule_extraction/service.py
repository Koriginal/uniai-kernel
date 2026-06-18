from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.ontology.asset_service import ontology_asset_service
from app.rule_extraction.models import (
    ExtractedClause,
    ExtractedRuleCandidate,
    RuleExtractionRequest,
    RuleExtractionResult,
    RuleExtractionUploadResult,
)


RULE_SIGNAL_PATTERN = re.compile(
    r"(超过|大于|高于|低于|少于|不得|严禁|禁止|必须|应当|需要|需|须|按照|执行|报批|审批|备案|报销|核销|公开|监督|检查|追究|适用|废止|施行|标准|预算|计划|票据|凭证|责任|原则|范围|高风险|风险|提示|预警|拦截|拒绝|评分|保证金|资质|资格|违约|验收)"
)


class RuleExtractionService:
    def extract_from_text(self, payload: RuleExtractionRequest) -> RuleExtractionResult:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is empty")
        clauses = self.segment_clauses(text)
        rules: List[ExtractedRuleCandidate] = []
        warnings: List[str] = []
        for clause in clauses:
            candidate = self.infer_rule(payload, clause)
            if candidate:
                rules.append(candidate)
                if len(rules) >= payload.max_rules:
                    break
            elif clause.is_rule_like:
                warnings.append(f"{clause.locator} 包含规则信号，但未生成结构化条件")
        return RuleExtractionResult(
            title=payload.title,
            source_type=payload.source_type,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            clause_count=len(clauses),
            rule_count=len(rules),
            clauses=clauses,
            rules=rules,
            warnings=warnings,
        )

    def extract_from_upload(
        self,
        *,
        title: Optional[str],
        source_type: str,
        max_rules: int,
        file_name: str,
        content_type: Optional[str],
        content: bytes,
    ) -> RuleExtractionUploadResult:
        if not content:
            raise HTTPException(status_code=400, detail="uploaded file is empty")
        if len(content) > ontology_asset_service.MAX_SOURCE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="uploaded file exceeds 8MB limit")
        text, warnings = ontology_asset_service._extract_uploaded_text(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        if not text.strip():
            raise HTTPException(status_code=400, detail={"message": "uploaded file text is empty", "warnings": warnings})
        result = self.extract_from_text(
            RuleExtractionRequest(
                title=title or file_name,
                source_type=source_type,
                text=text,
                max_rules=max_rules,
            )
        )
        data = result.model_dump()
        data["warnings"] = [*warnings, *result.warnings]
        return RuleExtractionUploadResult(
            **data,
            file_name=file_name,
            content_type=content_type,
            upload_metadata={
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "warnings": warnings,
            },
        )

    def segment_clauses(self, text: str) -> List[ExtractedClause]:
        clauses: List[ExtractedClause] = []
        chapter_path: List[str] = []
        current: Optional[Dict[str, Any]] = None
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            chapter = re.match(r"^(第\s*[一二三四五六七八九十百千万0-9]+\s*章)\s*(.*)$", line)
            if chapter:
                chapter_path = [" ".join(part for part in chapter.groups() if part).strip()]
                continue
            marker = re.match(r"^(第\s*[一二三四五六七八九十百千万0-9.]+\s*[条款])\s*(.*)$", line)
            numbered = re.match(r"^([0-9]+[.、])\s*(.*)$", line)
            if marker or numbered:
                if current:
                    clauses.append(self._clause_from_current(current))
                locator = marker.group(1) if marker else numbered.group(1)
                body = (marker.group(2) if marker else numbered.group(2)).strip() or line
                current = {
                    "locator": locator,
                    "text": body,
                    "chapter_path": list(chapter_path),
                    "line_start": line_no,
                    "line_end": line_no,
                }
                continue
            if current:
                current["text"] = f"{current['text']} {line}".strip()
                current["line_end"] = line_no
            else:
                current = {
                    "locator": f"第 {line_no} 行",
                    "text": line,
                    "chapter_path": list(chapter_path),
                    "line_start": line_no,
                    "line_end": line_no,
                }
        if current:
            clauses.append(self._clause_from_current(current))
        has_article_locator = any(re.match(r"^第\s*[一二三四五六七八九十百千万0-9.]+\s*[条款章节]$", item.locator) for item in clauses)
        if len(clauses) <= 1 and not has_article_locator:
            sentence_clauses = [
                ExtractedClause(
                    locator=f"句 {idx}",
                    text=item.strip(),
                    line_start=idx,
                    line_end=idx,
                    is_rule_like=bool(RULE_SIGNAL_PATTERN.search(item)),
                )
                for idx, item in enumerate(re.split(r"(?<=[。；;])", text), start=1)
                if item.strip()
            ]
            return sentence_clauses or clauses
        return clauses

    def infer_rule(self, payload: RuleExtractionRequest, clause: ExtractedClause) -> Optional[ExtractedRuleCandidate]:
        text = clause.text.strip()
        if not text or not clause.is_rule_like:
            return None
        field, label = self._infer_field(text)
        threshold = self._extract_threshold(text)
        operator = self._infer_operator(text)
        conditions: List[Dict[str, Any]] = []
        if field and threshold and operator:
            value = threshold["value"]
            if threshold["unit"] in {"万元", "万"}:
                value *= 10000
            conditions.append({"path": f"entity.{field}", "operator": operator, "value": value})
        elif field and re.search(r"(不得|严禁|禁止|不予|必须|应当|须|需要)", text):
            conditions.append({"path": f"entity.{field}", "operator": "exists"})
        severity = self._infer_severity(text)
        action = self._infer_action(text)
        stem = field or self._fallback_stem(text)
        if threshold and operator:
            stem = f"{stem}_{operator}_{threshold['value']}"
        code = self._normalize_code(f"{payload.source_type}_{stem}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6]}")
        return ExtractedRuleCandidate(
            rule_code=code[:120],
            name=self._build_name(text, label),
            description=f"从 {payload.title or '未命名来源'} {clause.locator} 提取的规则候选，发布前需要人工确认。",
            target_entity_type=self._infer_target_entity(payload.source_type, text, field),
            conditions=conditions,
            severity=severity,
            action=action,
            evidence_refs=[{"locator": clause.locator, "quote": text[:2000], "line_start": clause.line_start, "line_end": clause.line_end}],
            tags=[payload.source_type, "extracted"],
            extraction={
                "field": field,
                "operator": operator,
                "threshold": threshold,
                "chapter_path": clause.chapter_path,
            },
        )

    @staticmethod
    def _clause_from_current(item: Dict[str, Any]) -> ExtractedClause:
        text = item["text"].strip()
        return ExtractedClause(
            locator=item["locator"],
            text=text,
            chapter_path=item["chapter_path"],
            line_start=item["line_start"],
            line_end=item["line_end"],
            is_rule_like=bool(RULE_SIGNAL_PATTERN.search(text)),
        )

    @staticmethod
    def _infer_field(text: str) -> tuple[Optional[str], Optional[str]]:
        mapping = [
            ("payment_term_days", "付款周期", r"付款|支付|账期|结算"),
            ("contract_amount", "合同金额", r"合同金额|金额|价款"),
            ("liability_terms", "违约责任", r"违约|赔偿|责任"),
            ("acceptance_terms", "验收交付", r"验收|交付"),
            ("qualification", "资质资格", r"资质|资格|证书|业绩"),
            ("bid_bond", "投标保证金", r"保证金"),
            ("scoring_method", "评分办法", r"评分|分值|评审标准"),
            ("approval_materials", "审批材料", r"审批|报批|备案|材料|证明|凭证|票据"),
            ("budget_amount", "预算金额", r"预算|经费预算|超预算|无预算"),
            ("stay_days", "停留天数", r"停留天数|在外停留|天数"),
            ("reimbursement_document", "报销凭证", r"报销|发票|护照|签证|费用明细"),
        ]
        for field, label, pattern in mapping:
            if re.search(pattern, text):
                return field, label
        return None, None

    @staticmethod
    def _extract_threshold(text: str) -> Optional[Dict[str, Any]]:
        body = re.sub(r"^第\s*[一二三四五六七八九十百千万0-9.]+\s*[条款章节]\s*", "", text).strip()
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万元|万|元|天|日|%|人)?", body)
        if not match:
            return None
        value = float(match.group(1))
        if value.is_integer():
            value = int(value)
        return {"value": value, "unit": match.group(2) or ""}

    @staticmethod
    def _infer_operator(text: str) -> Optional[str]:
        if re.search(r"不得超过|不超过|小于等于|以内|以下", text):
            return "gt"
        if re.search(r"超过|大于|高于", text):
            return "gt"
        if re.search(r"低于|少于|小于", text):
            return "lt"
        return None

    @staticmethod
    def _infer_severity(text: str) -> str:
        if re.search(r"禁止|不得|严禁|拒绝|拦截|追究|处罚|废标|否决", text):
            return "critical"
        if re.search(r"高风险|超过|大于|高于|违约|保证金", text):
            return "high"
        if re.search(r"提示|关注|建议", text):
            return "low"
        return "medium"

    @staticmethod
    def _infer_action(text: str) -> str:
        if re.search(r"禁止|不得|严禁|拒绝|拦截|不予|废标|否决", text):
            return "block"
        if re.search(r"建议|推荐|参照|提示", text):
            return "recommend"
        return "flag"

    @staticmethod
    def _infer_target_entity(source_type: str, text: str, field: Optional[str]) -> Optional[str]:
        if "招标" in text or "投标" in text or "tender" in source_type:
            return "TenderDocument"
        if "合同" in text or field in {"payment_term_days", "contract_amount", "liability_terms", "acceptance_terms"}:
            return "Contract"
        if "报销" in text or "经费" in text or "出国" in text:
            return "ExpenseClaim"
        return None

    @staticmethod
    def _fallback_stem(text: str) -> str:
        for word in ["付款", "支付", "金额", "违约", "资质", "评分", "保证金", "审批", "预算", "报销"]:
            if word in text:
                return word
        return "RULE"

    @staticmethod
    def _build_name(text: str, label: Optional[str]) -> str:
        compact = re.sub(r"\s+", "", text)
        prefix = f"{label}：" if label else ""
        return f"{prefix}{compact[:48]}"

    @staticmethod
    def _normalize_code(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]+", "_", value.upper()).strip("_")


rule_extraction_service = RuleExtractionService()
