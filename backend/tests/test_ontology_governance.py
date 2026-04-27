from types import SimpleNamespace
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from app.ontology.domain_models import (
    ApprovalStatus,
    PackageKind,
    ReleaseRequest,
    RollbackRequest,
    VersionStage,
)
from app.ontology.persistent_service import PersistentOntologyService


def _pkg(kind: str, version: str, payload: dict):
    return SimpleNamespace(kind=kind, version=version, payload=payload)


def test_release_request_has_strict_compatibility_flag():
    req = ReleaseRequest(
        space_id="s1",
        kind=PackageKind.schema,
        version="1.0.0",
        target_stage=VersionStage.ga,
    )
    assert req.strict_compatibility is False


def test_rollback_request_shape():
    req = RollbackRequest(space_id="s1", kind=PackageKind.rule, target_version="1.2.3")
    assert req.target_version == "1.2.3"


def test_validate_stage_transition_allows_forward_paths():
    svc = PersistentOntologyService()
    svc._validate_stage_transition(VersionStage.draft, VersionStage.review)
    svc._validate_stage_transition(VersionStage.review, VersionStage.staging)
    svc._validate_stage_transition(VersionStage.staging, VersionStage.ga)
    svc._validate_stage_transition(VersionStage.ga, VersionStage.deprecated)


def test_validate_stage_transition_rejects_backward_paths():
    svc = PersistentOntologyService()
    try:
        svc._validate_stage_transition(VersionStage.ga, VersionStage.review)
    except HTTPException as exc:
        assert exc.status_code == 400
        return
    assert False, "expected HTTPException"


def test_validate_stage_transition_rejects_skip_paths():
    svc = PersistentOntologyService()
    for current, target in [
        (VersionStage.draft, VersionStage.staging),
        (VersionStage.draft, VersionStage.ga),
        (VersionStage.review, VersionStage.ga),
    ]:
        try:
            svc._validate_stage_transition(current, target)
        except HTTPException as exc:
            assert exc.status_code == 400
            continue
        assert False, f"expected skip transition blocked: {current.value}->{target.value}"


def test_collect_release_warnings_for_schema_removal_same_major():
    svc = PersistentOntologyService()
    previous = _pkg(
        "schema",
        "1.0.0",
        {"entity_types": [{"name": "Contract"}, {"name": "Clause"}]},
    )
    candidate = _pkg("schema", "1.1.0", {"entity_types": [{"name": "Contract"}]})
    warnings = svc._collect_release_warnings(previous, candidate)
    assert warnings
    assert "schema removes entity types" in warnings[0]


def test_collect_release_warnings_for_rule_removal_same_major():
    svc = PersistentOntologyService()
    previous = _pkg(
        "rule",
        "2.0.0",
        {"rules": [{"rule_id": "R1"}, {"rule_id": "R2"}]},
    )
    candidate = _pkg("rule", "2.1.0", {"rules": [{"rule_id": "R1"}]})
    warnings = svc._collect_release_warnings(previous, candidate)
    assert warnings
    assert "rule package removes rules" in warnings[0]


def test_collect_release_warnings_no_warning_on_major_bump():
    svc = PersistentOntologyService()
    previous = _pkg("schema", "1.9.0", {"entity_types": [{"name": "A"}]})
    candidate = _pkg("schema", "2.0.0", {"entity_types": []})
    warnings = svc._collect_release_warnings(previous, candidate)
    assert warnings == []


def test_semver_validation():
    svc = PersistentOntologyService()
    svc._assert_version("1.0.0")
    try:
        svc._assert_version("1.0")
    except HTTPException as exc:
        assert exc.status_code == 400
        return
    assert False, "expected semver validation error"


def test_risk_level_boundaries():
    svc = PersistentOntologyService()
    assert svc._to_risk_level(0) == "low"
    assert svc._to_risk_level(20) == "medium"
    assert svc._to_risk_level(40) == "high"
    assert svc._to_risk_level(80) == "critical"


def test_compare_exists():
    svc = PersistentOntologyService()
    assert svc._compare("x", "exists", None) is True
    assert svc._compare("", "exists", None) is False


