"""Capabilities tools for OLAV v0.8.

This module provides tools for searching capabilities (CLI commands and API endpoints)
and making API calls to external systems.
"""

from typing import Any, Literal

import httpx
from langchain_core.tools import tool

from olav.core.database import get_database


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
def api_call(
    system: str,
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> str:
    """Make an API call to an external system.

    This tool makes HTTP requests to external API systems like NetBox or Zabbix.
    Use search_capabilities() first to discover available endpoints.

    Args:
        system: API system name (e.g., "netbox", "zabbix")
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        endpoint: API endpoint path (e.g., "/dcim/devices/")
        params: URL query parameters (for GET requests)
        body: Request body (for POST, PUT, PATCH requests)

    Returns:
        API response data or error message

    Examples:
        >>> api_call("netbox", "GET", "/dcim/devices/", params={"name": "R1"})
        '{"count": 1, "results": [{"id": 1, "name": "R1", ...}]}'

        >>> api_call("netbox", "PATCH", "/dcim/devices/1/", body={"status": "active"})
        '{"id": 1, "name": "R1", "status": "active", ...}'

    Security:
        Write operations (POST, PUT, PATCH, DELETE) require HITL approval.
        API credentials are loaded from environment variables.
    """
    import os

    # Load API credentials from environment
    # Expected format: {SYSTEM}_URL, {SYSTEM}_TOKEN or {SYSTEM}_USER/PASSWORD
    url_var = f"{system.upper()}_URL"
    token_var = f"{system.upper()}_TOKEN"
    user_var = f"{system.upper()}_USER"
    password_var = f"{system.upper()}_PASSWORD"

    base_url = os.getenv(url_var)
    if not base_url:
        return f"Error: {url_var} environment variable not set"

    # Build full URL
    url = f"{base_url.rstrip('/')}{endpoint}"

    # Prepare headers
    headers = {"Content-Type": "application/json"}

    # Try token auth first
    token = os.getenv(token_var)
    if token:
        headers["Authorization"] = f"Token {token}"

    # Try basic auth
    username = os.getenv(user_var)
    password = os.getenv(password_var)
    if username and password and not token:
        # Use basic auth
        pass

    try:
        with httpx.Client() as client:
            if username and password and not token:
                # Basic auth
                if method.upper() == "GET":
                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "POST":
                    response = client.post(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "PUT":
                    response = client.put(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "PATCH":
                    response = client.patch(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                elif method.upper() == "DELETE":
                    response = client.delete(
                        url,
                        params=params,
                        headers=headers,
                        auth=(username, password),
                        timeout=30.0,
                    )
                else:
                    return f"Error: Unsupported HTTP method: {method}"
            else:
                # Token auth or no auth
                if method.upper() == "GET":
                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "POST":
                    response = client.post(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "PUT":
                    response = client.put(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "PATCH":
                    response = client.patch(
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=30.0,
                    )
                elif method.upper() == "DELETE":
                    response = client.delete(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30.0,
                    )
                else:
                    return f"Error: Unsupported HTTP method: {method}"

            # Check for HTTP errors
            response.raise_for_status()

            # Return JSON response
            return response.text

    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.text}"

    except httpx.RequestError as e:
        return f"Error: Request failed - {e}"

    except Exception as e:
        return f"Error: {e}"
