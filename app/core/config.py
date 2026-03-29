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
    BACKEND_CORS_ORIGINS: str = "http://localhost,http://localhost:5173"
    
    # --- 数据库配置 ---
    POSTGRES_USER: str = "root"
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agent_db"
    
    @property
    def DATABASE_URL(self) -> str:
        """自动构建数据库 URL"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # --- 安全配置 ---
    ENCRYPTION_KEY: str  # API Key 加密密钥
    
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

    # --- Agent 配置 ---
    # agent 循环的最大迭代次数
    MAX_AGENT_ITERATIONS: int = 25
    
    # --- 记忆管理配置 ---
    MEMORY_EXTRACTION_ENABLED: bool = True  # 是否启用自动记忆提取
    MEMORY_CONSOLIDATION_THRESHOLD: float = 0.8  # 记忆去重相似度阈值
    SESSION_COMPRESSION_THRESHOLD: int = 20  # 触发会话压缩的消息数
    
    # --- 默认模型配置（快速启动） ---
    # LLM
    DEFAULT_LLM_PROVIDER: Optional[str] = None
    DEFAULT_LLM_MODEL: Optional[str] = None
    DEFAULT_LLM_API_KEY: Optional[str] = None
    # Embedding
    DEFAULT_EMBEDDING_PROVIDER: Optional[str] = None
    DEFAULT_EMBEDDING_MODEL: Optional[str] = None
    DEFAULT_EMBEDDING_API_KEY: Optional[str] = None
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