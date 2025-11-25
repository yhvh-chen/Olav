"""Direct Parquet-based SuzieQ tools - bypasses SuzieQ library dependency conflicts.

This implementation reads SuzieQ Parquet files directly using pandas/pyarrow,
avoiding pydantic v1/v2 conflicts between SuzieQ and LangChain.
"""

import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# SuzieQ schema metadata (table → fields mapping)
SUZIEQ_SCHEMA = {
    "bgp": {
        "fields": [
            "namespace",
            "hostname",
            "vrf",
            "peer",
            "asn",
            "peerAsn",
            "state",
            "peerHostname",
        ],
        "description": "BGP protocol information",
    },
    "interfaces": {
        "fields": [
            "namespace",
            "hostname",
            "ifname",
            "state",
            "adminState",
            "type",
            "mtu",
            "speed",
        ],
        "description": "Network interface status and configuration",
    },
    "routes": {
        "fields": ["namespace", "hostname", "vrf", "prefix", "nexthopIp", "protocol", "metric"],
        "description": "Routing table entries",
    },
    "ospf": {
        "fields": ["namespace", "hostname", "vrf", "ifname", "area", "state", "nbrCount"],
        "description": "OSPF protocol information",
    },
    "lldp": {
        "fields": ["namespace", "hostname", "ifname", "peerHostname", "peerIfname"],
        "description": "LLDP neighbor discovery",
    },
    "macs": {
        "fields": ["namespace", "hostname", "vlan", "macaddr", "oif", "remoteVtepIp"],
        "description": "MAC address table",
    },
    "arpnd": {
        "fields": ["namespace", "hostname", "vrf", "ipAddress", "macaddr", "oif", "state"],
        "description": "ARP/ND table entries",
    },
    "device": {
        "fields": ["namespace", "hostname", "model", "vendor", "version", "architecture", "status"],
        "description": "Device hardware and software information",
    },
}


def _get_parquet_dir() -> Path:
    """Get SuzieQ parquet directory path."""
    # Try environment variable first, then fallback to default
    parquet_dir = Path("data/suzieq-parquet")
    if not parquet_dir.exists():
        logger.warning(f"SuzieQ parquet directory not found: {parquet_dir}")
    return parquet_dir


@tool
async def suzieq_schema_search(query: str) -> dict[str, Any]:
    """Search SuzieQ schema to discover available tables and fields.

    This tool helps you find what data SuzieQ can query. Always call this
    BEFORE using suzieq_query to discover available tables, fields, and methods.

    Args:
        query: Natural language query about what you want to find
               Examples: "BGP information", "interface statistics", "routing tables"

    Returns:
        Dictionary with matching tables, their fields, and supported methods

    Example:
        >>> await suzieq_schema_search("BGP routing information")
        {
            "tables": ["bgp", "routes"],
            "bgp": {
                "fields": ["namespace", "hostname", "vrf", "peer", "asn", "state"],
                "methods": ["get", "summarize"],
                "description": "BGP protocol information"
            },
            "routes": {
                "fields": ["namespace", "hostname", "vrf", "prefix", "nexthopIp", "protocol"],
                "methods": ["get", "summarize"],
                "description": "Routing table entries"
            }
        }
    """
    # Simple keyword matching
    keywords = query.lower().split()
    matching_tables = [
        table
        for table in SUZIEQ_SCHEMA
        if any(
            keyword in table.lower() or keyword in SUZIEQ_SCHEMA[table]["description"].lower()
            for keyword in keywords
        )
    ]

    if not matching_tables:
        matching_tables = list(SUZIEQ_SCHEMA.keys())[:5]  # Return top 5 if no match

    result: dict[str, Any] = {"tables": matching_tables}
    for table in matching_tables:
        result[table] = {
            **SUZIEQ_SCHEMA[table],
            "methods": ["get", "summarize"],  # Parquet supports get and basic aggregation
        }

    return result


