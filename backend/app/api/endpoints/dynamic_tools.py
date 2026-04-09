from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Tuple
from app.core.db import get_db
from app.models.dynamic_tool import DynamicTool
from app.core.plugins import registry
from pydantic import BaseModel
from datetime import datetime
import re
from app.services.ext_tools import ApiTool, McpTool, CliTool, McpSseTool

router = APIRouter()

VALID_TOOL_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{1,63}$")
VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

class DynamicToolCreate(BaseModel):
    name: str
    label: str
    description: str
    tool_type: str # api, mcp, cli
    config: Dict[str, Any]
    parameters_schema: Dict[str, Any] = {"type": "object", "properties": {}}
    category: str = "custom"

class DynamicToolResponse(BaseModel):
    id: str
    name: str
    label: str
    description: str
    category: str
    tool_type: str
    config: Dict[str, Any]
    parameters_schema: Dict[str, Any]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DynamicToolValidationRequest(BaseModel):
    name: str
    label: str
    description: str
    tool_type: str
    config: Dict[str, Any]
    parameters_schema: Dict[str, Any] = {"type": "object", "properties": {}}
    category: str = "custom"


class DynamicToolValidationResponse(BaseModel):
    ok: bool
    normalized_config: Dict[str, Any]
    normalized_schema: Dict[str, Any]
    warnings: List[str]


class DynamicToolTestRequest(DynamicToolValidationRequest):
    sample_args: Dict[str, Any] = {}


class DynamicToolTestResponse(BaseModel):
    ok: bool
    normalized_config: Dict[str, Any]
    normalized_schema: Dict[str, Any]
    warnings: List[str]
    result_preview: str


def _validate_parameters_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="parameters_schema 必须是合法 JSON 对象")
    if schema.get("type") != "object":
        raise HTTPException(status_code=400, detail="parameters_schema 顶层 type 必须为 object")
    properties = schema.get("properties", {})
    if properties is None:
        properties = {}
    if not isinstance(properties, dict):
        raise HTTPException(status_code=400, detail="parameters_schema.properties 必须是对象")

    required = schema.get("required", [])
    if required is None:
        required = []
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise HTTPException(status_code=400, detail="parameters_schema.required 必须是字符串数组")

    normalized = dict(schema)
    normalized["properties"] = properties
    normalized["required"] = required
    return normalized


def _normalize_dynamic_tool_payload(data: DynamicToolCreate | DynamicToolValidationRequest) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    warnings: List[str] = []

    if not VALID_TOOL_NAME.match(data.name):
        raise HTTPException(
            status_code=400,
            detail="函数名只能包含字母、数字和下划线，且必须以字母或下划线开头，长度 2-64"
        )
    if not data.label.strip():
        raise HTTPException(status_code=400, detail="展示名称不能为空")
    if len(data.description.strip()) < 8:
        raise HTTPException(status_code=400, detail="工具描述至少需要 8 个字符，便于模型正确理解用途")

    normalized_schema = _validate_parameters_schema(data.parameters_schema or {})
    tool_type = (data.tool_type or "").lower()
    config = data.config or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config 必须是 JSON 对象")

    normalized_config: Dict[str, Any] = {}

    def read_timeout(default: float) -> float:
        raw = config.get("timeout_seconds", default)
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="timeout_seconds 必须是数字")
        if timeout <= 0 or timeout > 120:
            raise HTTPException(status_code=400, detail="timeout_seconds 必须在 0 到 120 秒之间")
        if timeout > 60:
            warnings.append("超时时间超过 60 秒，可能拖慢智能体单轮响应。")
        return timeout

    if tool_type == "api":
        url = str(config.get("url", "")).strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="API 工具必须提供以 http:// 或 https:// 开头的 URL")
        method = str(config.get("method", "POST")).upper()
        if method not in VALID_HTTP_METHODS:
            raise HTTPException(status_code=400, detail=f"API method 仅支持 {', '.join(sorted(VALID_HTTP_METHODS))}")
        headers = config.get("headers", {})
        if headers is None:
            headers = {}
        if not isinstance(headers, dict):
            raise HTTPException(status_code=400, detail="API headers 必须是 JSON 对象")
        normalized_config = {
            "url": url,
            "method": method,
            "headers": {str(k): str(v) for k, v in headers.items()},
            "timeout_seconds": read_timeout(20),
        }
        if method == "GET" and normalized_schema.get("properties"):
            warnings.append("GET 工具会把参数作为 querystring 发送，请确认目标服务支持该形式。")

    elif tool_type == "mcp":
        transport = str(config.get("transport", "stdio")).lower()
        if transport not in {"stdio", "sse"}:
            raise HTTPException(status_code=400, detail="MCP transport 仅支持 stdio 或 sse")
        normalized_config["transport"] = transport

        if transport == "sse":
            url = str(config.get("url", "")).strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                raise HTTPException(status_code=400, detail="MCP SSE 模式必须提供以 http:// 或 https:// 开头的 URL")
            normalized_config["url"] = url
            normalized_config["timeout_seconds"] = read_timeout(30)
            warnings.append("MCP SSE 模式要求远端服务返回标准 endpoint 事件。")
        else:
            command = str(config.get("command", "")).strip()
            if not command:
                raise HTTPException(status_code=400, detail="MCP stdio 模式必须提供 command")
            args = config.get("args", [])
            if isinstance(args, str):
                args = [part for part in args.split(" ") if part]
            if not isinstance(args, list):
                raise HTTPException(status_code=400, detail="MCP args 必须是字符串数组")
            normalized_config["command"] = command
            normalized_config["args"] = [str(item) for item in args]
            normalized_config["timeout_seconds"] = read_timeout(30)
            warnings.append("MCP stdio 模式依赖内核运行环境能直接启动对应命令。")

    elif tool_type == "cli":
        script = str(config.get("script", "")).strip()
        if not script:
            raise HTTPException(status_code=400, detail="CLI 工具必须提供脚本内容")
        normalized_config["script"] = script
        normalized_config["timeout_seconds"] = read_timeout(30)
        warnings.append("CLI 工具会在服务器本地执行，请只接入可信脚本。")

    else:
        raise HTTPException(status_code=400, detail="tool_type 仅支持 api、mcp、cli")

    return normalized_config, normalized_schema, warnings


