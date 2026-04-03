import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import Base
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from app.models.agent import AgentProfile
from sqlalchemy import select
import os

# 1. 尝试连接数据库 (如果 .env 设置了 ENABLE_DATABASE=True)
DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL is not set. Please check your .env")
    exit(1)

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_demo_data():
    async with engine.begin() as conn:
        print("🔧 Ensuring tables exist...")
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        print("🌱 Checking and Seeding data...")
        
        # 1. 创建/获取供应商模板
        result = await db.execute(select(ProviderTemplate).where(ProviderTemplate.name == "qwen"))
        aliyun_template = result.scalar_one_or_none()
        
        if not aliyun_template:
            print("  + Creating qwen template...")
            aliyun_template = ProviderTemplate(
                name="qwen",
                provider_type="qwen",
                api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                supported_models=["qwen-flash", "qwen-plus", "qwen-max"]
            )
            db.add(aliyun_template)
            await db.flush()
        else:
            print("  - qwen template already exists.")

        # 2. 创建/获取用户供应商凭证
        user_id = "local_dev"
        result = await db.execute(
            select(UserProvider).where(UserProvider.user_id == user_id, UserProvider.template_id == aliyun_template.id)
        )
        user_provider = result.scalar_one_or_none()
        
        if not user_provider:
            print(f"  + Creating provider for {user_id}...")
            user_provider = UserProvider(
                user_id=user_id,
                template_id=aliyun_template.id,
                api_key_encrypted=settings.DEFAULT_LLM_API_KEY,
            )
            db.add(user_provider)
            await db.flush()
        else:
            print(f"  - provider for {user_id} already exists.")

        # 3. 创建/获取模型配置
        result = await db.execute(
            select(UserModelConfig).where(UserModelConfig.user_id == user_id, UserModelConfig.model_type == "llm")
        )
        qwen_config = result.scalar_one_or_none()
        
        if not qwen_config:
            print(f"  + Setting default LLM config for {user_id}...")
            qwen_config = UserModelConfig(
                user_id=user_id,
                model_type="llm",
                default_model_name="qwen-flash",
                provider_id=user_provider.id
            )
            db.add(qwen_config)
            await db.flush()
        else:
            print(f"  - LLM config for {user_id} already exists.")

        # 4. 创建/更新智能体 Profiles
        agents_data = [
            {
                "id": "agent-translator",
                "name": "中英即时翻译官",
                "description": "专门负责将中文翻译成优雅、地道的英文。",
                "system_prompt": "你是一个顶级翻译官。请将用户的所有输入翻译成地道的英文，不要回答其他多余内容。",
                "tools": []
            },
            {
                "id": "agent-researcher",
                "name": "UniAI 联网研究员",
                "description": "具备搜索互联网能力的智能研究助手。",
                "system_prompt": "你是一个专业的调查员。请充分利用搜索工具回答用户的问题，并给出可靠的分析。",
                "tools": ["web_search"]
            }
        ]
        
        for data in agents_data:
            result = await db.execute(select(AgentProfile).where(AgentProfile.id == data["id"]))
            agent = result.scalar_one_or_none()
            
            if not agent:
                print(f"  + Creating agent: {data['id']}...")
                agent = AgentProfile(
                    id=data["id"],
                    user_id=user_id,
                    name=data["name"],
                    description=data["description"],
                    model_config_id=qwen_config.id,
                    system_prompt=data["system_prompt"],
                    tools=data["tools"]
                )
                db.add(agent)
            else:
                print(f"  - agent {data['id']} already exists.")
        
        await db.commit()
        print("✅ Demo Data synchronization complete!")
        print("\nAPI IDs available:")
        print("1. agent-translator")
        print("2. agent-researcher")

if __name__ == "__main__":
    asyncio.run(init_demo_data())
