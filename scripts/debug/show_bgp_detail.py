"""Show detailed BGP data with address families."""
import asyncio
from olav.tools.suzieq_parquet_tool import suzieq_query

async def show_detailed_bgp():
    result = await suzieq_query.ainvoke({"table": "bgp", "hostname": "R1"})
    
    print(f"\n=== Unique BGP Sessions: {result['count']} ===")
    print(f"Data Type: {result.get('data_type')}")
    print(f"Note: {result.get('note')}\n")
    
    for record in result['data']:
        print(f"Peer: {record['peer']:15} | AFI/SAFI: {record['afi']:6}/{record['safi']:15} | State: {record['state']:10} | AS: {record['peerAsn']}")

if __name__ == "__main__":
    asyncio.run(show_detailed_bgp())
