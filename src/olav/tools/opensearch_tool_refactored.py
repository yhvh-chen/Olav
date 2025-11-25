"""OpenSearch RAG tools refactored to BaseTool protocol.

This module provides OpenSearch-based tools for schema and episodic memory search.
All tools implement the BaseTool protocol and return standardized ToolOutput.
"""

from __future__ import annotations

import logging
import time

from olav.core.memory import OpenSearchMemory
from olav.tools.adapters import OpenSearchAdapter
from olav.tools.base import BaseTool, ToolOutput

logger = logging.getLogger(__name__)


class OpenConfigSchemaTool(BaseTool):
    """Search OpenConfig YANG schema for XPaths matching user intent.

    Uses OpenSearch to query the openconfig-schema index built from YANG models.
    Returns matching XPaths with descriptions, types, and examples.
    """

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize OpenConfig schema search tool.

        Args:
            memory: OpenSearch memory instance. If None, creates new instance.
        """
        self._name = "openconfig_schema_search"
        self._description = (
            "Search OpenConfig YANG schema for XPaths matching user intent. "
            "Use this tool to find OpenConfig XPaths for configuration tasks. "
            "It searches the openconfig-schema index built from YANG models."
        )
        self._memory = memory
        self._adapter = OpenSearchAdapter()

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
        intent: str,
        device_type: str = "network-instance",
        max_results: int = 5,
    ) -> ToolOutput:
        """Search OpenConfig schema for XPaths matching intent.

        Args:
            intent: Natural language description of what you want to configure.
                   Examples: "change BGP router ID", "add VLAN interface", "configure OSPF area"
            device_type: OpenConfig module type (network-instance, interfaces, routing-policy)
            max_results: Maximum number of results to return (default: 5)

        Returns:
            ToolOutput with matching XPaths, descriptions, types, and examples.

        Example:
            >>> result = await tool.execute("configure BGP AS number", "network-instance")
            >>> result.data
            [
                {
                    "xpath": "/network-instances/.../bgp/global/config/as",
                    "description": "Local autonomous system number",
                    "type": "uint32",
                    "example": {"as": 65000}
                }
            ]
        """
        start_time = time.perf_counter()

        # Validate parameters
        if not intent or not intent.strip():
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": 0},
                error="Intent parameter cannot be empty",
            )

        try:
            # Build OpenSearch query (semantic match on description + filter by module)
            query = {
                "bool": {
                    "must": [
                        {"match": {"description": intent}},
                        {"term": {"module": device_type}},
                    ],
                },
            }

            # Execute search
            results = await self.memory.search_schema(
                index="openconfig-schema",
                query=query,
                size=max_results,
            )

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Use OpenSearchAdapter to normalize results
            return self._adapter.adapt(
                opensearch_hits=results,
                index="openconfig-schema",
                metadata={
                    "intent": intent,
                    "device_type": device_type,
                    "result_count": len(results),
                    "elapsed_ms": elapsed_ms,
                },
                error=None,
            )

        except ConnectionError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms},
                error=f"OpenSearch connection failed: {e}",
            )

        except TimeoutError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms},
                error=f"OpenSearch query timeout: {e}",
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("OpenConfig schema search failed")
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "schema_error"},
                error=f"Schema search error: {e}",
            )


class EpisodicMemoryTool(BaseTool):
    """Search episodic memory for previously successful intent→XPath mappings.

    Queries the olav-episodic-memory index for historical success patterns.
    Use this BEFORE OpenConfigSchemaTool to leverage past experience.
    """

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize episodic memory search tool.

        Args:
            memory: OpenSearch memory instance. If None, creates new instance.
        """
        self._name = "episodic_memory_search"
        self._description = (
            "Search episodic memory for previously successful intent→XPath mappings. "
            "This searches the learning index for historical success patterns. "
            "Use this BEFORE search_openconfig_schema to leverage past experience."
        )
        self._memory = memory
        self._adapter = OpenSearchAdapter()

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
        intent: str,
        max_results: int = 3,
        only_successful: bool = True,
    ) -> ToolOutput:
        """Search episodic memory for historical intent→XPath mappings.

        Args:
            intent: User intent to search for (natural language).
            max_results: Maximum number of results to return (default: 3).
            only_successful: Only return successful historical mappings (default: True).

        Returns:
            ToolOutput with historical mappings including intent, xpath, success status, context.

        Example:
            >>> result = await tool.execute("configure BGP neighbor")
            >>> result.data
            [
                {
                    "intent": "add BGP neighbor 192.168.1.1 AS 65001",
                    "xpath": "/network-instances/.../neighbors/neighbor[neighbor-address=192.168.1.1]/config",
                    "success": true,
                    "context": {"device": "router1", "timestamp": "2024-01-15T10:30:00Z"}
                }
            ]
        """
        start_time = time.perf_counter()

        # Validate parameters
        if not intent or not intent.strip():
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": 0},
                error="Intent parameter cannot be empty",
            )

        try:
            # Build OpenSearch query (semantic match on intent + filter by success)
            query_parts = [{"match": {"intent": intent}}]
            if only_successful:
                query_parts.append({"term": {"success": True}})

            query = {"bool": {"must": query_parts}}

            # Execute search
            results = await self.memory.search_schema(
                index="olav-episodic-memory",
                query=query,
                size=max_results,
            )

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Use OpenSearchAdapter to normalize results
            return self._adapter.adapt(
                opensearch_hits=results,
                index="olav-episodic-memory",
                metadata={
                    "intent": intent,
                    "only_successful": only_successful,
                    "result_count": len(results),
                    "elapsed_ms": elapsed_ms,
                },
                error=None,
            )

        except ConnectionError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "connection_error"},
                error=f"OpenSearch connection failed: {e}",
            )

        except TimeoutError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "timeout_error"},
                error=f"OpenSearch query timeout: {e}",
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Episodic memory search failed")
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "schema_error"},
                error=f"Memory search error: {e}",
            )


# Tools are auto-registered on module import but can be created independently for testing
# _openconfig_tool = OpenConfigSchemaTool()
# _episodic_tool = EpisodicMemoryTool()
