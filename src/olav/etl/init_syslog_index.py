"""Initialize syslog-raw index for device log collection.

This script creates the OpenSearch index used for storing network device
syslog messages received via rsyslog collector.

Index: syslog-raw
Purpose: Event-driven diagnostics (事件驱动诊断)
Fields:
    - @timestamp: Log timestamp (RFC3339)
    - device_ip: Source device IP address
    - facility: Syslog facility (kern, user, local0-7, etc.)
    - severity: Syslog severity (emerg, alert, crit, err, warning, notice, info, debug)
    - program: Program/process name
    - raw_message: Original log message text (full-text indexed)

ILM Policy:
    - Rollover at 5GB or 1 day
    - Delete after 7 days (configurable)
"""

from __future__ import annotations

import logging

from opensearchpy import OpenSearch

from olav.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEX_NAME = "syslog-raw"
ILM_POLICY_NAME = "syslog-retention-policy"

# Index settings optimized for log ingestion
INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "5s",  # Balance between real-time and performance
        "index": {
            "codec": "best_compression",  # Reduce storage for text-heavy logs
        },
    },
    "mappings": {
        "properties": {
            "@timestamp": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "device_ip": {
                "type": "ip",  # Efficient storage and range queries for IPs
            },
            "facility": {
                "type": "keyword",  # Exact match for filtering
            },
            "severity": {
                "type": "keyword",  # Exact match for filtering
            },
            "program": {
                "type": "keyword",  # Process/daemon name
            },
            "raw_message": {
                "type": "text",
                "analyzer": "standard",  # Full-text search
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 512,  # Also allow exact match on short messages
                    }
                },
            },
        },
    },
}

# ISM (Index State Management) policy for OpenSearch
# 7-day retention with daily rollover
ISM_POLICY = {
    "policy": {
        "description": "OLAV syslog retention policy - 7 day retention",
        "default_state": "hot",
        "states": [
            {
                "name": "hot",
                "actions": [
                    {
                        "rollover": {
                            "min_size": "5gb",
                            "min_index_age": "1d",
                        }
                    }
                ],
                "transitions": [
                    {
                        "state_name": "delete",
                        "conditions": {
                            "min_index_age": "7d",
                        },
                    }
                ],
            },
            {
                "name": "delete",
                "actions": [{"delete": {}}],
                "transitions": [],
            },
        ],
        "ism_template": {
            "index_patterns": ["syslog-raw*"],
            "priority": 100,
        },
    }
}


def get_opensearch_client() -> OpenSearch:
    """Create OpenSearch client from settings."""
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=settings.opensearch_url.startswith("https"),
        verify_certs=False,
        ssl_show_warn=False,
    )


def create_ism_policy(client: OpenSearch) -> bool:
    """Create or update ISM policy for syslog retention.

    Returns:
        True if policy was created/updated, False if it already exists
    """
    try:
        # Check if policy exists
        client.transport.perform_request(
            "GET",
            f"/_plugins/_ism/policies/{ILM_POLICY_NAME}",
        )
        logger.info(f"ISM policy '{ILM_POLICY_NAME}' already exists")
        return False
    except Exception:
        # Policy doesn't exist, create it
        pass

    try:
        client.transport.perform_request(
            "PUT",
            f"/_plugins/_ism/policies/{ILM_POLICY_NAME}",
            body=ISM_POLICY,
        )
        logger.info(f"✓ Created ISM policy: {ILM_POLICY_NAME}")
        return True
    except Exception as e:
        # OpenSearch may not have ISM plugin in all versions
        logger.warning(f"Could not create ISM policy (ISM plugin may not be installed): {e}")
        return False


def create_index(client: OpenSearch, force: bool = False) -> bool:
    """Create syslog-raw index.

    Args:
        client: OpenSearch client
        force: If True, delete existing index before creating

    Returns:
        True if index was created, False if it already exists
    """
    if client.indices.exists(index=INDEX_NAME):
        if force:
            logger.info(f"Force flag set, deleting existing index: {INDEX_NAME}")
            client.indices.delete(index=INDEX_NAME)
        else:
            # Get document count
            try:
                count = client.count(index=INDEX_NAME)["count"]
                logger.info(f"Index '{INDEX_NAME}' already exists with {count} documents")
            except Exception:
                logger.info(f"Index '{INDEX_NAME}' already exists")
            return False

    client.indices.create(index=INDEX_NAME, body=INDEX_SETTINGS)
    logger.info(f"✓ Created index: {INDEX_NAME}")
    return True


def main(force: bool = False) -> None:
    """Initialize syslog-raw index for device log collection.

    Args:
        force: If True, recreate index even if it exists
    """
    import os

    # Check environment variable for force reset
    force = force or os.getenv("OLAV_ETL_FORCE_SYSLOG", "false").lower() == "true"

    logger.info("=" * 60)
    logger.info("Initializing syslog-raw index...")
    logger.info("=" * 60)

    client = get_opensearch_client()

    # Verify OpenSearch connectivity
    try:
        info = client.info()
        logger.info(f"Connected to OpenSearch {info['version']['number']}")
    except Exception as e:
        logger.error(f"Failed to connect to OpenSearch: {e}")
        raise

    # Create ISM policy (optional, for automatic retention)
    create_ism_policy(client)

    # Create index
    created = create_index(client, force=force)

    if created:
        logger.info("✓ Syslog index initialization complete")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Configure network devices to send syslog to port 514")
        logger.info("  2. Start rsyslog container: docker-compose up -d rsyslog")
        logger.info("  3. Verify logs: curl http://localhost:9200/syslog-raw/_count")
    else:
        logger.info("✓ Syslog index already initialized")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize syslog-raw index")
    parser.add_argument("--force", action="store_true", help="Force recreate index")
    args = parser.parse_args()

    main(force=args.force)
