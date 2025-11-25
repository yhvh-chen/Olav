"""Initialize OpenConfig schema index from YANG models."""

import logging

from opensearchpy import OpenSearch

from olav.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Parse OpenConfig YANG models and index XPaths to OpenSearch.

    Process:
        1. Clone OpenConfig repos (openconfig/public)
        2. Parse YANG files to extract XPaths
        3. Index to openconfig-schema with descriptions and types
    """
    logger.info("Initializing OpenConfig schema index...")

    client = OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )

    # Create index
    index_name = "openconfig-schema"
    if client.indices.exists(index=index_name):
        logger.info(f"Index {index_name} already exists, skipping...")
        return

    mapping = {
        "mappings": {
            "properties": {
                "xpath": {"type": "keyword"},
                "module": {"type": "keyword"},
                "description": {"type": "text"},
                "type": {"type": "keyword"},
                "example": {"type": "object"},
            },
        },
    }

    client.indices.create(index=index_name, body=mapping)
    logger.info(f"✓ Created index: {index_name}")

    # TODO: Implement YANG parsing
    # For now, create sample entries
    sample_docs = [
        {
            "xpath": "/network-instances/network-instance/protocols/protocol/bgp/global/config/as",
            "module": "network-instance",
            "description": "Local autonomous system number of the router",
            "type": "uint32",
            "example": {"as": 65000},
        },
        {
            "xpath": "/interfaces/interface/config/description",
            "module": "interfaces",
            "description": "Description of the interface",
            "type": "string",
            "example": {"description": "Uplink to core router"},
        },
    ]

    for doc in sample_docs:
        client.index(index=index_name, body=doc)

    logger.info(f"✓ Indexed {len(sample_docs)} sample XPaths")
    logger.info("  TODO: Implement full YANG parser")


if __name__ == "__main__":
    main()
