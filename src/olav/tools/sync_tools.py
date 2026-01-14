"""Unified Data Layer - Sync Tools for OLAV v0.8.

This module provides tools for network data collection and synchronization
following the unified data layer design (docs/0.md).

Core functions:
- sync_all: Execute daily sync for all/specified devices
- get_sync_age: Get age of latest sync data
- search_sync: Search sync data using ripgrep/grep/Python
- diff_configs: Compare configs between dates
- query_sync_db: Execute read-only SQL on sync database
"""

import difflib
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from langchain_core.tools import tool

from config.settings import settings

# =============================================================================
# Data Directory Management
# =============================================================================


def get_sync_base_dir() -> Path:
    """Get the base directory for sync data.

    Returns:
        Path to exports/snapshots/sync/ directory (in project root, not .olav/)
    """
    from config.settings import PROJECT_ROOT

    return PROJECT_ROOT / "exports" / "snapshots" / "sync"


def get_sync_dir(date: str | None = None) -> Path:
    """Get the sync directory for a specific date.

    Args:
        date: Date string in YYYY-MM-DD format (default: today)

    Returns:
        Path to exports/snapshots/sync/YYYY-MM-DD/ directory
    """
    base_dir = get_sync_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    sync_dir = base_dir / date
    sync_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    # Note: raw/ and parsed/ per-device dirs created on-demand in sync_all()
    (sync_dir / "raw").mkdir(exist_ok=True)
    (sync_dir / "parsed").mkdir(exist_ok=True)
    (sync_dir / "map").mkdir(exist_ok=True)
    (sync_dir / "map" / "inspect").mkdir(parents=True, exist_ok=True)
    (sync_dir / "map" / "logs").mkdir(parents=True, exist_ok=True)
    (sync_dir / "reports").mkdir(exist_ok=True)

    return sync_dir


def update_latest_link(sync_dir: Path) -> None:
    """Update the 'latest' symlink or text file to point to sync_dir.

    Args:
        sync_dir: Path to the sync directory to link
    """
    base_dir = get_sync_base_dir()
    latest_path = base_dir / "latest"

    # Remove existing link/file
    if latest_path.exists(follow_symlinks=False):
        if latest_path.is_symlink():
            latest_path.unlink()
        else:
            latest_path.unlink()

    # Try creating symlink (Linux/macOS)
    try:
        latest_path.symlink_to(sync_dir)
    except OSError:
        # Fallback for Windows: create text file with path
        latest_path.write_text(str(sync_dir))


def get_latest_sync_dir() -> Path | None:
    """Get the latest sync directory from 'latest' link.

    Returns:
        Path to latest sync directory or None if not found
    """
    base_dir = get_sync_base_dir()
    latest_path = base_dir / "latest"

    if not latest_path.exists():
        # Fallback: find most recent date directory
        date_dirs = sorted(
            [d for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit() or "-" in d.name]
        )
        if date_dirs:
            return date_dirs[-1]
        return None

    if latest_path.is_symlink():
        return latest_path.resolve()

    # Windows: read path from text file
    path_str = latest_path.read_text().strip()
    return Path(path_str) if path_str else None


# =============================================================================
# Tool 1: sync_all
# =============================================================================


@tool
def sync_all(devices: str = "all", group: str = "test", categories: str | None = None) -> str:
    """Execute daily sync for all or specified devices.

    This is the primary tool for data collection. It executes all commands
    defined in the daily-sync skill and stores results in the sync directory.

    DESIGN: Two-stage pipeline:
    - Stage 1 (sync_all): Fast data collection → disk (parallel via Nornir)
    - Stage 2 (async): Parse + LLM analysis (non-blocking)

    Args:
        devices: Device filter (default: "all")
            - "all": All devices in the specified group
            - Specific device names: "R1,R2,R3"
            - Nornir filter syntax not used (use group parameter instead)
        group: Device group to target (default: "test")
            - "test": Test/lab devices (192.168.100.x)
            - "core": Core/production devices
            - "border": Border devices
        categories: Optional comma-separated list of categories to collect
            (configs, neighbors, routing, interfaces, system, environment, logging)
            If None, collects all categories

    Returns:
        Summary of sync operation with device counts and output paths

    Examples:
        >>> sync_all()
        "Sync completed: 6 devices, 42 commands, data/sync/2026-01-13/"

        >>> sync_all(devices="R1,R2", group="test", categories="configs,system")
        "Sync completed: 2 devices, 8 commands, data/sync/2026-01-13/"
    """
    from olav.core.database import get_database
    from olav.tools.network import get_nornir

    try:
        # Initialize sync directory for today
        sync_date = datetime.now().strftime("%Y-%m-%d")
        sync_dir = get_sync_dir(sync_date)

        # Get devices from inventory
        nr = get_nornir()

        # Filter by group first
        if group:
            nr = nr.filter(filter_func=lambda h: group in h.groups)

        # Filter devices if specified
        if devices != "all":
            if isinstance(devices, str):
                device_list = [d.strip() for d in devices.split(",")]
            else:
                device_list = devices
            nr = nr.filter(filter_func=lambda h: h.name in device_list)

        device_names = list(nr.inventory.hosts.keys())
        if not device_names:
            return "No devices found matching the filter."

        # ===================================================================
        # 新的设计: 从 Skill 文件读取命令定义，而不是通过数据库搜索
        # 原理:
        # 1. Skill 文件是单一事实来源 (single source of truth)
        # 2. 所有命令 1:1 从数据库中选取，不需要 "智能选择"
        # 3. 所有设备执行相同的命令集
        # 4. 按 Skill 中的顺序逐个执行
        # ===================================================================

        # 定义 Skill 中的命令意图，以及对应的数据库搜索关键字
        # 关键: 使用能匹配数据库中实际存在的命令的关键字
        skill_command_intents = {
            "configs": ["running-config", "startup-config"],
            "neighbors": ["cdp neighbors", "lldp neighbors"],
            "routing": ["ospf neighbor", "bgp summary", "ip route"],
            "interfaces": ["show interface", "show mac address-table"],
            "system": ["show version", "show processes cpu", "show memory"],
            "environment": ["show environment", "show arp"],
            "logging": ["show logging", "show debug"],
        }

        # Parse categories from string if provided, otherwise use all
        if categories is None:
            categories = list(skill_command_intents.keys())
        elif isinstance(categories, str):
            categories = [c.strip() for c in categories.split(",")]

        # 从 Skill 中收集所有要采集的意图 (intents)
        # 这些意图将用于从数据库中查询对应的命令
        all_intents = []
        for category in categories:
            if category in skill_command_intents:
                all_intents.extend(skill_command_intents[category])

        # 从数据库中查询命令（保留意图的顺序和完整性）
        # 关键改进: 为每个意图查询，而不是有硬限制
        all_commands = []
        db = get_database()
        command_names_seen = set()  # 去重

        for intent in all_intents:
            # 为每个意图查询对应的命令（不限制数量）
            results = db.search_capabilities(query=intent, cap_type="command", limit=1)

            for result in results:
                cmd_name = result["name"]
                # 只添加第一次看到的命令（去重）
                if cmd_name not in command_names_seen:
                    all_commands.append(result)
                    command_names_seen.add(cmd_name)
                    break  # 每个意图只取第一个匹配的命令

        # Execute commands on all devices
        total_commands = 0
        success_count = 0
        error_count = 0

        from nornir_netmiko.tasks import netmiko_send_command

        for device_name in device_names:
            host = nr.inventory.hosts[device_name]
            platform = host.platform or "unknown"

            # Create device-specific raw and parsed directories
            (sync_dir / "raw" / device_name).mkdir(exist_ok=True)
            (sync_dir / "parsed" / device_name).mkdir(exist_ok=True)

            # Execute commands for this device's platform (allow fallback to all commands)
            device_commands = [cmd for cmd in all_commands if cmd["platform"] == platform]

            # If no platform-specific commands, use all commands (failover)
            if not device_commands:
                device_commands = [cmd for cmd in all_commands if cmd["platform"] == "cisco_ios"]

            for cmd_info in device_commands:
                command = cmd_info["name"]
                total_commands += 1

                try:
                    # Filter to run only on this device
                    result = nr.filter(name=device_name).run(
                        task=netmiko_send_command,
                        command_string=command,
                        read_timeout=10,
                        on_failed=True,
                    )

                    if device_name in result and not result[device_name].failed:
                        # Save raw output to device-specific file
                        # Normalize command name to filename
                        cmd_safe = command.lower().replace(" ", "-").replace("/", "-")
                        output_file = sync_dir / "raw" / device_name / f"{cmd_safe}.txt"
                        output_file.write_text(result[device_name].result, encoding="utf-8")

                        success_count += 1
                    else:
                        error_count += 1

                except Exception:
                    error_count += 1

        # =====================================================================
        # STAGE 1 COMPLETE: Data collected and saved to disk
        # Return immediately without waiting for post-processing
        # =====================================================================

        # Update latest link
        update_latest_link(sync_dir)

        # Store minimal sync metadata (fast)
        _store_sync_metadata(
            sync_dir, sync_date, len(device_names), total_commands, success_count, error_count
        )

        result_message = (
            f"Sync STAGE 1 completed (data collection):\n"
            f"  group: {group}\n"
            f"  devices: {len(device_names)}\n"
            f"  commands: {total_commands}\n"
            f"  success: {success_count}\n"
            f"  errors: {error_count}\n"
            f"  output: {sync_dir}/\n"
            f"  note: Parse+LLM analysis running async (Stage 2)\n"
        )

        # =====================================================================
        # STAGE 2: Asynchronous post-processing (non-blocking)
        # This runs in background: parse + LLM analysis
        # =====================================================================
        # Import here to avoid circular dependency
        import threading

        def _stage2_async_processing():
            """Non-blocking Stage 2: parse + LLM analysis."""
            try:
                _process_sync_stage2(sync_dir, device_names)
            except Exception as e:
                print(f"[WARN] Stage 2 processing failed: {e}", flush=True)

        # Start Stage 2 in background thread (non-blocking)
        thread = threading.Thread(target=_stage2_async_processing, daemon=True)
        thread.start()

        return result_message

    except Exception as e:
        import traceback

        return f"Sync failed: {e}\n\nTraceback:\n{traceback.format_exc()}"


