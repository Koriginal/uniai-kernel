from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send
from app.core.db import SessionLocal
from app.services.user_service import user_service
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware:
    """
    多租户身份识别中间件 (ASGI 模式)
    摒弃 BaseHTTPMiddleware 以解决流式响应下的 CancelledError 问题。
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive)
        path = request.url.path

        # 1. 排除路径
        if path in ["/", "/docs", "/openapi.json", "/redoc"] or path.startswith("/static"):
            return await self.app(scope, receive, send)

        # 2. 控制台访问保护
        if path.startswith("/dashboard"):
            db_token = request.headers.get("X-Dashboard-Token")
            from app.core.config import settings
            if db_token != settings.DASHBOARD_PASSWORD:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Dashboard access denied. Invalid token."}
                )
                return await response(scope, receive, send)
            return await self.app(scope, receive, send)

        # 3. 提取 API Key 与 identity 注入
        api_key = request.headers.get("X-API-Key")
        user_id = "default_user"

        if api_key:
            async with SessionLocal() as db:
                user = await user_service.get_user_by_api_key(db, api_key)
                if not user:
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid API Key"}
                    )
                    return await response(scope, receive, send)
                user_id = user.id

        # 将身份注入 scope["state"] 而不是 request.state (ASGI 规范)
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user_id"] = user_id
        
        await self.app(scope, receive, send)
