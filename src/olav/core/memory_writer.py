"""Memory writer for capturing successful execution paths to episodic memory."""

import logging
from datetime import UTC, datetime
from typing import Any

from olav.core.memory import OpenSearchMemory
from olav.tools.base import ToolOutput

logger = logging.getLogger(__name__)


class MemoryWriter:
    """Captures successful strategy executions to episodic memory for future RAG retrieval.

    This component:
    1. Monitors strategy execution results
    2. Captures successful intent→tool→result patterns
    3. Stores to olav-episodic-memory index for learning
    4. Enables Fast Path optimization through historical patterns

    Usage:
        writer = MemoryWriter()
        await writer.capture_success(
            intent="查询 R1 BGP 状态",
            tool_used="suzieq_query",
            parameters={"table": "bgp", "hostname": "R1"},
            tool_output=tool_output,
            strategy_used="fast_path",
            execution_time_ms=234
        )
    """

    def __init__(self, memory: OpenSearchMemory | None = None) -> None:
        """Initialize memory writer.

        Args:
            memory: OpenSearch memory instance. If None, creates new instance.
        """
        self._memory = memory

    @property
    def memory(self) -> OpenSearchMemory:
        """Lazy-load OpenSearch memory to avoid connection at import."""
        if self._memory is None:
            self._memory = OpenSearchMemory()
        return self._memory

    async def capture_success(
        self,
        intent: str,
        tool_used: str,
        parameters: dict[str, Any],
        tool_output: ToolOutput,
        strategy_used: str,
        execution_time_ms: int | None = None,
    ) -> None:
        """Capture successful execution to episodic memory.

        Args:
            intent: User intent in natural language (e.g., "查询 R1 BGP 状态")
            tool_used: Tool name that executed successfully
            parameters: Tool parameters used
            tool_output: Tool execution result (must have success=True via no error)
            strategy_used: Strategy that executed (fast_path, deep_path, batch_path)
            execution_time_ms: Execution time in milliseconds

        Returns:
            None. Logs errors but doesn't raise to avoid breaking main workflow.
        """
        # Skip if tool execution failed
        if tool_output.error:
            logger.debug(f"Skipping memory capture for failed execution: {intent}")
            return

        try:
            # Build XPath representation based on tool type
            xpath = self._build_xpath_representation(tool_used, parameters)

            # Extract device info from tool output
            device_type = tool_output.device if tool_output.device != "unknown" else "router"

            # Generate result summary from tool output
            result_summary = self._generate_result_summary(tool_output)

            # Store to episodic memory
            await self.memory.store_episodic_memory(
                intent=intent,
                xpath=xpath,
                success=True,
                context={
                    "tool_used": tool_used,
                    "device_type": device_type,
                    "parameters": parameters,
                    "result_summary": result_summary,
                    "strategy_used": strategy_used,
                    "execution_time_ms": execution_time_ms or 0,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            logger.info(f"✓ Captured episodic memory: {intent} → {tool_used}")

        except Exception as e:
            # Log error but don't propagate to avoid breaking main workflow
            logger.error(f"Failed to capture episodic memory for '{intent}': {e}")

    async def capture_failure(
        self,
        intent: str,
        tool_used: str,
        parameters: dict[str, Any],
        error: str,
        strategy_used: str,
    ) -> None:
        """Capture failed execution for debugging (optional).

        Args:
            intent: User intent
            tool_used: Tool that failed
            parameters: Parameters used
            error: Error message
            strategy_used: Strategy used
        """
        try:
            xpath = self._build_xpath_representation(tool_used, parameters)

            await self.memory.store_episodic_memory(
                intent=intent,
                xpath=xpath,
                success=False,
                context={
                    "tool_used": tool_used,
                    "parameters": parameters,
                    "error": error,
                    "strategy_used": strategy_used,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            logger.debug(f"Captured failed execution: {intent} → {error}")

        except Exception as e:
            logger.error(f"Failed to capture failure memory: {e}")

    def _build_xpath_representation(self, tool_used: str, parameters: dict[str, Any]) -> str:
        """Build XPath-like representation for storage.

        For SuzieQ tools: "table=bgp, hostname=R1"
        For NETCONF tools: actual OpenConfig XPath
        For CLI tools: "command: show bgp summary"

        Args:
            tool_used: Tool name
            parameters: Tool parameters

        Returns:
            XPath-like string representation
        """
        if tool_used == "suzieq_query":
            # SuzieQ format: "table=bgp, hostname=R1, method=get"
            parts = []
            for key in ["table", "hostname", "method", "namespace"]:
                if key in parameters:
                    parts.append(f"{key}={parameters[key]}")
            return ", ".join(parts) if parts else str(parameters)

        if tool_used == "netconf_execute":
            # NETCONF: Use xpath parameter directly
            return parameters.get("xpath", str(parameters))

        if tool_used == "cli_execute":
            # CLI: Use command
            return f"command: {parameters.get('command', str(parameters))}"

        # Generic: JSON representation
        return str(parameters)

    def _generate_result_summary(self, tool_output: ToolOutput) -> str:
        """Generate brief summary from tool output.

        Args:
            tool_output: Tool execution result

        Returns:
            Human-readable summary string
        """
        if not tool_output.data:
            return "No data returned"

        # Count records
        record_count = len(tool_output.data)

        # Try to extract meaningful fields
        if record_count == 1:
            sample = tool_output.data[0]
            # Get first few field values for context
            fields = list(sample.keys())[:3]
            values = [str(sample[f]) for f in fields]
            return f"1 record: {', '.join(values)}"

        return f"{record_count} records retrieved"


# Singleton instance for easy import
_memory_writer_instance: MemoryWriter | None = None


def get_memory_writer() -> MemoryWriter:
    """Get singleton MemoryWriter instance.

    Returns:
        Singleton MemoryWriter instance
    """
    global _memory_writer_instance
    if _memory_writer_instance is None:
        _memory_writer_instance = MemoryWriter()
    return _memory_writer_instance
