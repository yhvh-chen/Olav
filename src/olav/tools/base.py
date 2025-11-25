"""
Base Tool Protocol and ToolOutput standardization.

This module defines the protocol for all OLAV tools and provides
standardized output formatting to eliminate hallucination caused by
inconsistent tool return types (DataFrame, dict, str, XML, etc.).

Key Components:
- ToolOutput: Pydantic model for unified tool responses
- BaseTool: Protocol defining tool interface
- ToolRegistry: Auto-discovery and registration of tools

Design Principles:
1. All tools return ToolOutput (source, device, timestamp, data, metadata)
2. Data field is always List[Dict[str, Any]] - no DataFrames or raw strings
3. Adapters normalize vendor-specific formats (XML, JSON, text) to dict
4. LLM receives clean JSON - no parsing required

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

    # Auto-register
    ToolRegistry.register(MyTool())
"""

import importlib
import inspect
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
    Central registry for tool auto-discovery and management.

    Tools register themselves by calling ToolRegistry.register(tool_instance).
    The registry can auto-discover tools by scanning the tools/ directory
    and importing modules that define BaseTool subclasses.

    Attributes:
        _tools: Dict mapping tool names to tool instances

    Example:
        # Manual registration
        ToolRegistry.register(SuzieqTool())

        # Auto-discovery
        ToolRegistry.discover_tools("olav.tools")

        # Retrieve tool
        tool = ToolRegistry.get_tool("suzieq_query")
        result = await tool.execute(table="bgp")
    """

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """
        Register a tool instance.

        Args:
            tool: Tool instance implementing BaseTool protocol

        Raises:
            ValueError: If tool with same name already registered
            TypeError: If tool doesn't implement BaseTool protocol
        """
        # Validate tool implements protocol
        if not hasattr(tool, "name") or not hasattr(tool, "execute"):
            msg = f"Tool {tool.__class__.__name__} does not implement BaseTool protocol"
            raise TypeError(msg)

        if tool.name in cls._tools:
            msg = (
                f"Tool '{tool.name}' already registered. "
                f"Existing: {cls._tools[tool.name].__class__.__name__}, "
                f"New: {tool.__class__.__name__}"
            )
            raise ValueError(msg)

        cls._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} ({tool.__class__.__name__})")

    @classmethod
    def get_tool(cls, name: str) -> BaseTool | None:
        """
        Retrieve tool by name.

        Args:
            name: Tool identifier

        Returns:
            Tool instance if found, None otherwise
        """
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> list[BaseTool]:
        """
        Get all registered tools.

        Returns:
            List of registered tool instances
        """
        return list(cls._tools.values())

    @classmethod
    def discover_tools(cls, package: str) -> None:
        """
        Auto-discover tools in a package by importing all *_tool.py files.

        This scans the specified package for modules matching *_tool.py pattern,
        imports them, and registers any classes that implement BaseTool.

        Args:
            package: Python package path (e.g., "olav.tools")

        Example:
            ToolRegistry.discover_tools("olav.tools")
            # Imports: suzieq_tool.py, netconf_tool.py, cli_tool.py, etc.
        """
        try:
            # Import the package
            pkg = importlib.import_module(package)
            pkg_path = Path(pkg.__file__).parent

            # Find all *_tool.py files
            tool_files = list(pkg_path.glob("*_tool.py"))

            logger.info(f"Discovering tools in {package}, found {len(tool_files)} modules")

            for tool_file in tool_files:
                module_name = f"{package}.{tool_file.stem}"

                try:
                    module = importlib.import_module(module_name)

                    # Find all classes implementing BaseTool
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # Check if class has required attributes (duck typing)
                        if (
                            hasattr(obj, "name")
                            and hasattr(obj, "description")
                            and hasattr(obj, "execute")
                            and not inspect.isabstract(obj)
                        ):
                            # Instantiate and register
                            try:
                                tool_instance = obj()
                                cls.register(tool_instance)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to instantiate tool {name} from {module_name}: {e}"
                                )

                except Exception as e:
                    logger.warning(f"Failed to import {module_name}: {e}")

        except Exception as e:
            logger.error(f"Failed to discover tools in {package}: {e}")

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered tools (primarily for testing).
        """
        cls._tools.clear()
        logger.debug("Cleared tool registry")

    @classmethod
    def tool_count(cls) -> int:
        """
        Get number of registered tools.

        Returns:
            Count of registered tools
        """
        return len(cls._tools)
