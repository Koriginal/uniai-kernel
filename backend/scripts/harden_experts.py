import asyncio
from sqlalchemy import select, update
from app.core.db import SessionLocal
from app.models.agent import AgentProfile

async def harden_translator_persona():
    async with SessionLocal() as db:
        new_prompt = (
            "你是一个顶级的文学与技术翻译专家。你的职责是直接交付高质量的译文。\n"
            "【执行准则】\n"
            "1. 当用户请求翻译某个作品、段落或词汇时，请直接输出该作品的内容翻译。\n"
            "2. 严禁仅仅翻译用户的请求语句。例如：用户说“翻译岳阳楼记”，你应该直接输出其英文译文内容，而不是翻译“帮我翻译...”这句话。\n"
            "3. 保持译文的地道、信雅达。不要包含任何多余的解释、确认信息或开场白。\n"
            "4. 如果用户没有提供具体内容，仅提供了一个名称（如“岳阳楼记”），请利用你的知识库输出该名篇的公认标准译文。"
        )
        
        stmt = update(AgentProfile).where(AgentProfile.id == 'agent-translator').values(system_prompt=new_prompt)
        await db.execute(stmt)
        await db.commit()
        print("Successfully hardened agent-translator persona.")

if __name__ == "__main__":
    asyncio.run(harden_translator_persona())
