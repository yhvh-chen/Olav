import json
import logging
from typing import Any

import requests
from langchain_core.tools import tool
from opensearchpy import OpenSearch

from olav.core.settings import settings

logger = logging.getLogger(__name__)


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_auth=None,
        use_ssl=False,
        verify_certs=False,
    )


@tool
def netbox_schema_search(query: str) -> list[dict[str, Any]]:
    """
    Search for NetBox API endpoints using natural language.
    Returns a list of matching endpoints with their HTTP methods and descriptions.

    Args:
        query: Description of the action (e.g., "create a new device", "list all sites")
    """
    client = get_opensearch_client()

    search_query = {
        "size": 5,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["summary^3", "description^2", "path", "tags"],
                "fuzziness": "AUTO",
            }
        },
    }

    results = client.search(index="netbox-schema", body=search_query)
    hits = []
    for hit in results["hits"]["hits"]:
        source = hit["_source"]
        hits.append(
            {
                "path": source["path"],
                "method": source["method"],
                "summary": source["summary"],
                "parameters": json.loads(source["parameters"]),
                # "request_body": json.loads(source["request_body"]) # Omitted for brevity, fetch if needed
            }
        )
    return hits


@tool
def netbox_api_call(
    path: str, method: str, data: dict | None = None, params: dict | None = None
) -> dict[str, Any]:
    """
    Execute a NetBox API call.

    Args:
        path: The API path (e.g., "/dcim/devices/")
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        data: JSON body for POST/PUT/PATCH
        params: Query parameters for GET
    """
    url = (
        f"{settings.netbox_url}/api{path}"
        if not path.startswith("/api")
        else f"{settings.netbox_url}{path}"
    )
    headers = {
        "Authorization": f"Token {settings.netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.request(
            method=method, url=url, headers=headers, json=data, params=params, verify=False
        )
        response.raise_for_status()
        if response.status_code == 204:
            return {"status": "success", "message": "No content"}
        return response.json()
    except requests.exceptions.HTTPError:
        return {"status": "error", "code": response.status_code, "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}
