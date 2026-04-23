import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    # --- 环境设置 ---
    ENVIRONMENT: str = "development"
    DOMAIN: str = "localhost"
    PORT: int = 8000  # [CODE DEFAULT] 保持 8000 兼容原有提交，本地通过 .env 覆盖
    BACKEND_CORS_ORIGINS: str = "http://localhost,http://localhost:5173"
    
    # --- 数据库配置 ---
    ENABLE_DATABASE: bool = True  # 【微内核降级开关】是否挂载持久化存储
    ENABLE_MEMORY: bool = True    # 【微内核降级开关】是否挂载记忆引擎
    POSTGRES_USER: str = "root"
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agent_db"
    
    @property
    def DATABASE_URL(self) -> str:
        """自动构建数据库 URL"""
        if not self.ENABLE_DATABASE:
            return ""
        if not self.POSTGRES_PASSWORD:
            return ""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # --- Redis 配置 ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    @property
    def REDIS_URL(self) -> str:
        """构建 Redis 连接 URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
    # --- 安全配置 ---
    # 已废弃：/dashboard 入口不再使用共享口令，统一走 JWT 登录体系
    DASHBOARD_PASSWORD: str = "deprecated-not-used"
    ENCRYPTION_KEY: Optional[str] = None  # API Key 加密密钥 (需在 .env 中设置)
    
    # --- JWT 鉴权配置 ---
    SECRET_KEY: str = "change-this-jwt-secret" # JWT 密钥（生产环境必须覆盖）
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 默认 7 天
    # 是否允许在无身份信息时回退到 admin（仅演示模式建议开启）
    ALLOW_ANONYMOUS_ADMIN_FALLBACK: bool = False
    # 生产安全模式：开启后将拒绝弱默认密钥
    ENFORCE_PRODUCTION_SECURITY: bool = True
    # 动态 CLI 工具默认关闭（需显式开启）
    ENABLE_DYNAMIC_CLI_TOOLS: bool = False
    
    # --- 自动初始化配置 (仅用于开发/演示环境快速启动) ---
    DEFAULT_USER_ID: str = "admin"
    # 安全默认：不再自动注入固定 Seed Key；如需演示可在 .env 显式设置
    DEFAULT_USER_API_KEY: Optional[str] = None
    
    # --- LLM 配置 (LiteLLM) ---
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # 默认模型
    # 默认模型 (可选，可由动态提供商覆盖)
    DEFAULT_CHAT_MODEL: Optional[str] = None
    
    # --- 向量模型配置 ---
    VECTOR_MODEL_PROVIDER: Optional[str] = None
    VECTOR_MODEL_NAME: Optional[str] = None
    
    # --- 音频模型配置 ---
    TTS_MODEL_PROVIDER: Optional[str] = None
    TTS_MODEL_NAME: Optional[str] = None
    STT_MODEL_PROVIDER: Optional[str] = None
    STT_MODEL_NAME: Optional[str] = None

    # --- 联网检索配置 ---
    WEB_SEARCH_PROVIDER: str = "auto"  # auto/tavily/serper/duckduckgo
    WEB_SEARCH_TIMEOUT_SECONDS: float = 15.0
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    WEB_SEARCH_ENABLE_PAGE_FETCH: bool = True
    WEB_SEARCH_MAX_CANDIDATES: int = 12
    WEB_SEARCH_MAX_PAGE_FETCH: int = 6
    WEB_SEARCH_PAGE_CHAR_LIMIT: int = 3000
    WEB_SEARCH_CACHE_TTL_SECONDS: int = 300
    WEB_SEARCH_BLOCKED_DOMAINS: str = "localhost,127.0.0.1,0.0.0.0"

    # --- Agent 配置 ---
    # agent 循环的最大迭代次数
    MAX_AGENT_ITERATIONS: int = 25
    
    # --- 记忆管理配置 ---
    MEMORY_EXTRACTION_ENABLED: bool = True  # 是否启用自动记忆提取
    MEMORY_AUTO_EXTRACT_THRESHOLD: int = 1  # 触发提取的消息条数下限 (设为 1 以便即时测试)
    MEMORY_CONSOLIDATION_THRESHOLD: float = 0.8  # 记忆去重相似度阈值
    SESSION_COMPRESSION_THRESHOLD: int = 20  # 触发会话压缩的消息数
    
    # --- 默认模型配置（快速启动） ---
    # LLM
    DEFAULT_LLM_PROVIDER: Optional[str] = None
    DEFAULT_LLM_MODEL: Optional[str] = None
    DEFAULT_LLM_API_KEY: Optional[str] = None
    DEFAULT_LLM_API_BASE: Optional[str] = None
    # Embedding
    DEFAULT_EMBEDDING_PROVIDER: Optional[str] = None
    DEFAULT_EMBEDDING_MODEL: Optional[str] = None
    DEFAULT_EMBEDDING_API_KEY: Optional[str] = None
    DEFAULT_EMBEDDING_API_BASE: Optional[str] = None
    # Rerank（重排序）
    DEFAULT_RERANK_PROVIDER: Optional[str] = None
    DEFAULT_RERANK_MODEL: Optional[str] = None
    DEFAULT_RERANK_API_KEY: Optional[str] = None
    # TTS（语音合成）
    DEFAULT_TTS_PROVIDER: Optional[str] = None
    DEFAULT_TTS_MODEL: Optional[str] = None
    DEFAULT_TTS_API_KEY: Optional[str] = None
    # STT（语音识别）
    DEFAULT_STT_PROVIDER: Optional[str] = None
    DEFAULT_STT_MODEL: Optional[str] = None
    DEFAULT_STT_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = "ignore" # 允许 .env 中的额外字段

settings = Settings()


def validate_security_baseline() -> None:
    """
    生产安全基线校验。
    在生产环境下，拒绝弱默认密钥和缺失加密密钥配置。
    """
    env = (settings.ENVIRONMENT or "").lower()
    is_production = env in {"prod", "production"}
    if not settings.ENFORCE_PRODUCTION_SECURITY or not is_production:
        return

    weak_secret = settings.SECRET_KEY in {
        "", "uniai-secret-2026-fallback", "change-this-jwt-secret"
    }

    errors = []
    if weak_secret:
        errors.append("SECRET_KEY must be set to a strong secret in production.")
    if not settings.ENCRYPTION_KEY:
        errors.append("ENCRYPTION_KEY must be set in production.")
    if settings.ALLOW_ANONYMOUS_ADMIN_FALLBACK:
        errors.append("ALLOW_ANONYMOUS_ADMIN_FALLBACK must be false in production.")

    if errors:
        raise ValueError(" | ".join(errors))
