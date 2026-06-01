from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.db import get_db
from app.models.application import AgentApplication
from app.models.user import User
from app.ontology.persistent_service import persistent_ontology_service
from app.services.application_service import (
    application_to_dict,
    build_runtime_contract,
    ensure_agent_access,
    ensure_application_access,
    list_user_applications,
    normalize_application_payload,
)

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


class AgentApplicationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    business_domain: Optional[str] = None
    scenario_type: str = "custom"
    primary_agent_id: Optional[str] = None
    runtime_provider_names: List[str] = []
    tool_names: List[str] = []
    ontology_space_id: Optional[str] = None
    runtime_policy: Dict[str, Any] = {}
    acceptance_policy: Dict[str, Any] = {}
    status: str = "active"


class AgentApplicationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    business_domain: Optional[str] = None
    scenario_type: Optional[str] = None
    primary_agent_id: Optional[str] = None
    runtime_provider_names: Optional[List[str]] = None
    tool_names: Optional[List[str]] = None
    ontology_space_id: Optional[str] = None
    runtime_policy: Optional[Dict[str, Any]] = None
    acceptance_policy: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class AgentApplicationResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    business_domain: Optional[str] = None
    scenario_type: str
    primary_agent_id: Optional[str] = None
    runtime_provider_names: List[str]
    tool_names: List[str]
    ontology_space_id: Optional[str] = None
    runtime_policy: Dict[str, Any]
    acceptance_policy: Dict[str, Any]
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


async def _ensure_ontology_space_access(db: AsyncSession, space_id: Optional[str], current_user: User) -> None:
    if not space_id:
        return
    await persistent_ontology_service._ensure_space_access(
        db,
        space_id,
        current_user.id,
        current_user.is_admin,
        action="read",
    )


@router.get("/", response_model=List[AgentApplicationResponse])
async def list_applications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    applications = await list_user_applications(db, user_id=current_user.id, is_admin=current_user.is_admin)
    return [application_to_dict(item) for item in applications]


@router.post("/", response_model=AgentApplicationResponse)
async def create_application(
    payload: AgentApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    data = normalize_application_payload(payload.model_dump())
    await ensure_agent_access(db, data.get("primary_agent_id"), user_id=current_user.id, is_admin=current_user.is_admin)
    await _ensure_ontology_space_access(db, data.get("ontology_space_id"), current_user)
    application = AgentApplication(
        user_id=current_user.id,
        **data,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application_to_dict(application)


@router.get("/{application_id}", response_model=AgentApplicationResponse)
async def get_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    application = await ensure_application_access(db, application_id, user_id=current_user.id, is_admin=current_user.is_admin)
    return application_to_dict(application)


@router.patch("/{application_id}", response_model=AgentApplicationResponse)
async def update_application(
    application_id: str,
    payload: AgentApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    application = await ensure_application_access(db, application_id, user_id=current_user.id, is_admin=current_user.is_admin)
    data = normalize_application_payload(payload.model_dump(exclude_unset=True), partial=True)
    if "primary_agent_id" in data:
        await ensure_agent_access(db, data.get("primary_agent_id"), user_id=current_user.id, is_admin=current_user.is_admin)
    if "ontology_space_id" in data:
        await _ensure_ontology_space_access(db, data.get("ontology_space_id"), current_user)
    for key, value in data.items():
        setattr(application, key, value)
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application_to_dict(application)


@router.get("/{application_id}/runtime-contract")
async def get_application_runtime_contract(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    application = await ensure_application_access(db, application_id, user_id=current_user.id, is_admin=current_user.is_admin)
    if application.status != "active":
        raise HTTPException(status_code=409, detail="Agent application is not active")
    return await build_runtime_contract(db, application, user_id=current_user.id, is_admin=current_user.is_admin)
