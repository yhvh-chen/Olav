"""OpenSearch RAG tools refactored to BaseTool protocol.

This module provides OpenSearch-based tools for schema and episodic memory search.
All tools implement the BaseTool protocol and return standardized ToolOutput.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.tools import tool

from olav.core.memory import OpenSearchMemory
from olav.tools.adapters import OpenSearchAdapter
from olav.tools.base import BaseTool, ToolOutput, ToolRegistry

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
            # Build OpenSearch query
            # If device_type is specified and looks like an OpenConfig module name,
            # use it as a filter. Otherwise just search by description.
            if device_type and device_type.startswith("openconfig-"):
                # Exact module match
                query = {
                    "bool": {
                        "must": [{"match": {"description": intent}}],
                        "filter": [{"term": {"module": device_type}}],
                    },
                }
            elif device_type and device_type in ("interfaces", "bgp", "vlan", "network-instance"):
                # Map common names to OpenConfig module prefixes
                module_prefix = f"openconfig-{device_type}"
                query = {
                    "bool": {
                        "must": [{"match": {"description": intent}}],
                        "filter": [{"prefix": {"module": module_prefix}}],
                    },
                }
            else:
                # Just search by description across all modules
                query = {
                    "bool": {
                        "must": [{"match": {"description": intent}}],
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


class MemoryStoreTool(BaseTool):
    """Store documents in OpenSearch indices for Agentic learning loop.
    
    This tool indexes diagnosis reports and other documents into OpenSearch
    for future retrieval by EpisodicMemoryTool (kb_search).
    
    Part of the Agentic closed-loop: Diagnosis → Index → Future Reference
    """
    
    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize memory store tool.
        
        Args:
            memory: OpenSearch memory instance. If None, creates new instance.
        """
        self._name = "memory_store"
        self._description = (
            "Store a document in OpenSearch episodic memory index. "
            "Use this to index successful diagnosis results for future reference. "
            "Enables Agentic learning loop: similar queries can retrieve past solutions."
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
        index: str,
        document: dict[str, Any],
        doc_id: str | None = None,
    ) -> ToolOutput:
        """Store a document in OpenSearch.
        
        Args:
            index: Target OpenSearch index (e.g., "olav-episodic-memory")
            document: Document to store (must be JSON-serializable dict)
            doc_id: Optional document ID. If None, OpenSearch generates one.
        
        Returns:
            ToolOutput with indexing result.
            
        Example:
            >>> result = await tool.execute(
            ...     index="olav-episodic-memory",
            ...     document={
            ...         "query": "R3 cannot access 10.0.100.100",
            ...         "root_cause": "BGP route-map blocks 10.0.0.0/16",
            ...         "layer": "L4",
            ...         "devices": ["R1", "R2"],
            ...         "timestamp": "2025-12-06T10:30:00Z"
            ...     },
            ...     doc_id="diag-20251206103000-1234"
            ... )
        """
        start_time = time.perf_counter()
        
        # Validate parameters
        if not index or not index.strip():
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": 0},
                error="Index parameter cannot be empty",
            )
        
        if not document or not isinstance(document, dict):
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": 0},
                error="Document must be a non-empty dictionary",
            )
        
        try:
            # Index document
            result = await self.memory.index_document(
                index=index,
                document=document,
                doc_id=doc_id,
            )
            
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[{
                    "indexed": True,
                    "index": index,
                    "doc_id": result.get("_id", doc_id),
                    "result": result.get("result", "created"),
                }],
                metadata={
                    "index": index,
                    "doc_id": doc_id,
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
        
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Memory store failed")
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "index_error"},
                error=f"Memory store error: {e}",
            )


# Register tools with registry for compatibility layer
ToolRegistry.register(OpenConfigSchemaTool())
ToolRegistry.register(EpisodicMemoryTool())
ToolRegistry.register(MemoryStoreTool())

# ---------------------------------------------------------------------------
# Compatibility Wrappers (@tool) expected by existing workflows
# ---------------------------------------------------------------------------


@tool
async def search_openconfig_schema(
    intent: str, device_type: str = "network-instance", max_results: int = 5
) -> dict[str, Any]:
    """Search OpenConfig YANG schema index for XPaths matching intent.

    Delegates to refactored OpenConfigSchemaTool and adapts ToolOutput
    to legacy dict format expected by existing workflows.
    """
    impl = ToolRegistry.get_tool("openconfig_schema_search")
    if impl is None:
        return {"success": False, "error": "openconfig_schema_search tool not registered"}
    result = await impl.execute(intent=intent, device_type=device_type, max_results=max_results)
    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }


@tool
async def search_episodic_memory(
    intent: str, max_results: int = 3, only_successful: bool = True
) -> dict[str, Any]:
    """Search episodic memory index for historical successful intent→XPath mappings.

    Delegates to refactored EpisodicMemoryTool and returns simplified dict
    for compatibility with legacy workflow logic.
    """
    impl = ToolRegistry.get_tool("episodic_memory_search")
    if impl is None:
        return {"success": False, "error": "episodic_memory_search tool not registered"}
    result = await impl.execute(
        intent=intent, max_results=max_results, only_successful=only_successful
    )
    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }


# Tools are auto-registered on module import but can be created independently for testing
# _openconfig_tool = OpenConfigSchemaTool()
# _episodic_tool = EpisodicMemoryTool()
