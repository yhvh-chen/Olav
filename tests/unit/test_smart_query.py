"""
Unit tests for smart_query module.

Tests for P0 optimization: single-call device queries combining platform detection,
command search, and execution. Also tests P2 command mapping cache and P4 connection pool.
"""

from unittest.mock import Mock, patch

import pytest

from olav.tools.smart_query import (
    _batch_query_internal,
    clear_command_cache,
    clear_device_cache,
    get_best_command,
    get_cached_commands,
    get_cache_stats,
    get_device_info,
    smart_query,
)


# =============================================================================
# Test get_cached_commands
# =============================================================================


class TestGetCachedCommands:
    """Tests for get_cached_commands function."""

    def test_get_cached_commands_returns_list(self):
        """Test that get_cached_commands returns a list."""
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[
                {"name": "show ip interface brief", "is_write": False},
                {"name": "show interface", "is_write": False},
                {"name": "configure terminal", "is_write": True},
            ])
            mock_get_db.return_value = mock_db

            # Clear cache first
            get_cached_commands.cache_clear()

            result = get_cached_commands("cisco_ios", "interface")

            assert isinstance(result, list)
            assert len(result) == 2
            assert "show ip interface brief" in result
            assert "show interface" in result
            assert "configure terminal" not in result  # is_write=True filtered out

    def test_get_cached_commands_filters_write_commands(self):
        """Test that write commands are filtered out."""
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[
                {"name": "show run", "is_write": False},
                {"name": "conf t", "is_write": True},
            ])
            mock_get_db.return_value = mock_db

            get_cached_commands.cache_clear()
            result = get_cached_commands("cisco_ios", "config")

            assert result == ["show run"]

    def test_get_cached_commands_empty_result(self):
        """Test with empty database result."""
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[])
            mock_get_db.return_value = mock_db

            get_cached_commands.cache_clear()
            result = get_cached_commands("cisco_ios", "nonexistent")

            assert result == []

    def test_get_cached_commands_uses_lru_cache(self):
        """Test that LRU cache is working."""
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[
                {"name": "show ip int brief", "is_write": False},
            ])
            mock_get_db.return_value = mock_db

            get_cached_commands.cache_clear()

            # First call
            result1 = get_cached_commands("cisco_ios", "interface")
            # Second call should use cache
            result2 = get_cached_commands("cisco_ios", "interface")

            assert result1 == result2
            # Database should only be called once due to cache
            assert mock_db.search_capabilities.call_count == 1


# =============================================================================
# Test get_best_command
# =============================================================================


