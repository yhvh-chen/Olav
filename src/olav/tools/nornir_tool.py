"""
Nornir Tool - BaseTool implementation with adapter integration.

Refactored to implement BaseTool protocol for NETCONF and CLI operations.
Uses CLIAdapter and NetconfAdapter for standardized ToolOutput returns.
"""

import logging
import time
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

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
                f"<target><running/></target>"
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

            # For edit-config, many backends return no payload (None) even on success.
            # Treat that as an explicit OK to avoid adapter errors.
            netconf_response: Any
            if result.success and result.output is None and operation == "edit-config":
                netconf_response = {"ok": True}
            else:
                netconf_response = result.output if result.success else None

            # Use NetconfAdapter to normalize response
            return NetconfAdapter.adapt(
                netconf_response=netconf_response,
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
                        "raw_error": str(e),
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
                        "raw_error": str(e),
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
# NETCONF: HITL required for edit-config (write) only
ToolRegistry.register(
    NetconfTool(),
    requires_hitl=lambda args: args.get("operation") == "edit-config",
    # More specific triggers - avoid generic "配置" which conflicts with openconfig
    triggers=["netconf", "rpc", "edit-config", "get-config", "netconf配置", "设备配置变更"],
    category="netconf",
    aliases=["netconf_tool", "netconf_execute"],
)
# CLI: HITL required for config commands only (not show commands)
# Note: cli_execute is raw, cli_show/cli_config wrappers provide semantic distinction
ToolRegistry.register(
    CLITool(),
    requires_hitl=lambda args: not args.get("command", "").strip().lower().startswith("show"),
    triggers=["cli", "ssh", "command line", "show run", "命令行"],
    category="cli",
    aliases=["cli_tool", "cli_execute"],
)

# ---------------------------------------------------------------------------
# Compatibility Wrappers (@tool) for legacy workflow/test integration
# ---------------------------------------------------------------------------


@tool
async def netconf_tool(
    device: str,
    operation: str,
    xpath: str | None = None,
    payload: str | None = None,
) -> dict[str, Any]:
    """Legacy-compatible NETCONF tool wrapper delegating to NetconfTool.

    Preserves original return structure (success/output/error + __meta__).
    """
    impl = ToolRegistry.get_tool("netconf_execute")
    if impl is None:
        return {"success": False, "error": "netconf_execute tool not registered"}
    result = await impl.execute(device=device, operation=operation, xpath=xpath, payload=payload)
    return {
        "success": result.error is None,
        "output": result.data,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


@tool
async def netconf_get(
    device: str,
    xpath: str,
) -> dict[str, Any]:
    """NETCONF get-config operation (read-only, no HITL required).

    Use this tool to read device configuration via NETCONF.
    Supports OpenConfig YANG paths for structured data retrieval.

    Args:
        device: Target device hostname (e.g., "R1")
        xpath: XPath filter for configuration data
               Examples:
               - /interfaces/interface[name='eth0']/state
               - /network-instances/network-instance/protocols/protocol/bgp
               - /openconfig-acl:acl/acl-sets

    Returns:
        dict with success/output/error keys

    Example:
        result = await netconf_get(
            device="R1",
            xpath="/interfaces/interface/state"
        )
    """
    impl = ToolRegistry.get_tool("netconf_execute")
    if impl is None:
        return {"success": False, "error": "netconf_execute tool not registered"}
    result = await impl.execute(device=device, operation="get-config", xpath=xpath)
    return {
        "success": result.error is None,
        "output": result.data,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


@tool
async def netconf_edit(
    device: str,
    payload: str,
) -> dict[str, Any]:
    """NETCONF edit-config operation (write, requires HITL approval).

    Use this tool to modify device configuration via NETCONF.
    **CRITICAL**: This triggers Human-in-the-Loop approval before execution.

    Args:
        device: Target device hostname (e.g., "R1")
        payload: XML configuration payload (OpenConfig format)
                 Must be valid XML matching the device's YANG schema

    Returns:
        dict with success/output/error keys

    Example:
        result = await netconf_edit(
            device="R1",
            payload='''
            <interfaces xmlns="http://openconfig.net/yang/interfaces">
              <interface>
                <name>Loopback0</name>
                <config>
                  <name>Loopback0</name>
                  <description>Management Loopback</description>
                </config>
              </interface>
            </interfaces>
            '''
        )
    """
    impl = ToolRegistry.get_tool("netconf_execute")
    if impl is None:
        return {"success": False, "error": "netconf_execute tool not registered"}
    result = await impl.execute(device=device, operation="edit-config", payload=payload)
    return {
        "success": result.error is None,
        "output": result.data,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


@tool
async def cli_tool(
    device: str,
    command: str | None = None,
    config_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Legacy-compatible CLI tool wrapper delegating to CLITool."""
    impl = ToolRegistry.get_tool("cli_execute")
    if impl is None:
        return {"success": False, "error": "cli_execute tool not registered"}
    result = await impl.execute(device=device, command=command, config_commands=config_commands)
    parsed = False
    if result.metadata:
        parsed = result.metadata.get("success") and any(
            isinstance(entry, dict) for entry in result.data
        )
    return {
        "success": result.error is None,
        "output": result.data,
        "parsed": parsed,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


@tool
async def cli_show(
    device: str,
    command: str,
) -> dict[str, Any]:
    """CLI show command execution (read-only, no HITL required).

    Use this tool to execute show commands on devices via SSH.
    Output is automatically parsed via TextFSM when templates are available.

    Args:
        device: Target device hostname (e.g., "R1", "SW01")
        command: Show command to execute
                 Examples:
                 - show ip interface brief
                 - show bgp summary
                 - show version

    Returns:
        dict with success/output/parsed/error keys
        output: Parsed data (list of dicts) if TextFSM template available,
                otherwise raw text

    Example:
        result = await cli_show(device="R1", command="show ip route")
    """
    impl = ToolRegistry.get_tool("cli_execute")
    if impl is None:
        return {"success": False, "error": "cli_execute tool not registered"}
    result = await impl.execute(device=device, command=command)
    parsed = False
    if result.metadata:
        parsed = result.metadata.get("success") and any(
            isinstance(entry, dict) for entry in result.data
        )
    return {
        "success": result.error is None,
        "output": result.data,
        "parsed": parsed,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


@tool
async def cli_config(
    device: str,
    config_commands: list[str],
) -> dict[str, Any]:
    """CLI configuration commands (write, requires HITL approval).

    Use this tool to push configuration changes to devices via SSH.
    **CRITICAL**: This triggers Human-in-the-Loop approval before execution.

    Args:
        device: Target device hostname (e.g., "R1", "SW01")
        config_commands: List of configuration commands to execute
                        Commands are executed in order within config mode

    Returns:
        dict with success/output/error keys

    Example:
        result = await cli_config(
            device="R1",
            config_commands=[
                "interface Loopback10",
                "description Test Loopback",
                "ip address 10.10.10.10 255.255.255.255"
            ]
        )
    """
    impl = ToolRegistry.get_tool("cli_execute")
    if impl is None:
        return {"success": False, "error": "cli_execute tool not registered"}
    result = await impl.execute(device=device, config_commands=config_commands)
    return {
        "success": result.error is None,
        "output": result.data,
        "error": result.error,
        "__meta__": {"elapsed_ms": result.metadata.get("elapsed_ms")},
    }


# ---------------------------------------------------------------------------
# Unified Device Config Tool - Auto-routes to NETCONF/CLI based on device tag
# ---------------------------------------------------------------------------


class DeviceConfigRouter:
    """Routes configuration operations to appropriate backend based on device transport tag.
    
    Device transport is determined by NetBox custom_field 'config_transport':
    - 'netconf': Use NETCONF (OpenConfig) - preferred for IOS-XE, Arista, Junos
    - 'cli': Use CLI (SSH) - for legacy devices
    - 'auto' or unset: Try NETCONF first, fallback to CLI on failure
    
    This eliminates LLM decision-making about transport, improving reliability.
    """
    
    def __init__(self) -> None:
        self._sandbox: NornirSandbox | None = None
    
    @property
    def sandbox(self) -> NornirSandbox:
        """Lazy-load Nornir sandbox."""
        if self._sandbox is None:
            self._sandbox = NornirSandbox()
        return self._sandbox
    
    def get_device_transport(self, device: str) -> str:
        """Get transport method for device from inventory.
        
        Checks NetBox custom_field 'config_transport'.
        Returns: 'netconf', 'cli', or 'auto'
        """
        try:
            hosts = self.sandbox.nr.inventory.hosts
            if device in hosts:
                host = hosts[device]
                # NBInventory may expose NetBox custom fields either at the top-level
                # (historical behavior) or under a nested 'custom_fields' dict.
                transport = host.data.get("config_transport")
                if not transport and isinstance(host.data.get("custom_fields"), dict):
                    transport = host.data.get("custom_fields", {}).get("config_transport")

                # Optional: allow tag-based transport selection if tags are present.
                if not transport:
                    tags = host.data.get("tags")
                    if isinstance(tags, list):
                        tag_names = {str(t).lower() for t in tags}
                        if "netconf" in tag_names or "openconfig" in tag_names:
                            transport = "netconf"
                    elif isinstance(tags, dict):
                        # Some NetBox APIs return tags as list of objects; be conservative.
                        pass

                transport = transport or "auto"
                if transport in ("netconf", "cli"):
                    logger.info(f"Device {device} transport from NetBox: {transport}")
                    return transport
            return "auto"
        except Exception as e:
            logger.warning(f"Failed to get transport for {device}: {e}")
            return "auto"
    
    async def execute_config(
        self,
        device: str,
        config_commands: list[str],
        interface: str | None = None,
        operation: str = "merge",
    ) -> dict[str, Any]:
        """Execute configuration change using appropriate transport.
        
        Args:
            device: Target device hostname
            config_commands: CLI-style configuration commands
            interface: Target interface (for interface operations)
            operation: 'merge', 'delete', 'replace' (for NETCONF)
            
        Returns:
            dict with success, output, transport_used, error
        """
        transport = self.get_device_transport(device)
        logger.info(f"Device {device} transport: {transport}")
        
        if transport == "netconf":
            return await self._execute_netconf(device, config_commands, interface, operation)
        elif transport == "cli":
            return await self._execute_cli(device, config_commands)
        else:  # auto
            return await self._execute_auto(device, config_commands, interface, operation)
    
    async def _execute_netconf(
        self,
        device: str,
        config_commands: list[str],
        interface: str | None,
        operation: str,
    ) -> dict[str, Any]:
        """Execute via NETCONF."""
        netconf_impl = ToolRegistry.get_tool("netconf_execute")
        if netconf_impl is None:
            return {"success": False, "error": "netconf_execute tool not registered", "transport_used": "netconf"}
        
        # Build NETCONF payload from CLI commands
        # For interface deletion, build OpenConfig XML
        payload = self._build_netconf_payload(config_commands, interface, operation)
        
        result = await netconf_impl.execute(
            device=device,
            operation="edit-config",
            payload=payload,
        )
        
        return {
            "success": result.error is None,
            "output": result.data,
            "error": result.error,
            "transport_used": "netconf",
            "__meta__": result.metadata,
        }
    
    async def _execute_cli(
        self,
        device: str,
        config_commands: list[str],
    ) -> dict[str, Any]:
        """Execute via CLI."""
        cli_impl = ToolRegistry.get_tool("cli_execute")
        if cli_impl is None:
            return {"success": False, "error": "cli_execute tool not registered", "transport_used": "cli"}
        
        result = await cli_impl.execute(device=device, config_commands=config_commands)
        
        return {
            "success": result.error is None,
            "output": result.data,
            "error": result.error,
            "transport_used": "cli",
            "__meta__": result.metadata,
        }
    
    async def _execute_auto(
        self,
        device: str,
        config_commands: list[str],
        interface: str | None,
        operation: str,
    ) -> dict[str, Any]:
        """Try NETCONF first, fallback to CLI on failure."""
        logger.info(f"Auto mode for {device}: trying NETCONF first")
        
        # Try NETCONF
        netconf_result = await self._execute_netconf(device, config_commands, interface, operation)
        
        if netconf_result.get("success"):
            logger.info(f"NETCONF succeeded for {device}")
            return netconf_result
        
        # Check if it's a connection error (worth trying CLI)
        error = netconf_result.get("error", "")
        error_l = error.lower()
        if (
            "connection" in error_l
            or "refused" in error_l
            or "timeout" in error_l
            or "auth" in error_l
            or "authentication" in error_l
            or "permission denied" in error_l
        ):
            logger.warning(f"NETCONF failed for {device}, falling back to CLI: {error}")
            cli_result = await self._execute_cli(device, config_commands)
            cli_result["fallback_reason"] = f"NETCONF failed: {error}"
            return cli_result
        
        # Non-connection error (e.g., config validation), don't fallback
        logger.error(f"NETCONF failed for {device} with non-retriable error: {error}")
        return netconf_result
    
    def _build_netconf_payload(
        self,
        config_commands: list[str],
        interface: str | None,
        operation: str,
    ) -> str:
        """Build OpenConfig NETCONF payload from CLI commands.
        
        This is a simplified converter. For complex configs, the LLM should
        provide the XML payload directly via netconf_edit tool.
        """
        # Detect interface deletion
        if interface and operation == "delete":
            # IOS-XE OpenConfig can advertise support but still reject interface delete operations
            # with schema validation errors. For Loopback deletes, use Cisco native YANG over NETCONF.
            if interface.lower().startswith("loopback"):
                loop_id = interface[len("Loopback") :]
                if loop_id.isdigit():
                    return (
                        '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">\n'
                        "  <interface>\n"
                        '    <Loopback xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" '
                        'nc:operation="delete">\n'
                        f"      <name>{loop_id}</name>\n"
                        "    </Loopback>\n"
                        "  </interface>\n"
                        "</native>"
                    )

            # Fallback: attempt OpenConfig delete for non-loopback interfaces.
            return (
                '<interfaces xmlns="http://openconfig.net/yang/interfaces">\n'
                '  <interface xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" '
                'nc:operation="delete">\n'
                f"    <name>{interface}</name>\n"
                "  </interface>\n"
                "</interfaces>"
            )
        
        # For other operations, we need more sophisticated CLI-to-XML conversion
        # For now, return a placeholder that indicates CLI should be used
        # TODO: Implement full CLI-to-OpenConfig translation
        logger.warning("Complex CLI-to-NETCONF translation not implemented, using CLI fallback")
        return ""


# Global router instance
_config_router: DeviceConfigRouter | None = None


def get_config_router() -> DeviceConfigRouter:
    """Get or create the global config router."""
    global _config_router
    if _config_router is None:
        _config_router = DeviceConfigRouter()
    return _config_router


@tool
async def device_config(
    device: str,
    config_commands: list[str],
    interface: str | None = None,
    operation: str = "merge",
) -> dict[str, Any]:
    """Execute configuration changes on network devices (HITL required).
    
    This is the PRIMARY tool for device configuration. It automatically:
    1. Checks device's config_transport tag from NetBox
    2. Routes to NETCONF (preferred) or CLI based on tag
    3. Falls back to CLI if NETCONF fails (for 'auto' mode)
    
    **Transport Selection** (NetBox custom_field 'config_transport'):
    - 'netconf': IOS-XE, Arista, Junos (OpenConfig support)
    - 'cli': Legacy devices (SSH only)
    - 'auto' or unset: Try NETCONF first, fallback to CLI
    
    Args:
        device: Target device hostname (e.g., "R1")
        config_commands: List of CLI-style configuration commands
                        Example: ["no interface Loopback11"]
        interface: Target interface name (for interface operations)
                  Example: "Loopback11"
        operation: Config operation type
                  - "merge": Add/modify configuration (default)
                  - "delete": Remove configuration
                  - "replace": Replace entire subtree
    
    Returns:
        dict with:
        - success: True if config applied
        - output: Execution result
        - transport_used: 'netconf' or 'cli'
        - error: Error message if failed
        - fallback_reason: Why CLI was used (if auto fallback)
    
    Examples:
        # Delete an interface
        device_config(
            device="R1",
            config_commands=["no interface Loopback11"],
            interface="Loopback11",
            operation="delete"
        )
        
        # Add configuration
        device_config(
            device="R1",
            config_commands=[
                "interface Loopback99",
                "ip address 99.99.99.99 255.255.255.255"
            ]
        )
        
        # Multiple devices - call once per device
        for dev in ["R1", "R2", "R3"]:
            device_config(device=dev, config_commands=["logging host 10.0.0.1"])
    """
    router = get_config_router()
    return await router.execute_config(
        device=device,
        config_commands=config_commands,
        interface=interface,
        operation=operation,
    )

