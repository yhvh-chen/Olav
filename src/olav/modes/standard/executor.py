"""Standard Mode Executor - Fast single-step tool execution.

Executes a single tool call based on classifier results.
Handles HITL (Human-in-the-Loop) for write operations.
"""

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from olav.core.unified_classifier import UnifiedClassificationResult
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    """Result of Standard Mode execution."""

    success: bool
    answer: str = ""
    tool_output: ToolOutput | None = None
    tool_name: str = ""
    execution_time_ms: float = 0.0
    hitl_triggered: bool = False
    hitl_approved: bool | None = None
    error: str | None = None

    # Metadata for debugging
    metadata: dict[str, Any] = Field(default_factory=dict)


class HITLRequiredError(Exception):
    """Exception raised when HITL approval is required."""

    def __init__(
        self,
        tool_name: str,
        operation: str,
        parameters: dict[str, Any],
        reason: str = "Write operation requires approval",
    ) -> None:
        self.tool_name = tool_name
        self.operation = operation
        self.parameters = parameters
        self.reason = reason
        super().__init__(reason)


class StandardModeExecutor:
    """Standard Mode executor - single-step tool execution.

    This executor:
    1. Takes a classification result
    2. Validates HITL requirements
    3. Executes the tool
    4. Formats the response

    HITL is triggered for:
    - netconf_edit / netconf_tool with edit operations
    - cli_config / cli_tool with config commands
    - netbox_api_call with POST/PUT/DELETE methods
    """

    # Tools that require HITL approval
    HITL_TOOLS = {
        "netconf_edit",
        "netconf_tool",
        "cli_config",
        "cli_tool",
    }

    # NetBox methods that require HITL
    NETBOX_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    # Keywords that indicate write operations (used as fallback when method is not specified)
    # Chinese + English patterns for NetBox write operations
    NETBOX_WRITE_KEYWORDS = {
        # Create operations
        "创建", "新建", "添加", "新增", "create", "add", "new",
        # Update operations
        "更新", "修改", "编辑", "变更", "update", "modify", "edit", "change",
        # Delete operations
        "删除", "移除", "清除", "remove", "delete", "clear",
    }

    # Parameter name aliases for LLM compatibility
    # Maps: tool_name -> {llm_param_name: actual_param_name}
    PARAM_ALIASES = {
        "netbox_api_call": {
            "endpoint": "path",
            "filters": "params",
        },
        "netbox_api": {
            "endpoint": "path",
            "filters": "params",
        },
    }

    # SuzieQ table name aliases - maps user-friendly names to actual SuzieQ table names
    # This handles cases where LLM returns "ospf" but actual table is "ospfNbr"
    SUZIEQ_TABLE_ALIASES = {
        # OSPF tables
        "ospf": "ospfNbr",          # OSPF neighbor information
        "ospf_neighbor": "ospfNbr",
        "ospf_nbr": "ospfNbr",
        "ospf_if": "ospfIf",        # OSPF interface information
        "ospf_interface": "ospfIf",
        # Interface tables
        "interface": "interfaces",
        "if": "interfaces",
        "ifcounters": "ifCounters",
        "if_counters": "ifCounters",
        # MAC table
        "mac": "macs",
        # EVPN
        "evpn": "evpnVni",
        "evpn_vni": "evpnVni",
        # Device config
        "config": "devconfig",
        "device_config": "devconfig",
        # Filesystem
        "filesystem": "fs",
        # Network
        "net": "network",
        # Polling
        "poller": "sqPoller",
        "sq_poller": "sqPoller",
        # Performance
        "topmemory": "topmem",
        "top_mem": "topmem",
        "top_cpu": "topcpu",
    }

    def __init__(
        self,
        tool_registry: ToolRegistry,
        yolo_mode: bool = False,
    ) -> None:
        """Initialize executor.

        Args:
            tool_registry: Registry of available tools.
            yolo_mode: If True, skip HITL approval (for testing).
        """
        self.tool_registry = tool_registry
        self.yolo_mode = yolo_mode

    def _requires_hitl(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        user_query: str = "",
    ) -> tuple[bool, str]:
        """Check if operation requires HITL approval.

        Args:
            tool_name: Name of the tool to execute.
            parameters: Tool parameters.
            user_query: Original user query for keyword-based fallback detection.

        Returns:
            Tuple of (requires_hitl, reason)
        """
        if self.yolo_mode:
            return False, ""

        # NETCONF/CLI tools always require HITL for config changes
        if tool_name in self.HITL_TOOLS:
            operation = parameters.get("operation", "")
            command = parameters.get("command", "")

            # Check for read-only operations
            read_only_ops = {"get", "get-config", "show"}
            if operation.lower() in read_only_ops:
                return False, ""

            # CLI: check for config commands
            if tool_name in ("cli_tool", "cli_config"):
                if command.startswith("show "):
                    return False, ""
                return True, f"CLI command may modify device: {command[:50]}"

            return True, f"NETCONF operation: {operation}"

        # NetBox: check HTTP method + keyword fallback
        if tool_name in ("netbox_api_call", "netbox_api"):
            method = parameters.get("method", "").upper()
            endpoint = parameters.get("path", parameters.get("endpoint", ""))

            # Method explicitly specified as write operation
            if method in self.NETBOX_WRITE_METHODS:
                return True, f"NetBox {method} to {endpoint}"

            # Keyword-based fallback: detect write intent from user query
            # This handles cases where LLM doesn't extract 'method' parameter
            if not method or method == "GET":
                query_lower = user_query.lower()
                for keyword in self.NETBOX_WRITE_KEYWORDS:
                    if keyword in query_lower:
                        # Infer method from keyword type
                        inferred_method = self._infer_http_method(keyword)
                        return True, f"NetBox {inferred_method} to {endpoint} (detected '{keyword}' in query)"

        return False, ""

    def _infer_http_method(self, keyword: str) -> str:
        """Infer HTTP method from write keyword.

        Args:
            keyword: The detected write keyword

        Returns:
            Inferred HTTP method (POST, PUT, PATCH, or DELETE)
        """
        keyword_lower = keyword.lower()
        create_keywords = {"创建", "新建", "添加", "新增", "create", "add", "new"}
        delete_keywords = {"删除", "移除", "清除", "remove", "delete", "clear"}

        if keyword_lower in create_keywords:
            return "POST"
        if keyword_lower in delete_keywords:
            return "DELETE"
        # Update keywords default to PATCH
        return "PATCH"

    def _map_parameters(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Map LLM parameter names to actual tool parameter names.

        Args:
            tool_name: Name of the tool (may be an alias)
            parameters: Parameters from LLM classification

        Returns:
            Parameters with names mapped to actual tool expectations
        """
        # Get alias mapping for this tool
        aliases = self.PARAM_ALIASES.get(tool_name, {})
        if not aliases:
            mapped = parameters.copy()
        else:
            # Map parameter names
            mapped = {}
            for key, value in parameters.items():
                mapped_key = aliases.get(key, key)
                mapped[mapped_key] = value

        # For SuzieQ tools, map table names to actual SuzieQ table names
        if tool_name in ("suzieq_query", "suzieq_tool"):
            mapped = self._map_suzieq_table(mapped)

        return mapped

    def _map_suzieq_table(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Map user-friendly table names to actual SuzieQ table names.

        Args:
            parameters: Tool parameters that may contain 'table' field

        Returns:
            Parameters with table name mapped to actual SuzieQ table
        """
        if "table" not in parameters:
            return parameters

        table = parameters["table"]
        table_lower = table.lower()

        # Check alias mapping (case-insensitive)
        if table_lower in self.SUZIEQ_TABLE_ALIASES:
            actual_table = self.SUZIEQ_TABLE_ALIASES[table_lower]
            logger.info(f"Mapped SuzieQ table: {table} → {actual_table}")
            parameters = parameters.copy()
            parameters["table"] = actual_table

        return parameters

    async def execute(
        self,
        classification: UnifiedClassificationResult,
        user_query: str,
    ) -> ExecutionResult:
        """Execute tool based on classification result.

        Args:
            classification: Classification result with tool and parameters.
            user_query: Original user query (for context).

        Returns:
            ExecutionResult with tool output and metadata.

        Raises:
            HITLRequiredError: If write operation needs approval and yolo_mode is False.
        """
        start_time = time.perf_counter()

        tool_name = classification.tool
        parameters = classification.parameters.copy()

        # Parameter name mapping for LLM compatibility
        # LLM may use different parameter names than the actual tool expects
        parameters = self._map_parameters(tool_name, parameters)

        # Check HITL requirement (before removing internal params)
        requires_hitl, hitl_reason = self._requires_hitl(tool_name, parameters, user_query)

        if requires_hitl:
            logger.warning(f"HITL required for {tool_name}: {hitl_reason}")
            raise HITLRequiredError(
                tool_name=tool_name,
                operation=hitl_reason,
                parameters=parameters,
                reason=hitl_reason,
            )

        # Get tool from registry
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            elapsed = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                error=f"Tool not found: {tool_name}",
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

        # Filter parameters to only those accepted by the tool
        # Remove internal params that tools don't accept
        internal_params = {"user_query"}
        tool_params = {k: v for k, v in parameters.items() if k not in internal_params}

        # Execute tool
        try:
            tool_output = await tool.execute(**tool_params)
            elapsed = (time.perf_counter() - start_time) * 1000

            if tool_output.error:
                return ExecutionResult(
                    success=False,
                    error=tool_output.error,
                    tool_output=tool_output,
                    tool_name=tool_name,
                    execution_time_ms=elapsed,
                )

            return ExecutionResult(
                success=True,
                tool_output=tool_output,
                tool_name=tool_name,
                execution_time_ms=elapsed,
                metadata={
                    "tool": tool_name,
                    "parameters": parameters,
                    "confidence": classification.confidence,
                },
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception(f"Tool execution failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

    async def execute_with_approval(
        self,
        classification: UnifiedClassificationResult,
        user_query: str,
        approval_callback: Any = None,
    ) -> ExecutionResult:
        """Execute tool with HITL approval flow.

        Args:
            classification: Classification result.
            user_query: Original user query.
            approval_callback: Async callback for approval.
                               Signature: async (tool, operation, params) -> bool

        Returns:
            ExecutionResult with hitl_triggered and hitl_approved fields.
        """
        start_time = time.perf_counter()

        tool_name = classification.tool
        parameters = classification.parameters.copy()
        parameters["user_query"] = user_query

        # Check HITL requirement
        requires_hitl, hitl_reason = self._requires_hitl(tool_name, parameters, user_query)

        if requires_hitl:
            logger.info(f"Requesting HITL approval for {tool_name}: {hitl_reason}")

            # Request approval
            if approval_callback:
                approved = await approval_callback(tool_name, hitl_reason, parameters)
            else:
                # No callback = rejection
                approved = False

            if not approved:
                elapsed = (time.perf_counter() - start_time) * 1000
                return ExecutionResult(
                    success=False,
                    error="Operation rejected by user",
                    tool_name=tool_name,
                    execution_time_ms=elapsed,
                    hitl_triggered=True,
                    hitl_approved=False,
                )

            # Approved - proceed with execution
            logger.info(f"HITL approved for {tool_name}")

        # Execute (reuse standard execute logic)
        try:
            result = await self.execute(classification, user_query)
            result.hitl_triggered = requires_hitl
            result.hitl_approved = True if requires_hitl else None
            return result

        except HITLRequiredError:
            # Should not happen here since we already handled it
            elapsed = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                error="Unexpected HITL requirement",
                tool_name=tool_name,
                execution_time_ms=elapsed,
                hitl_triggered=True,
                hitl_approved=False,
            )
