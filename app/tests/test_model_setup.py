import asyncio
import os
from services.openrouter import openrouter


async def test_models():
    print("🚀 Testing Model Setup...")

    # Test 1: Ingestion Model (Grok-4.1-Fast)
    print("\n🧪 Testing Ingestion Model (x-ai/grok-4.1-fast)...")
    try:
        ingestion_response, cost1 = await openrouter.chat_completion(
            "ingestion",
            [
                {
                    "role": "system",
                    "content": "You are a data processor. Convert the input to JSON.",
                },
                {
                    "role": "user",
                    "content": "The 2011 Ford F-150 5.0L takes 7.7 quarts of 5W-20 oil.",
                },
            ],
        )
        print(f"✅ Ingestion Response: {ingestion_response}")
        print(f"💰 Cost: ${cost1}")
    except Exception as e:
        print(f"❌ Ingestion Failed: {e}")

    # Test 2: Orchestrator Model (Gemini 2.5 Flash Lite)
    print("\n🧪 Testing Orchestrator Model (google/gemini-2.5-flash-lite)...")
    try:
        orchestrator_response, cost2 = await openrouter.chat_completion(
            "orchestrator",
            [
                {
                    "role": "system",
                    "content": "You are an expert mechanic. Plan a repair.",
                },
                {
                    "role": "user",
                    "content": "Customer has a P0301 on a 2011 F-150 5.0L. What chunks of info do I need?",
                },
            ],
        )
        print(f"✅ Orchestrator Response: {orchestrator_response}")
        print(f"💰 Cost: ${cost2}")
    except Exception as e:
        print(f"❌ Orchestrator Failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_models())
