"""
NetBox Tool - BaseTool implementation with adapter integration.

Refactored to implement BaseTool protocol and use NetBoxAdapter for
standardized ToolOutput returns.
"""

import contextlib
import json
import logging
from typing import Any, Literal
from urllib.parse import urljoin

import requests
from langchain_core.tools import tool

from opensearchpy import OpenSearch

from config.settings import settings
from olav.core.memory import create_opensearch_client
from olav.tools.adapters import NetBoxAdapter
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


def get_opensearch_client() -> OpenSearch:
    """Get OpenSearch client for schema search."""
    return create_opensearch_client(settings.opensearch_url)


class NetBoxAPITool:
    """
    NetBox API interaction tool - BaseTool implementation.

    Provides access to NetBox SSOT (Single Source of Truth) with:
    - REST API execution (GET/POST/PUT/PATCH/DELETE)
    - Automatic authentication via token
    - Error handling and status code validation
    - Standardized ToolOutput via NetBoxAdapter

    Attributes:
        name: Tool identifier
        description: Tool purpose description
        base_url: NetBox server URL
        token: Authentication token
    """

    name = "netbox_api"
    description = """Execute NetBox API calls for network infrastructure SSOT operations.

    Use this tool to interact with NetBox for:
    - Device inventory (create, read, update, delete devices)
    - Site and rack management
    - IP address and prefix management
    - Circuit and cable tracking
    - Configuration templates

    Supports all HTTP methods: GET, POST, PUT, PATCH, DELETE.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        """
        Initialize NetBoxAPITool.

        Args:
            base_url: NetBox server URL (default: from settings)
            token: NetBox API token (default: from settings)
        """
        self.base_url = base_url or settings.netbox_url
        self.token = token or settings.netbox_token

        if not self.base_url or not self.token:
            logger.warning("NetBox base_url or token not configured")

    async def execute(
        self,
        path: str,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET",
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        device: str | None = None,
    ) -> ToolOutput:
        """
        Execute NetBox API request and return standardized output.

        Args:
            path: API path (e.g., "/dcim/devices/" or "/api/dcim/devices/")
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            data: JSON request body for POST/PUT/PATCH (optional)
            params: Query parameters for GET (optional)
            device: Target device name for context (optional)

        Returns:
            ToolOutput with normalized data via NetBoxAdapter

        Example:
            # List all devices
            result = await tool.execute(path="/api/dcim/devices/", method="GET")

            # Create new device
            result = await tool.execute(
                path="/api/dcim/devices/",
                method="POST",
                data={"name": "R1", "device_type": 5, "site": 1, "status": "active"}
            )
        """
        metadata = {"path": path, "method": method, "params": params, "base_url": self.base_url}

        # Validate configuration
        if not self.base_url or not self.token:
            return ToolOutput(
                source="netbox",
                device=device or "unknown",
                data=[
                    {
                        "status": "CONFIG_ERROR",
                        "message": "NetBox base_url or token not configured",
                        "hint": "Set NETBOX_URL and NETBOX_TOKEN environment variables",
                    }
                ],
                metadata=metadata,
                error="NetBox not configured",
            )

        # Build full URL
        if not path.startswith("/api"):
            path = f"/api{path}"
        url = urljoin(self.base_url, path)

        # Prepare headers
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            # Execute request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                verify=False,  # TODO: Make SSL verification configurable
                timeout=30,
            )

            # Handle HTTP errors
            if not response.ok:
                return self._handle_error_response(
                    response, device=device or "unknown", metadata=metadata
                )

            # Parse successful response
            if response.status_code == 204:  # No Content
                response_data = {
                    "status": "success",
                    "message": f"{method} operation completed successfully",
                    "code": 204,
                }
            else:
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = {
                        "status": "success",
                        "content": response.text,
                        "code": response.status_code,
                    }

            # Use adapter to convert to ToolOutput
            return NetBoxAdapter.adapt(
                netbox_response=response_data,
                device=device or self._extract_device_from_response(response_data),
                endpoint=path,
                metadata={
                    **metadata,
                    "status_code": response.status_code,
                    "execution_time_ms": response.elapsed.total_seconds() * 1000,
                },
            )

        except requests.exceptions.Timeout as e:
            logger.error(f"NetBox API timeout: {url}")
            return ToolOutput(
                source="netbox",
                device=device or "unknown",
                data=[],
                metadata=metadata,
                error=f"Request timeout after 30s: {e}",
            )

        except requests.exceptions.ConnectionError as e:
            logger.error(f"NetBox connection error: {url}")
            return ToolOutput(
                source="netbox",
                device=device or "unknown",
                data=[],
                metadata=metadata,
                error=f"Connection error (is NetBox running?): {e}",
            )

        except Exception as e:
            logger.exception(f"NetBox API call failed: {e}")
            return ToolOutput(
                source="netbox",
                device=device or "unknown",
                data=[],
                metadata=metadata,
                error=f"Unexpected error: {e}",
            )

    def _handle_error_response(
        self, response: requests.Response, device: str, metadata: dict[str, Any]
    ) -> ToolOutput:
        """Handle HTTP error responses."""
        try:
            error_data = response.json()
        except json.JSONDecodeError:
            error_data = {"detail": response.text}

        return ToolOutput(
            source="netbox",
            device=device,
            data=[
                {
                    "status": "HTTP_ERROR",
                    "code": response.status_code,
                    "message": error_data.get("detail", response.text),
                    "errors": error_data if isinstance(error_data, dict) else {},
                }
            ],
            metadata={**metadata, "status_code": response.status_code},
            error=f"HTTP {response.status_code}: {response.reason}",
        )

    def _extract_device_from_response(self, data: Any) -> str:
        """Try to extract device name from response data."""
        if isinstance(data, dict):
            # Single object response
            if "name" in data:
                return str(data["name"])
            if "device" in data and isinstance(data["device"], dict):
                return str(data["device"].get("name", "multi"))

        elif isinstance(data, list) and data:
            # List response - check first item
            if isinstance(data[0], dict) and "name" in data[0]:
                return str(data[0]["name"])

        return "multi"


class NetBoxSchemaSearchTool:
    """
    NetBox schema discovery tool via OpenSearch.

    Helps LLM discover available API endpoints before executing calls.
    Requires OpenSearch index 'netbox-schema' populated with endpoint metadata.
    """

    name = "netbox_schema_search"
    description = """Search NetBox API schema to discover available endpoints.

    Use this tool BEFORE netbox_api to find out what endpoints exist
    and what parameters they require.

    Searches for:
    - API paths (/api/dcim/devices/, etc.)
    - HTTP methods (GET, POST, PUT, PATCH, DELETE)
    - Required/optional parameters
    - Request body schemas
    """

    async def execute(self, query: str) -> ToolOutput:
        """
        Search NetBox schema by keywords.

        Args:
            query: Natural language query (e.g., "create a new device", "list sites")

        Returns:
            ToolOutput with matching endpoints and their metadata

        Example:
            result = await tool.execute(query="list all devices")
            # Returns: [{"path": "/api/dcim/devices/", "method": "GET", ...}]
        """
        metadata = {"query": query}

        try:
            client = get_opensearch_client()

            # Multi-match search across multiple fields
            search_query = {
                "size": 5,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["summary^3", "description^2", "path", "tags"],
                        "fuzziness": "AUTO",
                    }
                },
                "_source": ["path", "method", "summary", "parameters", "request_body"],
            }

            results = client.search(index="netbox-schema", body=search_query)

            # Extract hits
            hits = []
            for hit in results["hits"]["hits"]:
                source = hit["_source"]

                # Parse JSON fields
                endpoint = {
                    "path": source.get("path"),
                    "method": source.get("method"),
                    "summary": source.get("summary", ""),
                    "score": hit["_score"],
                }

                # Add parameters if present
                if "parameters" in source:
                    try:
                        endpoint["parameters"] = json.loads(source["parameters"])
                    except (json.JSONDecodeError, TypeError):
                        endpoint["parameters"] = []

                # Add request_body for POST/PUT/PATCH
                if source.get("method") in ["POST", "PUT", "PATCH"] and "request_body" in source:
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        endpoint["request_body"] = json.loads(source["request_body"])

                hits.append(endpoint)

            return ToolOutput(
                source="netbox_schema",
                device="localhost",
                data=hits,
                metadata={
                    **metadata,
                    "total_hits": results["hits"]["total"]["value"],
                    "max_score": results["hits"]["max_score"],
                },
            )

        except Exception as e:
            logger.exception(f"NetBox schema search failed: {e}")
            return ToolOutput(
                source="netbox_schema",
                device="localhost",
                data=[],
                metadata=metadata,
                error=f"Schema search failed: {e}",
            )


# Register tools with ToolRegistry
ToolRegistry.register(NetBoxAPITool())
ToolRegistry.register(NetBoxSchemaSearchTool())

# ---------------------------------------------------------------------------
# Compatibility Wrappers (LangChain @tool functions)
# ---------------------------------------------------------------------------
# These provide backward-compatible interfaces expected by existing workflows
# and tests while internally delegating to the refactored BaseTool implementation.


@tool
async def netbox_api_call(
    path: str,
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET",
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper for NetBox API calls.

    Returns simplified dict structure for legacy consumers while using
    refactored NetBoxAPITool under the hood.
    """
    tool_impl = ToolRegistry.get_tool("netbox_api")
    if tool_impl is None:
        return {"success": False, "error": "netbox_api tool not registered"}
    result = await tool_impl.execute(
        path=path, method=method, data=data, params=params, device=device
    )
    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }


@tool
async def netbox_schema_search(query: str) -> dict[str, Any]:
    """Backward-compatible wrapper for NetBox schema search.

    Adapts ToolOutput to legacy dict format.
    """
    tool_impl = ToolRegistry.get_tool("netbox_schema_search")
    if tool_impl is None:
        return {"success": False, "error": "netbox_schema_search tool not registered"}
    result = await tool_impl.execute(query=query)
    return {
        "success": result.error is None,
        "error": result.error,
        "data": result.data,
        "metadata": result.metadata,
    }
