from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime_capabilities import get_runtime_provider_catalog
from app.core.plugins import registry
from app.models.agent import AgentProfile
from app.models.application import AgentApplication


SCENARIO_TYPES = {"risk_review", "contract_review", "customer_support", "research_workflow", "custom"}
APPLICATION_STATUSES = {"active", "paused", "archived"}
DEFAULT_PROVIDER_NAME = "default_task_runtime"


def normalize_name_list(values: Any) -> List[str]:
    items: List[str] = []
    for value in values or []:
        item = str(value).strip()
        if item and item not in items:
            items.append(item)
    return items


def normalize_application_payload(data: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    normalized = dict(data)
    if not partial or "name" in normalized:
        name = str(normalized.get("name") or "").strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="业务应用名称至少需要 2 个字符")
        normalized["name"] = name
    if "description" in normalized and normalized.get("description") is not None:
        normalized["description"] = str(normalized["description"]).strip()
    if "business_domain" in normalized and normalized.get("business_domain") is not None:
        normalized["business_domain"] = str(normalized["business_domain"]).strip() or None
    if not partial or "scenario_type" in normalized:
        scenario_type = str(normalized.get("scenario_type") or "custom").strip()
        if scenario_type not in SCENARIO_TYPES:
            raise HTTPException(status_code=400, detail=f"scenario_type 仅支持: {', '.join(sorted(SCENARIO_TYPES))}")
        normalized["scenario_type"] = scenario_type
    if "status" in normalized and normalized.get("status") is not None:
        status = str(normalized["status"]).strip()
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail=f"status 仅支持: {', '.join(sorted(APPLICATION_STATUSES))}")
        normalized["status"] = status
    if "runtime_provider_names" in normalized:
        normalized["runtime_provider_names"] = normalize_name_list(normalized.get("runtime_provider_names"))
    if "tool_names" in normalized:
        normalized["tool_names"] = normalize_name_list(normalized.get("tool_names"))
    if "runtime_policy" in normalized and normalized.get("runtime_policy") is not None and not isinstance(normalized["runtime_policy"], dict):
        raise HTTPException(status_code=400, detail="runtime_policy 必须是对象")
    if "acceptance_policy" in normalized and normalized.get("acceptance_policy") is not None and not isinstance(normalized["acceptance_policy"], dict):
        raise HTTPException(status_code=400, detail="acceptance_policy 必须是对象")
    if "ontology_space_id" in normalized and normalized.get("ontology_space_id") is not None:
        normalized["ontology_space_id"] = str(normalized["ontology_space_id"]).strip() or None
    if "primary_agent_id" in normalized and normalized.get("primary_agent_id") is not None:
        normalized["primary_agent_id"] = str(normalized["primary_agent_id"]).strip() or None
    return normalized


async def ensure_application_access(
    db: AsyncSession,
    application_id: str,
    *,
    user_id: str,
    is_admin: bool = False,
) -> AgentApplication:
    application = await db.get(AgentApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Agent application not found")
    if application.user_id != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to access this application")
    return application


async def ensure_agent_access(
    db: AsyncSession,
    agent_id: Optional[str],
    *,
    user_id: str,
    is_admin: bool = False,
) -> Optional[AgentProfile]:
    if not agent_id:
        return None
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="primary_agent_id 指向的智能体不存在")
    if agent.user_id != user_id and not agent.is_public and not is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to use this primary agent")
    return agent


def application_to_dict(application: AgentApplication) -> Dict[str, Any]:
    return {
        "id": application.id,
        "user_id": application.user_id,
        "name": application.name,
        "description": application.description,
        "business_domain": application.business_domain,
        "scenario_type": application.scenario_type,
        "primary_agent_id": application.primary_agent_id,
        "runtime_provider_names": application.runtime_provider_names or [],
        "tool_names": application.tool_names or [],
        "ontology_space_id": application.ontology_space_id,
        "runtime_policy": application.runtime_policy or {},
        "acceptance_policy": application.acceptance_policy or {},
        "status": application.status,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
    }


def _effective_provider_names(application: AgentApplication) -> List[str]:
    configured = normalize_name_list(application.runtime_provider_names)
    return configured or [DEFAULT_PROVIDER_NAME]


def _effective_tool_names(application: AgentApplication, agent: Optional[AgentProfile]) -> List[str]:
    app_tools = normalize_name_list(application.tool_names)
    if app_tools:
        return app_tools
    if agent and agent.tools:
        return normalize_name_list(agent.tools)
    return []


async def build_runtime_contract(
    db: AsyncSession,
    application: AgentApplication,
    *,
    user_id: str,
    is_admin: bool = False,
) -> Dict[str, Any]:
    agent = await ensure_agent_access(db, application.primary_agent_id, user_id=user_id, is_admin=is_admin)
    provider_names = _effective_provider_names(application)
    providers = [item for item in get_runtime_provider_catalog() if item.get("name") in provider_names]
    tool_names = _effective_tool_names(application, agent)
    action_map = {item["name"]: item for item in registry.get_action_catalog()}
    tools = list(action_map.values()) if "*" in tool_names else [action_map[name] for name in tool_names if name in action_map]
    missing_tools = [name for name in tool_names if name != "*" and name not in action_map]
    runtime_policy = dict((agent.runtime_policy if agent else {}) or {})
    runtime_policy.update(application.runtime_policy or {})

    ontology_config = dict((agent.ontology_config if agent else {}) or {})
    if application.ontology_space_id:
        ontology_config.update({"enabled": True, "mode": ontology_config.get("mode") or "auto", "space_id": application.ontology_space_id})

    return {
        "application": application_to_dict(application),
        "primary_agent": {
            "id": agent.id,
            "name": agent.name,
            "agent_type": agent.agent_type,
            "role": agent.role,
        } if agent else None,
        "runtime_provider_names": provider_names,
        "providers": providers,
        "tool_names": tool_names,
        "tools": tools,
        "missing_tools": missing_tools,
        "ontology_space_id": application.ontology_space_id,
        "ontology_config": ontology_config,
        "runtime_policy": runtime_policy,
        "acceptance_policy": application.acceptance_policy or {},
        "limits": {
            "provider_scope": "application" if application.runtime_provider_names else "default",
            "tool_scope": "application" if application.tool_names else "agent",
        },
    }


async def list_user_applications(db: AsyncSession, *, user_id: str, is_admin: bool = False) -> List[AgentApplication]:
    stmt = select(AgentApplication).order_by(AgentApplication.created_at.desc())
    if not is_admin:
        stmt = stmt.where(AgentApplication.user_id == user_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())
