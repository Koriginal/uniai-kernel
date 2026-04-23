import asyncio
import uuid
from sqlalchemy import select

from app.core.db import Base, engine, SessionLocal
from app.models.session import ChatSession


async def verify_session_persistence():
    print("--- 1. Initializing DB schema ---")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_id = str(uuid.uuid4())
    print(f"Generated session id: {session_id}")

    print("--- 2. Creating session row ---")
    async with SessionLocal() as db:
        new_session = ChatSession(
            id=session_id,
            title="Session Persistence Test",
            opening_remarks="Hello System",
        )
        db.add(new_session)
        await db.commit()

    print("--- 3. Reading session row back ---")
    async with SessionLocal() as db:
        res = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        row = res.scalars().first()
        assert row is not None
        assert row.id == session_id
        print(f"Session exists: {row.id}")

    print("Session verification passed.")


if __name__ == "__main__":
    asyncio.run(verify_session_persistence())
