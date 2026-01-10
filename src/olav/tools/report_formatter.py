"""Skill-controlled Markdown report formatter.

This module provides functionality to generate formatted reports in Markdown
based on skill frontmatter configuration, replacing the previous Jinja2 HTML
template approach.
"""

from datetime import datetime
from typing import Any

# Language strings for multilingual support
LANG_STRINGS: dict[str, dict[str, str]] = {
    "en-US": {
        "title": "Inspection Report",
        "time": "Inspection Time",
        "devices": "Total Devices",
        "summary": "Summary",
        "device": "Device",
        "status": "Status",
        "details": "Details",
        "command": "Command",
        "result": "Result",
        "recommendations": "Recommendations",
        "no_issues": "No issues found",
        "issues_found": "Issues Found",
    },
    "zh-CN": {
        "title": "巡检报告",
        "time": "巡检时间",
        "devices": "设备总数",
        "summary": "概览",
        "device": "设备",
        "status": "状态",
        "details": "详细信息",
        "command": "命令",
        "result": "结果",
        "recommendations": "建议",
        "no_issues": "未发现问题",
        "issues_found": "发现问题",
    },
}


def format_inspection_report(
    results: dict[str, list[dict[str, Any]]],
    skill_config: dict[str, Any],
    inspection_type: str = "Network Inspection",
) -> str:
    """Generate Markdown report based on skill output configuration.

    Args:
        results: Raw inspection results from nornir_bulk_execute.
            Format: {device_name: [result1, result2, ...]}
        skill_config: Skill frontmatter with output configuration.
            Expected keys:
                - output.format: "markdown" | "json" | "table"
                - output.language: "zh-CN" | "en-US" | "auto"
                - output.sections: list of sections to include
        inspection_type: Type of inspection (e.g., "L1-L4 Inspection", "Health Check")

    Returns:
        Formatted report string in Markdown format.

    Examples:
        >>> skill_config = {
        ...     "output": {
        ...         "format": "markdown",
        ...         "language": "en-US",
        ...         "sections": ["summary", "details"]
        ...     }
        ... }
        >>> results = {"R1": [{"command": "show version", "success": True, "output": "..."}]}
        >>> report = format_inspection_report(results, skill_config)
        >>> print(report)
        # Inspection Report
        ...
    """
    output_config = skill_config.get("output", {})
    lang = _resolve_language(output_config.get("language", "auto"))
    sections = output_config.get("sections", ["summary", "details"])

    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en-US"])

    lines = []

    # Header
    lines.append(f"# {strings['title']}")
    lines.append("")
    lines.append(f"**{strings['time']}**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Type**: {inspection_type}")
    lines.append(f"**{strings['devices']}**: {len(results)}")
    lines.append("")

    # Summary section
    if "summary" in sections:
        lines.append(_format_summary(results, strings))
        lines.append("")

    # Details section
    if "details" in sections:
        lines.append(_format_details(results, strings))
        lines.append("")

    # Recommendations section
    if "recommendations" in sections:
        lines.append(_format_recommendations(results, strings, lang))
        lines.append("")

    return "\n".join(lines)


def _resolve_language(language: str) -> str:
    """Resolve 'auto' language to actual language code.

    For simplicity, defaults to 'en-US'. In production, this would
    analyze the user's input language.

    Args:
        language: Language code from config ("auto", "en-US", "zh-CN")

    Returns:
        Resolved language code ("en-US" or "zh-CN")
    """
    if language == "auto":
        # TODO: Implement actual language detection from user input
        # For now, default to English
        return "en-US"
    return language


def _format_summary(results: dict[str, list[dict[str, Any]]], strings: dict[str, str]) -> str:
    """Format the summary section of the report.

    Args:
        results: Inspection results by device
        strings: Localized strings dictionary

    Returns:
        Markdown formatted summary table
    """
    lines = []
    lines.append(f"## {strings['summary']}")
    lines.append("")
    lines.append(f"| {strings['device']} | {strings['status']} | Success | Errors |")
    lines.append("|--------|--------|---------|--------|")

    total_success = 0
    total_errors = 0

    for device, device_results in results.items():
        success_count = sum(1 for r in device_results if r.get("success"))
        error_count = len(device_results) - success_count
        total_success += success_count
        total_errors += error_count

        # Status emoji based on success rate
        if error_count == 0:
            status = "✅"
        elif success_count > 0:
            status = "⚠️"
        else:
            status = "❌"

        lines.append(f"| {device} | {status} | {success_count}/{len(device_results)} | {error_count} |")

    # Overall status
    overall_status = "✅" if total_errors == 0 else ("⚠️" if total_success > 0 else "❌")
    lines.append("")
    lines.append(f"**Overall Status**: {overall_status}")
    lines.append(f"**Total Commands**: {total_success + total_errors}")
    lines.append(f"**Successful**: {total_success}")
    lines.append(f"**Failed**: {total_errors}")

    return "\n".join(lines)


