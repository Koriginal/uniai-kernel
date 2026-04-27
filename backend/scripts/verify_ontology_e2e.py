"""
本体治理端到端验收脚本（DB 持久化）

覆盖链路：
1) 组织（可选）与空间创建
2) schema/mapping/rule 包上载
3) 审批 -> 发布（review/staging/ga）
4) 映射执行 -> 规则执行 -> explain 回放
5) 新版本发布 -> 回滚验证
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.user import User
from app.ontology.domain_models import (
    ApprovalReviewRequest,
    ApprovalSubmitRequest,
    MappingExecuteRequest,
    MappingPackageCreate,
    OntologySpaceCreate,
    OrganizationCreate,
    PackageKind,
    ReleaseRequest,
    RollbackRequest,
    RuleCondition,
    RuleDef,
    RuleEvaluateRequest,
    RulePackageCreate,
    SchemaPackageCreate,
    VersionStage,
)
from app.ontology.persistent_service import persistent_ontology_service


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


async def _ensure_user(user_id: str, *, email: str, username: str, is_admin: bool) -> User:
    async with SessionLocal() as db:
        row = await db.get(User, user_id)
        if row:
            return row
        row = User(
            id=user_id,
            email=email,
            username=username,
            is_active=True,
            is_admin=is_admin,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def main() -> None:
    suffix = _utc()
    owner_id = f"verify-owner-{suffix[-6:]}"
    reviewer_id = "admin"

    await _ensure_user(owner_id, email=f"{owner_id}@example.local", username=owner_id, is_admin=False)
    await _ensure_user(reviewer_id, email="admin@uniai.local", username="Admin", is_admin=True)

    async with SessionLocal() as db:
        # 连接预检：避免数据库不可达时打印冗长堆栈
        await db.execute(text("SELECT 1"))
        org_id = None
        if settings.ENABLE_ORG_TENANCY:
            org = await persistent_ontology_service.create_org(
                db,
                OrganizationCreate(code=f"verify-org-{suffix[-6:]}", name="Verify Org"),
                actor_user_id=owner_id,
                is_admin=False,
            )
            org_id = org.id

        space = await persistent_ontology_service.create_space(
            db,
            OntologySpaceCreate(
                name=f"verify-space-{suffix[-6:]}",
                code=f"verify-space-{suffix[-6:]}",
                description="ontology e2e verify",
                org_id=org_id,
            ),
            owner_user_id=owner_id,
        )

        await persistent_ontology_service.upsert_schema(
            db,
            SchemaPackageCreate(
                space_id=space.id,
                version="1.0.0",
                entity_types=[
                    {
                        "name": "Contract",
                        "attributes": {
                            "amount": {"data_type": "number", "required": True},
                            "currency": {"data_type": "string", "required": True},
                        },
                    }
                ],
            ),
            actor_user_id=owner_id,
            is_admin=False,
        )

        await persistent_ontology_service.upsert_mapping(
            db,
            MappingPackageCreate(
                space_id=space.id,
                version="1.0.0",
                entity_mappings=[
                    {
                        "entity_type": "Contract",
                        "id_template": "contract:{{row.contract_id}}",
                        "source_path": "contract",
                        "field_mappings": [
                            {"source_path": "amount", "target_attr": "amount", "required": True, "transform": "to_float"},
                            {"source_path": "currency", "target_attr": "currency", "required": True, "transform": "upper"},
                        ],
                    }
                ],
            ),
            actor_user_id=owner_id,
            is_admin=False,
        )

        await persistent_ontology_service.upsert_rule(
            db,
            RulePackageCreate(
                space_id=space.id,
                version="1.0.0",
                rules=[
                    RuleDef(
                        rule_id="RISK_HIGH_AMOUNT",
                        name="High amount contract",
                        target_entity_type="Contract",
                        severity="high",
                        action="flag",
                        conditions=[RuleCondition(path="entity.amount", operator="gte", value=1_000_000)],
                    )
                ],
            ),
            actor_user_id=owner_id,
            is_admin=False,
        )

        for kind in (PackageKind.schema, PackageKind.mapping, PackageKind.rule):
            await persistent_ontology_service.release(
                db,
                ReleaseRequest(space_id=space.id, kind=kind, version="1.0.0", target_stage=VersionStage.review),
                actor_user_id=owner_id,
                is_admin=False,
            )

            for target_stage in (VersionStage.staging, VersionStage.ga):
                if (target_stage == VersionStage.staging and settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_STAGING) or (
                    target_stage == VersionStage.ga and settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA
                ):
                    approval = await persistent_ontology_service.submit_approval(
                        db,
                        ApprovalSubmitRequest(space_id=space.id, kind=kind, version="1.0.0", target_stage=target_stage, note="verify"),
                        actor_user_id=owner_id,
                        is_admin=False,
                    )
                    await persistent_ontology_service.review_approval(
                        db,
                        ApprovalReviewRequest(approval_id=approval.id, approve=True, review_note="approved for verify"),
                        actor_user_id=reviewer_id,
                        is_admin=True,
                    )

                await persistent_ontology_service.release(
                    db,
                    ReleaseRequest(space_id=space.id, kind=kind, version="1.0.0", target_stage=target_stage),
                    actor_user_id=owner_id,
                    is_admin=False,
                )

        mapped = await persistent_ontology_service.execute_mapping(
            db,
            MappingExecuteRequest(
                space_id=space.id,
                input_payload={"contract": {"contract_id": "v-001", "amount": "1500000", "currency": "cny"}},
            ),
            actor_user_id=owner_id,
            is_admin=False,
        )

        decision = await persistent_ontology_service.evaluate_rules(
            db,
            RuleEvaluateRequest(space_id=space.id, graph=mapped.graph),
            actor_user_id=owner_id,
            is_admin=False,
        )
        explanation = await persistent_ontology_service.explain(
            db,
            decision.decision_id,
            actor_user_id=owner_id,
            is_admin=False,
        )

        await persistent_ontology_service.upsert_rule(
            db,
            RulePackageCreate(
                space_id=space.id,
                version="1.0.1",
                rules=[
                    RuleDef(
                        rule_id="RISK_HIGH_AMOUNT",
                        name="High amount contract",
                        target_entity_type="Contract",
                        severity="critical",
                        action="block",
                        conditions=[RuleCondition(path="entity.amount", operator="gte", value=1_200_000)],
                    )
                ],
            ),
            actor_user_id=owner_id,
            is_admin=False,
        )
        await persistent_ontology_service.release(
            db,
            ReleaseRequest(space_id=space.id, kind=PackageKind.rule, version="1.0.1", target_stage=VersionStage.review),
            actor_user_id=owner_id,
            is_admin=False,
        )
        for target_stage in (VersionStage.staging, VersionStage.ga):
            if (target_stage == VersionStage.staging and settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_STAGING) or (
                target_stage == VersionStage.ga and settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA
            ):
                approval = await persistent_ontology_service.submit_approval(
                    db,
                    ApprovalSubmitRequest(
                        space_id=space.id,
                        kind=PackageKind.rule,
                        version="1.0.1",
                        target_stage=target_stage,
                        note=f"verify v1.0.1 {target_stage.value}",
                    ),
                    actor_user_id=owner_id,
                    is_admin=False,
                )
                await persistent_ontology_service.review_approval(
                    db,
                    ApprovalReviewRequest(approval_id=approval.id, approve=True, review_note="approved"),
                    actor_user_id=reviewer_id,
                    is_admin=True,
                )
            await persistent_ontology_service.release(
                db,
                ReleaseRequest(space_id=space.id, kind=PackageKind.rule, version="1.0.1", target_stage=target_stage),
                actor_user_id=owner_id,
                is_admin=False,
            )

        rollback = await persistent_ontology_service.rollback(
            db,
            RollbackRequest(space_id=space.id, kind=PackageKind.rule, target_version="1.0.0", notes="verify rollback"),
            actor_user_id=owner_id,
            is_admin=False,
        )

        events = await persistent_ontology_service.list_release_events(
            db,
            space_id=space.id,
            actor_user_id=owner_id,
            is_admin=False,
            kind=PackageKind.rule,
        )

    output = {
        "space_id": space.id,
        "org_id": org_id,
        "decision_id": decision.decision_id,
        "risk_level": decision.risk_level,
        "why_count": len(explanation.why),
        "rollback_stage": rollback.stage.value,
        "rule_release_events": len(events),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "ontology_e2e_db_unavailable_or_runtime_error",
                    "detail": str(exc),
                    "hint": "请确认 PostgreSQL 可达、迁移已执行（alembic upgrade head），并在 backend 目录执行该脚本。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)
