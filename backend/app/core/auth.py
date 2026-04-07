"""
用户认证依赖（可选集成）

开发框架预留的用户认证接口，方便后续集成任何用户体系。
"""
from fastapi import Header, HTTPException
from typing import Optional

async def get_current_user_id(
    x_user_id: Optional[str] = Header(None, description="用户 ID（可选）")
) -> str:
    """
    获取当前用户 ID（框架接口，可自定义实现）。
    
    默认实现：
    - 如果请求头包含 X-User-Id，使用该值
    - 否则使用 admin（单用户模式）
    
    ### 自定义认证示例
    
    ```python
    # 集成 JWT
    async def get_current_user_id(token: str = Depends(oauth2_scheme)):
        payload = jwt.decode(token, SECRET_KEY)
        return payload.get("user_id")
    
    # 集成 Session
    async def get_current_user_id(session: dict = Depends(get_session)):
        return session.get("user_id", "admin")
    
    # 集成第三方系统
    async def get_current_user_id(auth: str = Header(...)):
        user = await verify_external_auth(auth)
        return user.id
    ```
    
    ### 使用方法
    在需要的 API 端点中：
    ```python
    @router.post("/chat")
    async def chat(
        request: ChatRequest,
        user_id: str = Depends(get_current_user_id)
    ):
        ...
    ```
    """
    return x_user_id or "admin"


# 全局用户 ID（用于非 API 调用场景）
GLOBAL_USER_ID = "admin"
