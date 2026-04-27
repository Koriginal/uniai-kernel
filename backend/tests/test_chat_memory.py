"""
端到端测试脚本：智能对话 + 记忆管理

测试流程：
1. 创建会话
2. 进行多轮对话
3. 验证记忆提取
4. 验证会话压缩
5. 验证记忆召回
"""
import asyncio
import uuid
import pytest
from app.core.db import Base, engine, SessionLocal
from app.models.session import ChatSession
from app.models.message import ChatMessage
from app.services.memory_service import memory_service
from app.services.context_service import context_service
from sqlalchemy import select

@pytest.mark.asyncio
async def test_end_to_end():
    print("=" * 60)
    print("端到端测试：智能对话与记忆管理")
    print("=" * 60)
    
    # 1. 初始化数据库
    print("\n[1/6] 初始化数据库...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"Integration DB is not available for test_chat_memory: {exc}")
    
    session_id = str(uuid.uuid4())
    user_id = "test_user_001"
    
    # 2. 创建会话
    print(f"\n[2/6] 创建会话 (ID: {session_id})")
    async with SessionLocal() as db:
        new_session = ChatSession(
            id=session_id,
            title="测试会话：智能对话",
            opening_remarks="你是一个有用的 AI 助手。"
        )
        db.add(new_session)
        await db.commit()
        print("✅ 会话创建成功")
    
    # 3. 模拟对话并提取记忆
    print(f"\n[3/6] 模拟对话...")
    conversations = [
        ("我是一名 Python 开发者", "很高兴认识你！"),
        ("我喜欢简洁的代码风格", "我会记住你的偏好"),
        ("我正在开发一个 AI 应用", "听起来很有趣！")
    ]
    
    async with SessionLocal() as db:
        for i, (user_q, ai_a) in enumerate(conversations, 1):
            print(f"\n  对话 {i}:")
            print(f"    User: {user_q}")
            print(f"    AI: {ai_a}")
            
            # 保存消息
            user_msg = ChatMessage(
                session_id=session_id,
                role="user",
                content=user_q,
                user_id=user_id
            )
            ai_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=ai_a,
                user_id=user_id
            )
            db.add(user_msg)
            db.add(ai_msg)
            await db.commit()
            
            # 提取记忆
            print(f"    提取记忆中...")
            memories = await memory_service.extract_memories(
                db, user_id, user_q, ai_a
            )
            if memories:
                print(f"    ✅ 提取了 {len(memories)} 条记忆:")
                for m in memories:
                    print(f"      - [{m.category}] {m.content}")
            else:
                print(f"    ℹ️  未提取到新记忆")
    
    # 4. 验证记忆召回
    print(f"\n[4/6] 验证记忆召回...")
    results = await memory_service.search_memories(
        user_id, "用户的编程习惯", top_k=3
    )
    if results:
        print(f"✅ 召回了 {len(results)} 条相关记忆:")
        for r in results:
            print(f"  - [{r['category']}] {r['content']} (相似度: {r['similarity']})")
    else:
        print("ℹ️  未召回到记忆")
    
    # 5. 验证消息历史加载
    print(f"\n[5/6] 验证消息历史加载...")
    async with SessionLocal() as db:
        messages = await context_service.build_context_messages(
            session_id, user_id, "帮我写个 Python 函数",
            db, enable_memory=True, enable_session_context=True
        )
        print(f"✅ 构建了 {len(messages)} 条上下文消息:")
        for msg in messages:
            content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
            print(f"  - [{msg['role']}] {content_preview}")
    
    # 6. 验证会话压缩（需要足够多的消息）
    print(f"\n[6/6] 验证会话压缩...")
    async with SessionLocal() as db:
        # 添加更多消息以触发压缩
        for i in range(15):
            msg = ChatMessage(
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"测试消息 {i}",
                user_id=user_id
            )
            db.add(msg)
        await db.commit()
        
        # 执行压缩
        summary = await context_service.compress_session(session_id, db)
        if summary:
            print(f"✅ 会话已压缩，摘要:")
            print(f"  {summary[:100]}...")
        else:
            print("ℹ️  会话未触发压缩（消息数不足）")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(test_end_to_end())
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
