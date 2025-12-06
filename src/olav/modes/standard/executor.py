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


class HITLRequired(Exception):
    """Exception raised when HITL approval is required."""
    
    def __init__(
        self,
        tool_name: str,
        operation: str,
        parameters: dict[str, Any],
        reason: str = "Write operation requires approval",
    ):
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
    ) -> tuple[bool, str]:
        """Check if operation requires HITL approval.
        
        Args:
            tool_name: Name of the tool to execute.
            parameters: Tool parameters.
        
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
        
        # NetBox: check HTTP method
        if tool_name in ("netbox_api_call", "netbox_api"):
            method = parameters.get("method", "GET").upper()
            if method in self.NETBOX_WRITE_METHODS:
                endpoint = parameters.get("endpoint", "")
                return True, f"NetBox {method} to {endpoint}"
        
        return False, ""
    
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
            HITLRequired: If write operation needs approval and yolo_mode is False.
        """
        start_time = time.perf_counter()
        
        tool_name = classification.tool
        parameters = classification.parameters.copy()
        
        # Add user_query for tools that need it
        parameters["user_query"] = user_query
        
        # Check HITL requirement
        requires_hitl, hitl_reason = self._requires_hitl(tool_name, parameters)
        
        if requires_hitl:
            logger.warning(f"HITL required for {tool_name}: {hitl_reason}")
            raise HITLRequired(
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
        
        # Execute tool
        try:
            tool_output = await tool.execute(**parameters)
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
        requires_hitl, hitl_reason = self._requires_hitl(tool_name, parameters)
        
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
            
        except HITLRequired:
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
