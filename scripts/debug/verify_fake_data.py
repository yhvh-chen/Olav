"""Verify the source of the fake BGP peers (192.0.2.2 and 198.51.100.2)."""
import asyncio
import pandas as pd
from pathlib import Path
from datetime import datetime

async def verify_fake_peers():
    # Read ALL parquet data
    parquet_dir = Path("data/suzieq-parquet")
    table_dir = parquet_dir / "coalesced" / "bgp"
    if not table_dir.exists():
        table_dir = parquet_dir / "bgp"
    
    if not table_dir.exists():
        print(f"ERROR: {table_dir} does not exist!")
        return
    
    import pyarrow.dataset as ds
    dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
    df = dataset.to_table().to_pandas()
    
    # Filter to R1
    df_r1 = df[df["hostname"] == "R1"]
    
    print(f"\n=== 分析 R1 的 BGP 数据来源 ===\n")
    print(f"Total R1 BGP records: {len(df_r1)}")
    
    # Check for the fake peers
    fake_peers = df_r1[df_r1["peer"].isin(["192.0.2.2", "198.51.100.2"])]
    
    if len(fake_peers) > 0:
        print(f"\n🚨 发现虚假邻居数据！ ({len(fake_peers)} 条记录)\n")
        for idx, row in fake_peers.iterrows():
            ts = datetime.fromtimestamp(row['timestamp'] / 1000)
            print(f"Peer: {row['peer']}")
            print(f"  Timestamp: {ts} ({row['timestamp']})")
            print(f"  Namespace: {row['namespace']}")
            print(f"  State: {row['state']}")
            print(f"  Active: {row['active']}")
            print(f"  AFI/SAFI: {row['afi']}/{row['safi']}")
            print()
    
    # Show actual valid peers from device output
    print("\n=== 实际设备输出中的邻居 (SSH) ===")
    print("  3.3.3.3 (AS 65000) - Established")
    print("  10.1.12.2 (AS 65001) - Idle")
    
    # Show SuzieQ data for valid peers
    valid_peers = df_r1[df_r1["peer"].isin(["3.3.3.3", "10.1.12.2"])]
    print(f"\n=== SuzieQ 中这些真实邻居的记录数: {len(valid_peers)} ===")
    
    # Check if SuzieQ has current data for these peers
    latest_valid = valid_peers.sort_values("timestamp", ascending=False).drop_duplicates(subset=["peer", "afi", "safi"], keep="first")
    print(f"\n最新去重后的记录:")
    for idx, row in latest_valid.iterrows():
        ts = datetime.fromtimestamp(row['timestamp'] / 1000)
        print(f"  Peer: {row['peer']:15} | State: {row['state']:10} | Active: {row['active']} | Timestamp: {ts}")
    
    # Conclusion
    print("\n=== 结论 ===")
    if len(fake_peers) > 0:
        print("❌ SuzieQ Parquet 文件中包含测试/过期数据 (192.0.2.2, 198.51.100.2)")
        print("   这些邻居从未存在于实际设备中。")
        print("\n可能原因:")
        print("  1. 测试数据污染 (手动创建的示例 Parquet 文件)")
        print("  2. 旧的 SuzieQ poller 数据未清理")
        print("  3. 错误的 namespace 混合")
        print("\n建议:")
        print("  - 清空 data/suzieq-parquet/bgp/ 目录")
        print("  - 重新运行 SuzieQ poller 采集实际设备数据")
        print("  - 或在查询时添加时间过滤 (只查询最近 1 小时的数据)")

if __name__ == "__main__":
    asyncio.run(verify_fake_peers())
