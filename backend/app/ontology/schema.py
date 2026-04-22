from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class SemanticFrame(BaseModel):
    intent: str = "qa"
    domain: str = "general"
    interaction_mode: str = "chat"
    confidence: float = 0.0


class SemanticSlots(BaseModel):
    raw_query: str = ""
    entities: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    desired_artifacts: List[str] = Field(default_factory=list)
    delegated_task: Optional[str] = None


class SemanticContext(BaseModel):
    interaction_mode: str = "chat"
    frame: SemanticFrame = Field(default_factory=SemanticFrame)
    slots: SemanticSlots = Field(default_factory=SemanticSlots)


class DelegationDecision(BaseModel):
    allow_delegate: bool = False
    reason: str = ""
    confidence: float = 0.0
    recommended_task: Optional[str] = None
