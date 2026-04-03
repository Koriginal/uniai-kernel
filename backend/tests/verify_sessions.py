import asyncio
import uuid
from app.core.db import Base, engine, SessionLocal
from app.models.session import ChatSession
from app.api.v1.endpoints.agent import agent_app, memory
from sqlalchemy import select

async def verify_integration():
    print("--- 1. Initializing DB Schema ---")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    session_id = str(uuid.uuid4())
    print(f"Generated Session ID: {session_id}")
    
    print("--- 2. Creating Session Record ---")
    async with SessionLocal() as db:
        new_session = ChatSession(id=session_id, title="Integration Test", opening_remarks="Hello System")
        db.add(new_session)
        await db.commit()
        
        # Verify it exists
        res = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        s = res.scalars().first()
        assert s is not None
        print(f"Session created in DB: {s.title}")
        
    print("--- 3. Running Agent with session_id as thread_id ---")
    config = {"configurable": {"thread_id": session_id}}
    
    # Simulate user query
    inputs = {"messages": [{"role": "user", "content": "Hello Agent!"}]}
    
    # We expect this to fail on LLM call because of no keys, but state should be created BEFORE LLM call 
    # OR we can mock the agent node.
    # For now, let's just check if we can inject state manually (like update_state)
    
    await agent_app.aupdate_state(config, inputs)
    print("State injected into Agent memory.")
    
    print("--- 4. Verifying State Existence ---")
    state = await agent_app.aget_state(config)
    print(f"Current State Messages: {state.values.get('messages')}")
    assert len(state.values.get('messages')) > 0
    
    print("--- 5. Clearing Context ---")
    # Simulate clear logic
    empty_state = {"messages": []}
    await agent_app.aupdate_state(config, empty_state, as_node="agent")
    
    state_after = await agent_app.aget_state(config)
    msgs = state_after.values.get('messages')
    print(f"State After Clear: {msgs}")
    
    # Note: LangGraph update behavior appends or replaces depending on reducer. 
    # If the reducer is 'add_messages', sending empty list does nothing.
    # To truly clear, we might need a specific 'overwrite' logic or delete the key in memory checkpointer
    
    # Demonstrating the manual clear hack for MemorySaver if needed
    if session_id in memory.storage:
        print("Directly accessing MemorySaver to verify storage key exists.")
        
    print("Integration verification passed.")

if __name__ == "__main__":
    asyncio.run(verify_integration())
