"""Inspect BGP data for R1."""
import asyncio
import sys
import pandas as pd

# Fix Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from olav.tools.suzieq_tool import suzieq_query

async def inspect_r1():
    print("--- Querying BGP table for R1 ---")
    # Get raw rows for R1
    result = await suzieq_query.ainvoke({
        "table": "bgp", 
        "method": "get", 
        "hostname": "R1"
    })
    
    if "data" in result:
        df = pd.DataFrame(result["data"])
        if not df.empty:
            # Select relevant columns to display
            cols = ["namespace", "hostname", "peer", "peerAsn", "state", "timestamp"]
            # Filter cols that actually exist
            display_cols = [c for c in cols if c in df.columns]
            print(df[display_cols].to_string())
        else:
            print("No data found for R1 in bgp table.")
    else:
        print(f"Error: {result}")

if __name__ == "__main__":
    asyncio.run(inspect_r1())
