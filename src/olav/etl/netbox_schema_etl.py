"""NetBox Schema ETL - Index OpenAPI schema for Schema-Aware architecture.

This ETL creates two indices:
1. netbox-schema: API endpoint documentation (paths, methods, operations)
2. netbox-schema-fields: Field-level schema for entity types (Device, Interface, etc.)

The field-level schema enables Schema-Aware DiffEngine to dynamically map
NetBox fields to SuzieQ fields without hardcoding.
"""

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

# Two indices for different purposes
INDEX_NAME = "netbox-schema"  # API endpoints
FIELDS_INDEX_NAME = "netbox-schema-fields"  # Entity field schemas

# Priority entity types for sync operations
PRIORITY_ENTITIES = [
    "Device",
    "Interface",
    "IPAddress",
    "VLAN",
    "VRF",
    "Prefix",
    "Site",
    "Rack",
    "Cable",
    "Platform",
    "DeviceType",
    "DeviceRole",
]


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
    """Process OpenAPI schema and yield documents for indexing API endpoints."""
    paths = schema.get("paths", {})

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


def process_field_schemas(schema: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
    """Process component schemas and yield field-level documents for indexing.

    This creates detailed field documentation for Schema-Aware sync operations.
    Each field becomes a searchable document with type info and relationships.
    """
    components = schema.get("components", {}).get("schemas", {})

    for entity_name, entity_schema in components.items():
        # Skip Brief* variants and Request schemas
        if entity_name.startswith("Brief") or entity_name.endswith("Request"):
            continue

        # Skip non-priority entities for now (can be expanded later)
        is_priority = entity_name in PRIORITY_ENTITIES

        properties = entity_schema.get("properties", {})
        required_fields = entity_schema.get("required", [])

        for field_name, field_spec in properties.items():
            # Determine field type
            field_type = field_spec.get("type", "unknown")

            # Handle $ref (references to other schemas)
            ref = field_spec.get("$ref", "")
            if ref:
                # Extract referenced schema name from $ref
                ref_name = ref.split("/")[-1]
                field_type = f"ref:{ref_name}"

            # Handle allOf (common in OpenAPI for nested refs)
            all_of = field_spec.get("allOf", [])
            if all_of:
                refs = [item.get("$ref", "").split("/")[-1] for item in all_of if "$ref" in item]
                if refs:
                    field_type = f"ref:{refs[0]}"

            # Handle oneOf (union types)
            one_of = field_spec.get("oneOf", [])
            if one_of:
                types = []
                for item in one_of:
                    if "$ref" in item:
                        types.append(f"ref:{item['$ref'].split('/')[-1]}")
                    elif "type" in item:
                        types.append(item["type"])
                field_type = f"oneOf:[{','.join(types)}]"

            # Handle arrays
            if field_type == "array":
                items = field_spec.get("items", {})
                if "$ref" in items:
                    item_type = items["$ref"].split("/")[-1]
                    field_type = f"array[ref:{item_type}]"
                else:
                    item_type = items.get("type", "unknown")
                    field_type = f"array[{item_type}]"

            # Create field document
            doc = {
                "_index": FIELDS_INDEX_NAME,
                "_id": f"{entity_name}.{field_name}",
                "entity": entity_name,
                "field": field_name,
                "field_type": field_type,
                "is_required": field_name in required_fields,
                "is_read_only": field_spec.get("readOnly", False),
                "is_nullable": field_spec.get("nullable", False),
                "description": field_spec.get("description", ""),
                "title": field_spec.get("title", ""),
                "format": field_spec.get("format", ""),
                "enum": json.dumps(field_spec.get("enum", [])),
                "default": json.dumps(field_spec.get("default"))
                if "default" in field_spec
                else None,
                "max_length": field_spec.get("maxLength"),
                "min_length": field_spec.get("minLength"),
                "is_priority": is_priority,
                # For semantic search
                "searchable_text": f"{entity_name} {field_name} {field_spec.get('description', '')} {field_spec.get('title', '')}",
            }
            yield doc


def init_index(client: OpenSearch, force: bool = False) -> bool:
    """Initialize OpenSearch index with mapping.

    Args:
        client: OpenSearch client
        force: If True, delete existing index before recreating.

    Returns:
        True if index was created, False if skipped.
    """
    if client.indices.exists(index=INDEX_NAME):
        if force:
            logger.info(f"Index {INDEX_NAME} exists. Deleting (force=True)...")
            client.indices.delete(index=INDEX_NAME)
        else:
            logger.info(f"Index {INDEX_NAME} exists. Skipping (use force=True to reset).")
            return False

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
    return True


def init_fields_index(client: OpenSearch, force: bool = False) -> bool:
    """Initialize OpenSearch index for field-level schemas.

    Args:
        client: OpenSearch client
        force: If True, delete existing index before recreating.

    Returns:
        True if index was created, False if skipped.
    """
    if client.indices.exists(index=FIELDS_INDEX_NAME):
        if force:
            logger.info(f"Index {FIELDS_INDEX_NAME} exists. Deleting (force=True)...")
            client.indices.delete(index=FIELDS_INDEX_NAME)
        else:
            logger.info(f"Index {FIELDS_INDEX_NAME} exists. Skipping (use force=True to reset).")
            return False

    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "entity": {"type": "keyword"},
                "field": {"type": "keyword"},
                "field_type": {"type": "keyword"},
                "is_required": {"type": "boolean"},
                "is_read_only": {"type": "boolean"},
                "is_nullable": {"type": "boolean"},
                "is_priority": {"type": "boolean"},
                "description": {"type": "text", "analyzer": "standard"},
                "title": {"type": "text", "analyzer": "standard"},
                "format": {"type": "keyword"},
                "enum": {"type": "text", "index": False},
                "default": {"type": "text", "index": False},
                "max_length": {"type": "integer"},
                "min_length": {"type": "integer"},
                "searchable_text": {"type": "text", "analyzer": "standard"},
            }
        },
    }

    client.indices.create(index=FIELDS_INDEX_NAME, body=mapping)
    logger.info(f"Created index {FIELDS_INDEX_NAME}")
    return True


def main(force: bool = False) -> None:
    """Main ETL function.

    Args:
        force: If True, delete existing indices before recreating.
    """
    client = get_opensearch_client()

    # 1. Init Indices
    api_created = init_index(client, force=force)
    fields_created = init_fields_index(client, force=force)

    if not api_created and not fields_created and not force:
        logger.info("Both indices exist and force=False. Nothing to do.")
        return

    # 2. Fetch Schema
    try:
        schema = fetch_openapi_schema()
    except Exception:
        logger.warning("Could not fetch NetBox schema. Is NetBox running? Skipping ETL.")
        return

    # 3. Index API endpoints
    if api_created or force:
        logger.info("Indexing API endpoint documents...")
        success, failed = helpers.bulk(client, process_schema(schema), stats_only=True)
        logger.info(f"API endpoints indexed: {success} documents. Failed: {failed}")

    # 4. Index field schemas
    if fields_created or force:
        logger.info("Indexing field schema documents...")
        success, failed = helpers.bulk(client, process_field_schemas(schema), stats_only=True)
        logger.info(f"Field schemas indexed: {success} documents. Failed: {failed}")

    # 5. Log summary
    logger.info("NetBox schema ETL complete. Indices ready:")
    logger.info(f"  - {INDEX_NAME}: API endpoint documentation")
    logger.info(f"  - {FIELDS_INDEX_NAME}: Entity field schemas for Schema-Aware sync")


if __name__ == "__main__":
    main()
