"""Capabilities tools for OLAV v0.8.

This module provides tools for searching capabilities (CLI commands and API endpoints),
searching knowledge base (vendor docs, wiki, learned solutions),
and making API calls to external systems.

Refactored: API client moved to api_client.py, knowledge search to knowledge_search.py
"""

from typing import Literal

from langchain_core.tools import tool

from olav.core.database import get_database

# Re-export from refactored modules for backward compatibility
from olav.tools.api_client import api_call
from olav.tools.knowledge_search import rrf_fusion, search_knowledge

# Make exports available at module level
__all__ = [
    "search_capabilities",
    "search_capabilities_impl",
    "api_call",
    "search",
    "rrf_fusion",
    "search_knowledge",
]


def search_capabilities_impl(
    query: str,
    type: Literal["command", "api", "all"] = "all",
    platform: str | None = None,
    limit: int = 20,
) -> str:
    """Implementation of search_capabilities (not decorated).

    Search available CLI commands or API endpoints.

    This function searches the capability database for matching CLI commands or API endpoints.
    Use this to discover what commands are available before executing them.

    Args:
        query: Search keyword (e.g., "interface", "bgp", "device", "route")
        type: Capability type to search
            - "command": Only CLI commands
            - "api": Only API endpoints
            - "all": Search both (default)
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp", "netbox", "zabbix")
        limit: Maximum number of results to return (default: 20)

    Returns:
        List of matching capabilities with names, descriptions, and write status
    """
    db = get_database()

    results = db.search_capabilities(
        query=query,
        cap_type=type,
        platform=platform,
        limit=limit,
    )

    if not results:
        return f"No capabilities found matching '{query}'"

    output = [f"Found {len(results)} capabilities:"]

    for i, cap in enumerate(results, 1):
        cap_type = cap["type"]
        cap_platform = cap["platform"]
        name = cap["name"]
        method = cap.get("method", "")
        description = cap.get("description", "")
        is_write = cap["is_write"]

        if cap_type == "api":
            # API endpoint
            line = f"{i}. {method} {name} ({cap_platform})"
            if description:
                line += f" - {description}"
            if is_write:
                line += " - **REQUIRES APPROVAL**"
        else:
            # CLI command
            line = f"{i}. {name} ({cap_platform})"
            if description:
                line += f" - {description}"
            if is_write:
                line += " - **REQUIRES APPROVAL**"

        output.append(line)

    return "\n".join(output)


@tool
def search_capabilities(
    query: str,
    type: Literal["command", "api", "all"] = "all",
    platform: str | None = None,
    limit: int = 20,
) -> str:
    """Search available CLI commands or API endpoints.

    This tool searches the capability database for matching CLI commands or API endpoints.
    Use this to discover what commands are available before executing them.

    Args:
        query: Search keyword (e.g., "interface", "bgp", "device", "route")
        type: Capability type to search
            - "command": Only CLI commands
            - "api": Only API endpoints
            - "all": Search both (default)
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp", "netbox", "zabbix")
        limit: Maximum number of results to return (default: 20)

    Returns:
        List of matching capabilities with names, descriptions, and write status

    Examples:
        >>> search_capabilities("interface", type="command", platform="cisco_ios")
        "Found 3 capabilities:
        1. show interface* (cisco_ios) - Read-only
        2. show ip interface brief (cisco_ios) - Read-only
        3. configure terminal (cisco_ios) - **REQUIRES APPROVAL**"

        >>> search_capabilities("device", type="api", platform="netbox")
        "Found 2 capabilities:
        1. GET /dcim/devices/ (netbox) - Query device list
        2. PATCH /dcim/devices/{id}/ (netbox) - **REQUIRES APPROVAL**"
    """
    return search_capabilities_impl(query=query, type=type, platform=platform, limit=limit)


@tool
def search(
    query: str,
    scope: Literal["capabilities", "knowledge", "all"] = "all",
    platform: str | None = None,
    limit: int = 10,
) -> str:
    """Unified search for CLI commands, API endpoints, and documentation.

    This is the primary search tool combining:
    - Capabilities: CLI commands and API endpoints
    - Knowledge: Vendor docs, user wiki, runbooks, and learned solutions

    Args:
        query: Search query (command name, error code, or natural language)
        scope: What to search ("capabilities" | "knowledge" | "all")
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp")
        limit: Maximum results per scope (default: 10)

    Returns:
        Combined search results with source attribution

    Examples:
        >>> search("interface status", scope="all")
        "## CLI Commands & APIs
        Found 5 capabilities:
        ...

        ---
        ## Documentation
        ### Interface Troubleshooting
        To check interface status...
        ..."

        >>> search("BGP error", scope="knowledge", platform="cisco_ios")
        "## Documentation
        ### BGP Troubleshooting Guide (cisco_ios)
        Common BGP errors include...
        ..."
    """
    results = []

    # Search capabilities
    if scope in ("capabilities", "all"):
        cap_results = search_capabilities(  # type: ignore[misc]
            query=query,
            type="all",
            platform=platform,
            limit=limit,
        )
        if "No capabilities found" not in cap_results:
            results.append("## CLI Commands & APIs\n" + cap_results)

    # Search knowledge base
    if scope in ("knowledge", "all"):
        know_results = search_knowledge(query, platform, limit)
        if know_results:
            results.append("## Documentation\n" + know_results)

    if not results:
        return f"No results found for: {query}"

    return "\n\n---\n\n".join(results)
