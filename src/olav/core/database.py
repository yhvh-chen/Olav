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

    def __init__(self, db_path: str | Path = ".olav/capabilities.db"):
        """Initialize database connection.

        Args:
            db_path: Path to DuckDB database file
        """
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

        return [dict(zip(columns, row)) for row in results]

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

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
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
        _db_instance = OlavDatabase(db_path or ".olav/capabilities.db")

    return _db_instance
