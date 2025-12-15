
import asyncio
import os
import sys

# Add src to path
sys.path.append("src")

async def test_postgres_check():
    print("Testing PostgreSQL connection...")
    try:
        import asyncpg
        # Use localhost port 55432 as mapped in docker-compose
        uri = os.getenv("POSTGRES_URI", "postgresql://olav:OlavPG123!@localhost:55432/olav")
        print(f"Connecting to: {uri}")
        
        conn = await asyncpg.connect(uri, timeout=5)
        try:
            version = await conn.fetchval("SELECT version()")
            print(f"✅ Success! Version: {version}")
        finally:
            await conn.close()
    except Exception as e:
        print(f"❌ Failed: {e}")

async def test_opensearch_check():
    print("\nTesting OpenSearch connection...")
    try:
        import httpx
        url = os.getenv("OPENSEARCH_URL", "http://localhost:19200")
        print(f"Connecting to: {url}")
        
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(f"{url}/_cluster/health")
            if resp.status_code == 200:
                print(f"✅ Success! Status: {resp.json().get('status')}")
            else:
                print(f"❌ Failed: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Failed: {e}")

async def main():
    await test_postgres_check()
    await test_opensearch_check()

if __name__ == "__main__":
    asyncio.run(main())