@tool
async def suzieq_query(
    table: str,
    method: Literal["get", "summarize"] = "get",
    hostname: str | None = None,
    namespace: str | None = None,
    max_age_hours: int = 24,
    filters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Query SuzieQ historical network data from Parquet files.

    This tool provides access to historical network state collected by SuzieQ.
    Use this for trend analysis, historical comparisons, and aggregated statistics.

    IMPORTANT: By default, only queries data from the last 24 hours to avoid stale/test data pollution.
    Set max_age_hours=0 to query all historical data (use with caution).

    Args:
        table: Table name (use suzieq_schema_search to discover)
        max_age_hours: Maximum age of data to query in hours (default: 24, set to 0 for all data)
        method: Query method - "get" for raw data, "summarize" for aggregated statistics
        hostname: Filter by specific hostname (optional)
        namespace: Filter by namespace (optional, default: "all")
        filters: Dictionary of additional filters (optional)
        **kwargs: Additional filters passed as keyword arguments (e.g., state="up")

    Returns:
        Dictionary with query results:
        - "data": List of records (for "get") or summary statistics (for "summarize")
        - "count": Number of records
        - "columns": Available fields
        - "table": Table name

    Example:
        >>> await suzieq_query(table="interfaces", method="summarize", hostname="R1")
        {
            "data": [{"state_up": 3, "state_down": 1, "total_interfaces": 4}],
            "count": 1,
            "columns": ["state_up", "state_down", "total_interfaces"],
            "table": "interfaces"
        }
    """
    parquet_dir = _get_parquet_dir()

    # Combine explicit filters dict and kwargs
    query_filters = filters.copy() if filters else {}
    query_filters.update(kwargs)

    # Check if table exists in schema
    if table not in SUZIEQ_SCHEMA:
        return {
            "error": f"Unknown table '{table}'. Use suzieq_schema_search to discover available tables.",
            "available_tables": list(SUZIEQ_SCHEMA.keys()),
            "table": table,
            "status": "SCHEMA_NOT_FOUND",
            "warning": "⛔ DO NOT fabricate data. This table does not exist in SuzieQ schema.",
        }

    # SuzieQ uses Hive-style partitioning:
    # Coalesced data: data/suzieq-parquet/coalesced/{table}/sqvers={version}/namespace={ns}/...
    # Raw data: data/suzieq-parquet/{table}/sqvers={version}/namespace={ns}/hostname={host}/*.parquet
    # Prefer coalesced (optimized) over raw data
    table_dir = parquet_dir / "coalesced" / table
    if not table_dir.exists():
        # Fallback to raw data directory
        table_dir = parquet_dir / table

    if not table_dir.exists():
        # Return explicit NO_DATA_FOUND record to prevent hallucination
        return {
            "data": [
                {
                    "status": "NO_DATA_FOUND",
                    "message": f"No data directory found for table '{table}'",
                    "hint": "SuzieQ has not collected any data for this table. This is NOT an error.",
                    "warning": "DO NOT fabricate data. Inform the user that no data is available.",
                    "expected_path": str(table_dir),
                }
            ],
            "count": 0,
            "columns": ["status", "message", "hint", "warning", "expected_path"],
            "table": table,
        }

    try:
        # Read all parquet files recursively (handles Hive partitioning)
        parquet_files = list(table_dir.rglob("*.parquet"))
        if not parquet_files:
            # Return explicit NO_DATA_FOUND record to prevent hallucination
            return {
                "data": [
                    {
                        "status": "NO_DATA_FOUND",
                        "message": f"No parquet files found for table '{table}' in {table_dir}",
                        "hint": "SuzieQ has not collected data for this table yet. This is NOT an error - the table simply has no historical data.",
                        "warning": "DO NOT fabricate data. Inform the user that no data is available.",
                    }
                ],
                "count": 0,
                "columns": ["status", "message", "hint", "warning"],
                "table": table,
            }

        # Read and concat all parquet files
        # Use pyarrow dataset API for better Hive partition support
        try:
            import pyarrow.dataset as ds

            dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
            df = dataset.to_table().to_pandas()
        except Exception:
            # Fallback to manual concat
            dfs = [pd.read_parquet(f) for f in parquet_files]
            df = pd.concat(dfs, ignore_index=True)

        # CRITICAL: Filter by time window to avoid stale/test data pollution
        # Default: only last 24 hours (configurable via max_age_hours parameter)
        if max_age_hours > 0 and "timestamp" in df.columns:
            import time

            current_time_ms = int(time.time() * 1000)
            cutoff_time_ms = current_time_ms - (max_age_hours * 3600 * 1000)
            df = df[df["timestamp"] >= cutoff_time_ms]
            logger.info(f"Filtered to last {max_age_hours} hours: {len(df)} records remain")

        # Apply filters
        if hostname:
            df = df[df["hostname"] == hostname]

        # Apply namespace filter if provided
        if namespace and namespace != "all" and "namespace" in df.columns:
            df = df[df["namespace"] == namespace]

        for field, value in query_filters.items():
            if field in df.columns:
                df = df[df[field] == value]

        # CRITICAL: SuzieQ stores time-series data (multiple snapshots per peer)
        # Deduplicate by taking the latest timestamp for each unique entity
        # Priority: active=True records first
        if "active" in df.columns:
            # Filter to only active records first (current state)
            df_active = df[df["active"]]
            if len(df_active) > 0:
                df = df_active

        # Deduplicate based on table type (take latest timestamp)
        if "timestamp" in df.columns:
            # Define unique key columns by table
            unique_keys = {
                "bgp": ["hostname", "peer", "afi", "safi"],  # Unique per peer+address-family
                "interfaces": ["hostname", "ifname"],
                "routes": ["hostname", "vrf", "prefix"],
                "lldp": ["hostname", "ifname"],
                "device": ["hostname"],
            }

            key_cols = unique_keys.get(table, ["hostname"])  # Fallback to hostname only

            # Keep only latest record for each unique entity
            if all(col in df.columns for col in key_cols):
                df = df.sort_values("timestamp", ascending=False).drop_duplicates(
                    subset=key_cols, keep="first"
                )

        # Execute method
        if method == "get":
            # Return raw data (limit to 100 rows to avoid token overflow)
            data = df.head(100).to_dict(orient="records")
            return {
                "data": data,
                "count": len(df),
                "columns": list(df.columns),
                "table": table,
                "truncated": len(df) > 100,
                "data_type": "deduplicated_current_state",
                "note": "SuzieQ stores time-series data. This result shows only the latest state for each unique entity (active records prioritized).",
            }

        if method == "summarize":
            # Basic summarization - count by state/status fields
            summary = {}

            # Common summary patterns
            if "state" in df.columns:
                summary["state_counts"] = df["state"].value_counts().to_dict()
            if "adminState" in df.columns:
                summary["admin_state_counts"] = df["adminState"].value_counts().to_dict()
            if "type" in df.columns:
                summary["type_counts"] = df["type"].value_counts().to_dict()

            summary["total_records"] = len(df)
            summary["unique_hosts"] = df["hostname"].nunique() if "hostname" in df.columns else 0

            return {
                "data": [summary],
                "count": 1,
                "columns": list(summary.keys()),
                "table": table,
            }

        return {"error": f"Unsupported method '{method}'. Use 'get' or 'summarize'."}

    except Exception as e:
        logger.error(f"Error querying SuzieQ parquet: {e}", exc_info=True)
        return {
            "error": f"Failed to query parquet: {e!s}",
            "table": table,
            "method": method,
        }
