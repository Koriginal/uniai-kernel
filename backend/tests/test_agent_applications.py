import pytest
from fastapi import HTTPException

from app.models.agent import AgentProfile
from app.models.application import AgentApplication
from app.services.application_service import (
    build_runtime_contract,
    ensure_application_access,
    normalize_application_payload,
)


class _FakeDB:
    def __init__(self, items):
        self.items = items

    async def get(self, model, item_id):
        return self.items.get((model, item_id))


def test_normalize_application_payload_validates_scenario_and_lists():
    payload = normalize_application_payload(
        {
            "name": " 风控审核应用 ",
            "scenario_type": "risk_review",
            "runtime_provider_names": ["default_task_runtime", "default_task_runtime", ""],
            "tool_names": ["web_search", " web_search ", "ontology_evaluate_rules"],
        }
    )

    assert payload["name"] == "风控审核应用"
    assert payload["scenario_type"] == "risk_review"
    assert payload["runtime_provider_names"] == ["default_task_runtime"]
    assert payload["tool_names"] == ["web_search", "ontology_evaluate_rules"]


def test_normalize_application_payload_rejects_invalid_scenario():
    with pytest.raises(HTTPException) as exc:
        normalize_application_payload({"name": "业务应用", "scenario_type": "unknown"})

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_ensure_application_access_blocks_other_user():
    application = AgentApplication(id="app-1", user_id="owner-1", name="应用", scenario_type="custom")
    db = _FakeDB({(AgentApplication, "app-1"): application})

    with pytest.raises(HTTPException) as exc:
        await ensure_application_access(db, "app-1", user_id="user-2", is_admin=False)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_runtime_contract_resolves_agent_provider_tools_and_policies():
    agent = AgentProfile(
        id="agent-1",
        user_id="user-1",
        name="风控主控",
        agent_type="workflow",
        role="orchestrator",
        tools=["web_search", "upsert_canvas"],
        runtime_policy={"allow_tools": True, "allow_swarm": True},
        ontology_config={"enabled": False, "mode": "off"},
    )
    application = AgentApplication(
        id="app-1",
        user_id="user-1",
        name="风控审核应用",
        business_domain="risk",
        scenario_type="risk_review",
        primary_agent_id="agent-1",
        runtime_provider_names=[],
        tool_names=["web_search"],
        ontology_space_id="space-1",
        runtime_policy={"allow_swarm": False},
        acceptance_policy={"required_sections": ["结论", "证据"]},
        status="active",
    )
    db = _FakeDB({(AgentProfile, "agent-1"): agent})

    contract = await build_runtime_contract(db, application, user_id="user-1", is_admin=False)

    assert contract["primary_agent"]["id"] == "agent-1"
    assert contract["runtime_provider_names"] == ["default_task_runtime"]
    assert contract["tool_names"] == ["web_search"]
    assert contract["ontology_config"]["space_id"] == "space-1"
    assert contract["runtime_policy"]["allow_swarm"] is False
    assert contract["acceptance_policy"]["required_sections"] == ["结论", "证据"]
