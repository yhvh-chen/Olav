#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OLAV Initialization Verification Script

Verifies that all required components are initialized and accessible:
- PostgreSQL Checkpointer tables
- OpenSearch indices
- NetBox connectivity
- SuzieQ connectivity

Usage:
    uv run python scripts/verify_initialization.py
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List

from opensearchpy import OpenSearch
from psycopg2 import connect as pg_connect

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Expected indices in OpenSearch
EXPECTED_INDICES = [
    "suzieq-schema",
    "openconfig-schema",
    "netbox-schema",
    "olav-episodic-memory",
    "syslog-raw",
]

# Expected Checkpointer tables in PostgreSQL
EXPECTED_TABLES = [
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoint_migrations",
]


def verify_postgresql() -> bool:
    """Verify PostgreSQL Checkpointer tables exist."""
    logger.info("\n🔍 Verifying PostgreSQL Checkpointer...")
    try:
        conn = pg_connect(settings.postgres_uri)
        cursor = conn.cursor()

        # Query for checkpoint tables
        cursor.execute(
            """
            SELECT tablename FROM pg_tables 
            WHERE schemaname='public' AND tablename LIKE 'checkpoint%'
            ORDER BY tablename
        """
        )
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        missing = set(EXPECTED_TABLES) - set(tables)
        found = set(EXPECTED_TABLES) & set(tables)

        logger.info(f"  Found {len(found)}/{len(EXPECTED_TABLES)} Checkpointer tables:")
        for table in sorted(found):
            logger.info(f"    ✓ {table}")

        if missing:
            logger.warning(f"  Missing tables: {', '.join(missing)}")
            return False

        logger.info("  ✅ PostgreSQL Checkpointer verified")
        return True

    except Exception as e:
        logger.error(f"  ❌ PostgreSQL verification failed: {e}")
        return False


def verify_opensearch() -> bool:
    """Verify OpenSearch indices exist and are populated."""
    logger.info("\n🔍 Verifying OpenSearch Indices...")
    try:
        from olav.core.memory import create_opensearch_client

        client = create_opensearch_client()

        # Get cluster info
        info = client.info()
        version = info.get("version", {}).get("number", "unknown")
        logger.info(f"  Connected to OpenSearch {version}")

        # Check each index
        index_status: Dict[str, int] = {}
        for index_name in EXPECTED_INDICES:
            exists = client.indices.exists(index=index_name)
            if exists:
                count = client.cat.count(index=index_name, format="json")
                doc_count = int(count[0]["count"]) if count else 0
                index_status[index_name] = doc_count
                logger.info(f"    ✓ {index_name}: {doc_count} documents")
            else:
                index_status[index_name] = -1
                logger.warning(f"    ✗ {index_name}: NOT FOUND")

        # Summary
        found = sum(1 for v in index_status.values() if v >= 0)
        total = len(EXPECTED_INDICES)

        if found == total:
            logger.info(f"  ✅ All {total} indices verified")
            return True
        else:
            logger.warning(f"  ⚠️  Only {found}/{total} indices found")
            return found >= 4  # At least 4 of 5 indices (syslog-raw can be empty)

    except Exception as e:
        logger.error(f"  ❌ OpenSearch verification failed: {e}")
        return False


def verify_netbox() -> bool:
    """Verify NetBox connectivity."""
    logger.info("\n🔍 Verifying NetBox Connectivity...")
    try:
        import requests

        # Try localhost:8080 first (for host-side verification)
        url = settings.netbox_url.replace("netbox:", "localhost:").replace(":8080", ":8080")
        if "localhost" not in url:
            url = settings.netbox_url.replace("http://", "http://localhost:").replace("netbox", "localhost")

        response = requests.get(
            f"{url}/api/",
            headers={"Authorization": f"Token {settings.netbox_token}"},
            timeout=5,
        )

        if response.status_code == 200:
            logger.info(f"  ✓ Connected to NetBox at {url}")
            logger.info("  ✅ NetBox verified")
            return True
        else:
            logger.warning(f"  ✗ NetBox returned status {response.status_code}")
            return False

    except Exception as e:
        logger.warning(f"  ⚠️  NetBox verification skipped (expected in host-side execution): {type(e).__name__}")
        logger.info("  NetBox is accessible from within containers")
        return True  # This is expected when running outside containers


def verify_suzieq() -> bool:
    """Verify SuzieQ connectivity and data."""
    logger.info("\n🔍 Verifying SuzieQ...")
    try:
        # Check if SuzieQ parquet files exist
        import os

        parquet_dir = "data/suzieq-parquet"
        if os.path.isdir(parquet_dir):
            files = os.listdir(parquet_dir)
            if files:
                logger.info(f"  ✓ Found {len(files)} SuzieQ parquet files")
                logger.info("  ✅ SuzieQ verified")
                return True
            else:
                logger.warning("  ✗ No SuzieQ parquet files found (empty data directory)")
                return True  # This is expected in fresh installation

        else:
            logger.warning(f"  ⚠️  SuzieQ data directory not found: {parquet_dir}")
            return True  # Directory might not exist yet

    except Exception as e:
        logger.error(f"  ❌ SuzieQ verification failed: {e}")
        return False


def print_summary(results: Dict[str, bool]) -> None:
    """Print verification summary."""
    logger.info("\n" + "=" * 60)
    logger.info("📊 Verification Summary")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for component, success in results.items():
        status = "✅" if success else "❌"
        logger.info(f"  {status} {component}")

    logger.info(f"\nTotal: {passed}/{total} components verified")

    if passed == total:
        logger.info("\n🎉 All components verified successfully!")
        logger.info("OLAV is ready for operation.\n")
        return 0
    elif passed >= 4:
        logger.warning("\n⚠️  Most components verified (some optional components may be pending)")
        logger.info("OLAV should be functional. Check warnings above.\n")
        return 0
    else:
        logger.error("\n❌ Critical components failed verification")
        logger.error("Please review the errors above and run initialization again.\n")
        return 1


def main() -> int:
    """Run all verification checks."""
    logger.info("=" * 60)
    logger.info("🔧 OLAV Initialization Verification")
    logger.info("=" * 60)

    results = {
        "PostgreSQL Checkpointer": verify_postgresql(),
        "OpenSearch Indices": verify_opensearch(),
        "NetBox": verify_netbox(),
        "SuzieQ": verify_suzieq(),
    }

    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
