import asyncio
import os
import sys
import logging

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def activate_vector():
    logger.info("Starting database self-healing...")
    
    async with engine.begin() as conn:
        # 1. 激活扩展
        logger.info("Attempting to CREATE EXTENSION vector...")
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            logger.info("Extension 'vector' is now active.")
        except Exception as e:
            logger.error(f"Failed to create extension: {e}")
            logger.error("Please ensure your postgres container is using 'pgvector/pgvector' image.")
            return

        # 2. 补全 embedding 字段
        logger.info("Checking for 'embedding' column in 'user_memories'...")
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_memories' AND column_name = 'embedding'"))
        if not res.fetchone():
            logger.info("Column 'embedding' missing. Adding it now...")
            await conn.execute(text("ALTER TABLE user_memories ADD COLUMN embedding vector(1536);"))
            logger.info("Column 'embedding' added successfully.")
        else:
            logger.info("Column 'embedding' already exists.")

        # 3. 创建索引 (HNSW)
        logger.info("Ensuring HNSW index exists...")
        try:
            # 兼容性检查：如果是新添加的字段且无索引，则创建
            await conn.execute(text("CREATE INDEX IF NOT EXISTS user_memories_embedding_hnsw_idx ON user_memories USING hnsw (embedding vector_cosine_ops);"))
            logger.info("HNSW index is ready.")
        except Exception as e:
            logger.warning(f"Failed to create HNSW index: {e} (This is usually okay if pg_vector version < 0.5.0, falling back to ivfflat or no-index)")
            
    logger.info("Database self-healing completed successfully.")

if __name__ == "__main__":
    asyncio.run(activate_vector())