@router.post("/validate", response_model=DynamicToolValidationResponse)
async def validate_dynamic_tool(data: DynamicToolValidationRequest):
    """注册前校验与规范化，供前端预检配置。"""
    normalized_config, normalized_schema, warnings = _normalize_dynamic_tool_payload(data)
    return {
        "ok": True,
        "normalized_config": normalized_config,
        "normalized_schema": normalized_schema,
        "warnings": warnings,
    }


def _build_dynamic_tool_instance(data: DynamicToolValidationRequest, normalized_config: Dict[str, Any], normalized_schema: Dict[str, Any]):
    tool_type = data.tool_type.lower()
    if tool_type == "api":
        return ApiTool(
            name=data.name,
            label=data.label,
            description=data.description,
            url=normalized_config["url"],
            method=normalized_config["method"],
            headers=normalized_config.get("headers"),
            schema=normalized_schema,
            timeout_seconds=float(normalized_config.get("timeout_seconds", 20)),
        )
    if tool_type == "mcp":
        if normalized_config.get("transport") == "sse":
            return McpSseTool(
                name=data.name,
                label=data.label,
                description=data.description,
                url=normalized_config["url"],
                schema=normalized_schema,
                timeout_seconds=float(normalized_config.get("timeout_seconds", 30)),
            )
        return McpTool(
            name=data.name,
            label=data.label,
            description=data.description,
            command=normalized_config["command"],
            args=normalized_config.get("args", []),
            schema=normalized_schema,
            timeout_seconds=float(normalized_config.get("timeout_seconds", 30)),
        )
    return CliTool(
        name=data.name,
        label=data.label,
        description=data.description,
        script=normalized_config["script"],
        schema=normalized_schema,
        timeout_seconds=float(normalized_config.get("timeout_seconds", 30)),
    )


@router.post("/test", response_model=DynamicToolTestResponse)
async def test_dynamic_tool(data: DynamicToolTestRequest):
    """注册前执行一次真实探测，验证接入链路是否通畅。"""
    normalized_config, normalized_schema, warnings = _normalize_dynamic_tool_payload(data)
    tool = _build_dynamic_tool_instance(data, normalized_config, normalized_schema)
    sample_args = data.sample_args or {}
    if not isinstance(sample_args, dict):
        raise HTTPException(status_code=400, detail="sample_args 必须是 JSON 对象")
    try:
        result = await tool.execute(**sample_args)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"测试调用失败: {e}")
    result_preview = str(result)
    if len(result_preview) > 1200:
        result_preview = result_preview[:1200] + "\n...<truncated>"
    return {
        "ok": True,
        "normalized_config": normalized_config,
        "normalized_schema": normalized_schema,
        "warnings": warnings,
        "result_preview": result_preview,
    }

@router.get("/", response_model=List[DynamicToolResponse])
async def list_dynamic_tools(db: AsyncSession = Depends(get_db)):
    """获取所有动态注册工具的原始定义列表"""
    result = await db.execute(select(DynamicTool))
    return result.scalars().all()

@router.post("/", response_model=DynamicToolResponse)
async def create_dynamic_tool(
    data: DynamicToolCreate,
    db: AsyncSession = Depends(get_db)
):
    """注册一个新的动态工具 (API/MCP/CLI)"""
    # 检查重名
    existing = await db.execute(select(DynamicTool).where(DynamicTool.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tool with name '{data.name}' already exists")

    normalized_config, normalized_schema, _ = _normalize_dynamic_tool_payload(data)
    new_tool = DynamicTool(
        name=data.name,
        label=data.label.strip(),
        description=data.description.strip(),
        tool_type=data.tool_type.lower(),
        category=data.category or "custom",
        config=normalized_config,
        parameters_schema=normalized_schema
    )
    db.add(new_tool)
    await db.commit()
    await db.refresh(new_tool)
    
    # 立即尝试加载到当前内核注册表 (热更新)
    await registry.load_dynamic_tools(db)
    
    return new_tool

@router.delete("/{tool_id}")
async def delete_dynamic_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """删除动态工具"""
    tool = await db.get(DynamicTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    await db.delete(tool)
    await db.commit()
    await registry.load_dynamic_tools(db)
    return {"status": "success"}

@router.post("/{tool_id}/toggle")
async def toggle_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """启用/禁用动态工具"""
    tool = await db.get(DynamicTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    tool.is_active = not tool.is_active
    await db.commit()
    await registry.load_dynamic_tools(db)
    return {"status": "success", "is_active": tool.is_active}