def test_compare_eq_neq():
    svc = PersistentOntologyService()
    assert svc._compare(1, "eq", 1) is True
    assert svc._compare(1, "neq", 2) is True


def test_compare_numeric():
    svc = PersistentOntologyService()
    assert svc._compare(2, "gt", 1) is True
    assert svc._compare(2, "gte", 2) is True
    assert svc._compare(2, "lt", 3) is True
    assert svc._compare(2, "lte", 2) is True


def test_compare_contains():
    svc = PersistentOntologyService()
    assert svc._compare([1, 2, 3], "contains", 2) is True
    assert svc._compare("hello world", "contains", "world") is True


def test_compare_in():
    svc = PersistentOntologyService()
    assert svc._compare("a", "in", ["a", "b"]) is True
    assert svc._compare("c", "in", ["a", "b"]) is False


def test_get_path_nested():
    svc = PersistentOntologyService()
    data = {"a": {"b": {"c": 1}}}
    assert svc._get_path(data, "a.b.c") == 1


def test_pick_value_row_first_then_root():
    svc = PersistentOntologyService()
    row = {"x": 1}
    root = {"x": 2, "y": 3}
    assert svc._pick_value(row, root, "x") == 1
    assert svc._pick_value(row, root, "y") == 3


def test_resolve_source_rows():
    svc = PersistentOntologyService()
    payload = {"items": [{"id": 1}, {"id": 2}]}
    rows = svc._resolve_source_rows(payload, "items")
    assert len(rows) == 2


def test_render_template_row_root_index():
    svc = PersistentOntologyService()
    ctx = {"row": {"id": "r1"}, "root": {"tenant": "t1"}, "index": 4}
    out = svc._render_template("{{root.tenant}}:{{row.id}}:{{index}}", ctx)
    assert out == "t1:r1:4"


def test_apply_transforms():
    svc = PersistentOntologyService()
    assert svc._apply_transform(" A ", "trim") == "A"
    assert svc._apply_transform("A", "lower") == "a"
    assert svc._apply_transform("a", "upper") == "A"
    assert svc._apply_transform("42", "to_int") == 42
    assert svc._apply_transform("3.14", "to_float") == 3.14
    assert svc._apply_transform("true", "to_bool") is True


def test_resolve_condition_path_entity_and_graph():
    svc = PersistentOntologyService()
    entity = SimpleNamespace(id="e1", entity_type="Doc", attributes={"name": "n"})
    graph = SimpleNamespace(entities=[1, 2], relations=[1])
    assert svc._resolve_condition_path("entity.id", entity, graph, {}) == "e1"
    assert svc._resolve_condition_path("entity.name", entity, graph, {}) == "n"
    assert svc._resolve_condition_path("graph.entity_count", entity, graph, {}) == 2


def test_approval_status_enum_values():
    assert ApprovalStatus.pending.value == "pending"
    assert ApprovalStatus.approved.value == "approved"
    assert ApprovalStatus.rejected.value == "rejected"


def test_require_approval_skips_non_release_stages():
    svc = PersistentOntologyService()

    class Repo:
        async def get_approved_release_gate(self, _db=None, **_kwargs):
            raise AssertionError("should not query approvals for review stage")

    svc.repo = Repo()

    async def _run():
        await svc._require_approval_for_release(
            None,
            space_id="s1",
            kind=PackageKind.schema,
            version="1.0.0",
            target_stage=VersionStage.review,
        )

    asyncio.run(_run())