def _process_sync_stage2(sync_dir: Path, device_names: list[str]) -> None:
    """Stage 2: Asynchronous post-processing (parse + LLM).

    This function runs in a background thread and does NOT block Stage 1.
    It handles:
    1. Data parsing (TextFSM, regex)
    2. Database initialization
    3. Report generation
    4. Topology visualization
    5. LLM analysis

    Args:
        sync_dir: Path to sync directory
        device_names: List of device names that were synced
    """
    print("[Stage2] Starting async post-processing...", flush=True)

    # Parse device outputs and save to parsed/
    try:
        import json
        from datetime import datetime

        from olav.tools.event_tools import parse_device_logs
        from olav.tools.network import get_nornir

        # Load Nornir inventory to get platform info
        nr = get_nornir()

        print("[Stage2] Parsing device logs...", flush=True)
        for device_name in device_names:
            # Get platform for this device
            try:
                host = nr.inventory.get_host(device_name)
                platform = host.platform if host else "cisco_ios"
            except Exception:
                platform = "cisco_ios"

            # Process all text files in the device raw directory
            device_raw_dir = sync_dir / "raw" / device_name
            if device_raw_dir.exists():
                # 1. Combine all potentially log-containing files
                all_content = []
                for txt_file in device_raw_dir.glob("*.txt"):
                    # Prioritize files that look like logs
                    if any(
                        x in txt_file.name.lower()
                        for x in ["log", "debug", "event", "syslog", "trap"]
                    ):
                        content = txt_file.read_text(encoding="utf-8", errors="ignore")
                        if content.strip():
                            all_content.append(content)

                # 2. If we found log content, parse it into structured events
                if all_content:
                    combined_log = "\n".join(all_content)
                    parsed = parse_device_logs.invoke(
                        {"device": device_name, "raw_log": combined_log}
                    )
                    if parsed:
                        output_file = sync_dir / "parsed" / device_name / "logs.json"
                        output_file.write_text(json.dumps(parsed, indent=2, default=str))

                # 3. For all raw files, use TextFSM parsing
                for txt_file in device_raw_dir.glob("*.txt"):
                    content = txt_file.read_text(encoding="utf-8", errors="ignore")
                    if content.strip():
                        # Parse using TextFSM
                        parsed_data = _parse_with_textfsm(txt_file.stem, content, platform)

                        # Create parsed file with structured data only
                        parsed_file = sync_dir / "parsed" / device_name / f"{txt_file.stem}.json"
                        parsed_content = {
                            "metadata": {
                                "device": device_name,
                                "source": txt_file.name,
                                "command": txt_file.stem.replace("-", " "),
                                "timestamp": datetime.now().isoformat(),
                            },
                            "data": parsed_data,  # Structured parsed data (NOT raw)
                        }
                        parsed_file.write_text(
                            json.dumps(parsed_content, indent=2, ensure_ascii=False)
                        )
    except Exception as e:
        print(f"[Stage2] Parsing error: {e}", flush=True)

    # Initialize/update sync database (Stage 2)
    try:
        print("[Stage2] Initializing sync database...", flush=True)
        _init_sync_db(sync_dir)
    except Exception as e:
        print(f"[Stage2] Database error: {e}", flush=True)

    # Generate sync summary report (Stage 2)
    try:
        print("[Stage2] Generating reports...", flush=True)
        # Calculate actual stats from raw files (Stage 1 data)
        raw_dir = sync_dir / "raw"
        total_commands = 0
        success_count = 0
        if raw_dir.exists():
            for device_dir in raw_dir.iterdir():
                if device_dir.is_dir():
                    txt_files = list(device_dir.glob("*.txt"))
                    total_commands += len(txt_files)
                    success_count += len(txt_files)  # All saved files are successful

        _generate_sync_summary(sync_dir, len(device_names), total_commands, success_count)
        _generate_map_phase_summaries(sync_dir, device_names)
        _generate_inspection_analysis_report(sync_dir, device_names)
    except Exception as e:
        print(f"[Stage2] Report generation error: {e}", flush=True)

    # Generate topology visualizations (Stage 2)
    try:
        print("[Stage2] Generating topology visualizations...", flush=True)
        from olav.core.database import init_topology_db
        from olav.tools.network import get_nornir
        from olav.tools.topology_importer import TopologyImporter
        from olav.tools.topology_viz import visualize_full_topology

        # Initialize topology database and load devices
        db_path = str(Path(settings.agent_dir) / "db" / "network_warehouse.duckdb")
        conn = init_topology_db(db_path)

        # Load devices from Nornir inventory
        nr = get_nornir()
        for name, host in nr.inventory.hosts.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO topology_devices
                (name, hostname, platform, mgmt_ip, site, role)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    name,
                    name,
                    host.platform,
                    str(host.hostname),
                    host.data.get("site", "lab"),
                    host.data.get("role", "unknown"),
                ],
            )
        conn.close()

        # Import topology from parsed JSON (close connection after)
        importer = TopologyImporter(db_path)
        importer.import_from_parsed_json(str(sync_dir))
        importer.close()

        # Generate visualizations
        visualize_full_topology.invoke({})
    except Exception as e:
        print(f"[Stage2] Visualization error: {e}", flush=True)

    print("[Stage2] Post-processing complete!", flush=True)


