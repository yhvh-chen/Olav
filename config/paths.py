"""Path Configuration for OLAV v0.8.2+

Centralized path configuration to eliminate hardcoded paths.
All tools should import from this module instead of hardcoding paths.

Usage:
    from config.paths import NETWORK_WAREHOUSE_PATH, VISUALIZATION_DIR
    db_path = NETWORK_WAREHOUSE_PATH
"""

from pathlib import Path

from config.settings import PROJECT_ROOT, AGENT_DIR

# =============================================================================
# Database Paths (Internal - .olav/db/)
# =============================================================================

DB_DIR = AGENT_DIR / "db"
NETWORK_WAREHOUSE_PATH = DB_DIR / "network_warehouse.duckdb"
REGISTRY_PATH = DB_DIR / "registry.duckdb"
KNOWLEDGE_PATH = DB_DIR / "knowledge.duckdb"

# =============================================================================
# Export Paths (User-Facing - exports/)
# =============================================================================

EXPORTS_DIR = PROJECT_ROOT / "exports"
SNAPSHOTS_DIR = EXPORTS_DIR / "snapshots"
SNAPSHOT_SYNC_DIR = SNAPSHOTS_DIR / "sync"
REPORTS_DIR = EXPORTS_DIR / "reports"
REPORTS_ANALYSIS_DIR = REPORTS_DIR / "analysis"
REPORTS_SNAPSHOTS_DIR = REPORTS_DIR / "snapshots"
VISUALIZATION_DIR = EXPORTS_DIR / "visualizations"
TOPOLOGY_VIZ_DIR = VISUALIZATION_DIR / "topology"

# =============================================================================
# Configuration & Retention
# =============================================================================

# Log analysis time window (hours)
LOG_ANALYSIS_WINDOW_HOURS = 24

# Data retention policy (days)
# Snapshots older than this will be archived/deleted
RETENTION_DAYS = 30

# =============================================================================
# Backwards Compatibility (Deprecated)
# =============================================================================

# Legacy paths for migration scripts
LEGACY_DATA_SYNC_DIR = PROJECT_ROOT / "data" / "sync"
LEGACY_DATA_VIZ_DIR = PROJECT_ROOT / "data" / "visualizations"
LEGACY_OLAV_DATA_DIR = AGENT_DIR / "data"
