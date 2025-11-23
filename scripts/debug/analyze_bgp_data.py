"""Analyze the BGP data to understand what SuzieQ is showing."""
import asyncio
from olav.tools.suzieq_parquet_tool import suzieq_query

async def analyze_bgp():
    result = await suzieq_query.ainvoke({"table": "bgp", "hostname": "R1"})
    
    print(f"\n=== Total BGP Sessions (including historical): {result['count']} ===\n")
    
    # Count active vs inactive
    active = [r for r in result['data'] if r.get('active')]
    inactive = [r for r in result['data'] if not r.get('active')]
    
    print(f"Active sessions: {len(active)}")
    print(f"Inactive (historical) sessions: {len(inactive)}\n")
    
    # Group by state
    states = {}
    for record in result['data']:
        state = record.get('state', 'Unknown')
        states[state] = states.get(state, 0) + 1
    
    print("Sessions by state:")
    for state, count in states.items():
        print(f"  {state}: {count}")
    
    # Show active sessions only
    print("\n=== CURRENTLY ACTIVE BGP SESSIONS ===")
    for record in active:
        print(f"  Peer: {record['peer']} | State: {record['state']} | ASN: {record['peerAsn']} | Active: {record['active']}")

if __name__ == "__main__":
    asyncio.run(analyze_bgp())
