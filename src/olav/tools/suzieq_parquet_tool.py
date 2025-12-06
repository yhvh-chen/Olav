"""Direct Parquet-based SuzieQ tools - Schema-Aware implementation.

This implementation reads SuzieQ Parquet files directly using pandas/pyarrow,
with dynamic schema loading from OpenSearch, avoiding hardcoded dictionaries.
"""

import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from langchain_core.tools import tool

from olav.core.schema_loader import get_schema_loader

logger = logging.getLogger(__name__)


def _get_parquet_dir() -> Path:
    """Get SuzieQ parquet directory path."""
    # Try environment variable first, then fallback to default
    parquet_dir = Path("data/suzieq-parquet")
    if not parquet_dir.exists():
        logger.warning(f"SuzieQ parquet directory not found: {parquet_dir}")
    return parquet_dir


# Global schema loader instance
_schema_loader = get_schema_loader()


@tool
async def suzieq_schema_search(query: str) -> dict[str, Any]:
    """Search SuzieQ schema to discover available tables and fields.

    This tool helps you find what data SuzieQ can query. Always call this
    BEFORE using suzieq_query to discover available tables, fields, and methods.

    Schema is loaded dynamically from OpenSearch suzieq-schema index.

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
    # Load schema dynamically from OpenSearch
    suzieq_schema = await _schema_loader.load_suzieq_schema()

    # Simple keyword matching
    keywords = query.lower().split()
    matching_tables = [
        table
        for table in suzieq_schema
        if any(
            keyword in table.lower() or keyword in suzieq_schema[table]["description"].lower()
            for keyword in keywords
        )
    ]

    if not matching_tables:
        matching_tables = list(suzieq_schema.keys())[:5]  # Return top 5 if no match

    result: dict[str, Any] = {"tables": matching_tables}
    for table in matching_tables:
        result[table] = {
            **suzieq_schema[table],
            "methods": suzieq_schema[table].get("methods", ["get", "summarize"]),
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

    # Load schema dynamically
    suzieq_schema = await _schema_loader.load_suzieq_schema()

    # Check if table exists in schema
    if table not in suzieq_schema:
        return {
            "error": f"Unknown table '{table}'. Use suzieq_schema_search to discover available tables.",
            "available_tables": list(suzieq_schema.keys()),
            "table": table,
            "status": "SCHEMA_NOT_FOUND",
            "warning": "⛔ DO NOT fabricate data. This table does not exist in SuzieQ schema.",
        }

    # SuzieQ uses Hive-style partitioning:
    # Coalesced data: data/suzieq-parquet/coalesced/{table}/sqvers={version}/namespace={ns}/...
    # Raw data: data/suzieq-parquet/{table}/sqvers={version}/namespace={ns}/hostname={host}/*.parquet
    # Strategy: Try coalesced first, fallback to raw if coalesced is too old or empty
    coalesced_dir = parquet_dir / "coalesced" / table
    raw_dir = parquet_dir / table

    # Determine which directory to use
    table_dir = None
    use_raw_fallback = False

    if coalesced_dir.exists():
        # Check if coalesced data is fresh enough
        coalesced_files = list(coalesced_dir.rglob("*.parquet"))
        if coalesced_files:
            import time
            current_time = time.time()
            # Get the newest file modification time
            newest_mtime = max(f.stat().st_mtime for f in coalesced_files)
            age_hours = (current_time - newest_mtime) / 3600

            if age_hours <= max_age_hours:
                table_dir = coalesced_dir
            else:
                # Coalesced data is too old, try raw data
                use_raw_fallback = True
                logger.info(f"Coalesced data is {age_hours:.1f}h old, checking raw data...")

    if table_dir is None and raw_dir.exists():
        table_dir = raw_dir
        if use_raw_fallback:
            logger.info(f"Using raw data directory: {raw_dir}")

    if table_dir is None:
        table_dir = coalesced_dir if coalesced_dir.exists() else raw_dir

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
        original_count = len(df)
        latest_timestamp_ms = None
        if max_age_hours > 0 and "timestamp" in df.columns:
            import time

            current_time_ms = int(time.time() * 1000)
            cutoff_time_ms = current_time_ms - (max_age_hours * 3600 * 1000)
            latest_timestamp_ms = df["timestamp"].max() if len(df) > 0 else None
            df = df[df["timestamp"] >= cutoff_time_ms]
            logger.info(f"Filtered to last {max_age_hours} hours: {len(df)} records remain")

            # Check if time filtering removed all data
            if len(df) == 0 and original_count > 0 and latest_timestamp_ms is not None:
                data_age_hours = (current_time_ms - latest_timestamp_ms) / (1000 * 3600)
                return {
                    "data": [
                        {
                            "status": "DATA_TOO_OLD",
                            "message": f"Table '{table}' has {original_count} records, but all are older than {max_age_hours} hours",
                            "data_age_hours": round(data_age_hours, 1),
                            "hint": f"Data is {round(data_age_hours, 1)} hours old. Try setting max_age_hours={int(data_age_hours) + 1} or max_age_hours=0 for all historical data.",
                            "suggestion": "Call suzieq_query again with a larger max_age_hours value",
                        }
                    ],
                    "count": 0,
                    "columns": ["status", "message", "data_age_hours", "hint", "suggestion"],
                    "table": table,
                    "original_count": original_count,
                    "max_age_hours_used": max_age_hours,
                }

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
