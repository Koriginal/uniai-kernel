from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# 构建数据库 URL
def get_database_url() -> str:
    """从环境变量构建数据库 URL"""
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    
    # 自动构建
    return (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

# 创建引擎（带连接池配置）
try:
    DATABASE_URL = get_database_url()
    logger.info(f"[Database] Connecting to: {DATABASE_URL.split('@')[1]}")  # 不打印密码
    
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,              # 连接池大小
        max_overflow=10,          # 最大溢出连接
        pool_pre_ping=True,       # 检测连接有效性
        pool_recycle=3600,        # 1小时回收连接
    )
    
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,   # 提交后不过期对象
        autocommit=False,
        autoflush=False,
    )
    
    logger.info("[Database] Engine and session factory created successfully")
    
except Exception as e:
    logger.error(f"[Database] Failed to initialize: {e}")
    raise

async def get_db():
    """获取数据库会话（依赖注入）"""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"[Database] Session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()