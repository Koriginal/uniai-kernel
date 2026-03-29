import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.provider_manager import provider_manager, Provider
from app.core.config import settings

# Adjust path to include app
sys.path.append(os.getcwd())

async def verify_provider_workflow():
    print("--- Starting Provider Management Verification ---")
    
    # 1. Setup DB Connection
    # 1. Setup DB Connection
    database_url = settings.DATABASE_URL
    print(f"DEBUG: Using DB URL: {database_url}")
    engine = create_async_engine(database_url)
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession)
    
    async with AsyncSessionLocal() as session:
        # 2. Add a Mock Provider
        print("Adding Mock Provider...")
        try:
            provider = await provider_manager.add_provider(
                session,
                name="mock_openai",
                type="openai",
                api_base="https://api.openai.com/v1",
                api_key="sk-mock-key-123",
                extra_config={"description": "Test Provider"}
            )
            print(f"✅ Provider added: {provider.provider_name} (ID: {provider.id})")
        except Exception as e:
            if "unique constraint" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️  Provider already exists, fetching existing...")
                await session.rollback()
                from sqlalchemy import select
                result = await session.execute(select(Provider).where(Provider.provider_name == "mock_openai"))
                provider = result.scalars().first()
            else:
                print(f"❌ Failed to add provider: {e}")
                return

        # 3. Add a Model to this Provider
        print("Adding Mock Model...")
        try:
            # Re-fetch provider ID if needed, but we have it from above object usually
            # Check if model exists
            model = await provider_manager.add_model(
                session,
                name="gpt-4o-mock",
                provider_id=provider.id,
                type="llm",
                context_window=128000
            )
            print(f"✅ Model added: {model.model_name}")
        except Exception as e:
             if "unique constraint" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️  Model already exists.")
                await session.rollback()
             else:
                print(f"❌ Failed to add model: {e}")

        # 4. Verify Decryption
        print("Verifying Key Decryption...")
        await session.refresh(provider)
        decrypted_key = provider_manager.decrypt_key(provider.api_key_encrypted)
        if decrypted_key == "sk-mock-key-123":
            print("✅ Key Decryption Successful")
        else:
            print(f"❌ Key Decryption Failed: {decrypted_key}")

        # 5. List Active Providers
        print("Listing Active Providers...")
        providers = await provider_manager.get_active_providers(session)
        print(f"Found {len(providers)} active providers.")
        for p in providers:
            print(f" - {p.provider_name} ({p.provider_type})")

    print("--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify_provider_workflow())
