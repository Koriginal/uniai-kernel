import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.core.llm import completion, embedding
from app.agents.sample import create_sample_agent
from app.core.config import settings

# Mock configuration for testing if no key provided
print(f"DEBUG: DATABASE_URL={settings.DATABASE_URL}")
if not settings.OPENAI_API_KEY:
    print("WARNING: No OPENAI_API_KEY found. Tests may fail or require mock.")
    # For the purpose of this script, we assume the user will configure the key.

async def test_llm_direct():
    print("\n--- Testing Direct LLM Call ---")
    try:
        response = await completion(
            model="gpt-4o-mock",
            messages=[{"role": "user", "content": "Say 'Hello, World!'"}]
        )
        print("Success! Response:", response.choices[0].message.content)
    except Exception as e:
        print("Failed:", e)

async def test_embedding():
    print("\n--- Testing Embedding ---")
    try:
        response = await embedding(
            model="text-embedding-3-small",
            input="Test sentence"
        )
        data = response.get('data', [])
        if data:
            print(f"Success! Vector length: {len(data[0]['embedding'])}")
        else:
            print("Failed: No data returned")
    except Exception as e:
        print("Failed:", e)

async def test_agent_flow():
    print("\n--- Testing Sample Agent Flow ---")
    try:
        agent = create_sample_agent()
        inputs = {"input": "What is 2+2?", "messages": []}
        result = await agent.ainvoke(inputs)
        print("Success! Agent Answer:", result.get("final_answer"))
    except Exception as e:
        print("Failed:", e)

async def main():
    print("Starting Comprehensive Verification...")
    await test_llm_direct()
    await test_embedding()
    await test_agent_flow()

if __name__ == "__main__":
    asyncio.run(main())
