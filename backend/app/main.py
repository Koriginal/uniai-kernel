import logging
import os
import warnings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.core.config import settings

# 抑制 LiteLLM Pydantic 序列化警告
warnings.filterwarnings("ignore", category=UserWarning, message=".*Pydantic serializer warnings.*")

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动加载流水线
    logger.info("UniAI Kernel 启动加载流水线...")
    
    from app.core.plugins import registry
    registry.load_plugins("app.tools")
    
    # 2. 自动配置与动态数据加载
    from app.core.startup import auto_configure_admin
    from app.core.db import SessionLocal
    
    await auto_configure_admin()
    
    # 加载数据库中的动态工具
    async with SessionLocal() as session:
        await registry.load_dynamic_tools(session)
    
    logger.info(f"已加载内核扩展能力：{[t.metadata.name for t in registry.get_all_actions()]}")
    
    yield
    logger.info("UniAI Kernel 正在安全关闭...")

app = FastAPI(
    title="UniAI Kernel",
    description="智能体开发基座 - 支持多租户模型管理、记忆系统和智能对话",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
if settings.BACKEND_CORS_ORIGINS:
    origins = [origin.strip() for origin in str(settings.BACKEND_CORS_ORIGINS).split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "UniAI Kernel is running."}

from app.api.router import api_router
from app.core.middleware import AuthMiddleware

app.include_router(api_router)
app.add_middleware(AuthMiddleware)

# 挂载 Dashboard 静态资源 (适配专业化目录结构)
# 开发环境下建议使用 Vite 独立服务，生产环境下通过此处挂载 dist 产物
frontend_path = os.path.join(os.path.dirname(__file__), "../../frontend")
if os.path.exists(frontend_path):
    app.mount("/dashboard", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # 本地启动将采用 settings.PORT (由 .env 决定，代码默认 8000)
    logger.info(f"正在以本地模式启动服务在端口: {settings.PORT} ...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)