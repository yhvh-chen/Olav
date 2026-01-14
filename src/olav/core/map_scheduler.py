"""Unified Data Layer - Map Scheduler for OLAV v0.8.

This module provides async execution control for Map phase operations
with concurrency limiting and error handling (docs/0.md).

Core functions:
- run_inspect_map: Run inspect Map phase with concurrency control
- run_logs_map: Run logs Map phase with concurrency control
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from olav.core.llm_interface import MapReduceLLM

# =============================================================================
# Configuration
# =============================================================================


@dataclass
class MapConfig:
    """Configuration for Map phase execution.

    Attributes:
        max_concurrent: Maximum number of concurrent LLM calls
        timeout_per_call: Timeout for single LLM call (seconds)
        retry_count: Number of retries on failure
        continue_on_error: Whether to continue if single device fails
    """

    max_concurrent: int = 5
    timeout_per_call: float = 30.0
    retry_count: int = 3
    continue_on_error: bool = True


# =============================================================================
# Map Phase: Inspect
# =============================================================================


async def run_inspect_map(
    devices: list[str],
    sync_path: Path,
    llm: MapReduceLLM,
    config: MapConfig | None = None,
) -> dict[str, Any]:
    """Run inspect Map phase with concurrency control.

    This function executes LLM analysis for each device and each check type,
    with controlled concurrency and error handling.

    Args:
        devices: List of device names
        sync_path: Path to sync directory
        llm: MapReduceLLM instance
        config: Optional MapConfig (uses defaults if None)

    Returns:
        Dictionary with results:
        {
            "success": ["R1", "R2", ...],
            "failed": [{"device": "R3", "check": "cpu", "error": "timeout"}],
            "results_path": "map/inspect/"
        }

    Examples:
        >>> result = await run_inspect_map(["R1", "R2"], sync_path, llm)
        >>> print(result["success"])
        ["R1", "R2"]
    """
    if config is None:
        config = MapConfig()

    # Define check types for L1-L4 framework
    check_types = {
        "L4": ["cpu", "memory"],
        "L1": ["temperature", "power"],
        "L3": ["ospf", "bgp"],
        "L2": ["stp", "mac_table"],
    }

    # Collect all tasks
    tasks = []
    for device in devices:
        for layer, checks in check_types.items():
            for check in checks:
                tasks.append((device, layer, check))

    # Execute with semaphore for concurrency control
    semaphore = asyncio.Semaphore(config.max_concurrent)

    async def process_single_check(device: str, layer: str, check: str) -> dict[str, Any]:
        """Process single device check with semaphore."""
        async with semaphore:
            try:
                # Read raw output from sync data
                raw_file = _find_raw_file(sync_path, device, check)
                if not raw_file or not raw_file.exists():
                    return {
                        "device": device,
                        "check": check,
                        "status": "error",
                        "error": "Raw data not found",
                    }

                raw_output = raw_file.read_text(encoding="utf-8", errors="ignore")

                # Call LLM
                result = await asyncio.wait_for(
                    llm.analyze_inspect(device=device, layer=layer, check_type=check, raw_output=raw_output),
                    timeout=config.timeout_per_call,
                )

                # Save map result
                map_file = sync_path / "map" / "inspect" / f"{device}_{check}.json"
                map_file.parent.mkdir(parents=True, exist_ok=True)
                import json

                map_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

                return {"device": device, "check": check, "status": "success"}

            except TimeoutError:
                if config.continue_on_error:
                    return {"device": device, "check": check, "status": "failed", "error": "timeout"}
                else:
                    raise
            except Exception as e:
                if config.continue_on_error:
                    return {"device": device, "check": check, "status": "failed", "error": str(e)}
                else:
                    raise

    # Execute all tasks concurrently
    results = await asyncio.gather(*[process_single_check(d, l, c) for d, l, c in tasks], return_exceptions=True)

    # Aggregate results
    success = []
    failed = []

    for result in results:
        if isinstance(result, Exception):
            failed.append({"error": str(result)})
        elif result["status"] == "success":
            success.append(result["device"])
        else:
            failed.append(result)

    return {
        "success": list(set(success)),
        "failed": failed,
        "results_path": "map/inspect/",
        "timestamp": datetime.now().isoformat(),
    }


def _find_raw_file(sync_path: Path, device: str, check: str) -> Path | None:
    """Find raw output file for a device and check.

    Args:
        sync_path: Path to sync directory
        device: Device name
        check: Check type

    Returns:
        Path to raw file or None
    """
    # Map check types to raw directories
    check_to_category = {
        "cpu": "system",
        "memory": "system",
        "temperature": "environment",
        "power": "environment",
        "ospf": "routing",
        "bgp": "routing",
        "stp": "configs",
        "mac_table": "system",
        "interface": "interfaces",
    }

    category = check_to_category.get(check, "system")
    raw_file = sync_path / "raw" / category / f"{device}.txt"

    return raw_file if raw_file.exists() else None


# =============================================================================
# Map Phase: Logs
# =============================================================================


async def run_logs_map(
    devices: list[str],
    sync_path: Path,
    llm: MapReduceLLM,
    config: MapConfig | None = None,
) -> dict[str, Any]:
    """Run logs Map phase with concurrency control.

    This function executes LLM analysis for each device's logs,
    with controlled concurrency and error handling.

    Args:
        devices: List of device names
        sync_path: Path to sync directory
        llm: MapReduceLLM instance
        config: Optional MapConfig (uses defaults if None)

    Returns:
        Dictionary with results:
        {
            "success": ["R1", "R2", ...],
            "failed": [{"device": "R3", "error": "timeout"}],
            "results_path": "map/logs/"
        }

    Examples:
        >>> result = await run_logs_map(["R1", "R2"], sync_path, llm)
        >>> print(result["success"])
        ["R1", "R2"]
    """
    if config is None:
        config = MapConfig()

    # Execute with semaphore for concurrency control
    semaphore = asyncio.Semaphore(config.max_concurrent)

    async def process_device_logs(device: str) -> dict[str, Any]:
        """Process single device logs with semaphore."""
        async with semaphore:
            try:
                # Read raw logs from sync data
                log_file = sync_path / "raw" / "logging" / f"{device}.txt"
                if not log_file.exists():
                    return {
                        "device": device,
                        "status": "error",
                        "error": "Log file not found",
                    }

                raw_logs = log_file.read_text(encoding="utf-8", errors="ignore")

                # Parse events
                from olav.tools.event_tools import parse_device_logs

                events = parse_device_logs(device=device, raw_log=raw_logs)

                # Call LLM
                result = await asyncio.wait_for(
                    llm.analyze_logs(device=device, events=events),
                    timeout=config.timeout_per_call,
                )

                # Save map result
                map_file = sync_path / "map" / "logs" / f"{device}.json"
                map_file.parent.mkdir(parents=True, exist_ok=True)
                import json

                map_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

                return {"device": device, "status": "success"}

            except TimeoutError:
                if config.continue_on_error:
                    return {"device": device, "status": "failed", "error": "timeout"}
                else:
                    raise
            except Exception as e:
                if config.continue_on_error:
                    return {"device": device, "status": "failed", "error": str(e)}
                else:
                    raise

    # Execute all tasks concurrently
    results = await asyncio.gather(*[process_device_logs(d) for d in devices], return_exceptions=True)

    # Aggregate results
    success = []
    failed = []

    for result in results:
        if isinstance(result, Exception):
            failed.append({"error": str(result)})
        elif result["status"] == "success":
            success.append(result["device"])
        else:
            failed.append(result)

    return {
        "success": list(set(success)),
        "failed": failed,
        "results_path": "map/logs/",
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# Sync Function for Non-Async Contexts
# =============================================================================


def run_inspect_map_sync(
    devices: list[str],
    sync_path: Path,
    llm: MapReduceLLM,
    config: MapConfig | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for run_inspect_map.

    Args:
        devices: List of device names
        sync_path: Path to sync directory
        llm: MapReduceLLM instance
        config: Optional MapConfig

    Returns:
        Results dictionary
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(run_inspect_map(devices, sync_path, llm, config))


def run_logs_map_sync(
    devices: list[str],
    sync_path: Path,
    llm: MapReduceLLM,
    config: MapConfig | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for run_logs_map.

    Args:
        devices: List of device names
        sync_path: Path to sync directory
        llm: MapReduceLLM instance
        config: Optional MapConfig

    Returns:
        Results dictionary
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(run_logs_map(devices, sync_path, llm, config))
