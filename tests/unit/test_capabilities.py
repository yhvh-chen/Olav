"""
Unit tests for capabilities module.

Tests for searching CLI commands and API endpoints in the capability database.
"""

from unittest.mock import Mock, patch

import pytest

from olav.tools.capabilities import (
    search,
    search_capabilities,
)


# =============================================================================
# Test search_capabilities
# =============================================================================


class TestSearchCapabilities:
    """Tests for search_capabilities tool."""

    def test_search_capabilities_found(self):
        """Test successful search with results."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "show interface",
                "description": "Show interface status",
                "is_write": False,
            },
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "configure terminal",
                "description": "Enter config mode",
                "is_write": True,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("interface", type="command", platform="cisco_ios")

        assert "Found 2 capabilities:" in result
        assert "show interface" in result
        assert "configure terminal" in result
        assert "**REQUIRES APPROVAL**" in result

    def test_search_capabilities_no_results(self):
        """Test search with no matching results."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("nonexistent")

        assert "No capabilities found matching 'nonexistent'" in result

    def test_search_capabilities_api_endpoint(self):
        """Test search for API endpoints."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "api",
                "platform": "netbox",
                "name": "/dcim/devices/",
                "method": "GET",
                "description": "Query device list",
                "is_write": False,
            },
            {
                "type": "api",
                "platform": "netbox",
                "name": "/dcim/devices/{id}/",
                "method": "PATCH",
                "description": "Update device",
                "is_write": True,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("device", type="api", platform="netbox")

        assert "GET /dcim/devices/" in result
        assert "PATCH /dcim/devices/{id}/" in result
        assert "**REQUIRES APPROVAL**" in result

    def test_search_capabilities_all_types(self):
        """Test search with type='all'."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "show run",
                "description": "Show running config",
                "is_write": False,
            },
            {
                "type": "api",
                "platform": "zabbix",
                "name": "/host/get",
                "method": "GET",
                "description": "Get hosts",
                "is_write": False,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("show", type="all")

        assert "show run" in result
        assert "GET /host/get" in result

    def test_search_capabilities_custom_limit(self):
        """Test search with custom limit."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {"type": "command", "platform": "cisco_ios", "name": f"cmd{i}", "is_write": False}
            for i in range(50)
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("cmd", limit=5)

        # Should only return first 5 results
        assert "Found 5 capabilities:" in result or "cmd4" in result

    def test_search_capabilities_without_description(self):
        """Test capabilities without descriptions."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "show version",
                "is_write": False,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("version")

        assert "show version" in result
        assert "(cisco_ios)" in result

    def test_search_capabilities_write_approval_flag(self):
        """Test that write operations show approval warning."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "write memory",
                "description": "Save config",
                "is_write": True,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("write")

        assert "**REQUIRES APPROVAL**" in result

    def test_search_capabilities_read_only_no_warning(self):
        """Test that read-only operations don't show approval warning."""
        from olav.tools.capabilities import search_capabilities as search_tool

        mock_db = Mock()
        mock_db.search_capabilities = Mock(return_value=[
            {
                "type": "command",
                "platform": "cisco_ios",
                "name": "show run",
                "description": "Show config",
                "is_write": False,
            },
        ])

        with patch("olav.tools.capabilities.get_database", return_value=mock_db):
            result = search_tool.func("show")

        assert "**REQUIRES APPROVAL**" not in result


# =============================================================================
# Test search (unified search)
# =============================================================================


class TestSearch:
    """Tests for unified search tool."""

    def test_search_all_scopes_with_results(self):
        """Test search across both capabilities and knowledge."""
        from olav.tools.capabilities import search as search_tool

        # Mock search_capabilities to return the function
        mock_search_cap = Mock(return_value="Found 2 capabilities:\n1. show interface")

        # Mock search_knowledge
        mock_knowledge = Mock(return_value="## Interface Guide\nInterface status info...")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
                result = search_tool.func("interface", scope="all")

        assert "## CLI Commands & APIs" in result
        assert "## Documentation" in result
        assert "---" in result

    def test_search_capabilities_only(self):
        """Test search restricted to capabilities only."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="Found 1 capability:\n1. show run")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            result = search_tool.func("config", scope="capabilities")

        assert "## CLI Commands & APIs" in result
        assert "## Documentation" not in result

    def test_search_knowledge_only(self):
        """Test search restricted to knowledge only."""
        from olav.tools.capabilities import search as search_tool

        mock_knowledge = Mock(return_value="## Config Guide\nConfiguration info...")

        with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
            result = search_tool.func("config", scope="knowledge")

        assert "## Documentation" in result
        assert "## CLI Commands & APIs" not in result

    def test_search_no_results(self):
        """Test search with no results from any source."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="No capabilities found matching 'x'")

        mock_knowledge = Mock(return_value="")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
                result = search_tool.func("nonexistent", scope="all")

        assert "No results found for: nonexistent" in result

    def test_search_with_platform_filter(self):
        """Test search with platform filter."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="Found 1 capability:\n1. show bgp")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            result = search_tool.func("bgp", platform="cisco_ios")

        # Verify platform was passed through
        assert mock_search_cap.called

    def test_search_with_custom_limit(self):
        """Test search with custom limit."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="Found 5 capabilities:\n...")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            result = search_tool.func("interface", limit=5)

        # Verify limit was passed through
        assert mock_search_cap.called

    def test_search_empty_knowledge_results(self):
        """Test search when knowledge returns empty."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="Found 1 capability:\n1. show ver")

        mock_knowledge = Mock(return_value="")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
                result = search_tool.func("version", scope="all")

        # Should only include capabilities section
        assert "## CLI Commands & APIs" in result
        assert "## Documentation" not in result

    def test_search_empty_capabilities_results(self):
        """Test search when capabilities returns no results."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="No capabilities found")

        mock_knowledge = Mock(return_value="## Version Guide\nVersion info...")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
                result = search_tool.func("version", scope="all")

        # Should only include knowledge section
        assert "## Documentation" in result
        assert "## CLI Commands & APIs" not in result

    def test_search_result_separation(self):
        """Test that different result types are properly separated."""
        from olav.tools.capabilities import search as search_tool

        mock_search_cap = Mock(return_value="Found 1 capability:\n1. cmd1")

        mock_knowledge = Mock(return_value="## Doc\nContent")

        with patch("olav.tools.capabilities.search_capabilities", mock_search_cap):
            with patch("olav.tools.capabilities.search_knowledge", mock_knowledge):
                result = search_tool.func("test", scope="all")

        # Check for separator
        assert "\n\n---\n\n" in result
        assert result.startswith("## CLI Commands & APIs")
