"""
Base Tool Protocol and ToolOutput standardization.

This module defines the protocol for all OLAV tools and provides
standardized output formatting to eliminate hallucination caused by
inconsistent tool return types (DataFrame, dict, str, XML, etc.).

Key Components:
- ToolOutput: Pydantic model for unified tool responses
- BaseTool: Protocol defining tool interface
- ToolRegistry: Simple tool registry with self-registration and HITL checking

Design Principles:
1. All tools return ToolOutput (source, device, timestamp, data, metadata)
2. Data field is always List[Dict[str, Any]] - no DataFrames or raw strings
3. Adapters normalize vendor-specific formats (XML, JSON, text) to dict
4. LLM receives clean JSON - no parsing required
5. Tools self-register on module import (no discover_tools needed)
6. Tools declare HITL requirements at registration time (Tool Self-Declaration)

Usage:
    from olav.tools.base import ToolOutput, BaseTool, ToolRegistry

    class MyTool(BaseTool):
        name = "my_tool"
        description = "Does something useful"

        async def execute(self, **kwargs) -> ToolOutput:
            return ToolOutput(
                source="my_tool",
                device=kwargs.get("device", "unknown"),
                data=[{"result": "success"}]
            )

    # Self-register at module load with HITL declaration
    ToolRegistry.register(MyTool(), requires_hitl=False)  # Read-only tool

    # Dynamic HITL based on parameters (e.g., HTTP method)
    ToolRegistry.register(
        NetBoxAPITool(),
        requires_hitl=lambda args: args.get("method", "GET") not in {"GET", "HEAD", "OPTIONS"}
    )

    # Retrieve tool
    tool = ToolRegistry.get_tool("my_tool")

    # Check if HITL required for specific call
    needs_hitl = ToolRegistry.check_hitl("netbox_api", {"method": "POST"})  # True
    needs_hitl = ToolRegistry.check_hitl("netbox_api", {"method": "GET"})   # False
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Type alias for HITL checker function
# True = requires HITL, False = auto-approve
HITLChecker = Callable[[dict[str, Any]], bool]

# Tool triggers for keyword-based classification
TriggerKeywords = list[str]


class ToolOutput(BaseModel):
    """
    Standardized output format for all OLAV tools.

    This eliminates the LLM hallucination problem caused by inconsistent
    return types (DataFrame, XML, raw text, etc.).

    Attributes:
        source: Tool identifier (e.g., "suzieq", "netconf", "cli")
        device: Target device(s) - "multi" for aggregated results
        timestamp: When the data was collected
        data: Normalized data as list of dicts (NEVER DataFrame or XML)
        metadata: Optional metadata (query params, execution time, etc.)
        error: Optional error message if tool execution failed

    Examples:
        # SuzieQ query result
        ToolOutput(
            source="suzieq",
            device="multi",
            data=[
                {"hostname": "R1", "asn": "65001", "state": "Established"},
                {"hostname": "R2", "asn": "65002", "state": "Idle"}
            ],
            metadata={"table": "bgp", "method": "get"}
        )

        # NETCONF get-config result
        ToolOutput(
            source="netconf",
            device="R1",
            data=[{"interface": "Gi0/1", "admin_status": "up", "mtu": 1500}],
            metadata={"xpath": "/interfaces/interface"}
        )

        # CLI command result (parsed via TextFSM)
        ToolOutput(
            source="cli",
            device="Switch-A",
            data=[
                {"interface": "Gi1/0/1", "status": "up", "vlan": "100"},
                {"interface": "Gi1/0/2", "status": "down", "vlan": "200"}
            ],
            metadata={"command": "show interfaces status"}
        )
    """

    source: str = Field(description="Tool/data source identifier")
    device: str = Field(description="Target device hostname or 'multi' for aggregated results")
    timestamp: datetime = Field(default_factory=datetime.now)
    data: list[dict[str, Any]] = Field(
        description="Normalized data as list of dictionaries (NEVER DataFrame/XML/text)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata (query params, execution time, etc.)"
    )
    error: str | None = Field(default=None, description="Error message if tool execution failed")

    class Config:
        json_schema_extra = {
            "example": {
                "source": "suzieq",
                "device": "R1",
                "timestamp": "2025-11-24T10:30:00Z",
                "data": [{"interface": "Gi0/1", "state": "up", "speed": "1000"}],
                "metadata": {"table": "interfaces", "filters": {"hostname": "R1"}},
            }
        }


class BaseTool(Protocol):
    """
    Protocol defining the interface for all OLAV tools.

    Tools implementing this protocol can be auto-discovered and registered
    by the ToolRegistry. This enables plugin-style tool additions without
    modifying core code.

    Required Attributes:
        name: Unique tool identifier (snake_case)
        description: Human-readable description for LLM understanding
        input_schema: Pydantic model defining expected parameters
        output_schema: Must be ToolOutput or subclass

    Required Methods:
        execute(**kwargs) -> ToolOutput: Main execution logic

    Example:
        class SuzieqTool(BaseTool):
            name = "suzieq_query"
            description = "Query SuzieQ Parquet database for network state"
            input_schema = SuzieqQueryInput
            output_schema = ToolOutput

            async def execute(
                self,
                table: str,
                method: Literal["get", "summarize"],
                **filters
            ) -> ToolOutput:
                # Implementation
                pass
    """

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[ToolOutput] = ToolOutput

    async def execute(self, **kwargs: Any) -> ToolOutput:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters defined in input_schema

        Returns:
            ToolOutput with normalized data

        Raises:
            Any exceptions should be caught and returned in ToolOutput.error
        """
        ...


