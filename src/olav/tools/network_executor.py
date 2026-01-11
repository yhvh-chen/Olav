"""Network command executor for OLAV v0.8.

This module provides the core NetworkExecutor class for executing commands
on network devices using Nornir/Netmiko.
Separated from network.py for better maintainability (per DESIGN_V0.81.md optimization).
"""

from datetime import datetime
from pathlib import Path

from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import AggregatedResult, Result
from nornir_netmiko.tasks import netmiko_send_command
from pydantic import BaseModel, Field

from config.settings import settings
from olav.core.database import get_database

# ============================================================================
# P4: Nornir Connection Pool Singleton
# ============================================================================

_nornir_instance: Nornir | None = None


def get_nornir(
    config_file: str | Path | None = None,
) -> Nornir:
    """Get the global Nornir instance (singleton pattern).

    P4 Optimization: Reuse a single Nornir instance to avoid repeated
    initialization overhead (~200-500ms per InitNornir call).

    Args:
        config_file: Path to Nornir configuration file (defaults to agent_dir/config/nornir/config.yaml)

    Returns:
        Shared Nornir instance with credentials applied
    """
    global _nornir_instance

    if _nornir_instance is None:
        if config_file is None:
            config_file = Path(settings.agent_dir) / "config" / "nornir" / "config.yaml"
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
        nornir_config: str | Path | None = None,
        blacklist_file: str | Path | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            nornir_config: Path to Nornir configuration (defaults to agent_dir/config/nornir/config.yaml)
            blacklist_file: Path to command blacklist file (defaults to agent_dir/imports/commands/blacklist.txt)
            username: Device username (from .env if not provided)
            password: Device password (from .env if not provided)
        """
        if nornir_config is None:
            nornir_config = Path(settings.agent_dir) / "config" / "nornir" / "config.yaml"
        if blacklist_file is None:
            blacklist_file = Path(settings.agent_dir) / "imports" / "commands" / "blacklist.txt"

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
                thread_id="main",
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
        # Determine if TextFSM should be used
        if use_textfsm is None:
            use_textfsm = settings.execution.use_textfsm

        # Try TextFSM parsing if enabled
        if use_textfsm:
            try:
                return self._execute_with_textfsm(
                    device=device,
                    command=command,
                    timeout=timeout,
                )
            except Exception as e:
                # Check if fallback is enabled
                if settings.execution.textfsm_fallback_to_raw:
                    print(f"TextFSM parsing failed: {e}, falling back to raw text")
                    return self.execute(device, command, timeout)
                else:
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

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count (rough approximation: 1 token ≈ 4 characters)
        """
        from olav.tools.network_parser import estimate_tokens

        return estimate_tokens(text)

    def _execute_with_textfsm(
        self,
        device: str,
        command: str,
        timeout: int = 30,
    ) -> CommandExecutionResult:
        """Execute command with TextFSM structured parsing (internal method).

        Phase 4.2: Implements NTC template parsing with token statistics.
        This is the internal method called by execute_with_parsing when TextFSM is enabled.

        Args:
            device: Device name or IP
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            CommandExecutionResult with parsed output and token statistics
        """
        from olav.tools.network_parser import execute_with_textfsm

        nr = get_nornir(str(self.nornir_config))
        return execute_with_textfsm(
            nr=nr,
            device=device,
            command=command,
            timeout=timeout,
            db=self.db,
            blacklist_checker=self._is_blacklisted,
            platform_detector=self._detect_platform,
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
