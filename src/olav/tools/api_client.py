"""API client tools for OLAV v0.8.

This module provides HTTP client functionality for calling external APIs
(NetBox, Zabbix, etc.).
Separated from capabilities.py for better maintainability (per DESIGN_V0.81.md optimization).
"""

import os
from typing import Any

import httpx
from langchain_core.tools import tool


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

    try:
        return _execute_request(
            method=method,
            url=url,
            params=params,
            body=body,
            headers=headers,
            username=username if not token else None,
            password=password if not token else None,
        )
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.text}"
    except httpx.RequestError as e:
        return f"Error: Request failed - {e}"
    except Exception as e:
        return f"Error: {e}"


def _execute_request(
    method: str,
    url: str,
    params: dict | None,
    body: dict | None,
    headers: dict,
    username: str | None,
    password: str | None,
) -> str:
    """Execute HTTP request with proper authentication.

    Args:
        method: HTTP method
        url: Full URL
        params: Query parameters
        body: Request body
        headers: HTTP headers
        username: Basic auth username
        password: Basic auth password

    Returns:
        Response text

    Raises:
        httpx.HTTPStatusError: On HTTP errors
        httpx.RequestError: On request errors
    """
    auth = (username, password) if username and password else None

    with httpx.Client() as client:
        request_kwargs = {
            "headers": headers,
            "timeout": 30.0,
        }

        if params:
            request_kwargs["params"] = params

        if auth:
            request_kwargs["auth"] = auth

        method_upper = method.upper()

        if method_upper == "GET":
            response = client.get(url, **request_kwargs)
        elif method_upper in ("POST", "PUT", "PATCH"):
            if body:
                request_kwargs["json"] = body
            if method_upper == "POST":
                response = client.post(url, **request_kwargs)
            elif method_upper == "PUT":
                response = client.put(url, **request_kwargs)
            else:
                response = client.patch(url, **request_kwargs)
        elif method_upper == "DELETE":
            response = client.delete(url, **request_kwargs)
        else:
            return f"Error: Unsupported HTTP method: {method}"

        response.raise_for_status()
        return response.text
