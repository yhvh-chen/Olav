"""Test suzieq_parquet_tool.py to verify NO_DATA_FOUND return value."""
import asyncio
from olav.tools.suzieq_parquet_tool import suzieq_query

async def test_no_data():
    # LangChain tools need to be invoked via .ainvoke() or .arun()
    result = await suzieq_query.ainvoke({"table": "bgp", "hostname": "R1"})
    print("\n=== Tool Output ===")
    print(result)
    print("\n=== Validation ===")
    print(f"count: {result.get('count')}")
    print(f"status in data[0]: {result.get('data', [{}])[0].get('status')}")
    print(f"warning present: {'warning' in result.get('data', [{}])[0]}")

if __name__ == "__main__":
    asyncio.run(test_no_data())
