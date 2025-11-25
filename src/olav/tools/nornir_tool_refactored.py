"""
Nornir Tool - BaseTool implementation with adapter integration.

Refactored to implement BaseTool protocol for NETCONF and CLI operations.
Uses CLIAdapter and NetconfAdapter for standardized ToolOutput returns.
"""

import logging
import time
from pathlib import Path
from typing import Literal

from olav.execution.backends.nornir_sandbox import NornirSandbox
from olav.tools.adapters import CLIAdapter, NetconfAdapter
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)

# Derive CONFIG_DIR without importing non-packaged root module
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class NetconfTool:
    """
    NETCONF operation tool - BaseTool implementation.

    Provides NETCONF access to network devices with:
    - get-config and edit-config operations
    - XPath filtering for targeted data retrieval
    - HITL approval for write operations (edit-config)
    - Standardized ToolOutput via NetconfAdapter

    Attributes:
        name: Tool identifier
        description: Tool purpose description
        sandbox: NornirSandbox instance for execution
    """

    name = "netconf_execute"
    description = """Execute NETCONF operations on network devices.

    Use this tool for OpenConfig-based device configuration:
    - get-config: Read configuration data with XPath filters (read-only)
    - edit-config: Modify configuration (requires HITL approval)

    NETCONF provides structured, model-driven access to device configuration.
    Prefer this over CLI for configuration management.

    **CRITICAL**: edit-config operations trigger Human-in-the-Loop approval.
    """

    def __init__(self, sandbox: NornirSandbox | None = None) -> None:
        """
        Initialize NetconfTool.

        Args:
            sandbox: NornirSandbox instance (lazy-loaded if None)
        """
        self._sandbox = sandbox

    @property
    def sandbox(self) -> NornirSandbox:
        """Lazy-load Nornir sandbox (avoids NetBox connection at import time)."""
        if self._sandbox is None:
            self._sandbox = NornirSandbox()
        return self._sandbox

    async def execute(
        self,
        device: str,
        operation: Literal["get-config", "edit-config"],
        xpath: str | None = None,
        payload: str | None = None,
    ) -> ToolOutput:
        """
        Execute NETCONF operation and return standardized output.

        Args:
            device: Target device hostname
            operation: NETCONF operation (get-config or edit-config)
            xpath: XPath filter for get-config (required for get-config)
            payload: XML configuration payload for edit-config (required for edit-config)

        Returns:
            ToolOutput with normalized XML data via NetconfAdapter

        Example (Read):
            result = await tool.execute(
                device="R1",
                operation="get-config",
                xpath="/interfaces/interface[name='eth0']/state"
            )

        Example (Write - triggers HITL):
            result = await tool.execute(
                device="R1",
                operation="edit-config",
                payload="<interfaces><interface>...</interface></interfaces>"
            )
        """
        start_time = time.perf_counter()

        metadata = {
            "device": device,
            "operation": operation,
            "xpath": xpath,
            "requires_approval": operation == "edit-config",
        }

        # Validate parameters
        if operation == "get-config" and not xpath:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolOutput(
                source="netconf",
                device=device,
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": "get-config requires xpath parameter",
                        "hint": "Provide XPath filter like '/interfaces/interface/state'",
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error="Missing required parameter: xpath",
            )

        if operation == "edit-config" and not payload:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolOutput(
                source="netconf",
                device=device,
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": "edit-config requires payload parameter",
                        "hint": "Provide XML configuration payload",
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error="Missing required parameter: payload",
            )

        # Validate operation
        if operation not in ["get-config", "edit-config"]:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolOutput(
                source="netconf",
                device=device,
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": f"Unsupported operation: {operation}",
                        "supported": ["get-config", "edit-config"],
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"Unsupported operation: {operation}",
            )

        # Build NETCONF RPC
        requires_approval = operation == "edit-config"

        if operation == "get-config":
            command = (
                f"<get-config>"
                f"<source><running/></source>"
                f"<filter type='xpath' select='{xpath}'/>"
                f"</get-config>"
            )
        else:  # edit-config
            command = (
                f"<edit-config>"
                f"<target><candidate/></target>"
                f"<config>{payload}</config>"
                f"</edit-config>"
            )

        try:
            # Execute via NornirSandbox
            result = await self.sandbox.execute(
                command=command,
                device=device,
                requires_approval=requires_approval,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Use NetconfAdapter to convert XML response
            return NetconfAdapter.adapt(
                netconf_response=result.output if result.success else None,
                device=device,
                xpath=xpath or "",
                metadata={
                    **metadata,
                    "elapsed_ms": elapsed_ms,
                    "success": result.success,
                    "operation": operation,
                },
                error=result.error,
            )

        except ConnectionRefusedError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"NETCONF connection refused for {device}: {e}")
            return ToolOutput(
                source="netconf",
                device=device,
                data=[
                    {
                        "status": "CONNECTION_ERROR",
                        "message": "Connection refused on port 830",
                        "hint": "Device may not support NETCONF. Try CLI instead.",
                        "原始错误": str(e),
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"Connection refused (port 830): {e}",
            )

        except TimeoutError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"NETCONF timeout for {device}: {e}")
            return ToolOutput(
                source="netconf",
                device=device,
                data=[
                    {
                        "status": "TIMEOUT_ERROR",
                        "message": "Timeout connecting to port 830",
                        "hint": "Check device reachability and NETCONF service status",
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"Connection timeout: {e}",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(f"NETCONF execution failed for {device}: {e}")
            return ToolOutput(
                source="netconf",
                device=device,
                data=[],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"NETCONF execution failed: {e}",
            )


class CLITool:
    """
    CLI command execution tool - BaseTool implementation.

    Provides SSH-based CLI access to network devices with:
    - Show command execution with TextFSM parsing
    - Configuration commands with HITL approval
    - Standardized ToolOutput via CLIAdapter

    Attributes:
        name: Tool identifier
        description: Tool purpose description
        sandbox: NornirSandbox instance for execution
    """

    name = "cli_execute"
    description = """Execute CLI commands on network devices via SSH.

    Use this tool for:
    - Show commands: TextFSM-parsed structured output (read-only)
    - Configuration commands: Multi-line config changes (requires HITL approval)

    TextFSM parsing converts raw text to structured data automatically.
    Supports Cisco IOS, IOS-XR, NX-OS, Juniper, Arista, and more.

    **CRITICAL**: Configuration commands trigger Human-in-the-Loop approval.
    """

    def __init__(self, sandbox: NornirSandbox | None = None) -> None:
        """
        Initialize CLITool.

        Args:
            sandbox: NornirSandbox instance (lazy-loaded if None)
        """
        self._sandbox = sandbox

    @property
    def sandbox(self) -> NornirSandbox:
        """Lazy-load Nornir sandbox (avoids NetBox connection at import time)."""
        if self._sandbox is None:
            self._sandbox = NornirSandbox()
        return self._sandbox

    async def execute(
        self, device: str, command: str | None = None, config_commands: list[str] | None = None
    ) -> ToolOutput:
        """
        Execute CLI command(s) and return standardized output.

        Args:
            device: Target device hostname
            command: Single show/exec command (for read operations)
            config_commands: List of configuration commands (for write operations)

        Returns:
            ToolOutput with parsed CLI data via CLIAdapter

        Example (Read - TextFSM parsed):
            result = await tool.execute(
                device="R1",
                command="show ip interface brief"
            )
            # Returns: [{"interface": "Gi0/0", "ip_address": "192.168.1.1", ...}, ...]

        Example (Write - triggers HITL):
            result = await tool.execute(
                device="R1",
                config_commands=[
                    "interface GigabitEthernet0/0",
                    "mtu 9000",
                    "description Updated via OLAV"
                ]
            )
        """
        start_time = time.perf_counter()

        metadata = {
            "device": device,
            "command": command,
            "config_commands": config_commands,
            "is_config": config_commands is not None,
        }

        # Validate parameters
        if not command and not config_commands:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolOutput(
                source="cli",
                device=device,
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": "Must provide either command or config_commands",
                        "hint": "Use command for show/exec, config_commands for configuration",
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error="Missing required parameter: command or config_commands",
            )

        if command and config_commands:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolOutput(
                source="cli",
                device=device,
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": "Cannot provide both command and config_commands",
                        "hint": "Choose one: command (read) OR config_commands (write)",
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error="Conflicting parameters: command and config_commands",
            )

        # Determine if config operation (requires approval)
        is_config = config_commands is not None
        requires_approval = is_config

        try:
            if is_config:
                # Configuration commands (HITL approval)
                result = await self.sandbox.execute_cli_config(
                    device=device,
                    commands=config_commands,
                    requires_approval=requires_approval,
                )
                parsed = False
            else:
                # Show/exec command (TextFSM parsing)
                result = await self.sandbox.execute_cli_command(
                    device=device,
                    command=command,
                    use_textfsm=True,
                )
                parsed = result.metadata.get("parsed", False) if result.metadata else False

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Use CLIAdapter to convert output
            return CLIAdapter.adapt(
                cli_output=result.output if result.success else result.error,
                device=device,
                command=command or f"config: {len(config_commands)} lines",
                parsed=parsed and result.success,
                metadata={
                    **metadata,
                    "elapsed_ms": elapsed_ms,
                    "success": result.success,
                    "requires_approval": requires_approval,
                },
                error=result.error if not result.success else None,
            )

        except ConnectionRefusedError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"SSH connection refused for {device}: {e}")
            return ToolOutput(
                source="cli",
                device=device,
                data=[
                    {
                        "status": "CONNECTION_ERROR",
                        "message": "Connection refused on port 22",
                        "hint": "Check device SSH service and credentials",
                        "原始错误": str(e),
                    }
                ],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"Connection refused (port 22): {e}",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(f"CLI execution failed for {device}: {e}")
            return ToolOutput(
                source="cli",
                device=device,
                data=[],
                metadata={**metadata, "elapsed_ms": elapsed_ms},
                error=f"CLI execution failed: {e}",
            )


# Register tools with ToolRegistry
ToolRegistry.register(NetconfTool())
ToolRegistry.register(CLITool())
