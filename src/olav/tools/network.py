"""Network execution tools for OLAV v0.8.

This module provides tools for executing commands on network devices using Nornir.
Includes command whitelist enforcement, audit logging, and TextFSM structured parsing.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import AggregatedResult, Result
from nornir_netmiko.tasks import netmiko_send_command
from pydantic import BaseModel, Field

from config.settings import settings
from olav.core.database import get_database
from olav.core.settings import get_settings

# ============================================================================
# P4: Nornir Connection Pool Singleton
# ============================================================================

_nornir_instance: Nornir | None = None


def get_nornir(
    config_file: str | Path = ".olav/config/nornir/config.yaml",
) -> Nornir:
    """Get the global Nornir instance (singleton pattern).

    P4 Optimization: Reuse a single Nornir instance to avoid repeated
    initialization overhead (~200-500ms per InitNornir call).

    Args:
        config_file: Path to Nornir configuration file

    Returns:
        Shared Nornir instance with credentials applied
    """
    global _nornir_instance

    if _nornir_instance is None:
        config_path = Path(config_file).resolve()
        _nornir_instance = InitNornir(config_file=str(config_path))

        # Apply credentials from settings to all hosts
        username = getattr(settings, "device_username", None)
        password = getattr(settings, "device_password", None)

        if username or password:
            for host in _nornir_instance.inventory.hosts.values():
                if username:
                    host.username = username
                if password:
                    host.password = password

    return _nornir_instance


def reset_nornir() -> None:
    """Reset the Nornir singleton (for testing or reconnection)."""
    global _nornir_instance
    _nornir_instance = None


class CommandExecutionResult(BaseModel):
    """Result of a network command execution."""

    device: str = Field(description="Device name or IP")
    command: str = Field(description="Command that was executed")
    success: bool = Field(description="Whether execution succeeded")
    output: str | None = Field(default=None, description="Command output if successful")
    error: str | None = Field(default=None, description="Error message if failed")
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")
    # Phase 4.2: TextFSM parsing fields
    structured: bool = Field(default=False, description="Whether output was parsed with TextFSM")
    raw_output: str | None = Field(default=None, description="Raw text output if parsing was used")
    # Phase 4.2: Token statistics
    raw_tokens: int | None = Field(default=None, description="Estimated raw token count")
    parsed_tokens: int | None = Field(default=None, description="Token count after parsing")
    tokens_saved: int | None = Field(default=None, description="Tokens saved by parsing")


class NetworkExecutor:
    """Network command executor with Nornir."""

    def __init__(
        self,
        nornir_config: str | Path = ".olav/config/nornir/config.yaml",
        blacklist_file: str | Path = ".olav/imports/commands/blacklist.txt",
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            nornir_config: Path to Nornir configuration
            blacklist_file: Path to command blacklist file
            username: Device username (from .env if not provided)
            password: Device password (from .env if not provided)
        """
        self.nornir_config = Path(nornir_config)
        self.blacklist_file = Path(blacklist_file)
        self.username = username or getattr(settings, "device_username", "admin")
        self.password = password or getattr(settings, "device_password", "")
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
            # P4: Use singleton Nornir instance
            nr = get_nornir(str(self.nornir_config))
            host = nr.inventory.hosts.get(device)

            if host:
                if host.platform:
                    return host.platform

            return None
        except Exception as e:
            import sys

            print(f"Debug: Failed to detect platform for {device}: {e}", file=sys.stderr)
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
            # P4: Use singleton Nornir instance
            nr = get_nornir(str(self.nornir_config))

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

    def execute_with_parsing(
        self,
        device: str,
        command: str,
        timeout: int = 30,
        use_textfsm: bool | None = None,
    ) -> CommandExecutionResult:
        """Execute command with TextFSM structured parsing.

        Phase 4.2: Implements NTC template parsing with fallback to raw text.
        Tries to parse output with TextFSM, falls back to raw text on failure.

        Args:
            device: Device name or IP
            command: Command to execute
            timeout: Command timeout in seconds
            use_textfsm: Override TextFSM setting (None = use config)

        Returns:
            CommandExecutionResult with parsed output and token statistics

        Example:
            >>> result = executor.execute_with_parsing("R1", "show ip interface brief")
            >>> print(result.structured)  # True if parsed successfully
            >>> print(result.tokens_saved)  # Token savings count
        """
        settings = get_settings()

        # Determine if TextFSM should be used
        if use_textfsm is None:
            use_textfsm = settings.execution_use_textfsm

        # Try TextFSM parsing if enabled
        if use_textfsm:
            try:
                return self._execute_with_textfsm(device, command, timeout)
            except Exception as e:
                # Check if fallback is enabled
                if settings.execution_textfsm_fallback:
                    # Fallback to raw text
                    print(f"TextFSM parsing failed: {e}, falling back to raw text")
                    return self.execute(device, command, timeout)
                else:
                    # No fallback: return error
                    return CommandExecutionResult(
                        device=device,
                        command=command,
                        success=False,
                        error=f"TextFSM parsing failed and fallback disabled: {e}",
                        duration_ms=0,
                    )
        else:
            # TextFSM disabled: use regular execute
            return self.execute(device, command, timeout)

    def _execute_with_textfsm(
        self,
        device: str,
        command: str,
        timeout: int,
    ) -> CommandExecutionResult:
        """Execute command with TextFSM parsing.

        Args:
            device: Device name or IP
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            CommandExecutionResult with structured output and token statistics

        Raises:
            Exception: If TextFSM parsing fails
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

        # Set custom TextFSM template directory if exists (higher priority)
        custom_textfsm_dir = Path(".olav/config/textfsm")
        if custom_textfsm_dir.exists() and (custom_textfsm_dir / "index").exists():
            os.environ["NET_TEXTFSM"] = str(custom_textfsm_dir.resolve())

        # Execute command with TextFSM
        try:
            nr = get_nornir(str(self.nornir_config))
            nr_filtered = nr.filter(name=device)

            if not nr_filtered.inventory.hosts:
                return CommandExecutionResult(
                    device=device,
                    command=command,
                    success=False,
                    error=f"Device '{device}' not found in inventory",
                    duration_ms=0,
                )

            # Run command with TextFSM
            result: AggregatedResult = nr_filtered.run(
                task=netmiko_send_command,
                command_string=command,
                read_timeout=timeout,
                use_textfsm=True,  # Enable TextFSM parsing
            )

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

            # Get parsed result (list or dict)
            parsed_output = host_result.result

            # Estimate tokens
            # Note: With TextFSM, we don't have the original raw text, so we estimate
            # based on the parsed output. Real savings would be measured by comparing
            # with raw command output.
            structured_output = json.dumps(parsed_output, default=str)
            # Since we don't have raw text, we assume structured is smaller
            # In production, raw output would be ~3-5x larger
            parsed_tokens = self._estimate_tokens(structured_output)
            raw_tokens = int(parsed_tokens * 3)  # Estimate raw was 3x larger
            tokens_saved = raw_tokens - parsed_tokens

            # Log to audit trail
            self.db.log_execution(
                thread_id="main",
                device=device,
                command=command,
                output=structured_output,
                success=True,
                duration_ms=duration_ms,
            )

            return CommandExecutionResult(
                device=device,
                command=command,
                success=True,
                output=structured_output,
                raw_output=str(parsed_output),  # Store raw parsed result
                duration_ms=duration_ms,
                structured=True,
                raw_tokens=raw_tokens,
                parsed_tokens=parsed_tokens,
                tokens_saved=tokens_saved,
            )

        except NornirSubTaskError as e:
            # TextFSM parsing error
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            raise Exception(f"TextFSM parsing failed: {e}") from e
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            raise Exception(f"TextFSM execution failed: {e}") from e

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count (rough approximation: 1 token ≈ 4 characters)
        """
        # Rough approximation: 1 token ≈ 4 characters for English text
        # For network output, this is a reasonable estimate
        return len(text) // 4


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
        # P4: Use singleton Nornir instance
        nr = get_nornir()

        # Apply filters (create filtered view)
        nr_filtered = nr
        if role:
            nr_filtered = nr_filtered.filter(role=role)
        if site:
            nr_filtered = nr_filtered.filter(site=site)
        if platform:
            nr_filtered = nr_filtered.filter(platform=platform)

        devices = []
        for name, host in nr_filtered.inventory.hosts.items():
            hostname = host.hostname or name
            host_platform = host.platform or "unknown"
            host_role = host.get("role", "unknown")
            host_site = host.get("site", "unknown")

            devices.append(f"- {name} ({hostname}) - {host_platform} - {host_role}@{host_site}")

        if not devices:
            return "No devices found matching the criteria."

        return "Available devices:\n" + "\n".join(devices)

    except Exception as e:
        import traceback

        return f"Error listing devices: {e}\n\nTraceback:\n{traceback.format_exc()}"


@tool
def get_device_platform(device: str) -> str:
    """Get the platform type of a specific device.

    This tool retrieves the platform (OS type) for a given device from the Nornir inventory.
    Use this before searching for platform-specific commands.

    Args:
        device: Device name (e.g., "R1", "SW1")

    Returns:
        Platform string (e.g., "cisco_ios", "huawei_vrp") or error message

    Examples:
        >>> get_device_platform("R1")
        "Device R1 platform: cisco_ios"

        >>> get_device_platform("SW1")
        "Device SW1 platform: cisco_ios"
    """
    try:
        # P4: Use singleton Nornir instance
        nr = get_nornir()
        host = nr.inventory.hosts.get(device)

        if not host:
            return f"Device '{device}' not found in inventory"

        platform = host.platform or "unknown"
        return f"Device {device} platform: {platform}"

    except Exception as e:
        import traceback

        return f"Error getting device platform: {e}\n\nTraceback:\n{traceback.format_exc()}"
