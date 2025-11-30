"""Syslog search tool for event-driven diagnostics.

This module provides a tool to search network device syslog messages stored
in OpenSearch. It enables event-driven fault diagnosis by correlating log
events with SuzieQ historical data.

Usage:
    - Find fault trigger events (LINK-DOWN, BGP-NEIGHBOR-LOST)
    - Correlate with SuzieQ time windows for root cause analysis
    - Verify configuration change effects (CONFIG_CHANGE events)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.tools import tool

from olav.core.memory import OpenSearchMemory
from olav.tools.base import BaseTool, ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)

# Index name for syslog storage
SYSLOG_INDEX = "syslog-raw"

# Common syslog keywords for network events
SYSLOG_KEYWORDS = {
    "link": ["DOWN", "UP", "UPDOWN", "LINK", "CARRIER", "INTERFACE"],
    "bgp": ["BGP", "ADJCHANGE", "NEIGHBOR", "NOTIFICATION", "PEER"],
    "ospf": ["OSPF", "ADJACENCY", "NEIGHBOR", "NBRSTATE"],
    "config": ["CONFIG", "COMMIT", "CONFIGURATION", "CHANGE"],
    "hardware": ["MEMORY", "CPU", "TEMPERATURE", "FAN", "POWER", "SENSOR"],
    "auth": ["AUTH", "LOGIN", "FAILED", "DENIED", "ACCESS"],
}


class SyslogSearchTool(BaseTool):
    """Search device syslog for event-driven diagnostics.

    Use this tool to find fault trigger events and correlate them with
    network state changes detected by SuzieQ.

    Typical workflow:
        1. Use suzieq_query to identify anomaly time window
        2. Use syslog_search to find trigger events in that window
        3. Correlate log events with metric changes for root cause
    """

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize syslog search tool.

        Args:
            memory: OpenSearch memory instance. If None, creates new instance.
        """
        self._name = "syslog_search"
        self._description = (
            "Search device Syslog logs for event-driven diagnostics. "
            "Use after suzieq_query identifies an anomaly time window. "
            "Searches raw log messages by keyword, device IP, and time range. "
            "Common keywords: DOWN, BGP, OSPF, CONFIG, LINK, NEIGHBOR."
        )
        self._memory = memory

    @property
    def name(self) -> str:
        """Tool name for registration."""
        return self._name

    @property
    def description(self) -> str:
        """Tool description for LLM."""
        return self._description

    @property
    def memory(self) -> OpenSearchMemory:
        """Lazy-load OpenSearch memory to avoid connection at import."""
        if self._memory is None:
            self._memory = OpenSearchMemory()
        return self._memory

    async def execute(
        self,
        keyword: str,
        device_ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        severity: str | None = None,
        facility: str | None = None,
        limit: int = 50,
    ) -> ToolOutput:
        """Search syslog for matching events.

        Args:
            keyword: Text to search in log messages. Use | for OR queries.
                    Examples: "BGP", "DOWN", "LINK|INTERFACE", "CONFIG_CHANGE"
            device_ip: Filter by device IP address (optional).
                      Example: "10.0.0.1"
            start_time: Start of time range. Supports:
                       - ISO 8601: "2025-11-29T02:00:00Z"
                       - Relative: "now-1h", "now-30m", "now-1d"
            end_time: End of time range (same formats as start_time).
                     Default: "now"
            severity: Filter by syslog severity (optional).
                     Values: "emerg", "alert", "crit", "err", "warning",
                            "notice", "info", "debug"
            facility: Filter by syslog facility (optional).
                     Values: "kern", "user", "daemon", "local0"-"local7", etc.
            limit: Maximum results to return (default: 50, max: 500)

        Returns:
            ToolOutput with matching log entries, each containing:
            - timestamp: Log timestamp
            - device_ip: Source device IP
            - severity: Log severity level
            - message: Raw log message text

        Examples:
            # Find BGP events in last hour
            >>> await tool.execute(keyword="BGP", start_time="now-1h")

            # Find errors on specific device
            >>> await tool.execute(
            ...     keyword="DOWN",
            ...     device_ip="10.0.0.1",
            ...     severity="err"
            ... )

            # Correlate with SuzieQ anomaly window
            >>> await tool.execute(
            ...     keyword="LINK|INTERFACE",
            ...     start_time="2025-11-29T02:00:00Z",
            ...     end_time="2025-11-29T03:00:00Z"
            ... )
        """
        start_perf = time.perf_counter()

        # Validate and clamp limit
        limit = min(max(1, limit), 500)

        # Validate keyword
        if not keyword or not keyword.strip():
            return ToolOutput(
                source=self.name,
                device=device_ip or "all",
                data=[],
                metadata={"elapsed_ms": 0},
                error="Keyword parameter cannot be empty",
            )

        try:
            # Build OpenSearch query
            query = self._build_query(
                keyword=keyword,
                device_ip=device_ip,
                start_time=start_time,
                end_time=end_time,
                severity=severity,
                facility=facility,
            )

            # Execute search
            results = await self.memory.search_schema(
                index=SYSLOG_INDEX,
                query=query,
                size=limit,
            )

            elapsed_ms = int((time.perf_counter() - start_perf) * 1000)

            # Format results for readability
            # Note: Field names adapted for Fluent Bit output format
            formatted = [
                {
                    "timestamp": r.get("@timestamp"),
                    "device_ip": r.get("device_ip") or r.get("host"),  # Fluent Bit uses "host"
                    "severity": r.get("severity") or r.get("pri"),  # Fluent Bit uses "pri"
                    "facility": r.get("facility"),
                    "program": r.get("program"),
                    "message": r.get("message")
                    or r.get("raw_message"),  # Fluent Bit uses "message"
                }
                for r in results
            ]

            return ToolOutput(
                source=self.name,
                device=device_ip or "all",
                data=formatted,
                metadata={
                    "keyword": keyword,
                    "result_count": len(formatted),
                    "time_range": {
                        "start": start_time,
                        "end": end_time or "now",
                    },
                    "elapsed_ms": elapsed_ms,
                },
                error=None,
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_perf) * 1000)
            logger.exception("Syslog search failed")

            # Check if index doesn't exist
            error_msg = str(e)
            if "index_not_found" in error_msg.lower() or "no such index" in error_msg.lower():
                error_msg = (
                    f"Syslog index '{SYSLOG_INDEX}' not found. "
                    "Run 'python -m olav.etl.init_syslog_index' to create it."
                )

            return ToolOutput(
                source=self.name,
                device=device_ip or "unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms},
                error=f"Syslog search error: {error_msg}",
            )

    def _build_query(
        self,
        keyword: str,
        device_ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        severity: str | None = None,
        facility: str | None = None,
    ) -> dict[str, Any]:
        """Build OpenSearch query from search parameters.

        Handles:
        - OR queries with | separator (e.g., "BGP|OSPF")
        - Time range with OpenSearch date math
        - Multiple filter conditions
        """
        # Handle OR queries in keyword
        # Note: Use "message" field (Fluent Bit output) instead of "raw_message" (rsyslog output)
        if "|" in keyword:
            # Multiple keywords with OR
            keywords = [k.strip() for k in keyword.split("|") if k.strip()]
            must_clause = {
                "bool": {
                    "should": [{"match": {"message": k}} for k in keywords],
                    "minimum_should_match": 1,
                }
            }
        else:
            # Single keyword
            must_clause = {"match": {"message": keyword}}

        # Build bool query
        query: dict[str, Any] = {
            "bool": {
                "must": [must_clause],
            }
        }

        # Add filters
        filters = []

        if device_ip:
            filters.append({"term": {"device_ip": device_ip}})

        if severity:
            filters.append({"term": {"severity": severity.lower()}})

        if facility:
            filters.append({"term": {"facility": facility.lower()}})

        if start_time or end_time:
            time_range: dict[str, str] = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            else:
                time_range["lte"] = "now"
            filters.append({"range": {"@timestamp": time_range}})

        if filters:
            query["bool"]["filter"] = filters

        return query


