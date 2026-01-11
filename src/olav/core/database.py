"""DuckDB database module for OLAV v0.8.

This module provides the core database functionality for storing and querying
network capabilities, audit logs, and command caches.
"""

from pathlib import Path
from typing import Any

import duckdb


class OlavDatabase:
    """OLAV database manager using DuckDB.

    This database stores:
    - capabilities: CLI commands and API endpoints (from imports/)
    - audit_logs: Execution history and audit trail
    - command_cache: Cached command outputs (optional, not used in MVP)
    """

    def __init__(self, db_path: str | Path = None) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to DuckDB database file (defaults to agent_dir/data/capabilities.db)
        """
        if db_path is None:
            from config.settings import settings

            db_path = Path(settings.agent_dir) / "data" / "capabilities.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to DuckDB
        self.conn = duckdb.connect(str(self.db_path))

        # Initialize schema
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        # Capabilities table
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS capabilities_id_seq START 1
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS capabilities (
                id INTEGER PRIMARY KEY DEFAULT nextval('capabilities_id_seq'),
                type TEXT NOT NULL,
                platform TEXT NOT NULL,
                name TEXT NOT NULL,
                method TEXT,
                description TEXT,
                parameters TEXT,
                is_write BOOLEAN DEFAULT FALSE,
                source_file TEXT NOT NULL
            )
        """)

        # Create indexes for capabilities
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cap_type
            ON capabilities(type)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cap_platform
            ON capabilities(platform)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cap_name
            ON capabilities(name)
        """)

        # Audit logs table
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS audit_logs_id_seq START 1
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY DEFAULT nextval('audit_logs_id_seq'),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                thread_id TEXT NOT NULL,
                device TEXT NOT NULL,
                command TEXT NOT NULL,
                output TEXT,
                success BOOLEAN NOT NULL,
                duration_ms INTEGER,
                user TEXT
            )
        """)

        # Create indexes for audit logs
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_thread
            ON audit_logs(thread_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_device
            ON audit_logs(device)
        """)

        # Command cache table (optional, not used in MVP)
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS command_cache_id_seq START 1
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS command_cache (
                id INTEGER PRIMARY KEY DEFAULT nextval('command_cache_id_seq'),
                device TEXT NOT NULL,
                command TEXT NOT NULL,
                output TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ttl_seconds INTEGER DEFAULT 300,
                UNIQUE(device, command)
            )
        """)

        # Auto-load command whitelist if capabilities table is empty or has few commands
        self._ensure_command_whitelist_loaded()

    def _ensure_command_whitelist_loaded(self) -> None:
        """Ensure command whitelist is loaded into capabilities table."""
        # Check if we have enough commands loaded
        result = self.conn.execute(
            "SELECT COUNT(*) FROM capabilities WHERE type = 'command'"
        ).fetchone()
        command_count = result[0] if result else 0

        if command_count >= 10:
            # Already have commands loaded
            return

        # Load from whitelist files
        from config.settings import settings

        whitelist_dir = Path(settings.agent_dir) / "imports" / "commands"
        if not whitelist_dir.exists():
            return

        for platform_file in whitelist_dir.glob("*.txt"):
            if platform_file.name == "blacklist.txt":
                continue

            platform = platform_file.stem

            for line in platform_file.read_text(encoding="utf-8").split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Skip HITL commands (those starting with !)
                is_write = line.startswith("!")
                cmd = line[1:] if is_write else line

                try:
                    self.insert_capability(
                        cap_type="command",
                        platform=platform,
                        name=cmd,
                        source_file=str(platform_file),
                        is_write=is_write,
                    )
                except Exception:  # noqa: S110
                    # Ignore duplicates
                    pass

    def search_capabilities(
        self,
        query: str,
        cap_type: str = "all",
        platform: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search capabilities by keyword.

        Args:
            query: Search keyword
            cap_type: Filter by type ("command", "api", or "all")
            platform: Filter by platform (e.g., "cisco_ios", "netbox")
            limit: Maximum results to return

        Returns:
            List of matching capabilities
        """
        # Build base query
        sql = """
            SELECT type, platform, name, method, description, parameters, is_write
            FROM capabilities
            WHERE (name ILIKE ? OR description ILIKE ?)
        """
        pattern = f"%{query}%"
        params = [pattern, pattern]

        # Add platform filter
        if platform:
            sql += " AND platform = ?"
            params.append(platform)

        # Add type filter
        if cap_type != "all":
            sql += " AND type = ?"
            params.append(cap_type)

        sql += f" LIMIT {limit}"

        results = self.conn.execute(sql, params).fetchall()
        columns = ["type", "platform", "name", "method", "description", "parameters", "is_write"]

        return [dict(zip(columns, row, strict=False)) for row in results]

    def is_command_allowed(self, command: str, platform: str) -> bool:
        """Check if a command is in the whitelist.

        Args:
            command: Command to check
            platform: Platform name (e.g., "cisco_ios")

        Returns:
            True if command is allowed, False otherwise
        """
        cmd_lower = command.lower().strip()

        # Get all command patterns for this platform
        patterns = self.conn.execute(
            """
            SELECT name FROM capabilities
            WHERE type = 'command' AND platform = ?
        """,
            [platform],
        ).fetchall()

        for (pattern,) in patterns:
            pattern = pattern.lower().strip()
            if pattern.endswith("*"):
                # Wildcard match
                prefix = pattern[:-1]
                if cmd_lower.startswith(prefix):
                    return True
            else:
                # Exact match
                if cmd_lower == pattern:
                    return True

        return False

    def insert_capability(
        self,
        cap_type: str,
        platform: str,
        name: str,
        source_file: str,
        method: str | None = None,
        description: str | None = None,
        parameters: str | None = None,
        is_write: bool = False,
    ) -> None:
        """Insert a capability into the database.

        Args:
            cap_type: Type ("command" or "api")
            platform: Platform name
            name: Command or endpoint name
            source_file: Source file path
            method: HTTP method (for APIs)
            description: Optional description
            parameters: JSON string of parameters (for APIs)
            is_write: Whether this requires HITL approval
        """
        self.conn.execute(
            """
            INSERT INTO capabilities
            (type, platform, name, method, description, parameters, is_write, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [cap_type, platform, name, method, description, parameters, is_write, source_file],
        )

    def clear_capabilities(self) -> None:
        """Clear all capabilities from the database.

        Used during 'olav reload' operations.
        """
        self.conn.execute("DELETE FROM capabilities")

    def log_execution(
        self,
        thread_id: str,
        device: str,
        command: str,
        output: str,
        success: bool,
        duration_ms: int,
        user: str | None = None,
    ) -> None:
        """Log a command execution to the audit trail.

        Args:
            thread_id: Conversation/thread ID
            device: Device name or IP
            command: Command executed
            output: Command output
            success: Whether execution succeeded
            duration_ms: Execution time in milliseconds
            user: Optional user identifier
        """
        self.conn.execute(
            """
            INSERT INTO audit_logs
            (thread_id, device, command, output, success, duration_ms, user)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            [thread_id, device, command, output, success, duration_ms, user],
        )

    def get_command_cache(self, device: str, command: str) -> str | None:
        """Get cached command output if available and not expired.

        Args:
            device: Device name
            command: Command string

        Returns:
            Cached output or None if not found/expired
        """
        result = self.conn.execute(
            """
            SELECT output, cached_at, ttl_seconds
            FROM command_cache
            WHERE device = ? AND command = ?
            ORDER BY cached_at DESC
            LIMIT 1
        """,
            [device, command],
        ).fetchone()

        if not result:
            return None

        output, cached_at, ttl = result
        # Check if cache is still valid
        # Note: DuckDB returns timestamps as strings, need to parse
        # For MVP, we'll skip TTL checking and just return the cached value
        return output

    def set_command_cache(
        self, device: str, command: str, output: str, ttl_seconds: int = 300
    ) -> None:
        """Cache a command output.

        Args:
            device: Device name
            command: Command string
            output: Command output to cache
            ttl_seconds: Time-to-live in seconds (default 5 minutes)
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO command_cache
            (device, command, output, ttl_seconds)
            VALUES (?, ?, ?, ?)
        """,
            [device, command, output, ttl_seconds],
        )

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self) -> "OlavDatabase":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()


# Global database instance
_db_instance: OlavDatabase | None = None


def get_database(db_path: str | None = None) -> OlavDatabase:
    """Get the global database instance.

    Args:
        db_path: Optional database path (uses default if not provided)

    Returns:
        OlavDatabase instance
    """
    global _db_instance

    if _db_instance is None:
        _db_instance = OlavDatabase(db_path)

    return _db_instance


def reset_database() -> None:
    """Reset the global database instance.

    Use this in tests to ensure clean state between test runs.
    """
    global _db_instance
    if _db_instance is not None:
        try:
            _db_instance.close()
        except Exception:
            pass
        _db_instance = None


# =============================================================================
# Knowledge Database (Phase 4: Knowledge Base Integration)
# =============================================================================


def init_knowledge_db(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Initialize the knowledge database with vector support.

    This creates a separate database for storing indexed knowledge:
    - Vendor documentation (Cisco, Huawei, etc.)
    - Team wiki and runbooks
    - Learned solutions from HITL interactions

    Args:
        db_path: Path to knowledge database file (default: .olav/data/knowledge.db)

    Returns:
        DuckDB connection object

    Example:
        >>> conn = init_knowledge_db()
        >>> # Use connection for indexing...
        >>> conn.close()
    """
    from config.settings import settings

    if db_path is None:
        db_path = str(Path(settings.agent_dir) / "data" / "knowledge.db")

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB
    conn = duckdb.connect(db_path)

    try:
        # Enable DuckDB VSS extension for vector search
        conn.execute("INSTALL vss;")
        conn.execute("LOAD vss;")
    except Exception as e:
        print(f"Warning: Could not install/load VSS extension: {e}")
        print("Vector search will be disabled. FTS-only search will be used.")

    # Create knowledge sources table
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS knowledge_sources_id_seq START 1
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id INTEGER PRIMARY KEY DEFAULT nextval('knowledge_sources_id_seq'),
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            base_path TEXT,
            version TEXT,
            platform TEXT,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Initialize default knowledge sources (Phase 7)
    # These are inserted only if they don't already exist
    default_sources = [
        ("Skills", "markdown", ".olav/skills", None, "skills"),
        ("Knowledge Base", "markdown", ".olav/knowledge", None, "knowledge"),
        ("Reports", "markdown", "data/reports", None, "report"),
    ]

    for name, source_type, base_path, version, platform in default_sources:
        try:
            conn.execute(
                "INSERT INTO knowledge_sources "
                "(name, type, base_path, version, platform) "
                "VALUES (?, ?, ?, ?, ?)",
                [name, source_type, base_path, version, platform],
            )
        except Exception as e:  # noqa: S110, F841
            # Ignore duplicate key errors - sources already exist
            pass

    conn.commit()

    # Create knowledge chunks table with vector embeddings
    # Note: embedding dimension depends on model
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS knowledge_chunks_id_seq START 1
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY DEFAULT nextval('knowledge_chunks_id_seq'),
            source_id INTEGER REFERENCES knowledge_sources(id),
            file_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            platform TEXT,
            doc_type TEXT,
            keywords TEXT[],
            embedding FLOAT[768],
            file_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create full-text search index
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_fts
            ON knowledge_chunks USING FTS(title, content, keywords)
        """)
    except Exception as e:
        print(f"Warning: Could not create FTS index: {e}")

    # Create vector index (HNSW - Hierarchical Navigable Small World)
    # This provides fast approximate nearest neighbor search
    try:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_vector
            ON knowledge_chunks USING HNSW(embedding)
        """)
    except Exception as e:
        print(f"Warning: Could not create vector index: {e}")
        print("Vector search performance will be degraded.")

    # Create other indexes for efficient querying
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_file_path
        ON knowledge_chunks(file_path)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_source
        ON knowledge_chunks(source_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_platform
        ON knowledge_chunks(platform)
    """)

    return conn
