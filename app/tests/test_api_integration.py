import httpx
import json
import time
import sys
import asyncio


async def test_generate_chunks():
    url = "http://localhost:8000/api/generate-chunks"

    payload = {
        "year": "2011",
        "make": "Ford",
        "model": "F-150",
        "engine": "5.0L",
        "concern": "Overheating while towing uphill",
        "dtc_codes": [],
    }

    print(f"🚀 Sending request to {url}...")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload)
        end_time = time.time()

        print(f"\n⏱️ Response time: {end_time - start_time:.2f}s")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("\n✅ Success!")
            print(f"Chunks Found: {data.get('chunks_found')}")
            print(f"Chunks Generated: {data.get('chunks_generated')}")
            print(f"Total Cost: ${data.get('total_cost')}")

            chunks = data.get("chunks", [])
            print(f"\n📦 Returned {len(chunks)} chunks:")
            for i, chunk in enumerate(chunks):
                print(f"  {i+1}. [{chunk.get('chunk_type')}] {chunk.get('title')}")
                print(f"     Badge: {chunk.get('consensus_badge')}")
                print(f"     Score: {chunk.get('consensus_score')}")
        else:
            print(f"\n❌ Error: {response.text}")

    except httpx.ConnectError:
        print("\n❌ Could not connect to localhost:8000. Is the backend running?")
        sys.exit(1)
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"\n❌ Exception: {repr(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_generate_chunks())
