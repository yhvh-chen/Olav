"""Network execution tools for OLAV v0.8.

This module provides tools for executing commands on network devices using Nornir.
Includes command whitelist enforcement and audit logging.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from nornir import InitNornir
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import AggregatedResult, Result
from nornir_netmiko.tasks import netmiko_send_command
from pydantic import BaseModel, Field

from olav.core.database import get_database


class CommandExecutionResult(BaseModel):
    """Result of a network command execution."""

    device: str = Field(description="Device name or IP")
    command: str = Field(description="Command that was executed")
    success: bool = Field(description="Whether execution succeeded")
    output: str | None = Field(description="Command output if successful")
    error: str | None = Field(description="Error message if failed")
    duration_ms: int = Field(description="Execution time in milliseconds")


class NetworkExecutor:
    """Network command executor with Nornir."""

    def __init__(
        self,
        nornir_config: str | Path = ".olav/config/nornir/config.yaml",
        blacklist_file: str | Path = ".olav/imports/commands/blacklist.txt",
    ):
        """Initialize executor.

        Args:
            nornir_config: Path to Nornir configuration
            blacklist_file: Path to command blacklist file
        """
        self.nornir_config = Path(nornir_config)
        self.blacklist_file = Path(blacklist_file)
        self.blacklist = self._load_blacklist()
        self.db = get_database()

    def _load_blacklist(self) -> set[str]:
        """Load command blacklist from file.

        Returns:
            Set of blacklisted command patterns
        """
        if not self.blacklist_file.exists():
            return set()

        blacklist = set()
        for line in self.blacklist_file.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                blacklist.add(line.lower())

        return blacklist

    def _is_blacklisted(self, command: str) -> str | None:
        """Check if command is blacklisted.

        Args:
            command: Command to check

        Returns:
            Blacklisted pattern that matched, or None
        """
        cmd_lower = command.lower().strip()

        for pattern in self.blacklist:
            if pattern.endswith("*"):
                # Wildcard match
                if cmd_lower.startswith(pattern[:-1]):
                    return pattern
            else:
                # Exact match
                if cmd_lower == pattern:
                    return pattern

        return None

    def _detect_platform(self, device: str) -> str | None:
        """Detect device platform from Nornir inventory.

        Args:
            device: Device name

        Returns:
            Platform string (e.g., "cisco_ios") or None
        """
        try:
            nr = InitNornir(config=str(self.nornir_config))
            host = nr.inventory.hosts.get(device)

            if host and host.platform:
                return host.platform

            return None
        except Exception:
            return None

    def execute(
        self,
        device: str,
        command: str,
        timeout: int = 30,
    ) -> CommandExecutionResult:
        """Execute a command on a network device.

        Args:
            device: Device name or IP
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            CommandExecutionResult
        """
        start_time = datetime.now()

        # Check blacklist
        blacklisted_pattern = self._is_blacklisted(command)
        if blacklisted_pattern:
            return CommandExecutionResult(
                device=device,
                command=command,
                success=False,
                error=f"Command is blacklisted (matches pattern: {blacklisted_pattern})",
                duration_ms=0,
            )

        # Detect platform
        platform = self._detect_platform(device)

        # Check whitelist
        if platform:
            if not self.db.is_command_allowed(command, platform):
                return CommandExecutionResult(
                    device=device,
                    command=command,
                    success=False,
                    error=f"Command not in whitelist for platform {platform}",
                    duration_ms=0,
                )

        # Execute command
        try:
            nr = InitNornir(config=str(self.nornir_config))

            # Filter to single device
            nr_filtered = nr.filter(name=device)

            if not nr_filtered.inventory.hosts:
                return CommandExecutionResult(
                    device=device,
                    command=command,
                    success=False,
                    error=f"Device '{device}' not found in inventory",
                    duration_ms=0,
                )

            # Run command
            result: AggregatedResult = nr_filtered.run(
                task=netmiko_send_command,
                command_string=command,
                read_timeout=timeout,
            )

            # Extract result
            host_result: Result = result[device]

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            if host_result.failed:
                error_msg = str(host_result.exception) if host_result.exception else "Unknown error"
                return CommandExecutionResult(
                    device=device,
                    command=command,
                    success=False,
                    error=error_msg,
                    duration_ms=duration_ms,
                )

            # Log to audit trail
            self.db.log_execution(
                thread_id="main",  # TODO: Get from agent context
                device=device,
                command=command,
                output=str(host_result.result),
                success=True,
                duration_ms=duration_ms,
            )

            return CommandExecutionResult(
                device=device,
                command=command,
                success=True,
                output=str(host_result.result),
                duration_ms=duration_ms,
            )

        except NornirSubTaskError as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return CommandExecutionResult(
                device=device,
                command=command,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return CommandExecutionResult(
                device=device,
                command=command,
                success=False,
                error=f"Unexpected error: {e}",
                duration_ms=duration_ms,
            )


# Global executor instance
_executor: NetworkExecutor | None = None


def get_executor() -> NetworkExecutor:
    """Get the global network executor instance.

    Returns:
        NetworkExecutor instance
    """
    global _executor

    if _executor is None:
        _executor = NetworkExecutor()

    return _executor


@tool
def nornir_execute(device: str, command: str, timeout: int = 30) -> str:
    """Execute a command on a network device using Nornir.

    This tool executes CLI commands on network devices through Nornir/Netmiko.
    Commands must be in the whitelist (defined in .olav/imports/commands/*.txt).
    Dangerous commands in the blacklist will be rejected.

    Args:
        device: Device name or IP address from Nornir inventory
        command: CLI command to execute (e.g., "show version", "show interface status")
        timeout: Command timeout in seconds (default: 30)

    Returns:
        Command output or error message

    Examples:
        >>> nornir_execute("R1", "show version")
        "Cisco IOS XE, Version 17.3.1..."

        >>> nornir_execute("core-sw", "show interfaces status")
        "Port  Name  Status  Vlan..."
    """
    executor = get_executor()
    result = executor.execute(device=device, command=command, timeout=timeout)

    if result.success:
        return result.output or ""
    else:
        return f"Error: {result.error}"


@tool
def list_devices(
    role: str | None = None,
    site: str | None = None,
    platform: str | None = None,
) -> str:
    """List devices from the Nornir inventory.

    This tool queries the Nornir inventory to list available network devices.
    Devices can be filtered by role, site, or platform.

    Args:
        role: Optional role filter (e.g., "core", "access")
        site: Optional site filter (e.g., "datacenter1")
        platform: Optional platform filter (e.g., "cisco_ios", "huawei_vrp")

    Returns:
        List of devices with their properties

    Examples:
        >>> list_devices()
        "Available devices:
        - R1 (10.1.1.1) - cisco_ios - core
        - R2 (10.1.1.2) - cisco_ios - core
        - SW1 (10.1.2.1) - cisco_ios - access"

        >>> list_devices(role="core")
        "Core devices:
        - R1 (10.1.1.1) - cisco_ios
        - R2 (10.1.1.2) - cisco_ios"
    """
    try:
        from nornir import InitNornir

        nr = InitNornir(config=".olav/config/nornir/config.yaml")

        # Apply filters
        if role:
            nr = nr.filter(role=role)
        if site:
            nr = nr.filter(site=site)
        if platform:
            nr = nr.filter(platform=platform)

        devices = []
        for name, host in nr.inventory.hosts.items():
            hostname = host.hostname or name
            host_platform = host.platform or "unknown"
            host_role = host.get("role", "unknown")
            host_site = host.get("site", "unknown")

            devices.append(f"- {name} ({hostname}) - {host_platform} - {host_role}@{host_site}")

        if not devices:
            return "No devices found matching the criteria."

        return "Available devices:\n" + "\n".join(devices)

    except Exception as e:
        return f"Error listing devices: {e}"
