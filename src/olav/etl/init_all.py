"""Unified ETL initialization for OLAV.

This module provides a single entry point to initialize all required
infrastructure and schema indexes for OLAV.

Usage:
    # Initialize all (skip existing indexes)
    uv run python -m olav.etl.init_all

    # Force reset all indexes (delete and recreate)
    uv run python -m olav.etl.init_all --force

    # Initialize specific components
    uv run python -m olav.etl.init_all --postgres
    uv run python -m olav.etl.init_all --suzieq --openconfig --force

Environment Variables:
    OLAV_ETL_FORCE_RESET: Set to "true" to force reset ALL indexes
    OLAV_ETL_FORCE_SUZIEQ: Set to "true" to force reset suzieq-schema index
    OLAV_ETL_FORCE_OPENCONFIG: Set to "true" to force reset openconfig-schema index
    OLAV_ETL_FORCE_NETBOX: Set to "true" to force reset netbox-schema index
    OLAV_ETL_FORCE_EPISODIC: Set to "true" to force reset olav-episodic-memory index
    OLAV_ETL_FORCE_SYSLOG: Set to "true" to force reset syslog-raw index
    OPENCONFIG_DIR: Path to OpenConfig YANG repository (optional)
"""

import argparse
import logging
import os
import sys

from opensearchpy import OpenSearch

from olav.core.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _env_is_true(var_name: str) -> bool:
    """Check if environment variable is set to a truthy value."""
    return os.getenv(var_name, "").lower() in ("1", "true", "yes")


def _get_force_flag(component: str, global_force: bool) -> bool:
    """Get force flag for a specific component.

    Priority:
        1. Component-specific env var (OLAV_ETL_FORCE_<COMPONENT>)
        2. Global force flag (--force or OLAV_ETL_FORCE_RESET)

    Args:
        component: Component name (SUZIEQ, OPENCONFIG, NETBOX, EPISODIC)
        global_force: Global force flag from args or OLAV_ETL_FORCE_RESET

    Returns:
        True if force reset should be applied for this component
    """
    component_env = f"OLAV_ETL_FORCE_{component.upper()}"
    if os.getenv(component_env):
        return _env_is_true(component_env)
    return global_force


def get_opensearch_client() -> OpenSearch:
    """Get OpenSearch client."""
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
    )


def check_index_exists(client: OpenSearch, index_name: str) -> bool:
    """Check if an index exists."""
    return client.indices.exists(index=index_name)


def delete_index_if_exists(client: OpenSearch, index_name: str) -> bool:
    """Delete index if it exists. Returns True if deleted."""
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        logger.info(f"  ✗ Deleted existing index: {index_name}")
        return True
    return False


def init_postgres(force: bool = False) -> bool:
    """Initialize PostgreSQL Checkpointer tables.

    Args:
        force: If True, drop and recreate tables (not implemented for safety)

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing PostgreSQL Checkpointer")
    logger.info("=" * 60)

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(settings.postgres_uri) as checkpointer:
            checkpointer.setup()

        logger.info("  ✓ Checkpointer tables created/verified")
        return True

    except Exception as e:
        logger.error(f"  ✗ PostgreSQL init failed: {e}")
        return False


def init_suzieq_schema(force: bool = False) -> bool:
    """Initialize SuzieQ schema index.

    Args:
        force: If True, delete and recreate index

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing SuzieQ Schema Index")
    logger.info("=" * 60)

    try:
        # Import and run SuzieQ ETL (it handles force internally)
        from olav.etl import suzieq_schema_etl

        suzieq_schema_etl.main(force=force)

        logger.info("  ✓ SuzieQ schema index ready")
        return True

    except Exception as e:
        logger.error(f"  ✗ SuzieQ schema init failed: {e}")
        return False


def init_openconfig_schema(force: bool = False) -> bool:
    """Initialize OpenConfig YANG schema index.

    Args:
        force: If True, delete and recreate index

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing OpenConfig Schema Index")
    logger.info("=" * 60)

    try:
        # Import and run OpenConfig ETL (it handles force internally)
        from olav.etl import openconfig_full_yang_etl

        openconfig_full_yang_etl.main(force=force)

        logger.info("  ✓ OpenConfig schema index ready")
        return True

    except Exception as e:
        logger.error(f"  ✗ OpenConfig schema init failed: {e}")
        return False


def init_netbox_schema(force: bool = False) -> bool:
    """Initialize NetBox API schema index.

    Args:
        force: If True, delete and recreate index

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing NetBox Schema Index")
    logger.info("=" * 60)

    try:
        # Import and run NetBox ETL (it handles force internally)
        from olav.etl import netbox_schema_etl

        netbox_schema_etl.main(force=force)

        logger.info("  ✓ NetBox schema index ready")
        return True

    except Exception as e:
        logger.error(f"  ✗ NetBox schema init failed: {e}")
        return False


