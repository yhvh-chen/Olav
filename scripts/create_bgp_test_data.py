"""Create BGP test parquet data for OLAV testing.

This script generates realistic BGP neighbor data for R1, R2, R3, R4
matching the SuzieQ schema format.

Usage:
    uv run python scripts/create_bgp_test_data.py
"""

import pandas as pd
import time
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
PARQUET_DIR = PROJECT_ROOT / "data" / "suzieq-parquet"

# Current timestamp in milliseconds
current_ts = int(time.time() * 1000)

# BGP neighbor data matching SuzieQ schema
# Based on typical Cisco IOS-XE BGP neighbor output
bgp_data = [
    # R1 neighbors
    {
        "hostname": "R1",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.12.2",
        "peerHostname": "R2",
        "peerAsn": 65002,
        "asn": 65001,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 5,
        "pfxTx": 3,
        "estdTime": current_ts - 86400000,  # 1 day ago
        "updateSource": "10.1.12.1",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "1.1.1.1",
        "peerRouterId": "2.2.2.2",
        "numChanges": 1,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    {
        "hostname": "R1",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.13.3",
        "peerHostname": "R3",
        "peerAsn": 65003,
        "asn": 65001,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 4,
        "pfxTx": 3,
        "estdTime": current_ts - 86400000,
        "updateSource": "10.1.13.1",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "1.1.1.1",
        "peerRouterId": "3.3.3.3",
        "numChanges": 2,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    # R2 neighbors
    {
        "hostname": "R2",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.12.1",
        "peerHostname": "R1",
        "peerAsn": 65001,
        "asn": 65002,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 3,
        "pfxTx": 5,
        "estdTime": current_ts - 86400000,
        "updateSource": "10.1.12.2",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "2.2.2.2",
        "peerRouterId": "1.1.1.1",
        "numChanges": 1,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    {
        "hostname": "R2",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.24.4",
        "peerHostname": "R4",
        "peerAsn": 65004,
        "asn": 65002,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 2,
        "pfxTx": 6,
        "estdTime": current_ts - 43200000,  # 12 hours ago
        "updateSource": "10.1.24.2",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "2.2.2.2",
        "peerRouterId": "4.4.4.4",
        "numChanges": 3,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    # R3 neighbors
    {
        "hostname": "R3",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.13.1",
        "peerHostname": "R1",
        "peerAsn": 65001,
        "asn": 65003,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 3,
        "pfxTx": 4,
        "estdTime": current_ts - 86400000,
        "updateSource": "10.1.13.3",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "3.3.3.3",
        "peerRouterId": "1.1.1.1",
        "numChanges": 2,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    {
        "hostname": "R3",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.34.4",
        "peerHostname": "R4",
        "peerAsn": 65004,
        "asn": 65003,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 2,
        "pfxTx": 4,
        "estdTime": current_ts - 43200000,
        "updateSource": "10.1.34.3",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "3.3.3.3",
        "peerRouterId": "4.4.4.4",
        "numChanges": 1,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    # R4 neighbors
    {
        "hostname": "R4",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.24.2",
        "peerHostname": "R2",
        "peerAsn": 65002,
        "asn": 65004,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 6,
        "pfxTx": 2,
        "estdTime": current_ts - 43200000,
        "updateSource": "10.1.24.4",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "4.4.4.4",
        "peerRouterId": "2.2.2.2",
        "numChanges": 3,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
    {
        "hostname": "R4",
        "namespace": "default",
        "vrf": "default",
        "peer": "10.1.34.3",
        "peerHostname": "R3",
        "peerAsn": 65003,
        "asn": 65004,
        "state": "Established",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 4,
        "pfxTx": 2,
        "estdTime": current_ts - 43200000,
        "updateSource": "10.1.34.4",
        "bfdStatus": "disabled",
        "holdTime": 180,
        "keepaliveTime": 60,
        "reason": "",
        "notificnReason": "",
        "routerId": "4.4.4.4",
        "peerRouterId": "3.3.3.3",
        "numChanges": 1,
        "timestamp": current_ts,
        "active": True,
        "sqvers": "3.0",
    },
]

def main():
    """Create BGP parquet files."""
    # Create DataFrame
    df = pd.DataFrame(bgp_data)
    
    # Ensure correct types
    df["timestamp"] = df["timestamp"].astype("int64")
    df["estdTime"] = df["estdTime"].astype("int64")
    df["pfxRx"] = df["pfxRx"].astype("int64")
    df["pfxTx"] = df["pfxTx"].astype("int64")
    df["asn"] = df["asn"].astype("int64")
    df["peerAsn"] = df["peerAsn"].astype("int64")
    df["holdTime"] = df["holdTime"].astype("int64")
    df["keepaliveTime"] = df["keepaliveTime"].astype("int64")
    df["numChanges"] = df["numChanges"].astype("int64")
    
    # Save to coalesced directory (preferred by SuzieQ tool)
    output_dir = PARQUET_DIR / "coalesced" / "bgp"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "bgp_data.parquet"
    df.to_parquet(output_file, index=False)
    
    print(f"✅ Created BGP test data: {output_file}")
    print(f"   Records: {len(df)}")
    print(f"   Devices: {df['hostname'].unique().tolist()}")
    print(f"   Columns: {df.columns.tolist()}")
    
    # Verify
    verify_df = pd.read_parquet(output_file)
    print(f"\n📋 Verification:")
    print(verify_df[["hostname", "peer", "peerHostname", "state", "asn", "peerAsn"]].to_string())

if __name__ == "__main__":
    main()
