"""TextFSM parsing utilities for network command output.

This module provides TextFSM-based parsing for structured network data extraction.
Separated from network.py for better maintainability (per DESIGN_V0.81.md optimization).
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from nornir.core import Nornir
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import AggregatedResult, Result
from nornir_netmiko.tasks import netmiko_send_command

from config.settings import settings

if TYPE_CHECKING:
    from olav.core.database import OlavDatabase
    from olav.tools.network_executor import CommandExecutionResult


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count (rough approximation: 1 token ≈ 4 characters)
    """
    # Rough approximation: 1 token ≈ 4 characters for English text
    # For network output, this is a reasonable estimate
    return len(text) // 4


def execute_with_textfsm(
    nr: Nornir,
    device: str,
    command: str,
    timeout: int,
    db: "OlavDatabase",
    blacklist_checker: object,  # Function that takes str and returns str|None
    platform_detector: object,  # Function that takes str and returns str|None
) -> "CommandExecutionResult":
    """Execute command with TextFSM parsing.

    Args:
        nr: Nornir instance
        device: Device name or IP
        command: Command to execute
        timeout: Command timeout in seconds
        db: Database instance for whitelist/audit
        blacklist_checker: Function to check if command is blacklisted
        platform_detector: Function to detect device platform

    Returns:
        CommandExecutionResult with structured output and token statistics

    Raises:
        Exception: If TextFSM parsing fails
    """
    from olav.tools.network_executor import CommandExecutionResult

    start_time = datetime.now()

    # Check blacklist
    blacklisted_pattern = blacklist_checker(command) if callable(blacklist_checker) else None  # type: ignore[arg-type]
    if blacklisted_pattern:
        return CommandExecutionResult(
            device=device,
            command=command,
            success=False,
            error=f"Command is blacklisted (matches pattern: {blacklisted_pattern})",
            duration_ms=0,
        )

    # Detect platform
    platform = platform_detector(device) if callable(platform_detector) else None  # type: ignore[arg-type]

    # Check whitelist
    if platform and isinstance(platform, str):
        if not db.is_command_allowed(command, platform):
            return CommandExecutionResult(
                device=device,
                command=command,
                success=False,
                error=f"Command not in whitelist for platform {platform}",
                duration_ms=0,
            )

    # Set custom TextFSM template directory if exists (higher priority)
    custom_textfsm_dir = Path(settings.agent_dir) / "config" / "textfsm"
    if custom_textfsm_dir.exists() and (custom_textfsm_dir / "index").exists():
        os.environ["NET_TEXTFSM"] = str(custom_textfsm_dir.resolve())

    # Execute command with TextFSM
    try:
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

        host_result: Result = result[device]  # type: ignore[assignment]
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
        structured_output = json.dumps(parsed_output, default=str)
        parsed_tokens = estimate_tokens(structured_output)
        raw_tokens = int(parsed_tokens * 3)  # Estimate raw was 3x larger
        tokens_saved = raw_tokens - parsed_tokens

        # Log to audit trail
        db.log_execution(
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
        raise Exception(f"TextFSM parsing failed: {e}") from e
    except Exception as e:
        raise Exception(f"TextFSM execution failed: {e}") from e