def test_require_approval_blocks_when_missing():
    svc = PersistentOntologyService()

    class Repo:
        async def get_approved_release_gate(self, _db=None, **_kwargs):
            return None

    svc.repo = Repo()

    async def _run():
        try:
            await svc._require_approval_for_release(
                None,
                space_id="s1",
                kind=PackageKind.schema,
                version="1.0.0",
                target_stage=VersionStage.ga,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            return
        assert False, "expected 409 when approval missing"

    asyncio.run(_run())


def test_require_approval_pass_when_exists():
    svc = PersistentOntologyService()

    class Repo:
        async def get_approved_release_gate(self, _db=None, **_kwargs):
            return object()

    svc.repo = Repo()

    async def _run():
        await svc._require_approval_for_release(
            None,
            space_id="s1",
            kind=PackageKind.rule,
            version="1.0.0",
            target_stage=VersionStage.staging,
        )

    asyncio.run(_run())


def test_require_approval_respects_toggle_for_ga():
    svc = PersistentOntologyService()
    from app.core.config import settings
    original = settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA
    settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA = False

    class Repo:
        async def get_approved_release_gate(self, _db=None, **_kwargs):
            raise AssertionError("should not query gate when GA approval disabled")

    svc.repo = Repo()

    async def _run():
        await svc._require_approval_for_release(
            None,
            space_id="s1",
            kind=PackageKind.rule,
            version="1.0.0",
            target_stage=VersionStage.ga,
        )

    try:
        asyncio.run(_run())
    finally:
        settings.ONTOLOGY_REQUIRE_APPROVAL_FOR_GA = original


def test_diff_summary_schema_removed_entity():
    svc = PersistentOntologyService()
    old_pkg = _pkg("schema", "1.0.0", {"entity_types": [{"name": "A"}, {"name": "B"}]})
    new_pkg = _pkg("schema", "1.1.0", {"entity_types": [{"name": "A"}]})
    warnings = svc._collect_release_warnings(old_pkg, new_pkg)
    assert warnings and "remov" in warnings[0]


def test_diff_summary_rule_removed_rule():
    svc = PersistentOntologyService()
    old_pkg = _pkg("rule", "1.0.0", {"rules": [{"rule_id": "R1"}, {"rule_id": "R2"}]})
    new_pkg = _pkg("rule", "1.1.0", {"rules": [{"rule_id": "R1"}]})
    warnings = svc._collect_release_warnings(old_pkg, new_pkg)
    assert warnings and "remov" in warnings[0]


def test_release_rejects_draft_target_stage():
    svc = PersistentOntologyService()

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="u1")

        async def get_package(self, _db, _space_id, _kind, _version):
            return SimpleNamespace(id="pkg1", stage="review", kind="schema", version="1.0.0")

    svc.repo = Repo()

    class DB:
        async def commit(self):
            return None

        def add(self, _obj):
            return None

    async def _run():
        try:
            await svc.release(
                DB(),
                ReleaseRequest(
                    space_id="s1",
                    kind=PackageKind.schema,
                    version="1.0.0",
                    target_stage=VersionStage.draft,
                ),
                actor_user_id="u1",
                is_admin=False,
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            return
        assert False, "expected draft release to be blocked"

    asyncio.run(_run())


def test_submit_approval_rejects_duplicate_pending_gate():
    svc = PersistentOntologyService()

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="u1")

        async def get_package(self, _db, _space_id, _kind, _version):
            return SimpleNamespace(id="pkg1", stage="staging")

        async def get_pending_release_gate(self, _db, **_kwargs):
            return SimpleNamespace(id="appr1", status="pending")

    svc.repo = Repo()

    async def _run():
        try:
            await svc.submit_approval(
                None,
                payload=SimpleNamespace(
                    space_id="s1",
                    kind=PackageKind.schema,
                    version="1.0.0",
                    target_stage=VersionStage.ga,
                    note="go",
                ),
                actor_user_id="u1",
                is_admin=False,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            return
        assert False, "expected duplicate gate to be blocked"

    asyncio.run(_run())


def test_submit_approval_rejects_skip_stage_request():
    svc = PersistentOntologyService()

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="u1")

        async def get_package(self, _db, _space_id, _kind, _version):
            return SimpleNamespace(id="pkg1", stage="review")

        async def get_pending_release_gate(self, _db, **_kwargs):
            return None

    svc.repo = Repo()

    async def _run():
        try:
            await svc.submit_approval(
                None,
                payload=SimpleNamespace(
                    space_id="s1",
                    kind=PackageKind.schema,
                    version="1.0.0",
                    target_stage=VersionStage.ga,
                    note="skip to ga",
                ),
                actor_user_id="u1",
                is_admin=False,
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            return
        assert False, "expected skip transition approval request to be blocked"

    asyncio.run(_run())


def test_review_approval_rejects_non_pending():
    svc = PersistentOntologyService()

    class Repo:
        async def get_approval(self, _db, _approval_id):
            return SimpleNamespace(
                id="appr1",
                space_id="s1",
                requester_user_id="u1",
                status="approved",
                reviewer_user_id="u2",
                review_note="done",
                reviewed_at=None,
            )

        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="u1")

    svc.repo = Repo()

    class DB:
        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    async def _run():
        try:
            await svc.review_approval(
                DB(),
                payload=SimpleNamespace(approval_id="appr1", approve=True, review_note="redo"),
                actor_user_id="admin-1",
                is_admin=True,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            return
        assert False, "expected non-pending review to be blocked"

    asyncio.run(_run())


def test_review_approval_allows_org_admin_reviewer():
    svc = PersistentOntologyService()
    from app.core.config import settings
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    class Repo:
        async def get_approval(self, _db, _approval_id):
            return SimpleNamespace(
                id="appr1",
                space_id="s1",
                package_id="pkg1",
                kind="schema",
                version="1.0.0",
                requested_stage="staging",
                requester_user_id="member-1",
                status="pending",
                request_note=None,
                review_note=None,
                reviewed_at=None,
                created_at=datetime.now(timezone.utc),
            )

        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="owner-1", org_id="org-1")

        async def get_org_membership(self, _db, *, org_id, user_id):
            if org_id == "org-1" and user_id == "org-admin-1":
                return SimpleNamespace(org_id=org_id, user_id=user_id, role="admin", is_active=True)
            return None

    svc.repo = Repo()

    class DB:
        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    async def _run():
        reviewed = await svc.review_approval(
            DB(),
            payload=SimpleNamespace(approval_id="appr1", approve=True, review_note="ok"),
            actor_user_id="org-admin-1",
            is_admin=False,
        )
        assert reviewed.id == "appr1"
        assert reviewed.status == ApprovalStatus.approved

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_review_approval_blocks_org_member_reviewer():
    svc = PersistentOntologyService()
    from app.core.config import settings
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    class Repo:
        async def get_approval(self, _db, _approval_id):
            return SimpleNamespace(
                id="appr1",
                space_id="s1",
                package_id="pkg1",
                kind="schema",
                version="1.0.0",
                requested_stage="staging",
                requester_user_id="member-2",
                status="pending",
                request_note=None,
                review_note=None,
                reviewed_at=None,
                created_at=datetime.now(timezone.utc),
            )

        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="owner-1", org_id="org-1")

        async def get_org_membership(self, _db, *, org_id, user_id):
            if org_id == "org-1" and user_id == "member-1":
                return SimpleNamespace(org_id=org_id, user_id=user_id, role="member", is_active=True)
            return None

    svc.repo = Repo()

    class DB:
        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    async def _run():
        try:
            await svc.review_approval(
                DB(),
                payload=SimpleNamespace(approval_id="appr1", approve=True, review_note="ok"),
                actor_user_id="member-1",
                is_admin=False,
            )
        except HTTPException as exc:
            assert exc.status_code == 403
            return
        assert False, "expected org member reviewer to be denied"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_create_space_with_org_scope_rejects_when_feature_disabled():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def get_space_by_owner_code(self, _db, _owner_user_id, _code):
            return None

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = False

    async def _run():
        try:
            await svc.create_space(
                None,
                payload=SimpleNamespace(name="Space A", code="space-a", description=None, org_id="org-1"),
                owner_user_id="u1",
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            return
        assert False, "expected org scope disabled error"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_create_space_with_org_scope_rejects_when_not_member():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def is_org_member(self, _db, *, org_id, user_id):
            assert org_id == "org-1"
            assert user_id == "u1"
            return False

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    async def _run():
        try:
            await svc.create_space(
                None,
                payload=SimpleNamespace(name="Space A", code="space-a", description=None, org_id="org-1"),
                owner_user_id="u1",
            )
        except HTTPException as exc:
            assert exc.status_code == 403
            return
        assert False, "expected org membership check error"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_create_space_with_org_scope_rejects_member_without_space_create_permission():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def get_org_membership(self, _db, *, org_id, user_id):
            if org_id == "org-1" and user_id == "u1":
                return SimpleNamespace(org_id=org_id, user_id=user_id, role="member", is_active=True)
            return None

        async def get_space_by_owner_code(self, _db, _owner_user_id, _code):
            return None

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    async def _run():
        try:
            await svc.create_space(
                None,
                payload=SimpleNamespace(name="Space A", code="space-a", description=None, org_id="org-1"),
                owner_user_id="u1",
            )
        except HTTPException as exc:
            assert exc.status_code == 403
            return
        assert False, "expected org member without space_create to be denied"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_ensure_space_access_allows_org_member_when_enabled():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="owner-1", org_id="org-1")

        async def is_org_member(self, _db, *, org_id, user_id):
            return org_id == "org-1" and user_id == "member-1"

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    async def _run():
        space = await svc._ensure_space_access(None, "s1", "member-1", False)
        assert space.id == "s1"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_ensure_space_access_blocks_viewer_for_write_action():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="owner-1", org_id="org-1")

        async def get_org_membership(self, _db, *, org_id, user_id):
            return SimpleNamespace(org_id=org_id, user_id=user_id, role="viewer", is_active=True)

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    async def _run():
        try:
            await svc._ensure_space_access(None, "s1", "viewer-1", False, action="write")
        except HTTPException as exc:
            assert exc.status_code == 403
            return
        assert False, "expected viewer write denied"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_ensure_space_access_allows_member_for_execute_action():
    svc = PersistentOntologyService()
    from app.core.config import settings

    class Repo:
        async def get_space_by_id(self, _db, _space_id):
            return SimpleNamespace(id="s1", owner_user_id="owner-1", org_id="org-1")

        async def get_org_membership(self, _db, *, org_id, user_id):
            return SimpleNamespace(org_id=org_id, user_id=user_id, role="member", is_active=True)

    svc.repo = Repo()
    original = settings.ENABLE_ORG_TENANCY
    settings.ENABLE_ORG_TENANCY = True

    async def _run():
        space = await svc._ensure_space_access(None, "s1", "member-1", False, action="execute")
        assert space.id == "s1"

    try:
        asyncio.run(_run())
    finally:
        settings.ENABLE_ORG_TENANCY = original


