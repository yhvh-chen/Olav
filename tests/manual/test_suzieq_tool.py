"""Verify SuzieQ tool functionality."""
import asyncio
import sys
import os

# Fix Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from olav.tools.suzieq_tool import suzieq_query, suzieq_schema_search

async def test():
    print("--- Testing Schema Search ---")
    schema = await suzieq_schema_search.ainvoke("bgp")
    print(f"Schema result keys: {schema.keys()}")
    
    print("\n--- Testing Query (Summarize) ---")
    summary = await suzieq_query.ainvoke({"table": "bgp", "method": "summarize"})
    print(f"Summary result: {summary}")
    
    print("\n--- Testing Query (Get) ---")
    data = await suzieq_query.ainvoke({"table": "bgp", "method": "get"})
    if "data" in data:
        print(f"Got {len(data['data'])} rows")
        if len(data['data']) > 0:
            print(f"First row sample: {data['data'][0]}")
    else:
        print(f"Error or no data: {data}")

if __name__ == "__main__":
    asyncio.run(test())
