"""Test time-based filtering to exclude fake data."""
import asyncio
from olav.tools.suzieq_parquet_tool import suzieq_query

async def test_time_filter():
    print("\n=== 测试 1: 查询所有历史数据 (max_age_hours=0) ===")
    result_all = await suzieq_query.ainvoke({
        "table": "bgp",
        "hostname": "R1",
        "max_age_hours": 0  # All data
    })
    
    unique_peers_all = set(r['peer'] for r in result_all['data'])
    print(f"Found {result_all['count']} sessions, {len(unique_peers_all)} unique peers:")
    for peer in sorted(unique_peers_all):
        print(f"  - {peer}")
    
    print("\n=== 测试 2: 查询最近 24 小时数据 (max_age_hours=24, default) ===")
    result_24h = await suzieq_query.ainvoke({
        "table": "bgp",
        "hostname": "R1",
        "max_age_hours": 24
    })
    
    unique_peers_24h = set(r['peer'] for r in result_24h['data'])
    print(f"Found {result_24h['count']} sessions, {len(unique_peers_24h)} unique peers:")
    for peer in sorted(unique_peers_24h):
        print(f"  - {peer}")
    
    print("\n=== 测试 3: 查询最近 12 小时数据 (max_age_hours=12) ===")
    result_12h = await suzieq_query.ainvoke({
        "table": "bgp",
        "hostname": "R1",
        "max_age_hours": 12
    })
    
    unique_peers_12h = set(r['peer'] for r in result_12h['data'])
    print(f"Found {result_12h['count']} sessions, {len(unique_peers_12h)} unique peers:")
    for peer in sorted(unique_peers_12h):
        print(f"  - {peer}")
    
    print("\n=== 结论 ===")
    if "192.0.2.2" in unique_peers_24h or "198.51.100.2" in unique_peers_24h:
        print("❌ 24小时过滤不足以排除假数据 (数据是昨晚 20:52 插入的，仍在 24 小时内)")
        print("   建议使用 12 小时窗口或清理 Parquet 文件")
    else:
        print("✅ 24小时过滤成功排除假数据")
    
    if "192.0.2.2" not in unique_peers_12h and "198.51.100.2" not in unique_peers_12h:
        print("✅ 12小时过滤成功排除假数据")
    
    print("\n实际设备邻居 (SSH): 3.3.3.3, 10.1.12.2")
    if unique_peers_12h == {"3.3.3.3", "10.1.12.2"}:
        print("✅ 过滤后的数据与设备实际输出完全匹配！")
    else:
        print(f"⚠️  过滤后的数据: {unique_peers_12h}")
        print(f"   与设备输出不匹配，需要进一步调查")

if __name__ == "__main__":
    asyncio.run(test_time_filter())
