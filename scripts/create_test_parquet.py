"""Create sample Parquet test data for SuzieQ tables."""

import pandas as pd
from pathlib import Path
from datetime import datetime

# Base directory
BASE_DIR = Path(__file__).parent.parent / "data" / "suzieq-parquet"

# Sample BGP data
bgp_data = [
    {
        "namespace": "default",
        "hostname": "R1",
        "vrf": "default",
        "peer": "192.0.2.2",
        "asn": 65001,
        "peerAsn": 65002,
        "state": "Established",
        "peerIP": "192.0.2.2",
        "updateSource": "Loopback0",
        "peerRouterId": "2.2.2.2",
        "bfdStatus": "disabled",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 10,
        "pfxTx": 15,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
    {
        "namespace": "default",
        "hostname": "R1",
        "vrf": "default",
        "peer": "198.51.100.2",
        "asn": 65001,
        "peerAsn": 65003,
        "state": "Idle",
        "peerIP": "198.51.100.2",
        "updateSource": "Loopback0",
        "peerRouterId": "",
        "bfdStatus": "disabled",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 0,
        "pfxTx": 0,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": False,
    },
    {
        "namespace": "default",
        "hostname": "R2",
        "vrf": "default",
        "peer": "192.0.2.1",
        "asn": 65002,
        "peerAsn": 65001,
        "state": "Established",
        "peerIP": "192.0.2.1",
        "updateSource": "Loopback0",
        "peerRouterId": "1.1.1.1",
        "bfdStatus": "disabled",
        "afi": "ipv4",
        "safi": "unicast",
        "pfxRx": 15,
        "pfxTx": 10,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
]

# Sample interfaces data
interfaces_data = [
    {
        "namespace": "default",
        "hostname": "R1",
        "ifname": "GigabitEthernet0/0",
        "state": "up",
        "adminState": "up",
        "type": "ethernet",
        "mtu": 1500,
        "ipAddressList": ["192.0.2.1/30"],
        "ip6AddressList": [],
        "speed": 1000,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
    {
        "namespace": "default",
        "hostname": "R1",
        "ifname": "Loopback0",
        "state": "up",
        "adminState": "up",
        "type": "loopback",
        "mtu": 65536,
        "ipAddressList": ["1.1.1.1/32"],
        "ip6AddressList": [],
        "speed": 0,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
    {
        "namespace": "default",
        "hostname": "R2",
        "ifname": "GigabitEthernet0/0",
        "state": "up",
        "adminState": "up",
        "type": "ethernet",
        "mtu": 1500,
        "ipAddressList": ["192.0.2.2/30"],
        "ip6AddressList": [],
        "speed": 1000,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
]

# Sample routes data
routes_data = [
    {
        "namespace": "default",
        "hostname": "R1",
        "vrf": "default",
        "prefix": "0.0.0.0/0",
        "nexthopIps": ["192.0.2.2"],
        "oifs": ["GigabitEthernet0/0"],
        "protocol": "bgp",
        "preference": 20,
        "metric": 0,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
    {
        "namespace": "default",
        "hostname": "R1",
        "vrf": "default",
        "prefix": "192.0.2.0/30",
        "nexthopIps": [],
        "oifs": ["GigabitEthernet0/0"],
        "protocol": "connected",
        "preference": 0,
        "metric": 0,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "active": True,
    },
]

# Sample sqPoller data
#
# NOTE: The OLAV server /health/detailed endpoint checks freshness using
# data/suzieq-parquet/sqPoller/sqvers=*/namespace=*/hostname=*/*.parquet
# and expects parquet files directly under each hostname directory.
sq_poller_data = [
    {
        "namespace": "default",
        "hostname": "R1",
        "service": "test",
        "status": "success",
        "timestamp": int(datetime.now().timestamp() * 1000),
    }
]


def create_partitioned_parquet(table_name: str, data: list, partition_cols: list):
    """Create partitioned Parquet files for a SuzieQ table.
    
    Args:
        table_name: Table name (bgp, interfaces, routes, etc.)
        data: List of record dicts
        partition_cols: Columns to partition by (e.g., ['namespace', 'hostname'])
    """
    df = pd.DataFrame(data)
    
    # Create table directory
    table_dir = BASE_DIR / table_name / "sqvers=3.0"
    table_dir.mkdir(parents=True, exist_ok=True)
    
    # Write partitioned parquet
    df.to_parquet(
        table_dir,
        engine="pyarrow",
        partition_cols=partition_cols,
        index=False,
    )
    
    print(f"✅ Created {table_name} with {len(data)} records")


def create_sq_poller_parquet(data: list) -> None:
    """Create a minimal sqPoller parquet file for OLAV health checks."""
    df = pd.DataFrame(data)
    table_dir = BASE_DIR / "sqPoller" / "sqvers=3.0" / "namespace=default" / "hostname=R1"
    table_dir.mkdir(parents=True, exist_ok=True)

    # Write a single parquet file directly in the hostname directory
    out_file = table_dir / "sqPoller-0.parquet"
    df.to_parquet(out_file, engine="pyarrow", index=False)
    print(f"✅ Created sqPoller with {len(data)} records")


if __name__ == "__main__":
    print("Creating test Parquet data for SuzieQ...")
    
    # Create BGP table
    create_partitioned_parquet("bgp", bgp_data, ["namespace", "hostname"])
    
    # Create interfaces table
    create_partitioned_parquet("interfaces", interfaces_data, ["namespace", "hostname"])
    
    # Create routes table
    create_partitioned_parquet("routes", routes_data, ["namespace", "hostname"])

    # Create sqPoller table (required by OLAV /health/detailed freshness check)
    create_sq_poller_parquet(sq_poller_data)
    
    print("\n✅ All test data created successfully!")
    print(f"Location: {BASE_DIR}")