def _format_details(results: dict[str, list[dict[str, Any]]], strings: dict[str, str]) -> str:
    """Format the detailed results section of the report.

    Args:
        results: Inspection results by device
        strings: Localized strings dictionary

    Returns:
        Markdown formatted details section
    """
    lines = []
    lines.append(f"## {strings['details']}")
    lines.append("")

    for device, device_results in results.items():
        lines.append(f"### {device}")
        lines.append("")

        for result in device_results:
            cmd = result.get("command", "unknown")

            if result.get("success"):
                lines.append(f"**`{cmd}`** ✅")
                output = result.get("output", "")

                # Truncate long output
                if len(output) > 1000:
                    output = output[:1000] + "\n\n... (truncated)"

                lines.append("```")
                lines.append(output)
                lines.append("```")
            else:
                error = result.get("error", "Unknown error")
                lines.append(f"**`{cmd}`** ❌")
                lines.append(f"Error: {error}")

            lines.append("")

    return "\n".join(lines)


def _format_recommendations(
    results: dict[str, list[dict[str, Any]]],
    strings: dict[str, str],
    lang: str,
) -> str:
    """Generate recommendations based on inspection results.

    Args:
        results: Inspection results by device
        strings: Localized strings dictionary
        lang: Language code for output

    Returns:
        Markdown formatted recommendations section
    """
    lines = []
    lines.append(f"## {strings['recommendations']}")
    lines.append("")

    issues = []

    # Collect issues from results
    for device, device_results in results.items():
        for result in device_results:
            if not result.get("success"):
                cmd = result.get("command", "unknown")
                error = result.get("error", "Unknown error")
                issues.append(f"{device}: {cmd} failed - {error}")

    if issues:
        lines.append(f"### {strings['issues_found']}: {len(issues)}")
        lines.append("")

        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")

        lines.append("")
        lines.append("**Suggested Actions**:")
        lines.append("")
        lines.append("1. Review failed commands and error messages")
        lines.append("2. Check device connectivity and credentials")
        lines.append("3. Verify command syntax for the specific platform")
        lines.append("4. Re-run inspection after fixing issues")
    else:
        lines.append(f"### {strings['no_issues']}")
        lines.append("")
        lines.append("All devices are functioning normally. No immediate action required.")

    return "\n".join(lines)


def format_json_report(results: dict[str, list[dict[str, Any]]], skill_config: dict[str, Any]) -> str:
    """Generate JSON format report.

    Args:
        results: Raw inspection results
        skill_config: Skill configuration

    Returns:
        JSON formatted string
    """
    import json

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_devices": len(results),
        "devices": {},
    }

    for device, device_results in results.items():
        success_count = sum(1 for r in device_results if r.get("success"))
        report["devices"][device] = {
            "total_commands": len(device_results),
            "successful": success_count,
            "failed": len(device_results) - success_count,
            "results": device_results,
        }

    return json.dumps(report, indent=2, ensure_ascii=False)


def format_table_report(results: dict[str, list[dict[str, Any]]], skill_config: dict[str, Any]) -> str:
    """Generate simple table format report.

    Args:
        results: Raw inspection results
        skill_config: Skill configuration

    Returns:
        Table formatted string
    """
    lang = _resolve_language(skill_config.get("output", {}).get("language", "auto"))
    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en-US"])

    lines = []
    lines.append(f"| {strings['device']} | {strings['status']} | Commands | Success | Failed |")
    lines.append("|--------|--------|----------|---------|--------|")

    for device, device_results in results.items():
        success_count = sum(1 for r in device_results if r.get("success"))
        fail_count = len(device_results) - success_count

        status = "✅" if fail_count == 0 else ("⚠️" if success_count > 0 else "❌")

        lines.append(f"| {device} | {status} | {len(device_results)} | {success_count} | {fail_count} |")

    return "\n".join(lines)


def format_report(
    results: dict[str, list[dict[str, Any]]],
    skill_config: dict[str, Any],
    inspection_type: str = "Network Inspection",
) -> str:
    """Main entry point for report formatting.

    Selects the appropriate formatter based on output configuration.

    Args:
        results: Raw inspection results
        skill_config: Skill frontmatter configuration
        inspection_type: Type of inspection being performed

    Returns:
        Formatted report string
    """
    output_config = skill_config.get("output", {})
    output_format = output_config.get("format", "markdown")

    if output_format == "json":
        return format_json_report(results, skill_config)
    elif output_format == "table":
        return format_table_report(results, skill_config)
    else:  # markdown (default)
        return format_inspection_report(results, skill_config, inspection_type)