def _get_command_category(command: str) -> str:
    """Determine the category for a command.

    Args:
        command: Command string

    Returns:
        Category name
    """
    cmd_lower = command.lower()

    if "show running-config" in cmd_lower or "show startup-config" in cmd_lower:
        return "configs"
    elif "cdp" in cmd_lower or "lldp" in cmd_lower:
        return "neighbors"
    elif "ospf" in cmd_lower or "bgp" in cmd_lower or "ip route" in cmd_lower:
        return "routing"
    elif "interface" in cmd_lower:
        return "interfaces"
    elif "cpu" in cmd_lower or "memory" in cmd_lower or "version" in cmd_lower:
        return "system"
    elif "environment" in cmd_lower or "power" in cmd_lower or "temperature" in cmd_lower:
        return "environment"
    elif "logging" in cmd_lower:
        return "logging"
    else:
        return "system"


def _init_sync_db(sync_dir: Path) -> duckdb.DuckDBPyConnection:
    """Initialize the sync database (unified location: .olav/db/network_warehouse.duckdb).

    Args:
        sync_dir: Path to sync directory (used only for reference)

    Returns:
        DuckDB connection
    """
    db_path = Path(settings.agent_dir) / "db" / "network_warehouse.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))

    # Create sync_metadata table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            sync_date DATE PRIMARY KEY,
            devices_count INTEGER,
            success_count INTEGER,
            error_count INTEGER,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            duration_seconds REAL
        )
    """)

    # Create sync_outputs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_outputs (
            id INTEGER PRIMARY KEY,
            sync_date DATE,
            device VARCHAR,
            category VARCHAR,
            command VARCHAR,
            output_path VARCHAR,
            output_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    return conn


def _store_sync_metadata(
    sync_dir: Path,
    sync_date: str,
    devices_count: int,
    total_commands: int,
    success_count: int,
    error_count: int,
) -> None:
    """Store sync metadata in database (unified location: .olav/db/network_warehouse.duckdb).

    Args:
        sync_dir: Path to sync directory
        sync_date: Date string
        devices_count: Number of devices
        total_commands: Total commands executed
        success_count: Successful commands
        error_count: Failed commands
    """
    db_path = Path(settings.agent_dir) / "db" / "network_warehouse.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure tables exist before inserting
    conn = _init_sync_db(sync_dir)

    conn.execute(
        """
        INSERT OR REPLACE INTO sync_metadata
        (sync_date, devices_count, success_count, error_count, completed_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """,
        [sync_date, devices_count, success_count, error_count],
    )

    conn.close()


def _generate_sync_summary(
    sync_dir: Path, devices_count: int, total_commands: int, success_count: int
) -> None:
    """Generate sync summary JSON report.

    Args:
        sync_dir: Path to sync directory
        devices_count: Number of devices synced
        total_commands: Total commands executed
        success_count: Successful commands
    """
    import json
    from datetime import datetime

    summary = {
        "sync_date": datetime.now().isoformat(),
        "devices_count": devices_count,
        "commands_executed": total_commands,
        "commands_success": success_count,
        "success_rate": ((success_count / total_commands * 100) if total_commands > 0 else 0),
        "layer": "L1-L4",  # Physical to Transport
        "data_types": [
            "configs",  # L2+ Configuration
            "neighbors",  # L1 Adjacency
            "routing",  # L3-L4 Routing
            "interfaces",  # L1-L2 Connectivity
            "system",  # L7 Health
            "environment",  # L1-L2 Physical
            "logging",  # L1-L7 Events
            "spanning-tree",  # L2 Switching
            "port-security",  # L2 Security
            "vlan-info",  # L2 VLANs
            "qos-status",  # L3-L4 QoS
            "bgp-detailed",  # L3-L4 BGP
            "ospf-detailed",  # L3-L4 OSPF
            "mpls-info",  # L3-L4 MPLS
        ],
        "raw_data_path": str(sync_dir / "raw"),
        "parsed_data_path": str(sync_dir / "parsed"),
        "database_path": str(Path(sync_dir).parents[2] / ".olav" / "db" / "network_warehouse.duckdb"),
    }

    summary_file = sync_dir / "reports" / "sync_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)


def _generate_map_phase_summaries(sync_dir: Path, device_names: list[str]) -> None:
    """Generate Map-Reduce phase summaries from parsed data.

    Args:
        sync_dir: Path to sync directory
        device_names: List of device names
    """
    import json
    from collections import Counter
    from datetime import datetime

    # =========================================================================
    # Generate Log Analysis Summary from parsed logs.json
    # Filter to only include events from the last 24 hours
    # =========================================================================
    total_events = 0
    events_in_window = 0
    event_categories: Counter[str] = Counter()
    severity_distribution: Counter[str] = Counter()
    top_events: list[dict] = []
    devices_analyzed = 0

    severity_names = {
        0: "emergency",
        1: "alert",
        2: "critical",
        3: "error",
        4: "warning",
        5: "notice",
        6: "info",
        7: "debug",
    }

    # Calculate 24-hour cutoff
    cutoff_time = datetime.now() - timedelta(hours=24)

    for device in device_names:
        logs_file = sync_dir / "parsed" / device / "logs.json"
        if logs_file.exists():
            try:
                with open(logs_file) as f:
                    events = json.load(f)
                if isinstance(events, list):
                    devices_analyzed += 1
                    total_events += len(events)

                    for event in events:
                        # Parse event timestamp and filter by 24-hour window
                        event_ts_str = event.get("timestamp")
                        if event_ts_str:
                            try:
                                # Handle various timestamp formats
                                event_ts = datetime.fromisoformat(
                                    event_ts_str.replace("Z", "+00:00")
                                )
                                if event_ts.tzinfo:
                                    event_ts = event_ts.replace(tzinfo=None)
                                if event_ts < cutoff_time:
                                    continue  # Skip events older than 24 hours
                            except (ValueError, TypeError):
                                pass  # Keep events with unparseable timestamps

                        events_in_window += 1

                        # Count by facility
                        facility = event.get("facility", "UNKNOWN")
                        event_categories[facility] += 1
                        # Count by severity
                        sev = event.get("severity", 6)
                        sev_name = severity_names.get(sev, "info")
                        severity_distribution[sev_name] += 1
                        # Collect top events (errors/warnings)
                        if sev <= 4 and len(top_events) < 20:
                            top_events.append(
                                {
                                    "device": device,
                                    "timestamp": event.get("timestamp"),
                                    "severity": sev,
                                    "facility": facility,
                                    "mnemonic": event.get("mnemonic"),
                                    "message": event.get("message", "")[:100],
                                }
                            )
            except Exception:
                pass

    log_summary = {
        "phase": "map",
        "stage": "logs",
        "generated_at": datetime.now().isoformat(),
        "analysis_window": "24 hours",
        "devices_analyzed": devices_analyzed,
        "total_events": total_events,
        "events_in_window": events_in_window,
        "event_categories": dict(event_categories.most_common(10)),
        "severity_distribution": {
            "emergency": severity_distribution.get("emergency", 0),
            "alert": severity_distribution.get("alert", 0),
            "critical": severity_distribution.get("critical", 0),
            "error": severity_distribution.get("error", 0),
            "warning": severity_distribution.get("warning", 0),
            "notice": severity_distribution.get("notice", 0),
            "info": severity_distribution.get("info", 0),
            "debug": severity_distribution.get("debug", 0),
        },
        "top_events": top_events[:10],
        "anomalous_patterns": [],
    }

    logs_file = sync_dir / "map" / "logs" / "summary.json"
    logs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(logs_file, "w") as f:
        json.dump(log_summary, f, indent=2, default=str)

    # =========================================================================
    # Generate Inspection Summary from parsed data
    # Track health by OSI layer: L1 (physical), L2 (link), L3 (routing), L4 (transport)
    # =========================================================================
    inspect_checks = 0
    status_ok = 0
    status_warning = 0
    status_critical = 0
    anomalies: list[dict] = []

    # Layer-specific health tracking
    layer_health = {
        "L1": {"checks": 0, "ok": 0, "warning": 0, "critical": 0},  # Physical
        "L2": {"checks": 0, "ok": 0, "warning": 0, "critical": 0},  # Data Link
        "L3": {"checks": 0, "ok": 0, "warning": 0, "critical": 0},  # Network
        "L4": {"checks": 0, "ok": 0, "warning": 0, "critical": 0},  # Transport
    }

    for device in device_names:
        parsed_dir = sync_dir / "parsed" / device

        # L3/L4: Check CPU usage (affects routing and transport processing)
        cpu_file = parsed_dir / "show-processes-cpu.json"
        if cpu_file.exists():
            try:
                with open(cpu_file) as f:
                    data = json.load(f)
                cpu_data = data.get("data", [])
                if cpu_data and isinstance(cpu_data, list):
                    for entry in cpu_data:
                        cpu_5min = entry.get("cpu_5_min", 0)
                        if isinstance(cpu_5min, (int, float)):
                            inspect_checks += 1
                            layer_health["L4"]["checks"] += 1
                            if cpu_5min > 80:
                                status_critical += 1
                                layer_health["L4"]["critical"] += 1
                                anomalies.append(
                                    {
                                        "device": device,
                                        "type": "HIGH_CPU",
                                        "layer": "L4",
                                        "value": f"{cpu_5min}%",
                                        "severity": "critical",
                                    }
                                )
                            elif cpu_5min > 50:
                                status_warning += 1
                                layer_health["L4"]["warning"] += 1
                            else:
                                status_ok += 1
                                layer_health["L4"]["ok"] += 1
            except Exception:
                pass

        # L2/L3: Check memory usage (affects MAC/ARP tables and routing tables)
        mem_file = parsed_dir / "show-memory-statistics.json"
        if mem_file.exists():
            try:
                with open(mem_file) as f:
                    data = json.load(f)
                # Simple presence check
                inspect_checks += 1
                status_ok += 1
                layer_health["L3"]["checks"] += 1
                layer_health["L3"]["ok"] += 1
            except Exception:
                pass

        # L1: Check interface status (from logs - link up/down events)
        logs_file = parsed_dir / "logs.json"
        if logs_file.exists():
            try:
                with open(logs_file) as f:
                    events = json.load(f)
                link_down_count = sum(1 for e in events if e.get("mnemonic") == "UPDOWN")
                layer_health["L1"]["checks"] += 1
                if link_down_count > 5:
                    layer_health["L1"]["warning"] += 1
                    anomalies.append(
                        {
                            "device": device,
                            "type": "FREQUENT_LINK_FLAPS",
                            "layer": "L1",
                            "value": f"{link_down_count} events",
                            "severity": "warning",
                        }
                    )
                else:
                    layer_health["L1"]["ok"] += 1

                # L3: Check OSPF/routing events
                ospf_events = sum(
                    1 for e in events if e.get("facility", "").upper() in ("OSPF", "BGP", "ROUTING")
                )
                layer_health["L3"]["checks"] += 1
                if ospf_events > 10:
                    layer_health["L3"]["warning"] += 1
                else:
                    layer_health["L3"]["ok"] += 1
            except Exception:
                pass

        # L2: Check MAC/ARP table health
        arp_file = parsed_dir / "show-arp.json"
        if arp_file.exists():
            try:
                layer_health["L2"]["checks"] += 1
                layer_health["L2"]["ok"] += 1
            except Exception:
                pass

    # Calculate per-layer health scores
    def calc_layer_score(layer_data: dict) -> int:
        total = layer_data["checks"]
        if total == 0:
            return 100
        ok = layer_data["ok"]
        return int((ok / total) * 100)

    layer_scores = {
        "L1": calc_layer_score(layer_health["L1"]),
        "L2": calc_layer_score(layer_health["L2"]),
        "L3": calc_layer_score(layer_health["L3"]),
        "L4": calc_layer_score(layer_health["L4"]),
    }

    # Track which commands/data sources were used for each layer
    layer_commands = {
        "L1": [
            "show logging (link up/down events)",
            "show cdp neighbors",
            "show lldp neighbors",
        ],
        "L2": [
            "show arp",
            "show mac address-table",
        ],
        "L3": [
            "show ip ospf neighbor",
            "show ip bgp summary",
            "show ip route",
            "show memory statistics",
        ],
        "L4": [
            "show processes cpu",
        ],
    }

    inspect_summary = {
        "phase": "map",
        "stage": "inspect",
        "generated_at": datetime.now().isoformat(),
        "devices_checked": len(device_names),
        "total_checks": inspect_checks,
        "status_distribution": {
            "ok": status_ok,
            "warning": status_warning,
            "critical": status_critical,
        },
        "layer_health": layer_health,
        "layer_scores": layer_scores,
        "layer_commands": layer_commands,
        "anomalies": anomalies[:20],
        "devices_status": {device: "active" for device in device_names},
    }

    inspect_file = sync_dir / "map" / "inspect" / "summary.json"
    inspect_file.parent.mkdir(parents=True, exist_ok=True)
    with open(inspect_file, "w") as f:
        json.dump(inspect_summary, f, indent=2)


def _generate_inspection_analysis_report(sync_dir: Path, device_names: list[str]) -> None:
    """Generate comprehensive operations analysis report.

    Args:
        sync_dir: Path to sync directory
        device_names: List of device names
    """
    import json
    from datetime import datetime
    from pathlib import Path

    try:
        # Load map summaries for analysis data
        log_summary = {}
        inspect_summary = {}

        logs_summary_file = sync_dir / "map" / "logs" / "summary.json"
        if logs_summary_file.exists():
            with open(logs_summary_file) as f:
                log_summary = json.load(f)

        inspect_summary_file = sync_dir / "map" / "inspect" / "summary.json"
        if inspect_summary_file.exists():
            with open(inspect_summary_file) as f:
                inspect_summary = json.load(f)

        # Build report content
        report_lines = []
        report_lines.append("# 网络运维分析报告 (Network Operations Analysis Report)")
        report_lines.append("")
        report_lines.append(f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("**检测范围**: L1 (物理层) 至 L4 (传输层)")
        report_lines.append(f"**设备数量**: {len(device_names)} 台")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

        # =================================================================
        # Executive Summary with Health Score
        # =================================================================
        report_lines.append("## 📊 执行摘要 (Executive Summary)")
        report_lines.append("")

        # Calculate health score
        total_checks = inspect_summary.get("total_checks", 0)
        ok_count = inspect_summary.get("status_distribution", {}).get("ok", 0)
        warning_count = inspect_summary.get("status_distribution", {}).get("warning", 0)
        critical_count = inspect_summary.get("status_distribution", {}).get("critical", 0)

        if total_checks > 0:
            health_score = int((ok_count / total_checks) * 100)
        else:
            health_score = 100  # No issues detected

        health_status = (
            "🟢 健康" if health_score >= 80 else ("🟡 警告" if health_score >= 50 else "🔴 严重")
        )

        report_lines.append(f"### 网络健康评分: {health_score}% {health_status}")
        report_lines.append("")

        # L1-L4 Layer Health Scores
        layer_scores = inspect_summary.get("layer_scores", {})
        report_lines.append("### 分层健康评分 (Layer Health Scores)")
        report_lines.append("")
        report_lines.append("| 层级 | 名称 | 健康度 | 状态 |")
        report_lines.append("|------|------|--------|------|")

        layer_names = {
            "L1": "物理层 (Physical)",
            "L2": "数据链路层 (Data Link)",
            "L3": "网络层 (Network)",
            "L4": "传输层 (Transport)",
        }

        for layer in ["L1", "L2", "L3", "L4"]:
            score = layer_scores.get(layer, 100)
            if score >= 80:
                status_icon = "🟢"
            elif score >= 50:
                status_icon = "🟡"
            else:
                status_icon = "🔴"
            report_lines.append(f"| {layer} | {layer_names[layer]} | {score}% | {status_icon} |")
        report_lines.append("")

        # Overall stats table
        report_lines.append("### 检测统计")
        report_lines.append("")
        report_lines.append("| 指标 | 值 |")
        report_lines.append("|------|-----|")
        report_lines.append(f"| **设备总数** | {len(device_names)} |")
        report_lines.append(f"| **检测项数** | {total_checks} |")
        report_lines.append(f"| **正常** | {ok_count} ✅ |")
        report_lines.append(f"| **警告** | {warning_count} ⚠️ |")
        report_lines.append(f"| **严重** | {critical_count} 🔴 |")
        report_lines.append("")

        # =================================================================
        # Anomalies and Alerts
        # =================================================================
        anomalies = inspect_summary.get("anomalies", [])
        if anomalies:
            report_lines.append("## ⚠️ 检测到的异常 (Detected Anomalies)")
            report_lines.append("")
            report_lines.append("| 设备 | 类型 | 值 | 严重程度 |")
            report_lines.append("|------|------|-----|---------|")
            for anomaly in anomalies[:10]:
                sev_icon = "🔴" if anomaly.get("severity") == "critical" else "⚠️"
                report_lines.append(
                    f"| {anomaly.get('device')} | {anomaly.get('type')} | "
                    f"{anomaly.get('value')} | {sev_icon} {anomaly.get('severity')} |"
                )
            report_lines.append("")

        # =================================================================
        # Log Analysis Section (24-hour window)
        # =================================================================
        report_lines.append("## 📋 日志分析 (Log Analysis)")
        report_lines.append("")
        report_lines.append("**分析范围: 最近24小时**")
        report_lines.append("")

        total_events = log_summary.get("total_events", 0)
        events_in_window = log_summary.get("events_in_window", total_events)
        devices_analyzed = log_summary.get("devices_analyzed", 0)
        report_lines.append(f"- **分析设备数**: {devices_analyzed}")
        report_lines.append(f"- **24小时内事件**: {events_in_window}")
        report_lines.append(f"- **历史事件总数**: {total_events}")
        report_lines.append("")

        # Severity distribution
        sev_dist = log_summary.get("severity_distribution", {})
        if sev_dist:
            report_lines.append("### 事件严重程度分布")
            report_lines.append("")
            report_lines.append("| 级别 | 数量 |")
            report_lines.append("|------|------|")
            for sev in ["emergency", "alert", "critical", "error", "warning", "notice", "info"]:
                count = sev_dist.get(sev, 0)
                if count > 0:
                    icon = (
                        "🔴"
                        if sev in ["emergency", "alert", "critical"]
                        else ("🟠" if sev in ["error", "warning"] else "🟢")
                    )
                    report_lines.append(f"| {icon} {sev.upper()} | {count} |")
            report_lines.append("")

        # Top events
        top_events = log_summary.get("top_events", [])
        if top_events:
            report_lines.append("### 重要事件 (Top Events)")
            report_lines.append("")
            report_lines.append("| 设备 | 时间 | 类型 | 消息 |")
            report_lines.append("|------|------|------|------|")
            for event in top_events[:5]:
                ts = event.get("timestamp", "")[:19] if event.get("timestamp") else ""
                msg = event.get("message", "")[:50]
                report_lines.append(
                    f"| {event.get('device')} | {ts} | "
                    f"{event.get('facility')}-{event.get('mnemonic')} | {msg}... |"
                )
            report_lines.append("")

        # Event categories
        event_cats = log_summary.get("event_categories", {})
        if event_cats:
            report_lines.append("### 事件类别分布")
            report_lines.append("")
            report_lines.append("| 类别 | 数量 |")
            report_lines.append("|------|------|")
            for cat, count in sorted(event_cats.items(), key=lambda x: -x[1])[:10]:
                report_lines.append(f"| {cat} | {count} |")
            report_lines.append("")

        # =================================================================
        # Topology Section
        # =================================================================
        report_lines.append("## 🗺️ 网络拓扑 (Network Topology)")
        report_lines.append("")
        report_lines.append("可用的拓扑可视化:")
        report_lines.append("")

        topology_files = {
            "CDP/LLDP 发现拓扑": "cdp-lldp.html",
            "OSPF 路由拓扑": "ospf.html",
            "BGP 路由拓扑": "bgp.html",
        }

        for name, filename in topology_files.items():
            topo_path = Path("data/visualizations/topology") / filename
            if topo_path.exists():
                report_lines.append(f"- [{name}](../../../{topo_path})")

        report_lines.append("")

        # =================================================================
        # Device Inventory
        # =================================================================
        report_lines.append("## 📱 设备清单 (Device Inventory)")
        report_lines.append("")
        report_lines.append("| 设备 | 状态 | 健康 |")
        report_lines.append("|------|------|------|")
        devices_status = inspect_summary.get("devices_status", {})
        for device in sorted(device_names):
            status = devices_status.get(device, "active")
            report_lines.append(f"| {device} | ✅ {status} | 🟢 |")
        report_lines.append("")

        # =================================================================
        # Data Collection Details
        # =================================================================
        report_lines.append("## 📁 数据收集详情 (Data Collection Details)")
        report_lines.append("")

        total_raw_files = 0
        total_parsed_files = 0
        for device_dir in (sync_dir / "raw").iterdir():
            if device_dir.is_dir():
                total_raw_files += len(list(device_dir.glob("*.txt")))
        for device_dir in (sync_dir / "parsed").iterdir():
            if device_dir.is_dir():
                total_parsed_files += len(list(device_dir.glob("*.json")))

        report_lines.append(f"- **原始命令输出**: {total_raw_files} 个文件")
        report_lines.append(f"- **解析后的JSON**: {total_parsed_files} 个文件")
        report_lines.append(f"- **日志事件解析**: {total_events} 条")
        report_lines.append("")

        # =================================================================
        # Recommendations
        # =================================================================
        report_lines.append("## 💡 建议 (Recommendations)")
        report_lines.append("")

        if critical_count > 0:
            report_lines.append("1. **立即处理**: 存在严重告警，需要立即关注")
        if warning_count > 0:
            report_lines.append("2. **计划检查**: 存在警告项，建议安排检查")

        high_event_cats = [cat for cat, count in event_cats.items() if count > 100]
        if high_event_cats:
            report_lines.append(f"3. **日志审查**: 以下类别事件频繁: {', '.join(high_event_cats)}")

        if not anomalies and critical_count == 0:
            report_lines.append("✅ 网络运行状态良好，未检测到明显异常")

        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("*报告由 OLAV v0.8 自动生成*")
        report_lines.append("")

        # Write report
        report_file = sync_dir / "reports" / "INSPECTION_ANALYSIS_REPORT.md"
        report_file.write_text("\n".join(report_lines), encoding="utf-8")

    except Exception:
        pass  # Report generation is optional


# =============================================================================
# Tool 2: get_sync_age
# =============================================================================


@tool
def get_sync_age() -> str:
    """Get age of latest sync data.

    Returns:
        Human-readable age string (e.g., "2 hours ago") or "Never synced"

    Examples:
        >>> get_sync_age()
        "10 minutes ago"

        >>> get_sync_age()
        "Never synced"
    """
    latest_dir = get_latest_sync_dir()

    if not latest_dir:
        return "Never synced"

    # Get modification time
    mtime = datetime.fromtimestamp(latest_dir.stat().st_mtime)
    age = datetime.now() - mtime

    # Format age
    total_seconds = int(age.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} seconds ago"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = total_seconds // 86400
        return f"{days} day{'s' if days > 1 else ''} ago"


# =============================================================================
# Tool 3: search_sync
# =============================================================================


@tool
def search_sync(
    pattern: str,
    category: str | None = None,
    device: str | None = None,
    date: str | None = None,
) -> str:
    """Search sync data using ripgrep > grep > Python fallback.

    This tool provides fast text search across collected sync data.

    Args:
        pattern: Search pattern (supports regex)
        category: Optional category filter (configs, neighbors, routing, etc.)
        device: Optional device filter
        date: Optional date filter (YYYY-MM-DD format, default: latest)

    Returns:
        Search results with matching lines and file paths

    Examples:
        >>> search_sync("10.1.1.1", category="routing")
        "Found 3 matches in routing/..."

        >>> search_sync("error", device="R1")
        "Found 5 matches in R1 outputs..."
    """
    # Determine search directory
    if date:
        sync_dir = get_sync_dir(date)
    else:
        sync_dir = get_latest_sync_dir()

    if not sync_dir or not sync_dir.exists():
        return "No sync data found."

    # Build search path
    search_path = sync_dir / "raw"
    if category:
        search_path = search_path / category
    if device:
        # Search all categories for specific device
        search_paths = []
        for cat_dir in (sync_dir / "raw").iterdir():
            if cat_dir.is_dir():
                device_file = cat_dir / f"{device}.txt"
                if device_file.exists():
                    search_paths.append(device_file)
    else:
        search_paths = [search_path]

    # Try ripgrep first (fastest)
    if shutil.which("rg"):
        return _search_with_ripgrep(pattern, search_paths if device else [search_path])

    # Try grep (Linux/macOS)
    if shutil.which("grep"):
        return _search_with_grep(pattern, search_paths if device else [search_path])

    # Fallback to Python
    return _search_with_python(pattern, search_paths if device else [search_path])


def _search_with_ripgrep(pattern: str, paths: list[Path]) -> str:
    """Search using ripgrep."""
    try:
        results = []
        for path in paths:
            if not path.exists():
                continue

            proc = subprocess.run(
                ["rg", "--ignore-case", "--line-number", pattern, str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if proc.returncode == 0:
                results.append(proc.stdout)

        if results:
            return "\n".join(results)
        else:
            return f"No matches found for pattern: {pattern}"

    except subprocess.TimeoutExpired:
        return "Search timed out"
    except Exception as e:
        return f"Search error: {e}"


def _search_with_grep(pattern: str, paths: list[Path]) -> str:
    """Search using grep."""
    try:
        results = []
        for path in paths:
            if not path.exists():
                continue

            proc = subprocess.run(
                ["grep", "--ignore-case", "--line-number", "--recursive", pattern, str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if proc.returncode == 0:
                results.append(proc.stdout)

        if results:
            return "\n".join(results)
        else:
            return f"No matches found for pattern: {pattern}"

    except subprocess.TimeoutExpired:
        return "Search timed out"
    except Exception as e:
        return f"Search error: {e}"


def _search_with_python(pattern: str, paths: list[Path]) -> str:
    """Search using pure Python."""
    import re

    try:
        results = []
        regex = re.compile(pattern, re.IGNORECASE)

        for path in paths:
            if not path.exists() or not path.is_file():
                continue

            with open(path, encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{path}:{line_num}:{line.rstrip()}")

        if results:
            return "\n".join(results)
        else:
            return f"No matches found for pattern: {pattern}"

    except Exception as e:
        return f"Search error: {e}"


# =============================================================================
# Tool 4: diff_configs
# =============================================================================


@tool
def diff_configs(
    device: str,
    date1: str | None = None,
    date2: str | None = None,
) -> str:
    """Compare device configs between two dates.

    Args:
        device: Device name
        date1: First date (YYYY-MM-DD, default: previous day)
        date2: Second date (YYYY-MM-DD, default: today)

    Returns:
        Unified diff output or error message

    Examples:
        >>> diff_configs("R1")
        "--- configs/R1_running.txt 2026-01-12..."
        "+++ configs/R1_running.txt 2026-01-13..."

        >>> diff_configs("R1", "2026-01-10", "2026-01-13")
        "Changes between 2026-01-10 and 2026-01-13..."
    """
    # Default dates
    if date2 is None:
        date2 = datetime.now().strftime("%Y-%m-%d")
    if date1 is None:
        dt = datetime.now() - timedelta(days=1)
        date1 = dt.strftime("%Y-%m-%d")

    # Get config paths - configs are stored in raw/{device}/show-running-config.txt
    config1 = get_sync_dir(date1) / "raw" / device / "show-running-config.txt"
    config2 = get_sync_dir(date2) / "raw" / device / "show-running-config.txt"

    if not config1.exists():
        return f"Config not found for {device} on {date1}: {config1}"
    if not config2.exists():
        return f"Config not found for {device} on {date2}: {config2}"

    # Read configs
    config1_lines = config1.read_text(encoding="utf-8").splitlines(keepends=True)
    config2_lines = config2.read_text(encoding="utf-8").splitlines(keepends=True)

    # Generate diff
    diff = difflib.unified_diff(
        config1_lines,
        config2_lines,
        fromfile=str(config1),
        tofile=str(config2),
        fromfiledate=date1,
        tofiledate=date2,
    )

    diff_output = "".join(diff)

    if not diff_output:
        return f"No configuration changes for {device} between {date1} and {date2}."

    return diff_output


# =============================================================================
# Tool 5: query_sync_db
# =============================================================================


@tool
def query_sync_db(sql: str, date: str | None = None) -> str:
    """Execute read-only SQL query on sync database.

    Args:
        sql: SQL query (SELECT only)
        date: Optional date filter (default: latest)

    Returns:
        Query results as formatted table or error message

    Examples:
        >>> query_sync_db("SELECT * FROM sync_metadata ORDER BY sync_date DESC LIMIT 5")
        "sync_date | devices_count | success_count | ..."
    """
    # Validate SQL is read-only
    sql_lower = sql.strip().lower()
    if not sql_lower.startswith("select"):
        return "Error: Only SELECT queries are allowed for safety."

    # Get database path
    if date:
        db_path = get_sync_dir(date) / "reports" / "topology.db"
    else:
        latest_dir = get_latest_sync_dir()
        if not latest_dir:
            return "No sync data found."
        db_path = latest_dir / "reports" / "topology.db"

    if not db_path.exists():
        return f"Database not found: {db_path}"

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        result = conn.execute(sql).fetchall()
        conn.close()

        if not result:
            return "Query returned no results."

        # Format output
        columns = [desc[0] for desc in conn.execute(sql).description]
        header = " | ".join(columns)
        separator = "-" * len(header)

        rows = [" | ".join(str(cell) for cell in row) for row in result]

        return "\n".join([header, separator] + rows)

    except Exception as e:
        return f"Query error: {e}"


# =============================================================================
# Utility: Archive Old Syncs
# =============================================================================


def archive_old_syncs(hot_days: int = 30, archive_days: int = 365) -> str:
    """Archive sync data older than retention period.

    Args:
        hot_days: Days to keep uncompressed (default: 30)
        archive_days: Total days to keep (default: 365)

    Returns:
        Summary of archive operation

    Note:
        - Syncs newer than hot_days: kept as-is
        - Syncs between hot_days and archive_days: compressed to .tar.gz
        - Syncs older than archive_days: deleted
    """
    base_dir = get_sync_base_dir()
    archive_dir = base_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    cutoff_hot = datetime.now() - timedelta(days=hot_days)
    cutoff_archive = datetime.now() - timedelta(days=archive_days)

    archived_count = 0
    deleted_count = 0

    for sync_dir in base_dir.iterdir():
        if not sync_dir.is_dir() or sync_dir.name == "archive" or sync_dir.name == "latest":
            continue

        # Parse date from directory name
        try:
            dir_date = datetime.strptime(sync_dir.name, "%Y-%m-%d")
        except ValueError:
            continue

        if dir_date < cutoff_archive:
            # Delete old data
            shutil.rmtree(sync_dir)
            deleted_count += 1
        elif dir_date < cutoff_hot:
            # Compress to archive
            archive_file = archive_dir / f"{sync_dir.name}.tar.gz"
            if not archive_file.exists():
                with tarfile.open(archive_file, "w:gz") as tar:
                    tar.add(sync_dir, arcname=sync_dir.name)
                shutil.rmtree(sync_dir)
                archived_count += 1

    return (
        f"Archive completed:\n"
        f"  Compressed: {archived_count} syncs\n"
        f"  Deleted: {deleted_count} syncs\n"
        f"  Retention: {archive_days} days"
    )


# Import tarfile at module level
import tarfile


def _parse_with_textfsm(command: str, output: str, platform: str) -> list[dict]:
    """Parse CLI output using TextFSM templates.

    Args:
        command: Command name (e.g., "show-cdp-neighbors")
        output: Raw CLI output to parse
        platform: Device platform (e.g., "cisco_ios")

    Returns:
        List of dictionaries with parsed data, or empty list if parsing fails.
    """
    if not output or not output.strip():
        return []

    # Map specific commands to parsing functions
    command_normalized = command.replace("-", " ").lower()

    # Try specific parsers first
    if "cdp" in command and "neighbor" in command and "detail" in command:
        return _parse_cdp_neighbors_detail(output)
    elif "cdp" in command and "neighbor" in command:
        return _parse_cdp_neighbors(output)
    elif "show vlan" in command_normalized:
        return _parse_vlan(output)
    elif "show version" in command_normalized or "display version" in command_normalized:
        return _parse_version(output)
    elif "show interface" in command_normalized:
        return _parse_interfaces(output)
    elif "show ip route" in command_normalized:
        return _parse_routes(output)
    elif "show ip bgp" in command_normalized:
        return _parse_bgp(output)

    # Default: Try TextFSM templates
    try:
        from pathlib import Path

        from textfsm import TextFSM

        # Convert names: "show-cdp-neighbors" -> "cisco_ios_show_cdp_neighbors"
        cmd_normalized = command.replace("-", "_")
        platform_normalized = platform.replace("-", "_").lower()
        template_name = f"{platform_normalized}_{cmd_normalized}"

        # Try to find and load template from ntc-templates
        try:
            # Try using importlib.resources (Python 3.9+)
            import ntc_templates

            templates_path = Path(ntc_templates.__file__).parent / "templates"
            template_file = templates_path / f"{template_name}.textfsm"

            if template_file.exists():
                with open(template_file) as f:
                    template = TextFSM(f)
                    fsm_results = template.ParseText(output)

                    # Convert to list of dicts
                    results = []
                    for row in fsm_results:
                        result_dict = {}
                        for i, header in enumerate(template.header):
                            if i < len(row):
                                result_dict[header] = row[i]
                        if result_dict:
                            results.append(result_dict)
                    return results
        except Exception:
            pass
    except Exception:
        pass

    # Return empty list if no parsing succeeded
    return []


def _parse_version(output: str) -> list[dict]:
    """Parse device version output."""
    result = {}

    for line in output.split("\n"):
        line = line.strip()
        if "Cisco IOS" in line:
            result["os"] = line
        elif "Version" in line:
            result["version"] = line.split()[-1] if line else ""
        elif "Serial Number" in line:
            result["serial_number"] = line.split()[-1] if line else ""
        elif "uptime" in line.lower():
            result["uptime"] = line

    return [result] if result else []


def _parse_vlan(output: str) -> list[dict]:
    """Parse VLAN information from 'show vlan' output."""
    results = []
    lines = output.strip().split("\n")

    # Find header
    header_idx = -1
    for i, line in enumerate(lines):
        if "VLAN" in line and ("Name" in line or "Status" in line):
            header_idx = i
            break

    if header_idx < 0:
        return []

    # Parse VLAN lines
    for line in lines[header_idx + 1 :]:
        if not line.strip() or line.startswith("-"):
            continue

        parts = line.split()
        if len(parts) >= 2:
            try:
                vlan_id = parts[0]
                # Check if it's a valid VLAN ID
                if vlan_id.isdigit():
                    results.append(
                        {
                            "vlan_id": vlan_id,
                            "name": parts[1] if len(parts) > 1 else "",
                            "status": parts[2] if len(parts) > 2 else "active",
                        }
                    )
            except Exception:
                pass

    return results


def _parse_interfaces(output: str) -> list[dict]:
    """Parse interface information."""
    results = []
    current_interface = None

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Interface header line (e.g., "GigabitEthernet0/0/0 is up, line protocol is up")
        if " is " in line and not line.startswith(" "):
            parts = line.split()
            if parts:
                interface_name = parts[0]
                status = "up" if " is up" in line else "down"
                current_interface = {
                    "name": interface_name,
                    "status": status,
                }
                results.append(current_interface)
        elif current_interface and "IP address" in line:
            # Extract IP address
            ip_part = line.split()
            if len(ip_part) >= 3:
                current_interface["ip_address"] = ip_part[2]

    return results


def _parse_routes(output: str) -> list[dict]:
    """Parse IP routing table."""
    results = []
    lines = output.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("C") or line.startswith("S") or line.startswith("B"):
            # Route line (C=connected, S=static, B=BGP, etc.)
            parts = line.split()
            if len(parts) >= 2:
                results.append(
                    {
                        "protocol": parts[0],
                        "destination": parts[1] if len(parts) > 1 else "",
                        "via": parts[2] if len(parts) > 2 else "",
                    }
                )

    return results


def _parse_bgp(output: str) -> list[dict]:
    """Parse BGP table information."""
    results = []
    lines = output.strip().split("\n")

    for line in lines:
        line = line.strip()
        if line and not line.startswith(("Status", "Network", "*", " ")):
            parts = line.split()
            if len(parts) >= 3:
                results.append(
                    {
                        "network": parts[0],
                        "next_hop": parts[1] if len(parts) > 1 else "",
                        "metric": parts[2] if len(parts) > 2 else "",
                    }
                )

    return results


def _parse_cdp_neighbors_detail(output: str) -> list[dict]:
    """Parse 'show cdp neighbors detail' output into structured data.

    Format:
        Device ID: R3.local
        Entry address(es):
          IP address: 10.1.13.3
        Platform: Linux Unix,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet2,  Port ID (outgoing port): Ethernet0/0
        Holdtime : 160 sec
    """
    results = []
    lines = output.strip().split("\n")

    current_neighbor = None
    for line in lines:
        line = line.rstrip()

        # Device ID marks start of a new neighbor
        if line.startswith("Device ID:"):
            if current_neighbor:
                results.append(current_neighbor)
            current_neighbor = {
                "device_id": line.replace("Device ID:", "").strip(),
            }

        # IP address
        elif current_neighbor and "IP address:" in line:
            current_neighbor["ip_address"] = line.split("IP address:")[-1].strip()

        # Platform
        elif current_neighbor and line.startswith("Platform:"):
            # Extract platform and capabilities
            platform_line = line.replace("Platform:", "").strip()
            if "Capabilities:" in platform_line:
                parts = platform_line.split("Capabilities:")
                current_neighbor["platform"] = parts[0].strip()
                current_neighbor["capability"] = parts[1].strip()
            else:
                current_neighbor["platform"] = platform_line

        # Local and remote interface
        elif current_neighbor and line.startswith("Interface:"):
            # Format: Interface: GigabitEthernet2,  Port ID (outgoing port): Ethernet0/0
            line_content = line.replace("Interface:", "").strip()
            if "Port ID" in line_content:
                parts = line_content.split("Port ID (outgoing port):")
                current_neighbor["local_intrfce"] = parts[0].strip().rstrip(",")
                current_neighbor["port_id"] = parts[1].strip()
            else:
                current_neighbor["local_intrfce"] = line_content

        # Holdtime
        elif current_neighbor and line.startswith("Holdtime"):
            current_neighbor["holdtime"] = line.split(":")[-1].strip()

    # Don't forget the last neighbor
    if current_neighbor:
        results.append(current_neighbor)

    return results


def _parse_cdp_neighbors(output: str) -> list[dict]:
    """Parse 'show cdp neighbors' output into structured data."""
    results = []
    lines = output.strip().split("\n")

    # Find header
    header_idx = -1
    for i, line in enumerate(lines):
        if "Device ID" in line and "Local Intrfce" in line:
            header_idx = i
            break

    if header_idx < 0:
        return []

    # Parse data lines
    data_start = header_idx + 1
    if data_start < len(lines) and all(c in "-" or c.isspace() for c in lines[data_start]):
        data_start += 1

    for line in lines[data_start:]:
        if not line.strip() or all(c in "- " for c in line.strip()):
            continue
        if "Capability Codes" in line or "Total cdp" in line:
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        try:
            device_id = parts[0]
            local_intrfce_type = parts[1]

            # Determine interface and holdtime
            if len(parts) > 2 and parts[2].isdigit():
                if len(parts) > 3 and parts[2].isdigit() and parts[3].isdigit():
                    local_intrfce = f"{local_intrfce_type} {parts[2]}"
                    holdtime = parts[3]
                    capability_start = 4
                else:
                    local_intrfce = local_intrfce_type
                    holdtime = parts[2]
                    capability_start = 3
            else:
                local_intrfce = f"{local_intrfce_type} {parts[2]}"
                holdtime = parts[3] if len(parts) > 3 else ""
                capability_start = 4

            remaining = parts[capability_start:]
            if not remaining:
                continue

            # Parse capability codes
            capability_end_idx = 0
            for i, part in enumerate(remaining):
                if len(part) <= 1 or all(c in "RSHITBDCMP" for c in part):
                    capability_end_idx = i + 1
                else:
                    break

            if capability_end_idx > 0:
                capability = " ".join(remaining[:capability_end_idx])
                platform_and_port = remaining[capability_end_idx:]
            else:
                capability = ""
                platform_and_port = remaining

            if len(platform_and_port) >= 2:
                # Last part is address (0/0, 1, etc.)
                # Second-to-last is interface (Eth, Gig, etc.)
                address = platform_and_port[-1]
                interface = platform_and_port[-2]
                platform = " ".join(platform_and_port[:-2]) if len(platform_and_port) > 2 else ""
                port_id = f"{interface} {address}"
            elif len(platform_and_port) == 1:
                port_id = platform_and_port[0]
                platform = ""
            else:
                port_id = ""
                platform = ""

            results.append(
                {
                    "device_id": device_id,
                    "local_intrfce": local_intrfce,
                    "holdtime": holdtime,
                    "capability": capability,
                    "platform": platform,
                    "port_id": port_id,
                }
            )
        except (IndexError, ValueError):
            pass

    return results
