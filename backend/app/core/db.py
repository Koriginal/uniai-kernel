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

class DummyResult:
    def scalar_one_or_none(self): return None
    def scalars(self): return self
    def all(self): return []

class DummyAsyncSession:
    """黑洞会话：无状态模式下吃掉所有对象存储级的报错，充当无害化的桩(Stub)"""
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): pass
    def add(self, *args, **kwargs): pass
    async def commit(self): pass
    async def flush(self): pass
    async def refresh(self, *args, **kwargs): pass
    async def rollback(self): pass
    async def close(self): pass
    async def execute(self, *args, **kwargs): return DummyResult()
    def begin(self): return self

# 创建引擎（带连接池配置）
engine = None
SessionLocal = None

try:
    if settings.ENABLE_DATABASE:
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
    else:
        logger.warning("[Database] ENABLE_DATABASE=False. Running in Stateless Microkernel mode (No DB connection).")
        SessionLocal = DummyAsyncSession
    
except Exception as e:
    logger.error(f"[Database] Failed to initialize: {e}")
    raise

async def get_db():
    """获取数据库会话（依赖注入）"""
    if not SessionLocal:
        # Fallback to dummy if uninitialized
        yield DummyAsyncSession()
        return
        
    async with SessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"[Database] Session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()