"""Clean fake BGP data from SuzieQ Parquet files."""
import pandas as pd
from pathlib import Path
from datetime import datetime

def clean_fake_bgp_data():
    """Remove test/fake BGP peer data from Parquet files."""
    parquet_dir = Path("data/suzieq-parquet")
    table_dir = parquet_dir / "coalesced" / "bgp"
    if not table_dir.exists():
        table_dir = parquet_dir / "bgp"
    
    if not table_dir.exists():
        print(f"ERROR: {table_dir} does not exist!")
        return
    
    # Read all parquet files
    import pyarrow.dataset as ds
    dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
    df = dataset.to_table().to_pandas()
    
    print(f"\n=== 清理前 ===")
    print(f"Total records: {len(df)}")
    
    # Filter to R1
    df_r1 = df[df["hostname"] == "R1"]
    print(f"R1 BGP records: {len(df_r1)}")
    
    # Define fake peers (from user's device output, these don't exist)
    fake_peers = ["192.0.2.2", "198.51.100.2"]
    
    fake_count = len(df_r1[df_r1["peer"].isin(fake_peers)])
    print(f"Fake peer records to remove: {fake_count}")
    
    # Remove fake peers
    df_cleaned = df[~((df["hostname"] == "R1") & (df["peer"].isin(fake_peers)))]
    
    print(f"\n=== 清理后 ===")
    print(f"Total records: {len(df_cleaned)}")
    print(f"R1 BGP records: {len(df_cleaned[df_cleaned['hostname'] == 'R1'])}")
    print(f"Removed: {len(df) - len(df_cleaned)} records")
    
    # Backup original data
    backup_dir = parquet_dir / "backup"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"bgp_backup_{timestamp}.parquet"
    
    print(f"\n=== 备份原始数据 ===")
    print(f"Backup location: {backup_file}")
    df.to_parquet(backup_file, index=False)
    
    # Overwrite cleaned data
    print(f"\n=== 写入清理后的数据 ===")
    print(f"Warning: This will overwrite {table_dir}")
    print(f"\n如果要执行清理，请取消注释下面的代码：")
    print(f"# df_cleaned.to_parquet(table_dir / 'cleaned.parquet', index=False)")
    
    # Show what remains for R1
    print(f"\n=== 清理后 R1 的唯一邻居 ===")
    df_r1_cleaned = df_cleaned[df_cleaned["hostname"] == "R1"]
    unique_peers = df_r1_cleaned["peer"].unique()
    for peer in sorted(unique_peers):
        peer_data = df_r1_cleaned[df_r1_cleaned["peer"] == peer]
        states = peer_data["state"].unique()
        print(f"  {peer}: {', '.join(states)}")

if __name__ == "__main__":
    clean_fake_bgp_data()
