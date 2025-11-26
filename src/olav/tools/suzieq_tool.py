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
            "filters": filters,
        }

        # Load schema dynamically
        suzieq_schema = await self.schema_loader.load_suzieq_schema()

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


# Register tools with ToolRegistry
ToolRegistry.register(SuzieQTool())
ToolRegistry.register(SuzieQSchemaSearchTool())