class ToolRegistry:
    """
    Registry for OLAV tools with Self-Declaration pattern.

    Provides a centralized registry for tool instances with:
    - Tool registration with HITL requirements (hitl_config)
    - Trigger keywords for classification (triggers)
    - Unified HITL checking API
    - Keyword-based tool matching for fast classification
    - Tool lookup by name or alias

    Self-Declaration Pattern:
    - Tools declare their own triggers, HITL config, category at registration
    - No external config files or hardcoded mappings needed
    - Single source of truth for tool metadata

    Example:
        # Full self-declaration
        ToolRegistry.register(
            OpenConfigSchemaTool(),
            requires_hitl=False,
            triggers=["openconfig", "yang", "xpath", "schema"],
            category="knowledge",
            aliases=["schema_search"],
        )

        # Keyword match for classification
        match = ToolRegistry.keyword_match("查找 BGP 相关的 OpenConfig YANG 路径")
        # Returns: ("openconfig_schema_search", "knowledge", 0.9)

        # Check HITL
        needs_hitl = ToolRegistry.check_hitl("openconfig_schema_search", {})  # False
    """

    _tools: dict[str, BaseTool] = {}
    _hitl_checkers: dict[str, bool | HITLChecker] = {}
    _triggers: dict[str, list[str]] = {}  # tool_name -> trigger keywords
    _categories: dict[str, str] = {}  # tool_name -> category

    @classmethod
    def register(
        cls,
        tool: BaseTool,
        requires_hitl: bool | HITLChecker = True,
        triggers: list[str] | None = None,
        category: str = "general",
        aliases: list[str] | None = None,
    ) -> None:
        """
        Register a tool instance with Self-Declaration.

        Args:
            tool: Tool instance implementing BaseTool protocol
            requires_hitl: HITL requirement declaration
                - True: Always require HITL approval (default, safety-first)
                - False: Never require HITL (read-only tools)
                - Callable: Dynamic check based on call arguments
            triggers: Keyword list for classification matching
                - e.g., ["openconfig", "yang", "xpath"] for schema search
                - Used by keyword_match() before LLM fallback
            category: Tool category for intent classification
                - e.g., "knowledge", "query", "execution"
            aliases: Alternative names for this tool
                - e.g., ["netbox_api_call"] for "netbox_api"

        Note:
            If tool with same name exists, silently skips (idempotent).
            This allows safe re-imports without errors.
        """
        # Validate tool implements protocol
        if not hasattr(tool, "name") or not hasattr(tool, "execute"):
            msg = f"Tool {tool.__class__.__name__} does not implement BaseTool protocol"
            raise TypeError(msg)

        # Idempotent: skip if already registered (same class)
        if tool.name in cls._tools:
            existing = cls._tools[tool.name]
            if existing.__class__.__name__ == tool.__class__.__name__:
                # Same tool, skip silently
                return
            # Different class with same name - this is a real conflict
            msg = (
                f"Tool name conflict: '{tool.name}' - "
                f"Existing: {existing.__class__.__name__}, "
                f"New: {tool.__class__.__name__}"
            )
            raise ValueError(msg)

        cls._tools[tool.name] = tool
        cls._hitl_checkers[tool.name] = requires_hitl
        cls._triggers[tool.name] = triggers or []
        cls._categories[tool.name] = category

        # Register aliases
        if aliases:
            for alias in aliases:
                cls._aliases[alias] = tool.name

        logger.debug(
            f"Registered tool: {tool.name} "
            f"(hitl={requires_hitl}, triggers={triggers}, category={category})"
        )

    @classmethod
    def check_hitl(cls, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """
        Check if HITL approval is required for a tool call.

        Args:
            tool_name: Tool identifier (supports aliases)
            args: Tool call arguments (for dynamic HITL checkers)

        Returns:
            True if HITL required, False if auto-approve

        Note:
            Returns True (require HITL) if tool not found (safety-first).
        """
        # Resolve alias
        resolved_name = cls._aliases.get(tool_name, tool_name)

        # Get HITL checker
        checker = cls._hitl_checkers.get(resolved_name)

        if checker is None:
            # Unknown tool - require HITL for safety
            logger.warning(f"HITL check for unknown tool '{tool_name}' - defaulting to True")
            return True

        if isinstance(checker, bool):
            return checker

        # Callable checker - invoke with args
        if args is None:
            args = {}

        try:
            return checker(args)
        except Exception as e:
            logger.error(f"HITL checker for '{tool_name}' raised exception: {e}")
            return True  # Safety-first on error

    # Tool name aliases - populated dynamically via register(aliases=...)
    _aliases: dict[str, str] = {}

    @classmethod
    def keyword_match(cls, query: str) -> tuple[str, str, float] | None:
        """
        Match query against tool triggers for fast classification.

        This replaces the 3-layer architecture (FastPath + LLM + Fallback)
        with a simple 2-layer approach: Keyword Match → LLM Fallback.

        Uses "best match" strategy: returns the tool with the most trigger matches,
        not just the first match. This handles cases where multiple tools have
        overlapping triggers (e.g., "配置" in netconf vs "openconfig" in schema search).

        Args:
            query: User's natural language query.

        Returns:
            Tuple of (tool_name, category, confidence) if matched, None otherwise.
            Confidence is 0.9 for keyword matches.
        """
        query_lower = query.lower()

        # Find all matches and count triggers matched per tool
        matches: list[tuple[str, str, int, int]] = []  # (tool_name, category, match_count, trigger_specificity)

        for tool_name, triggers in cls._triggers.items():
            if not triggers:
                continue

            # Count how many triggers match
            matched_triggers = [kw for kw in triggers if kw in query_lower]
            if matched_triggers:
                category = cls._categories.get(tool_name, "general")
                # Specificity = sum of lengths of matched triggers (longer = more specific)
                specificity = sum(len(t) for t in matched_triggers)
                matches.append((tool_name, category, len(matched_triggers), specificity))

        if not matches:
            return None

        # Sort by: 1) match count (desc), 2) specificity (desc)
        matches.sort(key=lambda x: (x[2], x[3]), reverse=True)
        best_match = matches[0]

        logger.debug(f"Keyword match: {best_match[0]} (matches={best_match[2]}, specificity={best_match[3]})")
        return (best_match[0], best_match[1], 0.9)

    @classmethod
    def get_tool(cls, name: str) -> BaseTool | None:
        """
        Retrieve tool by name.

        Args:
            name: Tool identifier (supports aliases)

        Returns:
            Tool instance if found, None otherwise
        """
        # Check aliases first
        resolved_name = cls._aliases.get(name, name)
        return cls._tools.get(resolved_name)

    @classmethod
    def list_tools(cls) -> list[BaseTool]:
        """
        Get all registered tools.

        Returns:
            List of registered tool instances
        """
        return list(cls._tools.values())

    @classmethod
    def tool_names(cls) -> list[str]:
        """
        Get all registered tool names.

        Returns:
            List of tool name strings
        """
        return list(cls._tools.keys())

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered tools (primarily for testing).
        """
        cls._tools.clear()
        cls._hitl_checkers.clear()
        cls._triggers.clear()
        cls._categories.clear()
        cls._aliases.clear()
        logger.debug("Cleared tool registry")

    @classmethod
    def tool_count(cls) -> int:
        """
        Get number of registered tools.

        Returns:
            Count of registered tools
        """
        return len(cls._tools)