# Register tool with registry
ToolRegistry.register(SyslogSearchTool())


# ---------------------------------------------------------------------------
# Compatibility Wrapper (@tool) for existing workflows
# ---------------------------------------------------------------------------


@tool
async def syslog_search(
    keyword: str,
    device_ip: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search device Syslog logs for event-driven diagnostics.

    Use after suzieq_query to find the trigger event for an anomaly.
    This tool searches raw syslog messages stored in OpenSearch.

    Args:
        keyword: Text to search in log messages (e.g., "BGP", "LINK-DOWN", "CONFIG").
                Use | for OR queries: "BGP|OSPF|DOWN"
        device_ip: Filter by device IP address (optional)
        start_time: Start time - ISO 8601 ("2025-11-29T02:00:00Z") or relative ("now-1h")
        end_time: End time - same formats as start_time (default: "now")
        severity: Filter by severity (emerg, alert, crit, err, warning, notice, info, debug)
        limit: Maximum results to return (default: 50)

    Returns:
        Dict with success status, data (list of log entries), and metadata.

    Examples:
        # Find BGP events in last hour
        syslog_search(keyword="BGP", start_time="now-1h")

        # Find errors on specific device
        syslog_search(keyword="DOWN", device_ip="10.0.0.1", severity="err")

        # Correlate with SuzieQ anomaly window
        syslog_search(
            keyword="LINK|INTERFACE",
            start_time="2025-11-29T02:00:00Z",
            end_time="2025-11-29T03:00:00Z"
        )

        # Find configuration changes
        syslog_search(keyword="CONFIG|COMMIT", start_time="now-24h")

    Common Keywords by Category:
        - Link events: DOWN, UP, LINK, CARRIER, INTERFACE
        - BGP events: BGP, ADJCHANGE, NEIGHBOR, NOTIFICATION
        - OSPF events: OSPF, ADJACENCY, NBRSTATE
        - Config events: CONFIG, COMMIT, CHANGE
        - Hardware: MEMORY, CPU, TEMPERATURE, FAN
    """
    impl = ToolRegistry.get_tool("syslog_search")
    if impl is None:
        return {"success": False, "error": "syslog_search tool not registered"}

    result = await impl.execute(
        keyword=keyword,
        device_ip=device_ip,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        limit=limit,
    )

    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }


# Utility function to get suggested keywords
def get_syslog_keywords(category: str | None = None) -> dict[str, list[str]]:
    """Get common syslog keywords for network events.

    Args:
        category: Optional category to filter (link, bgp, ospf, config, hardware, auth)

    Returns:
        Dict mapping category to list of keywords
    """
    if category:
        return {category: SYSLOG_KEYWORDS.get(category, [])}
    return SYSLOG_KEYWORDS
