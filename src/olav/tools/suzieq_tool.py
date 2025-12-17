"""
SuzieQ Tool - BaseTool implementation with Schema-Aware architecture.

Dynamically loads schema from OpenSearch instead of hardcoded dictionaries.
Uses SuzieqAdapter for standardized ToolOutput returns.
"""

import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from olav.core.schema_loader import get_schema_loader
from olav.tools.adapters import SuzieqAdapter
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


class SuzieQTool:
    """
    SuzieQ query tool - Schema-Aware BaseTool implementation.

    Provides access to SuzieQ network telemetry data with:
    - Dynamic schema loading from OpenSearch
    - Direct Parquet file reading (no suzieq library dependency)
    - Automatic deduplication (latest state)
    - Time-window filtering (default: 24 hours)
    - Standardized ToolOutput via SuzieqAdapter

    Attributes:
        name: Tool identifier
        description: Tool purpose description
        parquet_dir: Path to SuzieQ Parquet files
        schema_loader: Dynamic schema loader instance
    """

    name = "suzieq_query"
    description = """Query SuzieQ historical network data from Parquet files.

    Use this tool to access network device state collected by SuzieQ.
    Schema is discovered dynamically - use suzieq_schema_search first.

    Default behavior: Returns only last 24 hours of data to avoid stale records.
    """

    def __init__(self, parquet_dir: Path | None = None) -> None:
        """
        Initialize SuzieQTool.

        Args:
            parquet_dir: Path to SuzieQ Parquet directory (default: data/suzieq-parquet)
        """
        self.parquet_dir = parquet_dir or Path("data/suzieq-parquet")
        self.schema_loader = get_schema_loader()
        if not self.parquet_dir.exists():
            logger.warning(f"SuzieQ parquet directory not found: {self.parquet_dir}")

    async def execute(
        self,
        table: str,
        method: Literal["get", "summarize"] = "get",
        hostname: str | None = None,
        namespace: str | None = None,
        max_age_hours: int = 24,
        max_age_seconds: int | None = None,
        **filters: Any,
    ) -> ToolOutput:
        """
        Execute SuzieQ query and return standardized output.

        Args:
            table: Table name (use suzieq_schema_search to discover)
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
            "max_age_seconds": max_age_seconds,
            "filters": filters,
        }

        # Resolve effective time window
        effective_max_age_seconds: int = 0
        if max_age_seconds is not None:
            effective_max_age_seconds = int(max_age_seconds)
        elif max_age_hours > 0:
            effective_max_age_seconds = int(max_age_hours) * 3600
        else:
            effective_max_age_seconds = 0

        metadata["max_age_seconds_used"] = effective_max_age_seconds

        # Load schema dynamically
        suzieq_schema = await self.schema_loader.load_suzieq_schema()

        # Normalize common table name variations (LLM may return singular)
        table_aliases = {
            "interface": "interfaces",
            "route": "routes",
            "mac": "macs",
            "vlan": "vlans",
            "neighbor": "ospfNbr",
            "ospfNeighbor": "ospfNbr",
            "ospf_neighbor": "ospfNbr",
            "ospf_interface": "ospfIf",
            "ospfInterface": "ospfIf",
        }
        if table in table_aliases:
            logger.info(f"Normalizing table name: {table} -> {table_aliases[table]}")
            table = table_aliases[table]
            metadata["table"] = table  # Update metadata with normalized name

        # Validate table exists in schema
        if table not in suzieq_schema:
            return ToolOutput(
                source="suzieq",
                device=hostname or "multi",
                data=[
                    {
                        "status": "SCHEMA_ERROR",
                        "message": f"Unknown table '{table}'",
                        "available_tables": list(suzieq_schema.keys()),
                    }
                ],
                metadata=metadata,
                error=f"Table '{table}' not in schema",
            )

        # Find table directory
        # Strategy: Prefer coalesced first (it contains merged/full state).
        # Do NOT use filesystem mtime as a freshness signal: on some platforms/bind mounts
        # (notably Windows), file mtimes can be misleading. We rely on the `timestamp`
        # column time-window filter below and only fall back to raw if coalesced yields
        # no usable records.
        coalesced_dir = self.parquet_dir / "coalesced" / table
        raw_dir = self.parquet_dir / table

        table_dir: Path | None = None

        if coalesced_dir.exists() and list(coalesced_dir.rglob("*.parquet")):
            table_dir = coalesced_dir
        elif raw_dir.exists() and list(raw_dir.rglob("*.parquet")):
            table_dir = raw_dir
        else:
            # Keep backward-compat behavior for error reporting below.
            table_dir = coalesced_dir if coalesced_dir.exists() else raw_dir

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
                # Check if directory exists but has no parquet files
                parquet_files = list(table_dir.rglob("*.parquet"))
                if not parquet_files:
                    return ToolOutput(
                        source="suzieq",
                        device=hostname or "multi",
                        data=[
                            {
                                "status": "NO_PARQUET_FILES",
                                "message": f"Table '{table}' directory exists but contains no parquet files",
                                "hint": f"SuzieQ has not yet collected {table} data. Run SuzieQ collector to populate.",
                                "directory": str(table_dir),
                            }
                        ],
                        metadata=metadata,
                    )
                return SuzieqAdapter.adapt(
                    dataframe=None, device=hostname or "multi", metadata=metadata
                )

            # Apply time window filter (seconds-based)
            original_count = len(df)
            dataset_used = "coalesced" if table_dir == coalesced_dir else "raw"
            coalesced_latest_ms: int | None = None
            raw_latest_ms: int | None = None

            if "timestamp" in df.columns and len(df) > 0:
                if dataset_used == "coalesced":
                    coalesced_latest_ms = int(df["timestamp"].max())
                else:
                    raw_latest_ms = int(df["timestamp"].max())

            if effective_max_age_seconds > 0 and "timestamp" in df.columns:
                df = self._filter_by_time_window_seconds(df, effective_max_age_seconds)

                # If coalesced exists but yields no recent rows, try raw as a fallback.
                if (
                    len(df) == 0
                    and table_dir == coalesced_dir
                    and raw_dir.exists()
                    and list(raw_dir.rglob("*.parquet"))
                ):
                    logger.info(
                        "Coalesced table '%s' produced no rows within %ss; falling back to raw",
                        table,
                        effective_max_age_seconds,
                    )
                    raw_df = self._read_parquet_table(raw_dir)
                    if raw_df is None or raw_df.empty:
                        df = pd.DataFrame()
                    else:
                        original_count = len(raw_df)
                        raw_latest_ms = (
                            int(raw_df["timestamp"].max())
                            if "timestamp" in raw_df.columns and len(raw_df) > 0
                            else None
                        )
                        df = raw_df
                        dataset_used = "raw"
                        if effective_max_age_seconds > 0 and "timestamp" in df.columns:
                            df = self._filter_by_time_window_seconds(df, effective_max_age_seconds)

            # Enrich metadata about dataset selection and freshness
            metadata["dataset_used"] = dataset_used
            metadata["coalesced_latest_timestamp_ms"] = coalesced_latest_ms
            metadata["raw_latest_timestamp_ms"] = raw_latest_ms

            # Check if time filtering removed all data
            if len(df) == 0 and original_count > 0 and (coalesced_latest_ms or raw_latest_ms):
                import time as time_module

                current_time_ms = int(time_module.time() * 1000)
                latest_ms = coalesced_latest_ms or raw_latest_ms
                data_age_seconds = (current_time_ms - int(latest_ms)) / 1000
                data_age_hours = data_age_seconds / 3600

                coalesced_age_hours: float | None = None
                raw_age_hours: float | None = None
                if coalesced_latest_ms is not None:
                    coalesced_age_hours = (current_time_ms - int(coalesced_latest_ms)) / 1000 / 3600
                if raw_latest_ms is not None:
                    raw_age_hours = (current_time_ms - int(raw_latest_ms)) / 1000 / 3600

                window_desc = (
                    f"{effective_max_age_seconds} seconds"
                    if effective_max_age_seconds > 0
                    else "all history"
                )
                return ToolOutput(
                    source="suzieq",
                    device=hostname or "multi",
                    data=[
                        {
                            "status": "DATA_TOO_OLD",
                            "message": f"Table '{table}' has {original_count} records, but none are within the last {window_desc}",
                            "data_age_hours": round(data_age_hours, 2),
                            "coalesced_age_hours": round(coalesced_age_hours, 2) if coalesced_age_hours is not None else None,
                            "raw_age_hours": round(raw_age_hours, 2) if raw_age_hours is not None else None,
                            "hint": "This usually means the poller/coalescer is not producing fresh data for this table/device.",
                            "suggestion": "Check suzieq-poller logs and verify inventory connectivity.",
                        }
                    ],
                    metadata={
                        **metadata,
                        "original_count": original_count,
                    },
                )

            # Apply hostname filter (handle both single string and list of hostnames)
            if hostname and "hostname" in df.columns:
                if isinstance(hostname, list):
                    df = df[df["hostname"].isin(hostname)]
                else:
                    df = df[df["hostname"] == hostname]

            # Apply namespace filter
            if namespace and namespace != "all" and "namespace" in df.columns:
                df = df[df["namespace"] == namespace]

            # Apply additional filters
            for field, value in filters.items():
                if field in df.columns:
                    df = df[df[field] == value]

            # Deduplicate to latest state
            df = await self._deduplicate_latest_state(df, table)

            # Execute method
            if method == "summarize":
                df = self._summarize_dataframe(df)
            # Limit rows to avoid token overflow
            elif len(df) > 100:
                df = df.head(100)
                metadata["truncated"] = True
                metadata["original_count"] = len(df)

            # Normalize hostname for adapter (must be string, not list)
            device_name = hostname
            if isinstance(hostname, list):
                device_name = ",".join(hostname) if hostname else "multi"
            elif not hostname:
                device_name = "multi"

            # Use adapter to convert to ToolOutput
            return SuzieqAdapter.adapt(dataframe=df, device=device_name, metadata=metadata)

        except Exception as e:
            logger.exception(f"SuzieQ query failed: {e}")
            # Normalize hostname for error response too
            device_name = hostname
            if isinstance(hostname, list):
                device_name = ",".join(hostname) if hostname else "multi"
            elif not hostname:
                device_name = "multi"
            return ToolOutput(
                source="suzieq",
                device=device_name,
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
        """Backward-compatible hours-based filter."""
        return self._filter_by_time_window_seconds(df, int(max_age_hours) * 3600)

    def _filter_by_time_window_seconds(self, df: pd.DataFrame, max_age_seconds: int) -> pd.DataFrame:
        """Filter DataFrame to recent time window (seconds)."""
        import time

        current_time_ms = int(time.time() * 1000)
        cutoff_time_ms = current_time_ms - (int(max_age_seconds) * 1000)

        filtered = df[df["timestamp"] >= cutoff_time_ms]
        logger.info(
            "Time window filter: %s/%s records (last %ss)",
            len(filtered),
            len(df),
            max_age_seconds,
        )
        return filtered

    async def _deduplicate_latest_state(self, df: pd.DataFrame, table: str) -> pd.DataFrame:
        """Deduplicate by keeping latest timestamp for each entity.

        Key fields are loaded dynamically from OpenSearch suzieq-schema-fields index.
        Falls back to sensible defaults if schema unavailable.
        """
        # Prioritize active=True records
        if "active" in df.columns:
            df_active = df[df["active"]]
            if not df_active.empty:
                df = df_active

        # Get key fields dynamically from schema
        key_cols = await self.schema_loader.get_key_fields(table)

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
    SuzieQ schema discovery tool - Schema-Aware implementation.

    Queries OpenSearch suzieq-schema index to discover available tables dynamically.
    """

    name = "suzieq_schema_search"
    description = """Search SuzieQ schema to discover available tables and fields.

    Use this tool BEFORE suzieq_query to find out what tables exist
    and what fields they contain. Schema is loaded dynamically from OpenSearch.
    """

    def __init__(self) -> None:
        """Initialize schema search tool."""
        self.schema_loader = get_schema_loader()

    async def execute(self, query: str) -> ToolOutput:
        """
        Search schema by keywords.

        Args:
            query: Natural language query (e.g., "BGP information")

        Returns:
            ToolOutput with matching tables and their metadata
        """
        # Load schema dynamically
        suzieq_schema = await self.schema_loader.load_suzieq_schema()

        keywords = query.lower().split()

        # Find matching tables
        matches = []
        for table, schema in suzieq_schema.items():
            if any(kw in table.lower() or kw in schema["description"].lower() for kw in keywords):
                matches.append(
                    {
                        "table": table,
                        "fields": schema["fields"],
                        "description": schema["description"],
                        "methods": schema.get("methods", ["get", "summarize"]),
                    }
                )

        # If no matches, return top 5 tables
        if not matches:
            matches = [
                {
                    "table": table,
                    "fields": schema["fields"],
                    "description": schema["description"],
                    "methods": schema.get("methods", ["get", "summarize"]),
                }
                for table, schema in list(suzieq_schema.items())[:5]
            ]

        return ToolOutput(
            source="suzieq_schema",
            device="localhost",
            data=matches,
            metadata={
                "query": query,
                "total_tables": len(suzieq_schema),
                "schema_source": "opensearch",
            },
        )


