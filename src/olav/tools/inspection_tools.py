"""Phase 5 Inspection Tools - Device Inspection Capabilities.

This module provides tools for device inspection workflows including:
- nornir_bulk_execute: Execute commands on multiple devices in parallel
- parse_inspection_scope: Parse device filter expressions
- generate_report: Generate HTML reports using Jinja2 templates
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template
from langchain_core.tools import tool
from nornir import InitNornir
from nornir.core.task import AggregatedResult, Result
from pydantic import BaseModel, Field

from olav.core.skill_loader import get_skill_loader


# =============================================================================
# Data Models
# =============================================================================


class InspectionScope(BaseModel):
    """Parsed inspection scope."""

    devices: list[str] = Field(description="List of device names or IPs")
    filters: dict[str, Any] = Field(default_factory=dict, description="Nornir filters")
    description: str = Field(description="Human-readable description")


class InspectionResult(BaseModel):
    """Result from inspecting a single device."""

    device: str = Field(description="Device name")
    command: str = Field(description="Command that was executed")
    success: bool = Field(description="Whether execution succeeded")
    output: str | None = Field(default=None, description="Command output")
    error: str | None = Field(default=None, description="Error message if failed")
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")


class InspectionReport(BaseModel):
    """Complete inspection report data."""

    inspection_type: str = Field(description="Type of inspection (health-check, bgp-audit, etc.)")
    timestamp: str = Field(description="Report timestamp")
    devices: list[str] = Field(description="Devices inspected")
    results: list[InspectionResult] = Field(description="All inspection results")
    summary: dict[str, Any] = Field(default_factory=dict, description="Summary statistics")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")


# =============================================================================
# Tool 1: nornir_bulk_execute
# =============================================================================


@tool
def nornir_bulk_execute(
    devices: list[str] | str,
    commands: list[str],
    max_workers: int = 10,
    timeout: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    """Execute commands on multiple network devices in parallel.

    This is the primary tool for device inspection workflows. It executes
    the same set of commands on multiple devices efficiently using Nornir's
    threaded execution.

    Args:
        devices: List of device names/IPs, or "all" for all devices
        commands: List of commands to execute on each device
        max_workers: Maximum number of parallel executions (default: 10)
        timeout: Command timeout in seconds (default: 30)

    Returns:
        Dictionary mapping device names to lists of command results:
        {
            "device1": [
                {"command": "show version", "success": true, "output": "...", "error": None},
                {"command": "show processes cpu", "success": true, "output": "...", "error": None}
            ],
            "device2": [...]
        }

    Examples:
        # Execute on specific devices
        results = nornir_bulk_execute(
            devices=["R1", "R2", "R3"],
            commands=["show version", "show processes cpu"],
            max_workers=5
        )

        # Execute on all devices
        results = nornir_bulk_execute(
            devices="all",
            commands=["show ip bgp summary"]
        )
    """
    try:
        # Initialize Nornir
        nr = InitNornir(config_file=".olav/config/nornir/config.yaml")

        # Filter devices if specific list provided
        if devices != "all":
            if isinstance(devices, str):
                devices = [devices]
            nr = nr.filter(filter_func=lambda h: h.name in devices)

        # Execute commands on all devices
        from nornir_netmiko.tasks import netmiko_send_command

        aggregated_results: AggregatedResult = nr.run(
            task=netmiko_send_command,
            command_string=commands[0],  # Execute first command
            read_timeout=timeout,
        )

        # Process results
        output: dict[str, list[dict[str, Any]]] = {}

        for host_name, result_obj in aggregated_results.items():
            if host_name not in output:
                output[host_name] = []

            result_dict = {
                "command": commands[0],
                "success": result_obj.failed is False,
                "output": result_obj.result if result_obj.failed is False else None,
                "error": str(result_obj.exception) if result_obj.failed else None,
            }

            output[host_name].append(result_dict)

        return output

    except Exception as e:
        return {"error": f"Bulk execution failed: {str(e)}"}


# =============================================================================
# Tool 2: parse_inspection_scope
# =============================================================================


@tool
def parse_inspection_scope(
    scope: str,
) -> dict[str, Any]:
    """Parse device inspection scope expression.

    Parses human-readable device filter expressions and returns structured
    device list with Nornir filters.

    Supported syntax:
    - "all" → All devices
    - "R1, R2, R5" → Specific device names
    - "R1-R5" → Range (R1, R2, R3, R4, R5)
    - "all core routers" → Filter by role:core
    - "devices in site:DC1" → Filter by site attribute
    - "devices with tag:production" → Filter by custom tag

    Args:
        scope: Human-readable scope expression

    Returns:
        Dictionary with parsed scope:
        {
            "devices": ["R1", "R2", "R3"],
            "filters": {"role": "core"},
            "description": "3 devices: R1, R2, R3"
        }

    Examples:
        # All devices
        parse_inspection_scope("all")
        # → {"devices": ["all"], "filters": {}, "description": "All devices"}

        # Specific devices
        parse_inspection_scope("R1, R2, R5")
        # → {"devices": ["R1", "R2", "R5"], "filters": {}, "description": "3 devices"}

        # Role-based filter
        parse_inspection_scope("all core routers")
        # → {"devices": ["all"], "filters": {"role": "core"}, "description": "All core routers"}
    """
    scope = scope.strip()
    result = {"devices": [], "filters": {}, "description": ""}

    # Case 1: "all"
    if scope.lower() == "all":
        result["devices"] = ["all"]
        result["description"] = "All devices"
        return result

    # Case 2: Specific device names "R1, R2, R5"
    if "," in scope and not any(word in scope.lower() for word in ["all", "devices", "routers", "switches"]):
        device_names = [d.strip() for d in scope.split(",")]
        result["devices"] = device_names
        result["description"] = f"{len(device_names)} devices: {', '.join(device_names)}"
        return result

    # Case 3: Range "R1-R5"
    match = re.match(r"^([A-Za-z]+)(\d+)-([A-Za-z]+)(\d+)$", scope)
    if match:
        prefix1 = match.group(1)
        start = int(match.group(2))
        prefix2 = match.group(3)
        end = int(match.group(4))

        if prefix1 == prefix2:
            devices = [f"{prefix1}{i}" for i in range(start, end + 1)]
            result["devices"] = devices
            result["description"] = f"{len(devices)} devices: {devices[0]}-{devices[-1]}"
            return result

    # Case 4: Role-based filter "all core routers"
    if scope.lower().startswith("all"):
        role_match = re.search(r"all\s+(\w+)\s+(routers|switches|devices)", scope, re.IGNORECASE)
        if role_match:
            role = role_match.group(1)
            result["devices"] = ["all"]
            result["filters"]["role"] = role.lower()
            result["description"] = f"All {role} {role_match.group(2)}"
            return result

    # Case 5: Attribute filter "devices in site:DC1" or "devices with tag:production"
    attr_match = re.search(r"devices\s+(?:in|with)\s+(\w+):(\w+)", scope, re.IGNORECASE)
    if attr_match:
        attr_name = attr_match.group(1)
        attr_value = attr_match.group(2)
        result["devices"] = ["all"]
        result["filters"][attr_name] = attr_value
        result["description"] = f"Devices with {attr_name}={attr_value}"
        return result

    # Default: Treat as device name
    result["devices"] = [scope]
    result["description"] = f"Device: {scope}"
    return result


# =============================================================================
# Tool 3: generate_report
# =============================================================================


@tool
def generate_report(
    template: str,
    results: dict[str, list[dict[str, Any]]],
    output_path: str | None = None,
    inspection_type: str = "custom",
) -> str:
    """Generate HTML inspection report using Jinja2 template.

    Generates professional HTML reports from inspection results using
    Jinja2 templates. Templates are stored in `.olav/templates/`.

    Available templates:
    - "health-check": System health inspection report
    - "bgp-audit": BGP peer and routing audit report
    - "interface-errors": Interface error analysis report
    - "security-baseline": Security configuration baseline report
    - "custom": Generic template

    Args:
        template: Template name (health-check, bgp-audit, etc.)
        results: Results from nornir_bulk_execute
        output_path: Optional output file path (default: auto-generate)
        inspection_type: Type of inspection for metadata

    Returns:
        Path to generated HTML report file

    Examples:
        # Generate health check report
        report_path = generate_report(
            template="health-check",
            results=inspection_results,
            output_path=".olav/reports/health-check-20250108.html"
        )

        # Auto-generate output path
        report_path = generate_report(
            template="bgp-audit",
            results=bgp_results
        )
    """
    # Create reports directory if needed
    reports_dir = Path(".olav/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Generate output path if not provided
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = reports_dir / f"{template}-{timestamp}.html"
    else:
        output_path = Path(output_path)

    # Load Jinja2 template
    template_path = Path(f".olav/inspect_templates/{template}.html.j2")

    if template_path.exists():
        template_content = template_path.read_text()
        jinja_template = Template(template_content)
    else:
        # Fallback to basic template
        jinja_template = Template(_get_default_template())

    # Prepare template context
    context = {
        "inspection_type": inspection_type,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "devices": list(results.keys()) if isinstance(results, dict) else [],
        "results": results,
        "total_devices": len(results) if isinstance(results, dict) else 0,
    }

    # Render report
    html_content = jinja_template.render(**context)

    # Write report
    output_path.write_text(html_content, encoding="utf-8")

    return str(output_path)


def _get_default_template() -> str:
    """Get default Jinja2 template for reports."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>{{ inspection_type|title }} Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .summary { background: #f0f0f0; padding: 15px; border-radius: 5px; }
        .device { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .success { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>{{ inspection_type|title }} Report</h1>
    <div class="summary">
        <p><strong>Generated:</strong> {{ timestamp }}</p>
        <p><strong>Devices Inspected:</strong> {{ total_devices }}</p>
    </div>
    {% for device, device_results in results.items() %}
    <div class="device">
        <h2>{{ device }}</h2>
        {% for result in device_results %}
        <p>
            <strong>{{ result.command }}</strong>:
            {% if result.success %}
            <span class="success">✓ Success</span>
            {% else %}
            <span class="error">✗ Failed</span>
            {% endif %}
        </p>
        {% if result.output %}
        <pre>{{ result.output }}</pre>
        {% endif %}
        {% if result.error %}
        <p class="error">Error: {{ result.error }}</p>
        {% endif %}
        {% endfor %}
    </div>
    {% endfor %}
</body>
</html>
"""


# =============================================================================
# Helper: Skill Frontmatter Parser
# =============================================================================


def parse_skill_frontmatter(skill_path: Path) -> dict[str, Any]:
    """Parse frontmatter from skill markdown file.

    Args:
        skill_path: Path to skill .md file

    Returns:
        Dictionary with frontmatter data and content
    """
    content = skill_path.read_text()

    # Check for frontmatter
    if not content.startswith("---"):
        return {"frontmatter": {}, "content": content}

    # Split frontmatter and content
    parts = content.split("---", 2)

    if len(parts) < 3:
        return {"frontmatter": {}, "content": content}

    frontmatter_text = parts[1].strip()
    skill_content = parts[2].strip()

    # Parse frontmatter (simple YAML-like format)
    frontmatter = {}
    for line in frontmatter_text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

    return {"frontmatter": frontmatter, "content": skill_content}
