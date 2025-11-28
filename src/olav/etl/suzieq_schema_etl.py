"""ETL pipeline for SuzieQ Avro schema indexing.

This ETL creates two indices:
1. suzieq-schema: Table-level schema (table name, all fields, methods)
2. suzieq-schema-fields: Field-level schema for Schema-Aware DiffEngine

The field-level schema enables LLM to discover field semantics and types
for dynamic mapping with NetBox schemas.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

from olav.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEX_NAME = "suzieq-schema"
FIELDS_INDEX_NAME = "suzieq-schema-fields"


def get_client() -> OpenSearch:
    """Get OpenSearch client."""
    url = getattr(settings, "opensearch_url", None) or os.getenv(
        "OPENSEARCH_URL", "http://localhost:9200"
    )
    return OpenSearch(
        hosts=[url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )


def main(force: bool = False) -> None:
    """Parse SuzieQ Avro schemas and index to OpenSearch.

    Args:
        force: If True, delete existing index before recreating.

    Process:
        1. Read .avsc files from suzieq/config/schema/
        2. Extract table, fields, and metadata
        3. Index to suzieq-schema for Schema-Aware tool discovery
        4. Index field-level details to suzieq-schema-fields
    """
    logger.info("Initializing SuzieQ schema indices...")

    client = get_client()

    # Create table-level index
    table_index_created = False
    if client.indices.exists(index=INDEX_NAME):
        if force:
            logger.info(f"Index {INDEX_NAME} exists. Deleting (force=True)...")
            client.indices.delete(index=INDEX_NAME)
            table_index_created = True
        else:
            logger.info(f"Index {INDEX_NAME} exists. Skipping (use force=True to reset).")
    else:
        table_index_created = True

    if table_index_created:
        mapping = {
            "mappings": {
                "properties": {
                    "table": {"type": "keyword"},
                    "fields": {"type": "keyword"},
                    "description": {"type": "text"},
                    "methods": {"type": "keyword"},
                },
            },
        }
        client.indices.create(index=INDEX_NAME, body=mapping)
        logger.info(f"✓ Created index: {INDEX_NAME}")

    # Create field-level index
    fields_index_created = False
    if client.indices.exists(index=FIELDS_INDEX_NAME):
        if force:
            logger.info(f"Index {FIELDS_INDEX_NAME} exists. Deleting (force=True)...")
            client.indices.delete(index=FIELDS_INDEX_NAME)
            fields_index_created = True
        else:
            logger.info(f"Index {FIELDS_INDEX_NAME} exists. Skipping (use force=True to reset).")
    else:
        fields_index_created = True

    if fields_index_created:
        fields_mapping = {
            "mappings": {
                "properties": {
                    "table": {"type": "keyword"},
                    "field": {"type": "keyword"},
                    "field_type": {"type": "keyword"},
                    "description": {"type": "text"},
                    "is_key": {"type": "boolean"},
                    "searchable_text": {"type": "text", "analyzer": "standard"},
                },
            },
        }
        client.indices.create(index=FIELDS_INDEX_NAME, body=fields_mapping)
        logger.info(f"✓ Created index: {FIELDS_INDEX_NAME}")

    if not table_index_created and not fields_index_created:
        logger.info("Both indices exist and force=False. Nothing to do.")
        return

    # Parse actual SuzieQ Avro schemas
    schema_dir = Path("archive/suzieq/suzieq/config/schema")
    if not schema_dir.exists():
        logger.warning(f"Schema directory not found: {schema_dir}, using sample data")
        schema_dir = None

    schemas: list[dict[str, Any]] = []
    field_docs: list[dict[str, Any]] = []

    if schema_dir:
        for avsc_file in schema_dir.glob("*.avsc"):
            try:
                with open(avsc_file, encoding="utf-8") as f:
                    avro_schema = json.load(f)

                table_name = avsc_file.stem  # filename without .avsc
                fields = []

                for field in avro_schema.get("fields", []):
                    field_name = field["name"]
                    fields.append(field_name)

                    # Extract field type from Avro schema
                    field_type = _extract_avro_type(field.get("type", "unknown"))

                    # Create field document
                    field_docs.append(
                        {
                            "_index": FIELDS_INDEX_NAME,
                            "_id": f"{table_name}.{field_name}",
                            "table": table_name,
                            "field": field_name,
                            "field_type": field_type,
                            "description": field.get("doc", ""),
                            "is_key": field.get("key", False),
                            "searchable_text": f"{table_name} {field_name} {field.get('doc', '')}",
                        }
                    )

                # Extract description from Avro doc field
                description = avro_schema.get("doc", f"{table_name} table")

                schemas.append(
                    {
                        "table": table_name,
                        "fields": fields,
                        "description": description,
                        "methods": ["get", "summarize", "unique", "aver"],
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to parse {avsc_file}: {e}")

    # Fallback to comprehensive sample data if parsing failed
    if not schemas:
        schemas, field_docs = _get_fallback_schemas()

    # Index table-level schemas
    if table_index_created or force:
        for schema in schemas:
            client.index(index=INDEX_NAME, body=schema)
        logger.info(f"✓ Indexed {len(schemas)} SuzieQ table schemas")

    # Index field-level schemas
    if field_docs and (fields_index_created or force):
        success, failed = helpers.bulk(client, field_docs, stats_only=True)
        logger.info(f"✓ Indexed {success} SuzieQ field schemas. Failed: {failed}")


def _extract_avro_type(avro_type: Any) -> str:
    """Extract a simplified type string from Avro type definition."""
    if isinstance(avro_type, str):
        return avro_type
    if isinstance(avro_type, list):
        # Union type - extract non-null types
        types = [t for t in avro_type if t != "null"]
        if len(types) == 1:
            return _extract_avro_type(types[0])
        return f"union[{','.join(_extract_avro_type(t) for t in types)}]"
    if isinstance(avro_type, dict):
        type_name = avro_type.get("type", "unknown")
        if type_name == "array":
            items = avro_type.get("items", "unknown")
            return f"array[{_extract_avro_type(items)}]"
        if type_name == "map":
            values = avro_type.get("values", "unknown")
            return f"map[{_extract_avro_type(values)}]"
        return type_name
    return "unknown"


def _get_fallback_schemas() -> tuple[list[dict], list[dict]]:
    """Return fallback schemas when Avro files are not available."""
    table_schemas = [
        {
            "table": "bgp",
            "fields": [
                "namespace",
                "hostname",
                "vrf",
                "peer",
                "asn",
                "state",
                "peerAsn",
                "afi",
            ],
            "description": "BGP protocol information including peer state and configuration",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "interfaces",
            "fields": [
                "namespace",
                "hostname",
                "ifname",
                "state",
                "adminState",
                "mtu",
                "speed",
                "type",
                "ipAddressList",
                "description",
                "macaddr",
                "master",
            ],
            "description": "Interface information including operational and admin state, IP addresses",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "routes",
            "fields": [
                "namespace",
                "hostname",
                "vrf",
                "prefix",
                "nexthopIp",
                "protocol",
                "metric",
            ],
            "description": "Routing table entries with next-hop and protocol information",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "device",
            "fields": [
                "namespace",
                "hostname",
                "model",
                "vendor",
                "version",
                "status",
                "serialNumber",
            ],
            "description": "Device hardware and software information",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "vlan",
            "fields": [
                "namespace",
                "hostname",
                "vlanName",
                "vlan",
                "state",
                "interfaces",
            ],
            "description": "VLAN configuration",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "ospfNbr",
            "fields": [
                "namespace",
                "hostname",
                "vrf",
                "ifname",
                "area",
                "state",
                "peerRouterId",
                "peerIP",
            ],
            "description": "OSPF neighbor information",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "ospfIf",
            "fields": [
                "namespace",
                "hostname",
                "vrf",
                "ifname",
                "area",
                "state",
                "networkType",
                "cost",
            ],
            "description": "OSPF interface configuration",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "lldp",
            "fields": [
                "namespace",
                "hostname",
                "ifname",
                "peerHostname",
                "peerIfname",
            ],
            "description": "LLDP neighbor discovery",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "macs",
            "fields": [
                "namespace",
                "hostname",
                "vlan",
                "macaddr",
                "oif",
            ],
            "description": "MAC address table",
            "methods": ["get", "summarize", "unique", "aver"],
        },
        {
            "table": "arpnd",
            "fields": [
                "namespace",
                "hostname",
                "ipAddress",
                "macaddr",
                "state",
            ],
            "description": "ARP/ND table entries",
            "methods": ["get", "summarize", "unique", "aver"],
        },
    ]

    # Generate field documents from fallback schemas
    field_docs = []
    field_type_hints = {
        "namespace": "string",
        "hostname": "string",
        "ifname": "string",
        "state": "string",
        "adminState": "string",
        "mtu": "long",
        "speed": "long",
        "type": "string",
        "ipAddressList": "array[string]",
        "description": "string",
        "macaddr": "string",
        "master": "string",
        "vrf": "string",
        "peer": "string",
        "asn": "long",
        "peerAsn": "long",
        "afi": "string",
        "prefix": "string",
        "nexthopIp": "string",
        "protocol": "string",
        "metric": "long",
        "model": "string",
        "vendor": "string",
        "version": "string",
        "status": "string",
        "serialNumber": "string",
        "vlanName": "string",
        "vlan": "long",
        "interfaces": "array[string]",
        "area": "string",
        "peerRouterId": "string",
        "peerIP": "string",
        "networkType": "string",
        "cost": "long",
        "peerHostname": "string",
        "peerIfname": "string",
        "oif": "string",
        "ipAddress": "string",
    }

    for schema in table_schemas:
        table = schema["table"]
        for field in schema["fields"]:
            field_docs.append(
                {
                    "_index": FIELDS_INDEX_NAME,
                    "_id": f"{table}.{field}",
                    "table": table,
                    "field": field,
                    "field_type": field_type_hints.get(field, "unknown"),
                    "description": "",
                    "is_key": field in ["namespace", "hostname", "ifname", "vrf", "peer"],
                    "searchable_text": f"{table} {field}",
                }
            )

    return table_schemas, field_docs


if __name__ == "__main__":
    main()
