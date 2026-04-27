import asyncio
import json
import httpx
from typing import Dict, Any, Optional
from app.tools.base import BaseTool
import os
import shlex
from pathlib import Path

from app.core.config import settings

class ApiTool(BaseTool):
    """通过 HTTP API 调用执行外部工具"""
    def __init__(self, name: str, label: str, description: str, url: str, method: str = "POST", headers: Dict[str, str] = None, schema: Dict[str, Any] = None, timeout_seconds: float = 20.0):
        super().__init__(name, label, description, category="api")
        self.url = url
        self.method = method
        self.headers = headers or {}
        self._schema = schema or {"type": "object", "properties": {}}
        self.timeout_seconds = timeout_seconds

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                if self.method.upper() == "GET":
                    resp = await client.get(self.url, params=kwargs, headers=self.headers)
                else:
                    resp = await client.post(self.url, json=kwargs, headers=self.headers)
                
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                return f"Error calling API tool {self.metadata.name}: {str(e)}"

class McpTool(BaseTool):
    """Model Context Protocol (MCP) 适配器 (基于 stdio 传输)"""
    def __init__(self, name: str, label: str, description: str, command: str, args: list = None, schema: Dict[str, Any] = None, timeout_seconds: float = 30.0):
        super().__init__(name, label, description, category="mcp")
        self.command = command
        self.args = args or []
        self._schema = schema or {"type": "object", "properties": {}}
        self.timeout_seconds = timeout_seconds

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs) -> str:
        # 简化版：启动 MCP Server 进程，发送 JSON-RPC 调用 (由于 MCP 协议较复杂，这里做核心逻辑模拟)
        # 实际生产中应当对接 MCP SDK
        proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # 构造简单的 MCP 风格请求
        request = {
            "jsonrpc": "2.0",
            "method": f"tools/call",
            "params": {"name": self.metadata.name, "arguments": kwargs},
            "id": 1
        }
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=json.dumps(request).encode()),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"MCP Error: execution timed out after {self.timeout_seconds:.0f}s"
        
        if proc.returncode != 0:
            return f"MCP Error: {stderr.decode()}"
        
        try:
            response = json.loads(stdout.decode())
            return str(response.get("result", {}).get("content", "No result"))
        except:
            return stdout.decode()

class CliTool(BaseTool):
    """本地命令行工具执行 (注意安全！)"""
    def __init__(self, name: str, label: str, description: str, script: str, schema: Dict[str, Any] = None, timeout_seconds: float = 30.0):
        super().__init__(name, label, description, category="cli")
        self.script = script
        self._schema = schema or {"type": "object", "properties": {}}
        self.timeout_seconds = timeout_seconds

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs) -> str:
        if not settings.ENABLE_DYNAMIC_CLI_TOOLS:
            return "CLI Error: dynamic CLI tools are disabled by server policy"

        # 生产安全基线：禁止 shell 解释器，使用 argv 直接执行，降低命令注入风险。
        argv = shlex.split(self.script)
        if not argv:
            return "CLI Error: empty command"
        command = Path(argv[0]).name

        allowed = {
            item.strip()
            for item in (settings.DYNAMIC_CLI_ALLOWED_COMMANDS or "").split(",")
            if item.strip()
        }
        if not allowed:
            return "CLI Error: command allowlist is empty (set DYNAMIC_CLI_ALLOWED_COMMANDS)"
        if command not in allowed:
            return f"CLI Error: command '{command}' is not in allowlist"

        # 最小环境变量注入：仅保留基础运行变量 + 工具参数
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }
        env.update({f"UAI_ARG_{k.upper()}": str(v) for k, v in kwargs.items() if k})

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=(settings.DYNAMIC_CLI_WORKDIR or None),
            start_new_session=True,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"CLI Error: execution timed out after {self.timeout_seconds:.0f}s"
        
        if proc.returncode != 0:
            return f"CLI Error: {stderr.decode()}"
        return stdout.decode().strip()

class McpSseTool(BaseTool):
    """Model Context Protocol (MCP) 适配器 (基于 SSE 传输)"""
    def __init__(self, name: str, label: str, description: str, url: str, schema: Dict[str, Any] = None, timeout_seconds: float = 30.0):
        super().__init__(name, label, description, category="mcp")
        self.url = url
        self._schema = schema or {"type": "object", "properties": {}}
        self.timeout_seconds = timeout_seconds

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs) -> str:
        """
        执行流程:
        1. GET 请求建立 SSE 连接。
        2. 从事件流中获取 'endpoint' 事件（包含实际的 POST URL 和 sessionId）。
        3. 发送 JSON-RPC 调用到该 endpoint。
        """
        from urllib.parse import urljoin
        
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            endpoint_url = None
            
            try:
                # 步骤 1: 建立并解析 SSE 握手
                async with client.stream("GET", self.url) as response:
                    if response.status_code != 200:
                        return f"MCP SSE Error: Failed to connect (Status: {response.status_code})"
                    
                    # 我们只需要找到第一个 endpoint 事件
                    async for line in response.aiter_lines():
                        if line.startswith("event: endpoint"):
                            continue
                        if line.startswith("data:"):
                            rel_url = line.replace("data:", "").strip()
                            endpoint_url = urljoin(self.url, rel_url)
                            break
                
                if not endpoint_url:
                    return f"MCP SSE Error: No endpoint received from {self.url}"

                # 步骤 2: 发送工具调用
                request_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": self.metadata.name, "arguments": kwargs},
                    "id": 1
                }
                
                resp = await client.post(endpoint_url, json=request_payload)
                resp.raise_for_status()
                
                result_info = resp.json()
                
                # 解析 MCP 响应格式: result.content[]
                result_data = result_info.get("result", {})
                content_list = result_data.get("content", [])
                
                if isinstance(content_list, list) and len(content_list) > 0:
                    texts = [item.get("text", "") for item in content_list if item.get("type") == "text"]
                    return "\n".join(texts)
                
                return str(result_data)

            except Exception as e:
                return f"MCP SSE Error: {str(e)}"