# =============================================================================
# Factory Functions for LangChain Tool Conversion
# =============================================================================


def create_suzieq_query_tool():
    """Create a LangChain-compatible SuzieQ query tool.

    Returns:
        LangChain tool for SuzieQ queries.
    """
    from langchain_core.tools import tool

    tool_instance = SuzieQTool()

    @tool
    async def suzieq_query(
        table: str,
        method: str = "get",
        hostname: str | None = None,
        namespace: str | None = None,
        max_age_hours: int = 24,
        max_age_seconds: int | None = None,
    ) -> dict:
        """Query SuzieQ historical network data from Parquet files.

        Use this tool to access network device state collected by SuzieQ.
        Schema is discovered dynamically - use suzieq_schema_search first.

        Args:
            table: Table name (e.g., 'bgp', 'interfaces', 'routes')
            method: Query method - 'get' for raw data, 'summarize' for aggregation
            hostname: Filter by specific device hostname
            namespace: Filter by namespace
            max_age_hours: Maximum data age in hours (default 24)

        Returns:
            Query results from SuzieQ Parquet data.
        """
        result = await tool_instance.execute(
            table=table,
            method=method,
            hostname=hostname,
            namespace=namespace,
            max_age_hours=max_age_hours,
            max_age_seconds=max_age_seconds,
        )
        return result.model_dump()

    return suzieq_query


