"""
SuzieQ Tool - BaseTool implementation with adapter integration.

Refactored to implement BaseTool protocol and use SuzieqAdapter for
standardized ToolOutput returns.
"""

import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from olav.tools.adapters import SuzieqAdapter
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


# SuzieQ schema metadata
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


class SuzieQTool:
    """
    SuzieQ query tool - BaseTool implementation.

    Provides access to SuzieQ network telemetry data with:
    - Direct Parquet file reading (no suzieq library dependency)
    - Automatic deduplication (latest state)
    - Time-window filtering (default: 24 hours)
    - Standardized ToolOutput via SuzieqAdapter

    Attributes:
        name: Tool identifier
        description: Tool purpose description
        parquet_dir: Path to SuzieQ Parquet files
    """

    name = "suzieq_query"
    description = """Query SuzieQ historical network data from Parquet files.

    Use this tool to access network device state collected by SuzieQ.
    Supports tables: bgp, interfaces, routes, ospf, lldp, macs, arpnd, device.

    Default behavior: Returns only last 24 hours of data to avoid stale records.
    """

    def __init__(self, parquet_dir: Path | None = None) -> None:
        """
        Initialize SuzieQTool.

        Args:
            parquet_dir: Path to SuzieQ Parquet directory (default: data/suzieq-parquet)
        """
        self.parquet_dir = parquet_dir or Path("data/suzieq-parquet")
        if not self.parquet_dir.exists():
            logger.warning(f"SuzieQ parquet directory not found: {self.parquet_dir}")

    async def execute(
        self,
        table: str,
        method: Literal["get", "summarize"] = "get",
        hostname: str | None = None,
        namespace: str | None = None,
        max_age_hours: int = 24,
        **filters: Any,
    ) -> ToolOutput:
        """
        Execute SuzieQ query and return standardized output.

        Args:
            table: Table name (bgp, interfaces, routes, etc.)
            method: Query method (get=raw data, summarize=aggregated)
            hostname: Filter by specific hostname
            namespace: Filter by namespace (default: all)
            max_age_hours: Maximum data age in hours (0=all historical data)
            **filters: Additional field filters (e.g., state="up")

        Returns:
            ToolOutput with normalized data via SuzieqAdapter
        """
        metadata = {
            "table": table,
            "method": method,
            "max_age_hours": max_age_hours,
            "filters": filters,
        }

        # Validate table exists in schema
        if table not in SUZIEQ_SCHEMA:
            return ToolOutput(
                source="suzieq",
                device=hostname or "multi",
                data=[
                    {
                        "status": "SCHEMA_ERROR",
                        "message": f"Unknown table '{table}'",
                        "available_tables": list(SUZIEQ_SCHEMA.keys()),
                    }
                ],
                metadata=metadata,
                error=f"Table '{table}' not in schema",
            )

        # Find table directory (prefer coalesced for performance)
        table_dir = self.parquet_dir / "coalesced" / table
        if not table_dir.exists():
            table_dir = self.parquet_dir / table

        if not table_dir.exists():
            return ToolOutput(
                source="suzieq",
                device=hostname or "multi",
                data=[
                    {
                        "status": "NO_DATA",
                        "message": f"No data directory for table '{table}'",
                        "hint": "SuzieQ has not collected data for this table",
                    }
                ],
                metadata=metadata,
            )

        try:
            # Read Parquet files
            df = self._read_parquet_table(table_dir)

            if df is None or df.empty:
                return SuzieqAdapter.adapt(
                    dataframe=None, device=hostname or "multi", metadata=metadata
                )

            # Apply time window filter
            if max_age_hours > 0 and "timestamp" in df.columns:
                df = self._filter_by_time_window(df, max_age_hours)

            # Apply hostname filter
            if hostname and "hostname" in df.columns:
                df = df[df["hostname"] == hostname]

            # Apply namespace filter
            if namespace and namespace != "all" and "namespace" in df.columns:
                df = df[df["namespace"] == namespace]

            # Apply additional filters
            for field, value in filters.items():
                if field in df.columns:
                    df = df[df[field] == value]

            # Deduplicate to latest state
            df = self._deduplicate_latest_state(df, table)

            # Execute method
            if method == "summarize":
                df = self._summarize_dataframe(df)
            # Limit rows to avoid token overflow
            elif len(df) > 100:
                df = df.head(100)
                metadata["truncated"] = True
                metadata["original_count"] = len(df)

            # Use adapter to convert to ToolOutput
            return SuzieqAdapter.adapt(dataframe=df, device=hostname or "multi", metadata=metadata)

        except Exception as e:
            logger.exception(f"SuzieQ query failed: {e}")
            return ToolOutput(
                source="suzieq",
                device=hostname or "multi",
                data=[],
                metadata=metadata,
                error=f"Query execution failed: {e}",
            )

    def _read_parquet_table(self, table_dir: Path) -> pd.DataFrame | None:
        """Read all Parquet files in table directory."""
        parquet_files = list(table_dir.rglob("*.parquet"))
        if not parquet_files:
            return None

        try:
            # Try PyArrow dataset API (better Hive partition support)
            import pyarrow.dataset as ds

            dataset = ds.dataset(str(table_dir), format="parquet", partitioning="hive")
            return dataset.to_table().to_pandas()
        except Exception:
            # Fallback to manual concatenation
            dfs = [pd.read_parquet(f) for f in parquet_files]
            return pd.concat(dfs, ignore_index=True)

    def _filter_by_time_window(self, df: pd.DataFrame, max_age_hours: int) -> pd.DataFrame:
        """Filter DataFrame to recent time window."""
        import time

        current_time_ms = int(time.time() * 1000)
        cutoff_time_ms = current_time_ms - (max_age_hours * 3600 * 1000)

        filtered = df[df["timestamp"] >= cutoff_time_ms]
        logger.info(
            f"Time window filter: {len(filtered)}/{len(df)} records (last {max_age_hours}h)"
        )
        return filtered

    def _deduplicate_latest_state(self, df: pd.DataFrame, table: str) -> pd.DataFrame:
        """Deduplicate by keeping latest timestamp for each entity."""
        # Prioritize active=True records
        if "active" in df.columns:
            df_active = df[df["active"]]
            if not df_active.empty:
                df = df_active

        # Define unique key columns per table
        unique_keys = {
            "bgp": ["hostname", "peer", "afi", "safi"],
            "interfaces": ["hostname", "ifname"],
            "routes": ["hostname", "vrf", "prefix"],
            "lldp": ["hostname", "ifname"],
            "device": ["hostname"],
        }

        key_cols = unique_keys.get(table, ["hostname"])

        if "timestamp" in df.columns and all(col in df.columns for col in key_cols):
            df = df.sort_values("timestamp", ascending=False)
            df = df.drop_duplicates(subset=key_cols, keep="first")

        return df

    def _summarize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate summary statistics from DataFrame."""
        summary = {}

        # Count by common state/status fields
        for field in ["state", "adminState", "type", "status"]:
            if field in df.columns:
                counts = df[field].value_counts().to_dict()
                summary[f"{field}_counts"] = counts

        summary["total_records"] = len(df)

        if "hostname" in df.columns:
            summary["unique_hosts"] = df["hostname"].nunique()

        # Convert summary dict to single-row DataFrame
        return pd.DataFrame([summary])


class SuzieQSchemaSearchTool:
    """
    SuzieQ schema discovery tool.

    Helps LLM discover available tables and fields before querying.
    """

    name = "suzieq_schema_search"
    description = """Search SuzieQ schema to discover available tables and fields.

    Use this tool BEFORE suzieq_query to find out what tables exist
    and what fields they contain.
    """

    async def execute(self, query: str) -> ToolOutput:
        """
        Search schema by keywords.

        Args:
            query: Natural language query (e.g., "BGP information")

        Returns:
            ToolOutput with matching tables and their metadata
        """
        keywords = query.lower().split()

        # Find matching tables
        matches = []
        for table, schema in SUZIEQ_SCHEMA.items():
            if any(kw in table.lower() or kw in schema["description"].lower() for kw in keywords):
                matches.append(
                    {
                        "table": table,
                        "fields": schema["fields"],
                        "description": schema["description"],
                        "methods": ["get", "summarize"],
                    }
                )

        # If no matches, return all tables
        if not matches:
            matches = [
                {
                    "table": table,
                    "fields": schema["fields"],
                    "description": schema["description"],
                    "methods": ["get", "summarize"],
                }
                for table, schema in list(SUZIEQ_SCHEMA.items())[:5]
            ]

        return ToolOutput(
            source="suzieq_schema",
            device="localhost",
            data=matches,
            metadata={"query": query, "total_tables": len(SUZIEQ_SCHEMA)},
        )


# Register tools with ToolRegistry
ToolRegistry.register(SuzieQTool())
ToolRegistry.register(SuzieQSchemaSearchTool())