def test_discover_entities_from_openapi_components():
    svc = PersistentOntologyService()
    spec = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Contract": {
                    "type": "object",
                    "required": ["id", "amount"],
                    "properties": {
                        "id": {"type": "string"},
                        "amount": {"type": "number"},
                        "active": {"type": "boolean"},
                    },
                }
            }
        },
    }

    entities = svc._discover_entities_from_openapi(spec)

    assert len(entities) == 1
    assert entities[0].name == "Contract"
    assert entities[0].primary_keys == ["id"]
    amount = next(col for col in entities[0].columns if col.name == "amount")
    assert amount.data_type == "number"
    assert amount.nullable is False


def test_normalize_discovered_type_boundaries():
    svc = PersistentOntologyService()
    assert svc._normalize_discovered_type("bigint") == "integer"
    assert svc._normalize_discovered_type("numeric") == "number"
    assert svc._normalize_discovered_type("boolean") == "boolean"
    assert svc._normalize_discovered_type("jsonb") == "object"
    assert svc._normalize_discovered_type("varchar") == "string"


def test_secret_encrypt_decrypt_roundtrip():
    svc = PersistentOntologyService()
    encrypted = svc._encrypt_secret("db-password")

    assert encrypted != "db-password"
    assert svc._decrypt_secret(encrypted) == "db-password"


def test_secret_ref_validation():
    svc = PersistentOntologyService()
    assert svc._normalize_secret_part("prod.db-1") == "prod.db-1"
    try:
        svc._normalize_secret_part("../bad")
    except HTTPException as exc:
        assert exc.status_code == 400
        return
    assert False, "expected invalid secret ref to be rejected"