def init_episodic_memory(force: bool = False) -> bool:
    """Initialize episodic memory index.

    Args:
        force: If True, delete and recreate index

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing Episodic Memory Index")
    logger.info("=" * 60)

    try:
        # Import and run episodic memory ETL (it handles force internally)
        from olav.etl import init_episodic_memory as episodic_etl

        episodic_etl.main(force=force)

        logger.info("  ✓ Episodic memory index ready")
        return True

    except Exception as e:
        logger.error(f"  ✗ Episodic memory init failed: {e}")
        return False


def init_syslog_index(force: bool = False) -> bool:
    """Initialize syslog-raw index for device log collection.

    Args:
        force: If True, delete and recreate index

    Returns:
        True if successful
    """
    logger.info("\n" + "=" * 60)
    logger.info("📦 Initializing Syslog Index")
    logger.info("=" * 60)

    try:
        # Import and run syslog index ETL
        from olav.etl import init_syslog_index as syslog_etl

        syslog_etl.main(force=force)

        logger.info("  ✓ Syslog index ready")
        return True

    except Exception as e:
        logger.error(f"  ✗ Syslog index init failed: {e}")
        return False


def show_index_status() -> None:
    """Show status of all OLAV indexes."""
    logger.info("\n" + "=" * 60)
    logger.info("📊 Index Status")
    logger.info("=" * 60)

    indexes = [
        "suzieq-schema",
        "openconfig-schema",
        "netbox-schema",
        "olav-episodic-memory",
        "syslog-raw",
    ]

    try:
        client = get_opensearch_client()

        for index_name in indexes:
            if client.indices.exists(index=index_name):
                # Get document count
                count = client.count(index=index_name)["count"]
                logger.info(f"  ✓ {index_name}: {count} documents")
            else:
                logger.info(f"  ✗ {index_name}: not found")

    except Exception as e:
        logger.error(f"  Failed to check index status: {e}")


def main() -> None:
    """Main entry point for unified ETL initialization."""
    parser = argparse.ArgumentParser(
        description="Initialize OLAV infrastructure and schema indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Initialize all components (skip existing)
    uv run python -m olav.etl.init_all

    # Force reset all indexes
    uv run python -m olav.etl.init_all --force

    # Initialize only specific components
    uv run python -m olav.etl.init_all --suzieq --openconfig

    # Show current index status
    uv run python -m olav.etl.init_all --status
        """,
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force reset indexes (delete and recreate)",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Initialize PostgreSQL Checkpointer",
    )
    parser.add_argument(
        "--suzieq",
        action="store_true",
        help="Initialize SuzieQ schema index",
    )
    parser.add_argument(
        "--openconfig",
        action="store_true",
        help="Initialize OpenConfig YANG schema index",
    )
    parser.add_argument(
        "--netbox",
        action="store_true",
        help="Initialize NetBox API schema index",
    )
    parser.add_argument(
        "--episodic",
        action="store_true",
        help="Initialize episodic memory index",
    )
    parser.add_argument(
        "--syslog",
        action="store_true",
        help="Initialize syslog-raw index for device logs",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show index status only (no initialization)",
    )

    args = parser.parse_args()

    # Check environment variable for global force reset
    global_force = args.force or _env_is_true("OLAV_ETL_FORCE_RESET")

    # If --status only, show status and exit
    if args.status:
        show_index_status()
        return

    # Determine which components to initialize
    # If no specific flags, initialize all
    init_all = not any(
        [args.postgres, args.suzieq, args.openconfig, args.netbox, args.episodic, args.syslog]
    )

    logger.info("=" * 60)
    logger.info("🚀 OLAV ETL Initialization")
    logger.info("=" * 60)
    logger.info(f"Global force reset: {global_force}")
    logger.info(f"OpenSearch URL: {settings.opensearch_url}")

    # Show component-specific force flags if any are set
    for comp in ["SUZIEQ", "OPENCONFIG", "NETBOX", "EPISODIC", "SYSLOG"]:
        comp_force = _get_force_flag(comp, global_force)
        if comp_force and not global_force:
            logger.info(f"  {comp} force reset: {comp_force} (from OLAV_ETL_FORCE_{comp})")

    results = {}

    # Initialize components with component-specific force flags
    if init_all or args.postgres:
        results["PostgreSQL"] = init_postgres(global_force)

    if init_all or args.suzieq:
        force_suzieq = _get_force_flag("SUZIEQ", global_force)
        results["SuzieQ Schema"] = init_suzieq_schema(force_suzieq)

    if init_all or args.openconfig:
        force_openconfig = _get_force_flag("OPENCONFIG", global_force)
        results["OpenConfig Schema"] = init_openconfig_schema(force_openconfig)

    if init_all or args.netbox:
        force_netbox = _get_force_flag("NETBOX", global_force)
        results["NetBox Schema"] = init_netbox_schema(force_netbox)

    if init_all or args.episodic:
        force_episodic = _get_force_flag("EPISODIC", global_force)
        results["Episodic Memory"] = init_episodic_memory(force_episodic)

    if init_all or args.syslog:
        force_syslog = _get_force_flag("SYSLOG", global_force)
        results["Syslog Index"] = init_syslog_index(force_syslog)

    # Show final status
    show_index_status()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📋 Initialization Summary")
    logger.info("=" * 60)

    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    for name, success in results.items():
        status = "✓" if success else "✗"
        logger.info(f"  {status} {name}")

    logger.info(f"\nTotal: {success_count}/{total_count} components initialized")

    if success_count < total_count:
        logger.warning("\n⚠️ Some components failed to initialize")
        sys.exit(1)
    else:
        logger.info("\n🎉 All components initialized successfully!")


if __name__ == "__main__":
    main()
