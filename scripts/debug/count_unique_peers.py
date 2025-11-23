"""Count unique BGP peers (not sessions)."""
import asyncio
from olav.tools.suzieq_parquet_tool import suzieq_query

async def count_unique_peers():
    result = await suzieq_query.ainvoke({"table": "bgp", "hostname": "R1"})
    
    # Get unique peers
    unique_peers = set()
    peers_by_state = {}
    
    for record in result['data']:
        peer = record['peer']
        state = record['state']
        unique_peers.add(peer)
        
        if peer not in peers_by_state:
            peers_by_state[peer] = set()
        peers_by_state[peer].add(state)
    
    print(f"\n=== Unique BGP Peers: {len(unique_peers)} ===\n")
    
    for peer in sorted(unique_peers):
        states = peers_by_state[peer]
        print(f"  {peer}: {', '.join(states)}")
    
    print(f"\n详细说明:")
    print(f"  - SuzieQ 数据显示了 {result['count']} 个唯一 BGP 会话 (按 peer+AFI/SAFI 去重)")
    print(f"  - 实际唯一邻居 IP 地址: {len(unique_peers)} 个")
    print(f"  - 这是正常的，因为同一个邻居可以建立多个会话 (不同地址族)")

if __name__ == "__main__":
    asyncio.run(count_unique_peers())