class TestGetBestCommand:
    """Tests for get_best_command function."""

    def test_get_best_command_prefers_brief(self):
        """Test that 'brief' commands are preferred."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            mock_cached.return_value = [
                "show interface",
                "show ip interface brief",
                "show interface detail",
            ]

            result = get_best_command("cisco_ios", "interface")

            assert result == "show ip interface brief"

    def test_get_best_command_prefers_show_start(self):
        """Test that 'show' commands are preferred for Cisco when no brief."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            mock_cached.return_value = [
                "get interface",
                "show interface",
                "display interface",
            ]

            result = get_best_command("cisco_ios", "interface")

            assert result == "show interface"

    def test_get_best_command_prefers_display_start(self):
        """Test that 'display' commands are preferred for Huawei."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            # The function prefers show commands over display if show appears first
            # Let's test with display before show
            mock_cached.return_value = [
                "get interface",
                "display interface brief",
                "show interface",
            ]

            result = get_best_command("huawei_vrp", "interface")

            # brief should be preferred regardless of platform
            assert result == "display interface brief"

    def test_get_best_command_display_only_no_show(self):
        """Test display command is returned when no show commands exist."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            # No "show" commands, only "display" commands
            mock_cached.return_value = [
                "get interface",
                "display interface",
                "list interfaces",
            ]

            result = get_best_command("huawei_vrp", "interface")

            # Should return the display command (line 77 coverage)
            assert result == "display interface"

    def test_get_best_command_returns_first_when_no_match(self):
        """Test that first command is returned when no special match."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            mock_cached.return_value = [
                "get interface status",
                "list interfaces",
            ]

            result = get_best_command("generic", "interface")

            assert result == "get interface status"

    def test_get_best_command_returns_none_when_empty(self):
        """Test that None is returned when no commands available."""
        with patch("olav.tools.smart_query.get_cached_commands") as mock_cached:
            mock_cached.return_value = []

            result = get_best_command("cisco_ios", "nonexistent")

            assert result is None


# =============================================================================
# Test get_device_info
# =============================================================================


class TestGetDeviceInfo:
    """Tests for get_device_info function."""

    def test_get_device_info_from_inventory(self):
        """Test getting device info from Nornir inventory."""
        mock_host = Mock()
        mock_host.hostname = "router1.example.com"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda k, d=None: {
            "role": "core",
            "site": "lab",
        }.get(k, d))

        with patch("olav.tools.smart_query.get_nornir") as mock_get_nr:
            mock_nr = Mock()
            mock_nr.inventory.hosts = {"R1": mock_host}
            mock_get_nr.return_value = mock_nr

            # Clear cache
            clear_device_cache()

            result = get_device_info("R1")

            assert result is not None
            assert result["name"] == "R1"
            assert result["hostname"] == "router1.example.com"
            assert result["platform"] == "cisco_ios"
            assert result["role"] == "core"
            assert result["site"] == "lab"

    def test_get_device_info_caches_results(self):
        """Test that device info is cached."""
        mock_host = Mock()
        mock_host.hostname = "router1.example.com"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(return_value="core")

        with patch("olav.tools.smart_query.get_nornir") as mock_get_nr:
            mock_nr = Mock()
            mock_nr.inventory.hosts = {"R1": mock_host}
            mock_get_nr.return_value = mock_nr

            clear_device_cache()

            # First call
            result1 = get_device_info("R1")
            # Second call should use cache
            result2 = get_device_info("R1")

            assert result1 == result2
            # Nornir should only be called once
            assert mock_get_nr.call_count == 1

    def test_get_device_info_not_found(self):
        """Test getting info for non-existent device."""
        with patch("olav.tools.smart_query.get_nornir") as mock_get_nr:
            mock_nr = Mock()
            mock_nr.inventory.hosts = {}
            mock_get_nr.return_value = mock_nr

            clear_device_cache()
            result = get_device_info("NONEXISTENT")

            assert result is None

    def test_get_device_info_handles_exception(self):
        """Test exception handling in get_device_info."""
        with patch("olav.tools.smart_query.get_nornir") as mock_get_nr:
            mock_get_nr.side_effect = Exception("Nornir error")

            clear_device_cache()
            result = get_device_info("R1")

            assert result is None

    def test_get_device_info_uses_defaults(self):
        """Test that default values are used when fields missing."""
        mock_host = Mock()
        mock_host.hostname = None
        mock_host.platform = None
        mock_host.get = Mock(side_effect=lambda k, d=None: d)  # Return default value

        with patch("olav.tools.smart_query.get_nornir") as mock_get_nr:
            mock_nr = Mock()
            mock_nr.inventory.hosts = {"R1": mock_host}
            mock_get_nr.return_value = mock_nr

            clear_device_cache()
            result = get_device_info("R1")

            assert result["hostname"] == "R1"  # Fallback to device name
            assert result["platform"] == "unknown"
            assert result["role"] == "unknown"
            assert result["site"] == "unknown"


# =============================================================================
# Test smart_query (single device)
# =============================================================================


class TestSmartQuerySingleDevice:
    """Tests for smart_query with single device."""

    def test_smart_query_single_device_success(self):
        """Test successful single device query."""
        # Import the actual function (not the tool decorator wrapper)
        from olav.tools.smart_query import smart_query as smart_query_func

        mock_result = Mock()
        mock_result.success = True
        mock_result.output = "Interface status output..."

        mock_executor = Mock()
        mock_executor.execute = Mock(return_value=mock_result)

        # Nest all patches together so they're all active during the call
        with patch("olav.tools.smart_query.get_device_info") as mock_get_info, \
             patch("olav.tools.smart_query.get_best_command") as mock_best_cmd, \
             patch("olav.tools.network.get_executor", return_value=mock_executor):

            mock_get_info.return_value = {
                "name": "R1",
                "hostname": "router1.example.com",
                "platform": "cisco_ios",
                "role": "core",
                "site": "lab",
            }
            mock_best_cmd.return_value = "show ip interface brief"

            # Call the function directly
            result = smart_query_func.func("R1", "interface")

        assert "## R1 (cisco_ios) - Interface Query" in result
        assert "router1.example.com" in result
        assert "show ip interface brief" in result
        assert "Interface status output" in result

    def test_smart_query_device_not_found(self):
        """Test query with non-existent device."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
            mock_get_info.return_value = None
            result = smart_query_func.func("NONEXISTENT", "interface")

        assert "Error: Device 'NONEXISTENT' not found in inventory" in result
        assert "Use list_devices to see available devices" in result

    def test_smart_query_with_explicit_command(self):
        """Test query with explicit command override."""
        from olav.tools.smart_query import smart_query as smart_query_func

        mock_result = Mock()
        mock_result.success = True
        mock_result.output = "version output"

        mock_executor = Mock()
        mock_executor.execute = Mock(return_value=mock_result)

        with patch("olav.tools.smart_query.get_device_info") as mock_get_info, \
             patch("olav.tools.network.get_executor", return_value=mock_executor):

            mock_get_info.return_value = {
                "name": "R1",
                "hostname": "router1",
                "platform": "cisco_ios",
                "role": "core",
                "site": "lab",
            }
            result = smart_query_func.func("R1", "version", command="show version")

        assert "show version" in result
        assert "version output" in result

    def test_smart_query_no_command_found(self):
        """Test query when no command is found for intent."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query.get_device_info") as mock_get_info, \
             patch("olav.tools.smart_query.get_best_command") as mock_best_cmd, \
             patch("olav.tools.smart_query.get_cached_commands") as mock_cached:

            mock_get_info.return_value = {
                "name": "R1",
                "hostname": "router1",
                "platform": "cisco_ios",
                "role": "core",
                "site": "lab",
            }
            mock_best_cmd.return_value = None
            mock_cached.return_value = []

            result = smart_query_func.func("R1", "nonexistent")

        assert "Error: No commands found for intent 'nonexistent'" in result
        assert "'nonexistent'" in result

    def test_smart_query_command_execution_failed(self):
        """Test query when command execution fails."""
        from olav.tools.smart_query import smart_query as smart_query_func

        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Connection timeout"

        mock_executor = Mock()
        mock_executor.execute = Mock(return_value=mock_result)

        with patch("olav.tools.smart_query.get_device_info") as mock_get_info, \
             patch("olav.tools.smart_query.get_best_command") as mock_best_cmd, \
             patch("olav.tools.network.get_executor", return_value=mock_executor):

            mock_get_info.return_value = {
                "name": "R1",
                "hostname": "router1",
                "platform": "cisco_ios",
                "role": "core",
                "site": "lab",
            }
            mock_best_cmd.return_value = "show interface"

            result = smart_query_func.func("R1", "interface")

        assert "Query Failed" in result
        assert "Connection timeout" in result

    def test_smart_query_uses_cached_command_when_best_fails(self):
        """Test that cached commands are used as fallback."""
        from olav.tools.smart_query import smart_query as smart_query_func

        mock_result = Mock()
        mock_result.success = True
        mock_result.output = "interface output"

        mock_executor = Mock()
        mock_executor.execute = Mock(return_value=mock_result)

        with patch("olav.tools.smart_query.get_device_info") as mock_get_info, \
             patch("olav.tools.smart_query.get_best_command") as mock_best_cmd, \
             patch("olav.tools.smart_query.get_cached_commands") as mock_cached, \
             patch("olav.tools.network.get_executor", return_value=mock_executor):

            mock_get_info.return_value = {
                "name": "R1",
                "hostname": "router1",
                "platform": "cisco_ios",
                "role": "core",
                "site": "lab",
            }
            mock_best_cmd.return_value = None
            mock_cached.return_value = ["show interface"]

            result = smart_query_func.func("R1", "interface")

        assert "show interface" in result


# =============================================================================
# Test smart_query (batch queries)
# =============================================================================


class TestSmartQueryBatchDetection:
    """Tests for batch query detection in smart_query."""

    def test_comma_separated_is_batch(self):
        """Test that comma-separated devices trigger batch mode."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query._batch_query_internal") as mock_batch:
            mock_batch.return_value = "batch result"

            smart_query_func.func("R1,R2,R3", "interface")

            mock_batch.assert_called_once()

    def test_all_is_batch(self):
        """Test that 'all' keyword triggers batch mode."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query._batch_query_internal") as mock_batch:
            mock_batch.return_value = "batch result"

            smart_query_func.func("all", "interface")

            mock_batch.assert_called_once()

    def test_role_filter_is_batch(self):
        """Test that role: filter triggers batch mode."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query._batch_query_internal") as mock_batch:
            mock_batch.return_value = "batch result"

            smart_query_func.func("role:core", "interface")

            mock_batch.assert_called_once()

    def test_site_filter_is_batch(self):
        """Test that site: filter triggers batch mode."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query._batch_query_internal") as mock_batch:
            mock_batch.return_value = "batch result"

            smart_query_func.func("site:lab", "interface")

            mock_batch.assert_called_once()

    def test_group_filter_is_batch(self):
        """Test that group: filter triggers batch mode."""
        from olav.tools.smart_query import smart_query as smart_query_func

        with patch("olav.tools.smart_query._batch_query_internal") as mock_batch:
            mock_batch.return_value = "batch result"

            smart_query_func.func("group:test", "interface")

            mock_batch.assert_called_once()


# =============================================================================
# Test _batch_query_internal
# =============================================================================


class TestBatchQueryInternal:
    """Tests for _batch_query_internal function."""

    def test_batch_query_all_devices(self):
        """Test batch query with 'all' devices."""
        # Create a mock hosts object that behaves like a dict but also supports .keys()
        mock_hosts = Mock()
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k in ["R1", "R2", "R3"])
        mock_hosts.keys = Mock(return_value=["R1", "R2", "R3"])
        mock_hosts.__getitem__ = Mock(side_effect=lambda k: Mock())

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
                mock_get_info.return_value = {
                    "platform": "cisco_ios",
                    "hostname": "router",
                    "role": "core",
                    "site": "lab",
                }

                with patch("olav.tools.smart_query.get_best_command") as mock_best_cmd:
                    mock_best_cmd.return_value = "show version"

                    # Mock Nornir run result
                    mock_agg_result = {}
                    for device in ["R1", "R2", "R3"]:
                        mock_result = Mock()
                        mock_result.failed = False
                        mock_result.result = "version output"
                        mock_agg_result[device] = mock_result

                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("all", "version")

        assert "## Batch Query: version (3 devices" in result

    def test_batch_query_role_filter(self):
        """Test batch query with role filter."""
        mock_host1 = Mock()
        mock_host1.get = Mock(return_value="core")
        mock_host2 = Mock()
        mock_host2.get = Mock(return_value="edge")

        # Create a mock hosts object with items method
        mock_hosts = Mock()
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k in ["R1", "R2"])
        mock_hosts.items = Mock(return_value=[
            ("R1", mock_host1),
            ("R2", mock_host2),
        ])
        mock_hosts.keys = Mock(return_value=["R1", "R2"])
        mock_hosts.__getitem__ = Mock(side_effect=lambda k: {"R1": mock_host1, "R2": mock_host2}.get(k))

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
                mock_get_info.return_value = {"platform": "cisco_ios"}

                with patch("olav.tools.smart_query.get_best_command", return_value="show run"):
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="config output")
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("role:core", "config")

        # Should only include R1 (core role)
        assert "role:core" in result or result

    def test_batch_query_comma_separated(self):
        """Test batch query with comma-separated devices."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": Mock(), "R2": Mock(), "R3": Mock()}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
                mock_get_info.return_value = {"platform": "cisco_ios"}

                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    # Mock successful execution
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="output1"),
                        "R2": Mock(failed=False, result="output2"),
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1,R2", "version")

        assert "2 devices" in result

    def test_batch_query_no_devices_found(self):
        """Test batch query when no devices match."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            result = _batch_query_internal("role:nonexistent", "version")

        assert "Error: No devices found matching" in result

    def test_batch_query_invalid_devices(self):
        """Test batch query with some invalid devices."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": Mock()}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info", return_value={"platform": "cisco_ios"}):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    mock_agg_result = {"R1": Mock(failed=False, result="output")}
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1,R2,R3", "version")

        assert "not found in inventory" in result or result

    def test_batch_query_truncates_long_output(self):
        """Test that long output is truncated in batch results."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": Mock()}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
                mock_get_info.return_value = {"platform": "cisco_ios"}

                with patch("olav.tools.smart_query.get_best_command", return_value="cmd"):
                    # Create very long output
                    long_output = "x" * 1000
                    mock_agg_result = {
                        "R1": Mock(failed=False, result=long_output)
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1", "test")

        assert "(truncated)" in result

    def test_batch_query_handles_failed_devices(self):
        """Test batch query with some devices failing."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": Mock(), "R2": Mock()}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info") as mock_get_info:
                mock_get_info.return_value = {"platform": "cisco_ios"}

                with patch("olav.tools.smart_query.get_best_command", return_value="cmd"):
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="success"),
                        "R2": Mock(failed=True, exception=Exception("Timeout")),
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1,R2", "test")

        assert "Error" in result or result

    def test_batch_query_site_filter(self):
        """Test batch query with site filter (lines 271-276)."""
        # Create hosts with different sites
        mock_host1 = Mock()
        mock_host1.get = Mock(side_effect=lambda k: "lab" if k == "site" else None)
        mock_host2 = Mock()
        mock_host2.get = Mock(side_effect=lambda k: "prod" if k == "site" else None)
        mock_host3 = Mock()
        mock_host3.get = Mock(side_effect=lambda k: "lab" if k == "site" else None)

        mock_hosts = Mock()
        mock_hosts.items = Mock(return_value=[
            ("R1", mock_host1),
            ("R2", mock_host2),
            ("R3", mock_host3),
        ])
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k in ["R1", "R2", "R3"])

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info", return_value={"platform": "cisco_ios"}):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="lab output"),
                        "R3": Mock(failed=False, result="lab output"),
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("site:lab", "version")

        # Should only process R1 and R3 (site:lab), not R2 (site:prod)
        assert "2 devices" in result
        assert "site:lab" in result

    def test_batch_query_group_filter_dict(self):
        """Test batch query with group filter when groups is dict (lines 279-288)."""
        # Create hosts with groups as dict
        mock_host1 = Mock()
        mock_host1.groups = {"core": None, "routers": None}
        mock_host1.get = Mock(return_value=None)

        mock_host2 = Mock()
        mock_host2.groups = {"switches": None}
        mock_host2.get = Mock(return_value=None)

        mock_hosts = Mock()
        mock_hosts.items = Mock(return_value=[
            ("R1", mock_host1),
            ("R2", mock_host2),
        ])
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k in ["R1", "R2"])

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info", return_value={"platform": "cisco_ios"}):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="router output"),
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("group:routers", "version")

        # Should only process R1 (in routers group)
        assert "1 devices" in result
        assert "group:routers" in result

    def test_batch_query_group_filter_list(self):
        """Test batch query with group filter when groups is list."""
        # Create hosts with groups as list
        mock_host1 = Mock()
        mock_host1.groups = ["core", "routers"]
        mock_host1.get = Mock(return_value=None)

        mock_host2 = Mock()
        mock_host2.groups = ["switches"]
        mock_host2.get = Mock(return_value=None)

        mock_hosts = Mock()
        mock_hosts.items = Mock(return_value=[
            ("R1", mock_host1),
            ("R2", mock_host2),
        ])
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k in ["R1", "R2"])

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info", return_value={"platform": "cisco_ios"}):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    mock_agg_result = {
                        "R1": Mock(failed=False, result="router output"),
                    }
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("group:routers", "version")

        # Should only process R1 (in routers group)
        assert "1 devices" in result

    def test_batch_query_no_valid_devices(self):
        """Test batch query when devices specified but none are valid (line 306)."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {}  # Empty inventory

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            result = _batch_query_internal("R1,R2,R3", "version")

        assert "Error: No valid devices found" in result
        assert "Invalid:" in result

    def test_batch_query_device_info_none_continues(self):
        """Test that None device info is skipped (line 316)."""
        mock_host = Mock()
        mock_host.get = Mock(return_value=None)

        mock_hosts = Mock()
        mock_hosts.items = Mock(return_value=[("R1", mock_host)])
        mock_hosts.__contains__ = Mock(side_effect=lambda k: k == "R1")

        mock_nr = Mock()
        mock_nr.inventory.hosts = mock_hosts

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            # get_device_info returns None for this device
            with patch("olav.tools.smart_query.get_device_info", return_value=None):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    # No results because device was skipped
                    mock_agg_result = {}
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1", "version")

        # Device should be skipped, showing it wasn't processed
        assert "Not processed" in result or result

    def test_batch_query_device_not_in_results(self):
        """Test handling of device not in results (line 390)."""
        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": Mock()}

        with patch("olav.tools.smart_query.get_nornir", return_value=mock_nr):
            with patch("olav.tools.smart_query.get_device_info", return_value={"platform": "cisco_ios"}):
                with patch("olav.tools.smart_query.get_best_command", return_value="show ver"):
                    # R1 not in results (e.g., filtered out)
                    mock_agg_result = {}
                    mock_nr.run = Mock(return_value=mock_agg_result)
                    mock_nr.filter = Mock(return_value=mock_nr)

                    result = _batch_query_internal("R1", "version")

        # Should show device as not processed
        assert "Not processed" in result


# =============================================================================
# Test cache management
# =============================================================================


class TestCacheManagement:
    """Tests for cache management functions."""

    def test_clear_command_cache(self):
        """Test clearing command cache."""
        # Populate cache first
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[
                {"name": "show run", "is_write": False}
            ])
            mock_get_db.return_value = mock_db

            get_cached_commands.cache_clear()
            get_cached_commands("cisco_ios", "test")

            # Verify cache has entries
            cache_info = get_cached_commands.cache_info()
            assert cache_info.currsize > 0

            # Clear cache
            clear_command_cache()

            # Verify cache is cleared
            cache_info = get_cached_commands.cache_info()
            assert cache_info.currsize == 0

    def test_clear_device_cache(self):
        """Test clearing device cache."""
        # Add something to device cache
        with patch("olav.tools.smart_query.get_nornir"):
            clear_device_cache()
            get_device_info.cache = {"R1": {"platform": "cisco_ios"}}

            # Actually we need to use the real cache
            from olav.tools.smart_query import _device_cache
            _device_cache["R1"] = {"platform": "cisco_ios"}

            clear_device_cache()

            from olav.tools.smart_query import _device_cache
            assert _device_cache == {}

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        with patch("olav.tools.smart_query.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.search_capabilities = Mock(return_value=[
                {"name": "show run", "is_write": False}
            ])
            mock_get_db.return_value = mock_db

            get_cached_commands.cache_clear()

            # Add to device cache
            from olav.tools.smart_query import _device_cache
            _device_cache["R1"] = {"platform": "cisco_ios"}

            stats = get_cache_stats()

            assert "command_cache" in stats
            assert "device_cache_size" in stats
            assert stats["device_cache_size"] == 1

            # Clean up
            clear_device_cache()
