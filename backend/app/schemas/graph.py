from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class GraphTopologyVersionBase(BaseModel):
    name: Optional[str] = Field(None, description="版本名称或备注")
    topology: Dict[str, Any] = Field(..., description="拓扑结构 JSON")
    mode: str = Field("auto", description="编排模式: auto/manual")
    is_active: bool = Field(False, description="是否立即激活")

class GraphTopologyVersionCreate(GraphTopologyVersionBase):
    pass

class GraphTopologyVersion(GraphTopologyVersionBase):
    id: int
    template_id: str
    version_code: int
    created_at: datetime
    user_id: Optional[str] = None

    class Config:
        from_attributes = True

class GraphTopologyVersionList(BaseModel):
    versions: List[GraphTopologyVersion]
    active_version_id: Optional[int] = None
