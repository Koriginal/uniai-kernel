# Ontology Governance Runbook

## 1. Scope
This runbook describes how to operate ontology governance in production:
- package lifecycle (draft -> review -> staging -> ga -> deprecated)
- approval workflow for staging/ga releases
- compatibility checks and strict mode
- rollback procedure

## 2. Prerequisites
- Backend service is running.
- Database migrations are up to date:
  - `e1c3f9b6d2a1_add_ontology_persistence_tables`
  - `a4d8c7b1e902_add_ontology_approvals`
  - `c3f4a8b9d102_add_ontology_governance_constraints`
- Auth token belongs to owner/admin reviewer role.

## 3. Configuration
Set in `backend/.env`:
- `ENABLE_ONTOLOGY_ENGINE=True`
- `ONTOLOGY_REQUIRE_APPROVAL_FOR_STAGING=True`
- `ONTOLOGY_REQUIRE_APPROVAL_FOR_GA=True`
- `ONTOLOGY_MAX_TRACE_ITEMS=500`
- `ENABLE_ORG_TENANCY=False` (默认用户级；开启后支持组织级作用域)

## 4. Governance Workflow
1. Create ontology space:
   - `POST /api/v1/ontology/spaces`
2. Upsert package version (`schema` / `mapping` / `rules`):
   - `POST /api/v1/ontology/schema`
   - `POST /api/v1/ontology/mapping`
   - `POST /api/v1/ontology/rules`
3. Submit approval request:
   - `POST /api/v1/ontology/governance/approvals/submit`
4. Reviewer approves/rejects:
   - `POST /api/v1/ontology/governance/approvals/review`
5. Release package stage:
   - `POST /api/v1/ontology/governance/release`
6. If required, rollback to target version:
   - `POST /api/v1/ontology/governance/rollback`

## 5. Approval Rules
- Staging/GA releases require approved gate by default.
- Requester cannot approve their own request.
- Owner/admin can review approvals.
- Missing gate returns `409 release approval required`.

## 6. Compatibility Checks
- Compatible warnings are generated on GA release when same major version removes entities/rules.
- Set `strict_compatibility=true` to block release when warnings exist.
- Governance constraints are enforced at DB level:
  - package kind/stage check constraints
  - approval status/requested_stage check constraints
  - unique pending approval gate per `space_id + kind + version + requested_stage`

## 7. Rollback Procedure
1. Pick target version from package list.
2. Trigger rollback endpoint with `space_id/kind/target_version`.
3. Validate:
   - target version stage becomes `ga`
   - previous active version becomes `deprecated`
   - release event is recorded

## 8. Auditing
The following actions are audited:
- `ontology.space.create`
- `ontology.package.upsert`
- `ontology.approval.submit`
- `ontology.approval.review`
- `ontology.package.release`
- `ontology.package.rollback`
- `ontology.mapping.execute`
- `ontology.rules.evaluate`

## 9. Failure Handling
- `409 compatibility checks failed`: use non-strict mode or fix breaking changes.
- `409 release approval required`: submit and approve gate first.
- `403 forbidden`: verify owner/admin permissions.
- `404 package version not found`: check kind/version in package list.

## 10. Operational Checklist
- Before release:
  - run mapping debug and rule evaluate in console
  - inspect package diff
  - ensure approval gate exists for staging/ga
- After release:
  - verify release events
  - run explain replay on critical decision IDs
- Weekly:
  - review audit logs for unusual release/review activities

## 11. E2E Verification Script
Run database-backed acceptance in one command:
- `cd backend && uv run python scripts/verify_ontology_e2e.py`

Expected output includes:
- `space_id`
- `decision_id`
- `rollback_stage=ga`
- `rule_release_events` (>= 2)
