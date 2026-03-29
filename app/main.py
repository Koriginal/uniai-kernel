import logging
import warnings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings

# 抑制 LiteLLM Pydantic 序列化警告
warnings.filterwarnings("ignore", category=UserWarning, message=".*Pydantic serializer warnings.*")

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UniAI Kernel 正在启动...")
    from app.core.startup import auto_configure_default_user
    await auto_configure_default_user()
    yield
    logger.info("UniAI Kernel 正在关闭...")

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

app.include_router(api_router, prefix="/api/v1")