def create_suzieq_schema_tool():
    """Create a LangChain-compatible SuzieQ schema search tool.

    Returns:
        LangChain tool for schema search.
    """
    from langchain_core.tools import tool

    tool_instance = SuzieQSchemaSearchTool()

    @tool
    async def suzieq_schema_search(query: str) -> dict:
        """Search SuzieQ schema to discover available tables and fields.

        Use this tool BEFORE suzieq_query to find out what tables exist
        and what fields they contain.

        Args:
            query: Natural language query describing what data you need
                   (e.g., "BGP information", "interface status", "routing table")

        Returns:
            Matching tables with their fields and descriptions.
        """
        result = await tool_instance.execute(query=query)
        return result.model_dump()

    return suzieq_schema_search


# Register tools with ToolRegistry
# SuzieQ is read-only (Parquet queries) - no HITL required
ToolRegistry.register(
    SuzieQTool(),
    requires_hitl=False,
    triggers=["bgp", "ospf", "interface", "route", "vlan", "mac", "lldp", "arp", "mlag", "网络状态", "邻居"],
    category="suzieq",
    aliases=["suzieq_query", "network_query"],
)
ToolRegistry.register(
    SuzieQSchemaSearchTool(),
    requires_hitl=False,
    triggers=["suzieq schema", "suzieq table", "suzieq 表"],
    category="suzieq",
)
