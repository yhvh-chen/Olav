"""Topology discovery and query tools.

This module provides tools for discovering network topology through
L1 (CDP/LLDP) and L3 (OSPF/BGP) protocols, storing results in DuckDB,
and querying topology information.
"""

import json
from datetime import datetime
from typing import Any, Protocol

import duckdb
from langchain_core.tools import tool

from olav.core.database import get_database, init_topology_db
from olav.tools.network_executor import get_executor
from olav.tools.topology_graph import TopologyGraph


class NetworkExecutor(Protocol):
    """Protocol for network executor."""

    def execute(self, device: str, command: str, timeout: int = 30) -> object:
        """Execute command on device."""
        ...


class CapabilityDatabase(Protocol):
    """Protocol for capability database."""

    def search_capabilities(
        self, query: str, platform: str | None = None, limit: int = 10
    ) -> list[dict[str, str]]:
        """Search for capabilities."""
        ...


@tool
def discover_topology(devices: str | None = None) -> str:
    """Discover network topology and store in database.

    This function discovers L1 (CDP/LLDP) and L3 (OSPF/BGP) neighbor
    relationships for network devices and stores them in the topology database.

    Args:
        devices: Comma-separated device names, or None for all devices

    Returns:
        Discovery results summary

    Examples:
        >>> discover_topology()
        "Discovered topology: 5 devices, 12 links"

        >>> discover_topology("R1,R2,R3")
        "Discovered topology: 3 devices, 6 links"
    """
    from olav.tools.network import get_nornir

    # Initialize topology database
    conn = init_topology_db()
    db = get_database()

    # Get device list
    device_list: list[str] = []
    if devices:
        device_list = [d.strip() for d in devices.split(",")]
    else:
        # Get all devices from Nornir
        nr = get_nornir()
        device_list = list(nr.inventory.hosts.keys())

    if not device_list:
        return "No devices found for topology discovery."

    executor = get_executor()
    devices_discovered = 0
    links_discovered = 0

    for device_name in device_list:
        try:
            # Get device info from Nornir
            nr = get_nornir()
            host = nr.inventory.hosts.get(device_name)

            if not host:
                continue

            # Store device info
            hostname = host.hostname or device_name
            platform = host.platform or "unknown"
            mgmt_ip = hostname
            site = host.get("site", "unknown")
            role = host.get("role", "unknown")

            conn.execute(
                """
                INSERT OR REPLACE INTO topology_devices
                (name, hostname, platform, mgmt_ip, site, role, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [device_name, hostname, platform, mgmt_ip, site, role, datetime.now()],
            )

            devices_discovered += 1

            # Discover L1 neighbors (CDP/LLDP)
            links_discovered += _discover_l1_neighbors(conn, executor, db, device_name, platform)

            # Discover L3 neighbors (OSPF/BGP)
            links_discovered += _discover_l3_neighbors(conn, executor, db, device_name, platform)

        except Exception as e:
            # Continue with other devices on error
            print(f"Error discovering topology for {device_name}: {e}")

    conn.close()

    return (
        f"Discovered topology: {devices_discovered} devices, {links_discovered} links. "
        f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."
    )


def _discover_l1_neighbors(
    conn: duckdb.DuckDBPyConnection,
    executor: NetworkExecutor,
    db: CapabilityDatabase,
    device: str,
    platform: str,
) -> int:
    """Discover L1 neighbors using CDP/LLDP.

    Args:
        conn: Topology database connection
        executor: Network executor instance
        db: Capabilities database
        device: Device name
        platform: Device platform

    Returns:
        Number of links discovered
    """
    links_found = 0

    # Search for CDP/LLDP commands
    cdp_commands = db.search_capabilities("cdp neighbors", platform=platform, limit=5)
    lldp_commands = db.search_capabilities("lldp neighbor", platform=platform, limit=5)

    # Try CDP first, then LLDP
    for cmd_info in cdp_commands + lldp_commands:
        command = cmd_info["name"]

        # Skip if not a neighbor command
        if "neighbor" not in command.lower():
            continue

        result = executor.execute(device, command, timeout=30)

        if result.success and result.output:
            # Parse neighbor information
            neighbors = _parse_cdp_lldp_output(result.output, platform)

            for neighbor in neighbors:
                try:
                    # Insert link using DuckDB's ON CONFLICT syntax
                    conn.execute(
                        """
                        INSERT INTO topology_links
                        (local_device, local_port, remote_device, remote_port,
                         layer, protocol, metadata, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (local_device, local_port, remote_device, remote_port, layer)
                        DO UPDATE SET
                            protocol = EXCLUDED.protocol,
                            metadata = EXCLUDED.metadata,
                            discovered_at = EXCLUDED.discovered_at
                    """,
                        [
                            device,
                            neighbor.get("local_port"),
                            neighbor.get("remote_device"),
                            neighbor.get("remote_port"),
                            "L1",
                            neighbor.get("protocol", "Unknown"),
                            json.dumps(neighbor.get("metadata", {})),
                            datetime.now(),
                        ],
                    )
                    links_found += 1
                except Exception as e:
                    # Skip duplicate or invalid links
                    print(f"Warning: Failed to insert L1 link for {device}: {e}")
                    continue
            # Found neighbors, don't try more commands
            if neighbors:
                break

    return links_found


def _discover_l3_neighbors(
    conn: duckdb.DuckDBPyConnection,
    executor: NetworkExecutor,
    db: CapabilityDatabase,
    device: str,
    platform: str,
) -> int:
    """Discover L3 neighbors using OSPF/BGP.

    Args:
        conn: Topology database connection
        executor: Network executor instance
        db: Capabilities database
        device: Device name
        platform: Device platform

    Returns:
        Number of links discovered
    """
    links_found = 0

    # Search for OSPF neighbor commands
    ospf_commands = db.search_capabilities("ospf neighbor", platform=platform, limit=5)

    for cmd_info in ospf_commands:
        command = cmd_info["name"]

        result = executor.execute(device, command, timeout=30)

        if result.success and result.output:
            neighbors = _parse_ospf_output(result.output, platform)

            for neighbor in neighbors:
                try:
                    conn.execute(
                        """
                        INSERT INTO topology_links
                        (local_device, local_port, remote_device, remote_port,
                         layer, protocol, metadata, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (local_device, local_port, remote_device, remote_port, layer)
                        DO UPDATE SET
                            protocol = EXCLUDED.protocol,
                            metadata = EXCLUDED.metadata,
                            discovered_at = EXCLUDED.discovered_at
                    """,
                        [
                            device,
                            neighbor.get("local_port"),
                            neighbor.get("remote_device"),
                            None,
                            "L3",
                            "OSPF",
                            json.dumps(neighbor.get("metadata", {})),
                            datetime.now(),
                        ],
                    )
                    links_found += 1
                except Exception as e:
                    print(f"Warning: Failed to insert OSPF link for {device}: {e}")
                    continue

            if neighbors:
                break

    # Search for BGP neighbor commands
    bgp_commands = db.search_capabilities("bgp summary", platform=platform, limit=5)

    for cmd_info in bgp_commands:
        command = cmd_info["name"]

        result = executor.execute(device, command, timeout=30)

        if result.success and result.output:
            neighbors = _parse_bgp_output(result.output, platform)

            for neighbor in neighbors:
                try:
                    conn.execute(
                        """
                        INSERT INTO topology_links
                        (local_device, local_port, remote_device, remote_port,
                         layer, protocol, metadata, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (local_device, local_port, remote_device, remote_port, layer)
                        DO UPDATE SET
                            protocol = EXCLUDED.protocol,
                            metadata = EXCLUDED.metadata,
                            discovered_at = EXCLUDED.discovered_at
                    """,
                        [
                            device,
                            neighbor.get("local_port"),
                            neighbor.get("remote_device"),
                            None,
                            "L3",
                            "BGP",
                            json.dumps(neighbor.get("metadata", {})),
                            datetime.now(),
                        ],
                    )
                    links_found += 1
                except Exception as e:
                    print(f"Warning: Failed to insert BGP link for {device}: {e}")
                    continue

            if neighbors:
                break

    return links_found


def _parse_cdp_lldp_output(output: str, platform: str) -> list[dict[str, Any]]:
    """Parse CDP/LLDP command output.

    This is a simple parser. In production, use TextFSM templates
    for more reliable parsing.

    Args:
        output: Command output text
        platform: Device platform

    Returns:
        List of neighbor dictionaries
    """
    neighbors = []
    lines = output.split("\n")

    current_protocol = "CDP" if "cdp" in platform.lower() else "LLDP"

    # Simple parsing logic - look for device names and interfaces
    # This is a basic implementation; TextFSM would be better
    for _i, line in enumerate(lines):
        line = line.strip()

        # Look for lines containing device names and interfaces
        # Format varies by platform, so we use flexible patterns
        if line and not line.startswith(" ") and not line.startswith("-"):
            # Skip header lines
            if any(
                word in line.lower()
                for word in ["device", "interface", "port", "neighbor", "hold", "capability"]
            ):
                continue

            # Try to extract device and interface from line
            parts = line.split()
            if len(parts) >= 2:
                neighbor = {
                    "remote_device": parts[0],
                    "local_port": parts[1] if len(parts) > 1 else None,
                    "remote_port": parts[2] if len(parts) > 2 else None,
                    "protocol": current_protocol,
                    "metadata": {"raw_line": line},
                }
                neighbors.append(neighbor)

    return neighbors


def _parse_ospf_output(output: str, platform: str) -> list[dict[str, Any]]:
    """Parse OSPF neighbor command output.

    Args:
        output: Command output text
        platform: Device platform

    Returns:
        List of neighbor dictionaries
    """
    neighbors = []
    lines = output.split("\n")

    for line in lines:
        # Look for neighbor IP addresses
        # Typical format: "Neighbor ID Pri State Dead Time Address Interface"
        parts = line.split()

        if len(parts) >= 3:
            # Check if this looks like an OSPF neighbor line
            # Usually has IP-like strings and state info
            neighbor = {
                "remote_device": parts[0],  # Usually Neighbor ID (IP)
                "local_port": parts[-1] if len(parts) > 0 else None,  # Usually interface
                "metadata": {
                    "priority": parts[1] if len(parts) > 1 else None,
                    "state": parts[2] if len(parts) > 2 else None,
                    "raw_line": line,
                },
            }
            neighbors.append(neighbor)

    return neighbors


def _parse_bgp_output(output: str, platform: str) -> list[dict[str, Any]]:
    """Parse BGP summary command output.

    Args:
        output: Command output text
        platform: Device platform

    Returns:
        List of neighbor dictionaries
    """
    neighbors = []
    lines = output.split("\n")

    for line in lines:
        # Look for BGP neighbor entries
        # Typically has neighbor IP, AS, state, etc.
        parts = line.split()

        if len(parts) >= 2:
            # Check for IP-like string (neighbor)
            if "." in parts[0] or ":" in parts[0]:
                neighbor = {
                    "remote_device": parts[0],  # Neighbor IP
                    "local_port": None,  # BGP doesn't always show interface
                    "metadata": {
                        "remote_as": parts[1] if len(parts) > 1 else None,
                        "state": parts[2] if len(parts) > 2 else None,
                        "raw_line": line,
                    },
                }
                neighbors.append(neighbor)

    return neighbors


@tool
def get_topology_age() -> str:
    """Get the age of topology data.

    Returns:
        Human-readable age string (e.g., "10 minutes ago") or "Never discovered"

    Examples:
        >>> get_topology_age()
        "10 minutes ago"
    """
    graph = TopologyGraph()
    return graph.get_topology_age()


@tool
def query_path(source: str, destination: str) -> str:
    """Query the shortest path between two devices.

    Args:
        source: Source device name
        destination: Destination device name

    Returns:
        Path information with age

    Examples:
        >>> query_path("R1", "R5")
        "Path: R1 -> R2 -> R3 -> R5 (Data age: 10 minutes ago)"
    """
    graph = TopologyGraph()
    path = graph.shortest_path(source, destination)
    age = graph.get_topology_age()

    if not path:
        return f"No path found between {source} and {destination}. (Data age: {age})"

    path_str = " -> ".join(path)
    return f"Path: {path_str} (Data age: {age})"


@tool
def query_neighbors(device: str, layer: str | None = None) -> str:
    """Query neighbors of a device.

    Args:
        device: Device name
        layer: Optional filter by layer ('L1' or 'L3')

    Returns:
        Neighbor information with age

    Examples:
        >>> query_neighbors("R1")
        "R1 neighbors (3): R2 via Gi0/1 (L1/CDP), R3 via Gi0/2 (L1/CDP), ISP via Gi0/0 (L3/BGP) (Data age: 10 minutes ago)"
    """
    graph = TopologyGraph()
    neighbors = graph.get_neighbors(device, layer)
    age = graph.get_topology_age()

    if not neighbors:
        return f"No neighbors found for {device}. (Layer: {layer or 'All'}, Data age: {age})"

    neighbor_strs = []
    for n in neighbors:
        port_info = f" via {n['local_port']}" if n["local_port"] else ""
        layer_info = f" ({n['layer']}/{n['protocol']})" if n["protocol"] else ""
        neighbor_strs.append(f"{n['device']}{port_info}{layer_info}")

    result = f"{device} neighbors ({len(neighbors)}): " + ", ".join(neighbor_strs)
    return f"{result} (Data age: {age})"


@tool
def show_topology() -> str:
    """Show topology summary.

    Returns:
        Topology summary with device and link counts

    Examples:
        >>> show_topology()
        "Topology Summary: 5 devices, 12 links (Data age: 10 minutes ago)"
    """
    graph = TopologyGraph()
    devices = graph.get_all_devices()
    links = graph.get_link_count()
    age = graph.get_topology_age()

    return f"Topology Summary: {len(devices)} devices, {links} links (Data age: {age})"
