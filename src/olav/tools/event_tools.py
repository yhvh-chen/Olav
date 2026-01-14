"""Unified Data Layer - Event Tools for OLAV v0.8.

This module provides tools for parsing and analyzing network log events,
following the unified data layer design (docs/0.md).

Core functions:
- parse_device_logs: Parse show logging output into structured events
- query_events: Query events from DuckDB
- detect_topology_changes: Detect topology changes from log events
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from olav.tools.sync_tools import get_latest_sync_dir, get_sync_dir

# =============================================================================
# Data Models
# =============================================================================


class NetworkEvent(BaseModel):
    """Parsed network event from device logs.

    Attributes:
        timestamp: Event timestamp (may be None if unparseable)
        device: Device name
        severity: Syslog severity (0-7, 0=emergency, 7=debug)
        facility: Facility name (LINK, OSPF, BGP, SYS, etc.)
        mnemonic: Event mnemonic (UPDOWN, ADJCHG, etc.)
        interface: Interface name (if applicable)
        neighbor: Neighbor identifier (if applicable)
        message: Full log message
    """

    timestamp: datetime | None = Field(default=None, description="Event timestamp")
    device: str = Field(description="Device name")
    severity: int = Field(description="Syslog severity (0-7)")
    facility: str = Field(description="Facility name")
    mnemonic: str = Field(description="Event mnemonic")
    interface: str | None = Field(default=None, description="Interface name")
    neighbor: str | None = Field(default=None, description="Neighbor identifier")
    message: str = Field(description="Full log message")


# =============================================================================
# Tool 1: parse_device_logs
# =============================================================================


@tool
def parse_device_logs(
    device: str, raw_log: str | None = None, date: str | None = None
) -> list[dict[str, Any]]:
    """Parse show logging output into structured events.

    This tool parses Cisco/Huawei syslog output into structured NetworkEvent objects.
    It handles multiple timestamp formats and extracts facility, mnemonic, and other fields.

    Args:
        device: Device name
        raw_log: Raw log output (if None, reads from sync data)
        date: Optional date for reading from sync (YYYY-MM-DD, default: latest)

    Returns:
        List of event dictionaries with timestamp, severity, facility, mnemonic, etc.

    Examples:
        >>> events = parse_device_logs("R1")
        >>> print(events[0])
        {
            "timestamp": "2026-01-13T02:15:23Z",
            "device": "R1",
            "severity": 3,
            "facility": "LINK",
            "mnemonic": "UPDOWN",
            "interface": "GigabitEthernet0/2",
            "message": "Interface GigabitEthernet0/2, changed state to down"
        }

        >>> events = parse_device_logs("R1", raw_log="*Jan 13 02:15:23.000: %LINK-3-UPDOWN...")
        [...]
    """
    # Read from sync data if raw_log not provided
    if raw_log is None:
        sync_dir = get_sync_dir(date) if date else get_latest_sync_dir()
        if not sync_dir:
            return []

        log_file = sync_dir / "raw" / "logging" / f"{device}.txt"
        if not log_file.exists():
            return []

        raw_log = log_file.read_text(encoding="utf-8", errors="ignore")

    # Parse events
    events = []
    for line in raw_log.split("\n"):
        line = line.strip()
        if not line:
            continue

        event = _parse_log_line(device, line)
        if event:
            events.append(event.model_dump())

    return events


def _parse_log_line(device: str, line: str) -> NetworkEvent | None:
    """Parse a single log line into a NetworkEvent.

    Args:
        device: Device name
        line: Log line

    Returns:
        NetworkEvent object or None if parsing fails
    """
    # Cisco IOS format examples:
    # *Jan 13 02:15:23.000: %LINK-3-UPDOWN: Interface GigabitEthernet0/2, changed state to down
    # *Jan 13 02:15:23.543: %OSPF-5-ADJCHG: Process 1, Nbr 10.1.1.2 on GigabitEthernet0/1 from LOADING to FULL, Loading Took 00:00:01
    # Jan 13 02:15:23.000: %SYS-5-CONFIG_I: Configured from console by console

    # Huawei VRP format examples:
    # Jan 13 2026 02:15:23+08:00 R1 %%01IFNET/4/LINK_STATE(l)[0]: The line protocol IP
    # for the interface GigabitEthernet0/0/1 has changed to down.

    # Try Cisco IOS format
    # Pattern: *Jan 13 15:16:47.888: %SYS-6-LOGOUT: User cisco has exited...
    cisco_pattern = r"""
        ^\*?(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d{3})?)?\s*:\s*  # Timestamp + colon
        %(\w+)-(\d)-(\w+):\s*                                          # %FACILITY-SEVERITY-MNEMONIC:
        (.+)                                                           # Message
    """

    match = re.match(cisco_pattern, line, re.VERBOSE)
    if match:
        timestamp_str, facility, severity_str, mnemonic, message = match.groups()

        # Parse timestamp
        timestamp = None
        if timestamp_str:
            try:
                # Add current year if missing
                timestamp = datetime.strptime(
                    f"{datetime.now().year} {timestamp_str}", "%Y %b %d %H:%M:%S.%f"
                )
            except ValueError:
                try:
                    timestamp = datetime.strptime(
                        f"{datetime.now().year} {timestamp_str}", "%Y %b %d %H:%M:%S"
                    )
                except ValueError:
                    pass

        # Parse severity
        try:
            severity = int(severity_str)
        except ValueError:
            severity = 6  # Default to info

        # Extract interface and neighbor from message
        interface = _extract_interface(message)
        neighbor = _extract_neighbor(message)

        return NetworkEvent(
            timestamp=timestamp,
            device=device,
            severity=severity,
            facility=facility,
            mnemonic=mnemonic,
            interface=interface,
            neighbor=neighbor,
            message=message,
        )

    # Try Huawei VRP format
    huawei_pattern = r"""
        ^
        (\w{3}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?)\s+  # Timestamp
        (\S+)\s+                                                           # Device
        %%(\d+)(\w+)/(\d+)/(\w+)                                          # %%FACILITY/SEVERITY/MNEMONIC
        .*
        :\s*(.+)                                                          # Message
    """

    match = re.match(huawei_pattern, line, re.VERBOSE)
    if match:
        timestamp_str, _, _, facility, severity_str, mnemonic, message = match.groups()

        # Parse timestamp
        timestamp = None
        try:
            timestamp = datetime.strptime(timestamp_str, "%b %d %Y %H:%M:%S%z")
        except ValueError:
            try:
                timestamp = datetime.strptime(timestamp_str, "%b %d %Y %H:%M:%S")
            except ValueError:
                pass

        # Parse severity
        try:
            severity = int(severity_str)
        except ValueError:
            severity = 6

        # Extract interface and neighbor
        interface = _extract_interface(message)
        neighbor = _extract_neighbor(message)

        return NetworkEvent(
            timestamp=timestamp,
            device=device,
            severity=severity,
            facility=facility,
            mnemonic=mnemonic,
            interface=interface,
            neighbor=neighbor,
            message=message,
        )

    return None


def _extract_interface(message: str) -> str | None:
    """Extract interface name from message.

    Args:
        message: Log message

    Returns:
        Interface name or None
    """
    # Common interface patterns
    patterns = [
        r"(?:Interface|interface)\s+([A-Za-z]+\d+(?:/\d+)*)",  # Cisco
        r"(?:GigabitEthernet|FastEthernet|Ethernet|TenGigabitEthernet|Serial|Vlan|Loopback)\d+/\d+(/\d+)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)

    return None


def _extract_neighbor(message: str) -> str | None:
    """Extract neighbor identifier from message.

    Args:
        message: Log message

    Returns:
        Neighbor IP/ID or None
    """
    # IP address patterns
    ip_pattern = r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    ips = re.findall(ip_pattern, message)

    # Return first IP if found
    if ips:
        return ips[0]

    # Look for "Nbr X" pattern (OSPF/BGP)
    nbr_match = re.search(r"[Nn]br\s+(\S+)", message)
    if nbr_match:
        return nbr_match.group(1)

    return None


# =============================================================================
# Tool 2: query_events
# =============================================================================


@tool
def query_events(
    event_type: str | None = None,
    device: str | None = None,
    severity_max: int = 5,
    time_range: str = "24h",
    date: str | None = None,
) -> str:
    """Query events from DuckDB database.

    This tool queries the network_events table in the sync database,
    allowing filtering by event type, device, severity, and time range.

    Args:
        event_type: Optional event type filter (e.g., "UPDOWN", "ADJCHG")
        device: Optional device filter
        severity_max: Maximum severity level (default: 5, include 0-5)
        time_range: Time range filter (default: "24h", also "7d", "30d")
        date: Optional date for database (default: latest)

    Returns:
        Formatted event list or error message

    Examples:
        >>> query_events(event_type="UPDOWN", device="R1")
        "Found 3 interface state change events..."

        >>> query_events(severity_max=3)
        "Found 5 critical events..."
    """
    # Get database path
    if date:
        db_path = get_sync_dir(date) / "reports" / "topology.db"
    else:
        sync_dir = get_latest_sync_dir()
        if not sync_dir:
            return "No sync data found."
        db_path = sync_dir / "reports" / "topology.db"

    if not db_path.exists():
        # Initialize database if not exists
        from olav.tools.sync_tools import _init_sync_db

        sync_dir = get_latest_sync_dir()
        if not sync_dir:
            return "No sync data found."
        _init_sync_db(sync_dir)
        db_path = sync_dir / "reports" / "topology.db"

    try:
        conn = duckdb.connect(str(db_path), read_only=True)

        # Build query
        sql = "SELECT device, timestamp, severity, facility, mnemonic, interface, neighbor, message FROM network_events WHERE 1=1"
        params = []

        if event_type:
            sql += " AND mnemonic = ?"
            params.append(event_type)

        if device:
            sql += " AND device = ?"
            params.append(device)

        sql += " AND severity <= ?"
        params.append(severity_max)

        # Add time range filter
        if time_range.endswith("h"):
            hours = int(time_range[:-1])
            sql += f" AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours} hours'"
        elif time_range.endswith("d"):
            days = int(time_range[:-1])
            sql += f" AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '{days} days'"

        sql += " ORDER BY timestamp DESC LIMIT 100"

        result = conn.execute(sql, params).fetchall()
        conn.close()

        if not result:
            return "No events found matching the criteria."

        # Format output
        lines = [f"Found {len(result)} events:", ""]
        for row in result:
            device, timestamp, severity, facility, mnemonic, interface, neighbor, message = row
            ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
            intf_str = f" [{interface}]" if interface else ""
            lines.append(
                f"{ts_str} | {device} | {facility}-{severity}-{mnemonic}{intf_str} | {message}"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"Query error: {e}"


# =============================================================================
# Tool 3: detect_topology_changes
# =============================================================================


@tool
def detect_topology_changes(time_range: str = "24h", date: str | None = None) -> str:
    """Detect topology changes from log events.

    This tool analyzes network_events to detect topology-related changes:
    - Interface state changes (UPDOWN)
    - OSPF neighbor changes (ADJCHG)
    - BGP session changes (ADJCHANGE)

    Args:
        time_range: Time range to analyze (default: "24h")
        date: Optional date for database (default: latest)

    Returns:
        Summary of topology changes

    Examples:
        >>> detect_topology_changes()
        "Topology changes in last 24h:
         - Interface changes: 5
         - OSPF changes: 2
         - BGP changes: 0
         Devices affected: R1, R2, R3"
    """
    # Query for topology-related events
    conn = None
    try:
        # Get database
        if date:
            db_path = get_sync_dir(date) / "reports" / "topology.db"
        else:
            sync_dir = get_latest_sync_dir()
            if not sync_dir:
                return "No sync data found."
            db_path = sync_dir / "reports" / "topology.db"

        if not db_path.exists():
            return "No events database found."

        conn = duckdb.connect(str(db_path), read_only=True)

        # Build time filter (using safe parameters)
        if time_range.endswith("h"):
            hours = int(time_range[:-1])
            time_filter = f"timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours} hours'"
        elif time_range.endswith("d"):
            days = int(time_range[:-1])
            time_filter = f"timestamp >= CURRENT_TIMESTAMP - INTERVAL '{days} days'"
        else:
            time_filter = "1=1"

        # Query topology-related events (safe: mnemonic values are hardcoded)
        query_parts = [
            "SELECT mnemonic, device, interface, neighbor, COUNT(*) as count,",
            "       MIN(timestamp) as first_seen, MAX(timestamp) as last_seen",
            "FROM network_events",
            f"WHERE {time_filter}",
            "  AND mnemonic IN ('UPDOWN', 'ADJCHG', 'ADJCHANGE', 'STATECHANGE')",
            "GROUP BY mnemonic, device, interface, neighbor",
            "ORDER BY first_seen DESC",
        ]
        sql = "\n".join(query_parts)

        result = conn.execute(sql).fetchall()

        if not result:
            return f"No topology changes detected in the last {time_range}."

        # Aggregate by event type
        interface_changes = []
        ospf_changes = []
        bgp_changes = []
        devices_affected = set()

        for row in result:
            mnemonic, device, interface, neighbor, count, first_seen, last_seen = row
            devices_affected.add(device)

            if mnemonic == "UPDOWN":
                interface_changes.append((device, interface, count, first_seen))
            elif mnemonic == "ADJCHG":
                ospf_changes.append((device, neighbor, count, first_seen))
            elif mnemonic == "ADJCHANGE":
                bgp_changes.append((device, neighbor, count, first_seen))

        # Build summary
        lines = [
            f"Topology changes in last {time_range}:",
            "",
            f"Interface state changes: {len(interface_changes)}",
            f"OSPF neighbor changes: {len(ospf_changes)}",
            f"BGP session changes: {len(bgp_changes)}",
            f"Devices affected: {', '.join(sorted(devices_affected))}",
            "",
        ]

        if interface_changes:
            lines.append("Interface changes:")
            for device, interface, count, first_seen in interface_changes[:10]:
                fs = first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else "N/A"
                lines.append(f"  - {device}: {interface} ({count} changes, first: {fs})")

        if ospf_changes:
            lines.append("")
            lines.append("OSPF neighbor changes:")
            for device, neighbor, count, first_seen in ospf_changes[:10]:
                fs = first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else "N/A"
                nbr_str = f"neighbor {neighbor}" if neighbor else "unknown neighbor"
                lines.append(f"  - {device}: {nbr_str} ({count} changes, first: {fs})")

        if bgp_changes:
            lines.append("")
            lines.append("BGP session changes:")
            for device, neighbor, count, first_seen in bgp_changes[:10]:
                fs = first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else "N/A"
                lines.append(f"  - {device}: {neighbor} ({count} changes, first: {fs})")

        return "\n".join(lines)

    except Exception as e:
        import traceback

        return f"Detection error: {e}\n\nTraceback:\n{traceback.format_exc()}"
    finally:
        if conn:
            conn.close()


# =============================================================================
# Database Initialization for Events
# =============================================================================


def init_events_table(db_path: Path) -> None:
    """Initialize network_events table in database.

    Args:
        db_path: Path to topology database
    """
    conn = duckdb.connect(str(db_path))

    # Create network_events table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS network_events (
            id INTEGER PRIMARY KEY,
            sync_date DATE,
            device VARCHAR NOT NULL,
            timestamp TIMESTAMP,
            severity INTEGER,
            facility VARCHAR,
            mnemonic VARCHAR,
            interface VARCHAR,
            neighbor VARCHAR,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_device ON network_events(device)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON network_events(severity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON network_events(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_mnemonic ON network_events(mnemonic)")

    conn.close()


def store_events(db_path: Path, events: list[NetworkEvent], sync_date: str) -> int:
    """Store parsed events in database.

    Args:
        db_path: Path to topology database
        events: List of NetworkEvent objects
        sync_date: Sync date string

    Returns:
        Number of events stored
    """
    if not events:
        return 0

    init_events_table(db_path)

    conn = duckdb.connect(str(db_path))

    for event in events:
        conn.execute(
            """
            INSERT INTO network_events
            (sync_date, device, timestamp, severity, facility, mnemonic, interface, neighbor, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                sync_date,
                event.device,
                event.timestamp,
                event.severity,
                event.facility,
                event.mnemonic,
                event.interface,
                event.neighbor,
                event.message,
            ],
        )

    count = len(events)
    conn.close()
    return count
