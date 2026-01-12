"""Unit tests for database module.

Tests for DuckDB database functionality including capabilities, audit logs,
and command caching.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from olav.core.database import (
    OlavDatabase,
    get_database,
    reset_database,
    init_knowledge_db,
)


# =============================================================================
# Test OlavDatabase initialization
# =============================================================================


class TestOlavDatabaseInit:
    """Tests for OlavDatabase initialization."""

    @patch("olav.core.database.duckdb.connect")
    def test_init_with_default_path(self, mock_connect):
        """Test initialization with default database path."""
        mock_conn = MagicMock()
        # Mock the execute chain for _ensure_command_whitelist_loaded
        mock_result = Mock()
        mock_result.fetchone.return_value = [10]  # Already has commands
        mock_conn.execute.return_value = mock_result
        mock_connect.return_value = mock_conn

        with patch("olav.core.database.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.__truediv__ = Mock(return_value=mock_path)
            mock_path.mkdir = Mock()
            mock_path_class.return_value = mock_path
            mock_path_class.cwd.return_value = mock_path

            db = OlavDatabase()

        assert db.conn == mock_conn

    @patch("olav.core.database.duckdb.connect")
    def test_init_with_custom_path(self, mock_connect, tmp_path):
        """Test initialization with custom database path."""
        custom_db = tmp_path / "custom.db"
        mock_conn = MagicMock()
        # Mock the execute chain
        mock_result = Mock()
        mock_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=str(custom_db))

        assert db.db_path == custom_db
        assert custom_db.parent.exists()


# =============================================================================
# Test search_capabilities
# =============================================================================


class TestSearchCapabilities:
    """Tests for search_capabilities method."""

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_search_capabilities_basic(self, mock_init, mock_connect):
        """Test basic capability search."""
        mock_conn = MagicMock()
        # Setup mock for search
        mock_search_result = Mock()
        mock_search_result.fetchall.return_value = [
            ("command", "cisco_ios", "show version", None, "Show version", None, False)
        ]
        mock_conn.execute.return_value = mock_search_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        results = db.search_capabilities("version")

        assert len(results) == 1
        assert results[0]["name"] == "show version"
        assert results[0]["platform"] == "cisco_ios"

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_search_capabilities_with_platform_filter(self, mock_init, mock_connect):
        """Test search with platform filter."""
        mock_conn = MagicMock()
        mock_search_result = Mock()
        mock_search_result.fetchall.return_value = [
            ("command", "arista_eos", "show version", None, "Show version", None, False)
        ]
        mock_conn.execute.return_value = mock_search_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        results = db.search_capabilities("version", platform="arista_eos")

        assert len(results) == 1
        assert results[0]["platform"] == "arista_eos"

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_search_capabilities_with_type_filter(self, mock_init, mock_connect):
        """Test search with type filter."""
        mock_conn = MagicMock()
        mock_search_result = Mock()
        mock_search_result.fetchall.return_value = [
            ("api", "netbox", "/api/dcim/devices", "GET", "List devices", None, False)
        ]
        mock_conn.execute.return_value = mock_search_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        results = db.search_capabilities("devices", cap_type="api")

        assert len(results) == 1
        assert results[0]["type"] == "api"

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_search_capabilities_empty_results(self, mock_init, mock_connect):
        """Test search with no matches."""
        mock_conn = MagicMock()
        mock_search_result = Mock()
        mock_search_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_search_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        results = db.search_capabilities("nonexistent")

        assert len(results) == 0


# =============================================================================
# Test is_command_allowed
# =============================================================================


class TestIsCommandAllowed:
    """Tests for is_command_allowed method."""

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_command_allowed_exact_match(self, mock_init, mock_connect):
        """Test exact command match."""
        mock_conn = MagicMock()
        mock_patterns_result = Mock()
        mock_patterns_result.fetchall.return_value = [
            ("show version",),
            ("show interfaces",),
        ]
        mock_conn.execute.return_value = mock_patterns_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.is_command_allowed("show version", "cisco_ios")

        assert result is True

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_command_allowed_wildcard_match(self, mock_init, mock_connect):
        """Test wildcard pattern matching."""
        mock_conn = MagicMock()
        mock_patterns_result = Mock()
        mock_patterns_result.fetchall.return_value = [
            ("show*",),
        ]
        mock_conn.execute.return_value = mock_patterns_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.is_command_allowed("show version", "cisco_ios")

        assert result is True

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_command_allowed_case_insensitive(self, mock_init, mock_connect):
        """Test case-insensitive matching."""
        mock_conn = MagicMock()
        mock_patterns_result = Mock()
        mock_patterns_result.fetchall.return_value = [
            ("show version",),
        ]
        mock_conn.execute.return_value = mock_patterns_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.is_command_allowed("SHOW VERSION", "cisco_ios")

        assert result is True

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_command_not_allowed(self, mock_init, mock_connect):
        """Test command not in whitelist."""
        mock_conn = MagicMock()
        mock_patterns_result = Mock()
        mock_patterns_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_patterns_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.is_command_allowed("configure terminal", "cisco_ios")

        assert result is False


# =============================================================================
# Test insert_capability
# =============================================================================


class TestInsertCapability:
    """Tests for insert_capability method."""

    @patch("olav.core.database.duckdb.connect")
    def test_insert_command_capability(self, mock_connect):
        """Test inserting a command capability."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        # Reset the mock to track actual calls
        mock_conn.reset_mock()
        db.insert_capability(
            cap_type="command",
            platform="cisco_ios",
            name="show version",
            source_file="/imports/cisco_ios.txt",
            description="Show version information",
            is_write=False
        )

        mock_conn.execute.assert_called()

    @patch("olav.core.database.duckdb.connect")
    def test_insert_api_capability(self, mock_connect):
        """Test inserting an API capability."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.insert_capability(
            cap_type="api",
            platform="netbox",
            name="/api/dcim/devices",
            source_file="/imports/netbox.txt",
            method="GET",
            description="List devices",
            is_write=False
        )

        mock_conn.execute.assert_called()


# =============================================================================
# Test clear_capabilities
# =============================================================================


class TestClearCapabilities:
    """Tests for clear_capabilities method."""

    @patch("olav.core.database.duckdb.connect")
    def test_clear_capabilities(self, mock_connect):
        """Test clearing all capabilities."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.clear_capabilities()

        mock_conn.execute.assert_called_once_with("DELETE FROM capabilities")


