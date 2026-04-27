from app.ontology.domain_models import (
    MappingExecuteRequest,
    MappingPackageCreate,
    OntologySpaceCreate,
    ReleaseRequest,
    RuleCondition,
    RuleDef,
    RuleEvaluateRequest,
    RulePackageCreate,
    SchemaPackageCreate,
    EntityTypeDef,
    AttributeDef,
    EntityInstance,
    InstanceGraph,
    PackageKind,
    VersionStage,
)
from app.ontology.ontology_service import OntologyService


def test_ontology_full_lifecycle():
    service = OntologyService()
    actor = "user-1"

    space = service.create_space(
        OntologySpaceCreate(name="Contract Ontology", code="contract-core"),
        owner_user_id=actor,
    )

    schema = SchemaPackageCreate(
        space_id=space.id,
        version="1.0.0",
        entity_types=[
            EntityTypeDef(
                name="Contract",
                attributes={
                    "amount": AttributeDef(data_type="number", required=True),
                    "currency": AttributeDef(data_type="string", required=True),
                },
            )
        ],
    )
    service.upsert_schema(schema, actor_user_id=actor)
    service.release(
        ReleaseRequest(
            space_id=space.id,
            kind=PackageKind.schema,
            version="1.0.0",
            target_stage=VersionStage.ga,
        ),
        actor_user_id=actor,
    )

    mapping = MappingPackageCreate(
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
    )
    service.upsert_mapping(mapping, actor_user_id=actor)
    service.release(
        ReleaseRequest(
            space_id=space.id,
            kind=PackageKind.mapping,
            version="1.0.0",
            target_stage=VersionStage.ga,
        ),
        actor_user_id=actor,
    )

    rule_pkg = RulePackageCreate(
        space_id=space.id,
        version="1.0.0",
        rules=[
            RuleDef(
                rule_id="RISK_HIGH_AMOUNT",
                name="High amount contract",
                target_entity_type="Contract",
                severity="high",
                action="flag",
                conditions=[RuleCondition(path="entity.amount", operator="gte", value=1000000)],
            )
        ],
    )
    service.upsert_rule(rule_pkg, actor_user_id=actor)
    service.release(
        ReleaseRequest(
            space_id=space.id,
            kind=PackageKind.rule,
            version="1.0.0",
            target_stage=VersionStage.ga,
        ),
        actor_user_id=actor,
    )

    mapped = service.execute_mapping(
        MappingExecuteRequest(
            space_id=space.id,
            input_payload={
                "contract": {
                    "contract_id": "c-001",
                    "amount": "1200000",
                    "currency": "cny",
                }
            },
        ),
        actor_user_id=actor,
    )

    assert mapped.mapping_version == "1.0.0"
    assert len(mapped.graph.entities) == 1
    assert mapped.graph.entities[0].attributes["currency"] == "CNY"

    decision = service.evaluate_rules(
        RuleEvaluateRequest(space_id=space.id, graph=mapped.graph),
        actor_user_id=actor,
    )

    assert decision.risk_level in {"medium", "high", "critical"}
    assert any(hit.rule_id == "RISK_HIGH_AMOUNT" for hit in decision.hits)

    exp = service.explain(decision.decision_id, actor_user_id=actor)
    assert exp.decision.decision_id == decision.decision_id
    assert exp.why


def test_rule_evaluate_without_mapping_path():
    service = OntologyService()
    actor = "user-2"

    space = service.create_space(OntologySpaceCreate(name="Generic"), owner_user_id=actor)

    service.upsert_rule(
        RulePackageCreate(
            space_id=space.id,
            version="1.0.0",
            rules=[
                RuleDef(
                    rule_id="GLOBAL_ENTITY_MIN",
                    name="entity count must be >=1",
                    severity="low",
                    action="recommend",
                    conditions=[RuleCondition(path="graph.entity_count", operator="gte", value=1)],
                )
            ],
        ),
        actor_user_id=actor,
    )
    service.release(
        ReleaseRequest(
            space_id=space.id,
            kind=PackageKind.rule,
            version="1.0.0",
            target_stage=VersionStage.ga,
        ),
        actor_user_id=actor,
    )

    graph = InstanceGraph(entities=[EntityInstance(id="e1", entity_type="Doc", attributes={})])
    decision = service.evaluate_rules(RuleEvaluateRequest(space_id=space.id, graph=graph), actor_user_id=actor)
    assert decision.hits
