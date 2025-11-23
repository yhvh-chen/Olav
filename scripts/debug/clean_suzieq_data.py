"""清理 SuzieQ Parquet 中的测试数据 (192.0.2.2 和 198.51.100.2)。

警告：这会修改 Parquet 文件！运行前已自动备份。
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
import shutil

def clean_test_data():
    """删除测试邻居数据，保留真实设备数据。"""
    parquet_dir = Path("data/suzieq-parquet")
    
    # 查找 BGP 数据目录
    possible_dirs = [
        parquet_dir / "coalesced" / "bgp",
        parquet_dir / "bgp"
    ]
    
    table_dir = None
    for d in possible_dirs:
        if d.exists():
            table_dir = d
            break
    
    if not table_dir:
        print("ERROR: 未找到 BGP parquet 目录")
        return
    
    print(f"=== 清理 {table_dir} ===\n")
    
    # 备份整个目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = parquet_dir / "backup" / f"bgp_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"1. 备份原始数据到: {backup_dir}")
    shutil.copytree(table_dir, backup_dir, dirs_exist_ok=True)
    print(f"   ✅ 备份完成\n")
    
    # 读取所有 parquet 文件
    import pyarrow.dataset as ds
    dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
    df = dataset.to_table().to_pandas()
    
    print(f"2. 读取数据")
    print(f"   总记录数: {len(df)}")
    
    # 查找假数据
    fake_peers = ["192.0.2.2", "198.51.100.2"]
    df_r1 = df[df["hostname"] == "R1"]
    fake_records = df_r1[df_r1["peer"].isin(fake_peers)]
    
    print(f"   R1 BGP 记录: {len(df_r1)}")
    print(f"   假数据记录: {len(fake_records)}\n")
    
    if len(fake_records) > 0:
        print("3. 发现以下假数据:")
        for idx, row in fake_records.iterrows():
            ts = datetime.fromtimestamp(row['timestamp'] / 1000)
            print(f"   - Peer: {row['peer']} | State: {row['state']} | Timestamp: {ts}")
        print()
        
        # 删除假数据
        df_cleaned = df[~((df["hostname"] == "R1") & (df["peer"].isin(fake_peers)))]
        
        print(f"4. 删除假数据")
        print(f"   清理后总记录: {len(df_cleaned)}")
        print(f"   删除记录数: {len(df) - len(df_cleaned)}\n")
        
        # 写回 parquet（覆盖原文件）
        # 注意：这里需要重新创建 Hive 分区结构
        print(f"5. 写入清理后的数据")
        
        # 简化方案：写入单个 parquet 文件
        output_file = table_dir / "cleaned_data.parquet"
        df_cleaned.to_parquet(output_file, index=False)
        print(f"   ✅ 已写入: {output_file}\n")
        
        # 显示清理结果
        df_r1_cleaned = df_cleaned[df_cleaned["hostname"] == "R1"]
        unique_peers = sorted(df_r1_cleaned["peer"].unique())
        
        print(f"6. 验证清理结果")
        print(f"   R1 剩余邻居: {unique_peers}")
        print(f"   实际设备邻居: ['3.3.3.3', '10.1.12.2']")
        
        if set(unique_peers) == {"3.3.3.3", "10.1.12.2"}:
            print(f"   ✅ 匹配成功！\n")
        else:
            print(f"   ⚠️  不匹配，请检查\n")
        
        print("=" * 60)
        print("下一步:")
        print("1. 删除旧的 parquet 文件: rm -Recurse data/suzieq-parquet/bgp/*.parquet")
        print("2. 重命名清理后的文件: mv data/suzieq-parquet/bgp/cleaned_data.parquet data/suzieq-parquet/bgp/data.parquet")
        print("3. 重启 SuzieQ poller 开始采集实时数据")
        print("=" * 60)
    else:
        print("✅ 未发现假数据，无需清理")

if __name__ == "__main__":
    clean_test_data()