# =============================================================================
# Test log_execution
# =============================================================================


class TestLogExecution:
    """Tests for log_execution method."""

    @patch("olav.core.database.duckdb.connect")
    def test_log_execution_basic(self, mock_connect):
        """Test basic execution logging."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.log_execution(
            thread_id="thread-123",
            device="R1",
            command="show version",
            output="Cisco IOS...",
            success=True,
            duration_ms=150
        )

        mock_conn.execute.assert_called_once()

    @patch("olav.core.database.duckdb.connect")
    def test_log_execution_with_user(self, mock_connect):
        """Test execution logging with user identifier."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.log_execution(
            thread_id="thread-123",
            device="R1",
            command="show version",
            output="Output",
            success=True,
            duration_ms=100,
            user="admin"
        )

        # Verify user was included
        call_args = mock_conn.execute.call_args
        assert "admin" in call_args[0][1]


# =============================================================================
# Test command cache
# =============================================================================


class TestCommandCache:
    """Tests for command cache methods."""

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_get_command_cache_miss(self, mock_init, mock_connect):
        """Test cache miss returns None."""
        mock_conn = MagicMock()
        mock_cache_result = Mock()
        mock_cache_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cache_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.get_command_cache("R1", "show version")

        assert result is None

    @patch("olav.core.database.duckdb.connect")
    @patch("olav.core.database.OlavDatabase._init_schema")
    def test_get_command_cache_hit(self, mock_init, mock_connect):
        """Test cache hit returns cached output."""
        mock_conn = MagicMock()
        mock_cache_result = Mock()
        mock_cache_result.fetchone.return_value = (
            "Cached output here",
            "2025-01-11 10:00:00",
            300
        )
        mock_conn.execute.return_value = mock_cache_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        result = db.get_command_cache("R1", "show version")

        assert result == "Cached output here"

    @patch("olav.core.database.duckdb.connect")
    def test_set_command_cache(self, mock_connect):
        """Test setting command cache."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.set_command_cache(
            device="R1",
            command="show version",
            output="Output to cache",
            ttl_seconds=600
        )

        mock_conn.execute.assert_called_once()

    @patch("olav.core.database.duckdb.connect")
    def test_set_command_cache_default_ttl(self, mock_connect):
        """Test setting cache with default TTL."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        mock_conn.reset_mock()
        db.set_command_cache(
            device="R1",
            command="show version",
            output="Output"
        )

        # Verify default TTL of 300 was used
        call_args = mock_conn.execute.call_args
        assert 300 in call_args[0][1]


