"""Check for the missing peer 198.51.100.2 in all data (including inactive)."""
import asyncio
import pandas as pd
from pathlib import Path

async def find_missing_peer():
    # Read ALL parquet data (bypass the tool's active filter)
    parquet_dir = Path("data/suzieq-parquet")
    table_dir = parquet_dir / "coalesced" / "bgp"
    if not table_dir.exists():
        table_dir = parquet_dir / "bgp"
    
    import pyarrow.dataset as ds
    dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
    df = dataset.to_table().to_pandas()
    
    # Filter to R1
    df_r1 = df[df["hostname"] == "R1"]
    
    # Check for 198.51.100.2
    peer_198 = df_r1[df_r1["peer"] == "198.51.100.2"]
    
    print(f"\n=== Looking for peer 198.51.100.2 in ALL data ===\n")
    print(f"Total R1 BGP records: {len(df_r1)}")
    print(f"Records for 198.51.100.2: {len(peer_198)}")
    
    if len(peer_198) > 0:
        print(f"\nFound 198.51.100.2! Details:")
        for idx, row in peer_198.iterrows():
            print(f"  State: {row['state']} | Active: {row['active']} | Timestamp: {row['timestamp']}")
    else:
        print(f"\n198.51.100.2 NOT FOUND in SuzieQ data (SuzieQ has not collected this peer yet)")
    
    # Show what unique peers SuzieQ has (including inactive)
    print(f"\n=== All unique peers in SuzieQ (including inactive) ===")
    unique_all = df_r1.groupby('peer').agg({
        'active': lambda x: any(x),  # Any active record?
        'state': lambda x: list(set(x)),  # Unique states
    })
    for peer, row in unique_all.iterrows():
        print(f"  {peer}: Active={row['active']} | States={row['state']}")

if __name__ == "__main__":
    asyncio.run(find_missing_peer())
