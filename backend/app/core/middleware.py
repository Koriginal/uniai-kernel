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
        if (
            path in ["/", "/docs", "/openapi.json", "/redoc"]
            or path.startswith("/static")
            or path.startswith("/dashboard")
        ):
            return await self.app(scope, receive, send)

        # 2. 提取 API Key 与 identity 注入（不再默认注入 admin）
        api_key = request.headers.get("X-API-Key")
        user_id = None

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
        if user_id:
            scope["state"]["user_id"] = user_id
        
        await self.app(scope, receive, send)