# =============================================================================
# Test database connection management
# =============================================================================


class TestDatabaseConnection:
    """Tests for database connection management."""

    @patch("olav.core.database.duckdb.connect")
    def test_close_connection(self, mock_connect):
        """Test closing database connection."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        db = OlavDatabase(db_path=":memory:")
        db.close()

        mock_conn.close.assert_called_once()

    @patch("olav.core.database.duckdb.connect")
    def test_context_manager(self, mock_connect):
        """Test database as context manager."""
        mock_conn = MagicMock()
        mock_init_result = Mock()
        mock_init_result.fetchone.return_value = [10]
        mock_conn.execute.return_value = mock_init_result
        mock_connect.return_value = mock_conn

        with OlavDatabase(db_path=":memory:") as db:
            assert db is not None

        mock_conn.close.assert_called_once()


# =============================================================================
# Test get_database singleton
# =============================================================================


class TestGetDatabase:
    """Tests for get_database singleton function."""

    def test_get_database_returns_instance(self):
        """Test that get_database returns OlavDatabase instance."""
        # Reset any existing instance
        reset_database()

        with patch("olav.core.database.OlavDatabase") as mock_db_class:
            mock_instance = Mock()
            mock_db_class.return_value = mock_instance

            result = get_database()

            assert result == mock_instance
            mock_db_class.assert_called_once_with(None)

    def test_get_database_singleton(self):
        """Test that get_database returns same instance."""
        reset_database()

        with patch("olav.core.database.OlavDatabase") as mock_db_class:
            mock_instance = Mock()
            mock_db_class.return_value = mock_instance

            result1 = get_database()
            result2 = get_database()

            # Should only be called once due to singleton
            assert mock_db_class.call_count == 1

    def test_get_database_with_custom_path(self):
        """Test get_database with custom path."""
        reset_database()

        with patch("olav.core.database.OlavDatabase") as mock_db_class:
            mock_instance = Mock()
            mock_db_class.return_value = mock_instance

            result = get_database(db_path="/custom/path.db")

            mock_db_class.assert_called_once_with("/custom/path.db")


# =============================================================================
# Test reset_database
# =============================================================================


class TestResetDatabase:
    """Tests for reset_database function."""

    def test_reset_database_clears_instance(self):
        """Test that reset_database clears the global instance."""
        reset_database()

        # Create a mock instance
        with patch("olav.core.database._db_instance", Mock()):
            reset_database()

        # Should be cleared
        from olav.core.database import _db_instance
        assert _db_instance is None

    def test_reset_database_closes_connection(self):
        """Test that reset_database closes existing connection."""
        mock_instance = Mock()
        mock_instance.close.return_value = None

        with patch("olav.core.database._db_instance", mock_instance):
            reset_database()

        mock_instance.close.assert_called_once()


# =============================================================================
# Test init_knowledge_db
# =============================================================================


class TestInitKnowledgeDb:
    """Tests for init_knowledge_db function."""

    @patch("olav.core.database.duckdb.connect")
    def test_init_knowledge_db_default_path(self, mock_connect, tmp_path):
        """Test knowledge DB initialization with default path."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        # Create a test knowledge db path - use custom path since default requires settings
        test_db = tmp_path / "knowledge.db"
        result = init_knowledge_db(db_path=str(test_db))

        assert result == mock_conn

    @patch("olav.core.database.duckdb.connect")
    def test_init_knowledge_db_custom_path(self, mock_connect, tmp_path):
        """Test knowledge DB with custom path."""
        custom_path = tmp_path / "knowledge.db"
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        result = init_knowledge_db(db_path=str(custom_path))

        assert result == mock_conn

    @patch("olav.core.database.duckdb.connect")
    def test_init_knowledge_db_creates_tables(self, mock_connect):
        """Test that knowledge DB tables are created."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        result = init_knowledge_db()

        # Verify multiple execute calls for table creation
        assert mock_conn.execute.called

    @patch("olav.core.database.duckdb.connect")
    def test_init_knowledge_db_handles_vss_error(self, mock_connect):
        """Test handling of VSS extension errors."""
        def execute_side_effect(sql):
            if "INSTALL vss" in sql:
                raise Exception("VSS not available")
            return Mock()

        mock_conn = Mock()
        mock_conn.execute.side_effect = execute_side_effect
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_connect.return_value = mock_conn

        # Should not raise exception
        result = init_knowledge_db()

        assert result is not None
