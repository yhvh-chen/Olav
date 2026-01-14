"""Unified Data Layer - Map Tools for OLAV v0.8.

This module provides tools for aggregating Map phase results in the
Map-Reduce workflow (docs/0.md).

Core functions:
- aggregate_inspect_maps: Aggregate all inspect map results into summary
- aggregate_log_maps: Aggregate all log map results into summary
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# =============================================================================
# Tool 1: aggregate_inspect_maps
# =============================================================================


def aggregate_inspect_maps(map_dir: Path) -> dict[str, Any]:
    """Aggregate all inspect map results into summary.

    This function reads all JSON files from map/inspect/ directory
    and aggregates them into a summary for the Reduce phase.

    Args:
        map_dir: Path to map/inspect/ directory

    Returns:
        Dictionary with aggregated results:
        {
            "summary": {"total_checks": 42, "ok": 38, "warning": 3, "critical": 1},
            "anomalies": [...],  # only warning/critical items
            "all_ok_devices": ["R2", "R4"]
        }

    Examples:
        >>> summary = aggregate_inspect_maps(Path("data/sync/2026-01-13/map/inspect"))
        >>> print(summary["summary"])
        {"total_checks": 42, "ok": 38, "warning": 3, "critical": 1}
    """
    if not map_dir.exists():
        return {
            "summary": {"total_checks": 0, "ok": 0, "warning": 0, "critical": 0},
            "anomalies": [],
            "all_ok_devices": [],
            "generated_at": datetime.now().isoformat(),
        }

    # Read all map files
    all_results = []
    for map_file in map_dir.glob("*.json"):
        try:
            content = map_file.read_text(encoding="utf-8")
            result = json.loads(content)
            all_results.append(result)
        except (OSError, json.JSONDecodeError):
            continue

    if not all_results:
        return {
            "summary": {"total_checks": 0, "ok": 0, "warning": 0, "critical": 0},
            "anomalies": [],
            "all_ok_devices": [],
            "generated_at": datetime.now().isoformat(),
        }

    # Aggregate by status
    total_checks = len(all_results)
    status_counts = {"ok": 0, "warning": 0, "critical": 0, "error": 0}

    anomalies = []
    device_checks: dict[str, dict[str, int]] = {}

    for result in all_results:
        status = result.get("status", "unknown")
        if status in status_counts:
            status_counts[status] += 1

        # Track device-level status
        device = result.get("device", "unknown")
        if device not in device_checks:
            device_checks[device] = {"ok": 0, "warning": 0, "critical": 0, "error": 0}
        if status in device_checks[device]:
            device_checks[device][status] += 1

        # Collect anomalies (warning or critical)
        if status in ("warning", "critical"):
            anomaly = {
                "device": device,
                "check": result.get("check", "unknown"),
                "status": status,
                "layer": result.get("layer", "unknown"),
            }

            # Add optional fields
            if "value" in result:
                anomaly["value"] = result["value"]
            if "threshold" in result:
                anomaly["threshold"] = result["threshold"]
            if "detail" in result:
                anomaly["detail"] = result["detail"]
            if "interface" in result:
                anomaly["interface"] = result["interface"]

            anomalies.append(anomaly)

    # Find devices with all checks OK
    all_ok_devices = [
        device
        for device, counts in device_checks.items()
        if counts["warning"] == 0 and counts["critical"] == 0 and counts["error"] == 0
    ]

    # Sort anomalies by severity and device
    anomalies.sort(
        key=lambda x: ({"critical": 0, "warning": 1, "error": 2}.get(x["status"], 3), x["device"])
    )

    return {
        "summary": {
            "total_devices": len(device_checks),
            "total_checks": total_checks,
            "status_counts": status_counts,
        },
        "anomalies": anomalies,
        "all_ok_devices": sorted(all_ok_devices),
        "generated_at": datetime.now().isoformat(),
    }


# =============================================================================
# Tool 2: aggregate_log_maps
# =============================================================================


def aggregate_log_maps(map_dir: Path) -> dict[str, Any]:
    """Aggregate all log map results into summary.

    This function reads all JSON files from map/logs/ directory
    and aggregates them into a summary for the Reduce phase.

    Args:
        map_dir: Path to map/logs/ directory

    Returns:
        Dictionary with aggregated results:
        {
            "summary": {"total_devices": 6, "devices_with_events": 2},
            "anomalies": [...],  # only devices with events
            "all_ok_devices": ["R2", "R4", "SW1", "SW2"]
        }

    Examples:
        >>> summary = aggregate_log_maps(Path("data/sync/2026-01-13/map/logs"))
        >>> print(summary["summary"])
        {"total_devices": 6, "devices_with_events": 2}
    """
    if not map_dir.exists():
        return {
            "summary": {"total_devices": 0, "devices_with_events": 0, "total_events": 0},
            "anomalies": [],
            "all_ok_devices": [],
            "generated_at": datetime.now().isoformat(),
        }

    # Read all map files
    all_results = []
    for map_file in map_dir.glob("*.json"):
        try:
            content = map_file.read_text(encoding="utf-8")
            result = json.loads(content)
            all_results.append(result)
        except (OSError, json.JSONDecodeError):
            continue

    if not all_results:
        return {
            "summary": {"total_devices": 0, "devices_with_events": 0, "total_events": 0},
            "anomalies": [],
            "all_ok_devices": [],
            "generated_at": datetime.now().isoformat(),
        }

    total_devices = len(all_results)
    devices_with_events = 0
    total_events = 0

    anomalies = []
    all_ok_devices = []

    for result in all_results:
        device = result.get("device", "unknown")
        status = result.get("status", "ok")
        event_count = result.get("event_count", 0)
        events = result.get("events", [])

        if status == "warning" and events:
            devices_with_events += 1
            total_events += event_count

            anomaly = {
                "device": device,
                "status": status,
                "event_count": event_count,
                "events": events,
            }

            anomalies.append(anomaly)
        else:
            # Device has no events to report
            all_ok_devices.append(device)

    # Sort anomalies by device
    anomalies.sort(key=lambda x: x["device"])

    return {
        "summary": {
            "total_devices": total_devices,
            "devices_with_events": devices_with_events,
            "total_events": total_events,
        },
        "anomalies": anomalies,
        "all_ok_devices": sorted(all_ok_devices),
        "generated_at": datetime.now().isoformat(),
    }


# =============================================================================
# Utility: Save Summary to File
# =============================================================================


def save_inspect_summary(sync_dir: Path, summary: dict[str, Any]) -> Path:
    """Save inspect summary to JSON file.

    Args:
        sync_dir: Path to sync directory
        summary: Aggregated inspect summary

    Returns:
        Path to saved summary file
    """
    reports_dir = sync_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_file = reports_dir / "inspect_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary_file


def save_log_summary(sync_dir: Path, summary: dict[str, Any]) -> Path:
    """Save log summary to JSON file.

    Args:
        sync_dir: Path to sync directory
        summary: Aggregated log summary

    Returns:
        Path to saved summary file
    """
    reports_dir = sync_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_file = reports_dir / "log_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary_file
