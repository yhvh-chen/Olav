import json
import logging
import os
from collections.abc import Generator
from typing import Any

import requests
from opensearchpy import OpenSearch, helpers

from olav.core.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEX_NAME = "netbox-schema"


def get_opensearch_client() -> OpenSearch:
    """Return OpenSearch client using lowercase settings attribute or env fallback.

    EnvSettings exposes fields in lowercase (opensearch_url). Older code referenced
    OPENSEARCH_URL directly which raises AttributeError. This helper normalizes.
    """
    url = getattr(settings, "opensearch_url", None) or os.getenv("OPENSEARCH_URL")
    if not url:
        msg = "Missing OpenSearch URL (opensearch_url/OPENSEARCH_URL)"
        raise RuntimeError(msg)
    return OpenSearch(
        hosts=[url],
        http_auth=None,  # Add auth if needed
        use_ssl=False,
        verify_certs=False,
    )


def fetch_openapi_schema() -> dict[str, Any]:
    """Fetch OpenAPI 3.0 schema from NetBox using lowercase settings or env fallback."""
    netbox_url = getattr(settings, "netbox_url", None) or os.getenv("NETBOX_URL")
    netbox_token = getattr(settings, "netbox_token", None) or os.getenv("NETBOX_TOKEN")
    if not netbox_url or not netbox_token:
        msg = "Missing NetBox URL/token (netbox_url/NETBOX_URL or netbox_token/NETBOX_TOKEN)"
        raise RuntimeError(msg)
    url = f"{netbox_url.rstrip('/')}/api/schema/"
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Accept": "application/json",
    }
    logger.info(f"Fetching OpenAPI schema from {url}...")
    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch schema: {e}")
        raise


def process_schema(schema: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """Process OpenAPI schema and yield documents for indexing."""
    paths = schema.get("paths", {})
    schema.get("components", {}).get("schemas", {})

    for path, methods in paths.items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "patch", "delete"]:
                continue

            # Resolve operation ID and tags
            operation_id = details.get("operationId", "")
            tags = details.get("tags", [])
            summary = details.get("summary", "")
            description = details.get("description", "")

            # Format document
            doc = {
                "_index": INDEX_NAME,
                "_id": f"{method.upper()}:{path}",
                "path": path,
                "method": method.upper(),
                "operation_id": operation_id,
                "tags": tags,
                "summary": summary,
                "description": description,
                "parameters": json.dumps(details.get("parameters", [])),
                "request_body": json.dumps(details.get("requestBody", {})),
                # Store full details for the tool to use
                "full_spec": json.dumps(details),
            }
            yield doc


def init_index(client: OpenSearch) -> None:
    """Initialize OpenSearch index with mapping."""
    if client.indices.exists(index=INDEX_NAME):
        logger.info(f"Index {INDEX_NAME} exists. Deleting...")
        client.indices.delete(index=INDEX_NAME)

    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "path": {"type": "keyword"},
                "method": {"type": "keyword"},
                "operation_id": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "summary": {"type": "text", "analyzer": "standard"},
                "description": {"type": "text", "analyzer": "standard"},
                "parameters": {"type": "text", "index": False},
                "request_body": {"type": "text", "index": False},
                "full_spec": {"type": "text", "index": False},
            }
        },
    }

    client.indices.create(index=INDEX_NAME, body=mapping)
    logger.info(f"Created index {INDEX_NAME}")


def main() -> None:
    client = get_opensearch_client()

    # 1. Init Index
    init_index(client)

    # 2. Fetch Schema
    try:
        schema = fetch_openapi_schema()
    except Exception:
        logger.warning("Could not fetch NetBox schema. Is NetBox running? Skipping ETL.")
        return

    # 3. Index Data
    logger.info("Indexing schema documents...")
    success, failed = helpers.bulk(client, process_schema(schema), stats_only=True)
    logger.info(f"Indexed {success} documents. Failed: {failed}")


if __name__ == "__main__":
    main()
