"""Unit tests for network module.

Tests for network execution tools using Nornir.
"""

from unittest.mock import Mock, patch

import pytest

from olav.tools.network import (
    get_device_platform,
    list_devices,
    nornir_execute,
)


# =============================================================================
# Test nornir_execute
# =============================================================================


class TestNornirExecute:
    """Tests for nornir_execute function."""

    def test_nornir_execute_success(self):
        """Test successful command execution."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.output = "Command output here"

        mock_executor = Mock()
        mock_executor.execute.return_value = mock_result

        with patch("olav.tools.network.get_executor", return_value=mock_executor):
            result = nornir_execute.invoke({
                "device": "R1",
                "command": "show version",
                "timeout": 30
            })

            assert result == "Command output here"
            mock_executor.execute.assert_called_once_with(device="R1", command="show version", timeout=30)

    def test_nornir_execute_with_custom_timeout(self):
        """Test command execution with custom timeout."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.output = "Output"

        mock_executor = Mock()
        mock_executor.execute.return_value = mock_result

        with patch("olav.tools.network.get_executor", return_value=mock_executor):
            result = nornir_execute.invoke({
                "device": "R1",
                "command": "show run",
                "timeout": 60
            })

            assert result == "Output"
            mock_executor.execute.assert_called_once_with(device="R1", command="show run", timeout=60)

    def test_nornir_execute_failure(self):
        """Test command execution failure."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Connection failed"

        mock_executor = Mock()
        mock_executor.execute.return_value = mock_result

        with patch("olav.tools.network.get_executor", return_value=mock_executor):
            result = nornir_execute.invoke({
                "device": "R1",
                "command": "show version"
            })

            assert result == "Error: Connection failed"

    def test_nornir_execute_empty_output(self):
        """Test command execution with empty output."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.output = None

        mock_executor = Mock()
        mock_executor.execute.return_value = mock_result

        with patch("olav.tools.network.get_executor", return_value=mock_executor):
            result = nornir_execute.invoke({
                "device": "R1",
                "command": "show version"
            })

            assert result == ""


# =============================================================================
# Test list_devices
# =============================================================================


class TestListDevices:
    """Tests for list_devices function."""

    def test_list_devices_all(self):
        """Test listing all devices."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({})

            assert "Available devices:" in result
            assert "R1" in result
            assert "10.1.1.1" in result
            assert "cisco_ios" in result

    def test_list_devices_with_role_filter(self):
        """Test filtering devices by role."""
        mock_host1 = Mock()
        mock_host1.hostname = "10.1.1.1"
        mock_host1.platform = "cisco_ios"
        mock_host1.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host1.groups = []

        mock_host2 = Mock()
        mock_host2.hostname = "10.1.1.2"
        mock_host2.platform = "arista_eos"
        mock_host2.get = Mock(side_effect=lambda x, d=None: {
            "role": "access",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host2.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host1, "R2": mock_host2}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"role": "core"})

            assert "Devices with role 'core':" in result
            assert "R1" in result
            assert "R2" not in result

    def test_list_devices_with_site_filter(self):
        """Test filtering devices by site."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "datacenter",
            "aliases": []
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"site": "datacenter"})

            assert "Devices at site 'datacenter':" in result
            assert "R1" in result

    def test_list_devices_with_platform_filter(self):
        """Test filtering devices by platform."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"platform": "cisco_ios"})

            assert "R1" in result

    def test_list_devices_with_group_filter(self):
        """Test filtering devices by group."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))

        # Create a mock groups object that behaves like a dict
        mock_groups = Mock()
        mock_groups.keys.return_value = ["test"]
        # hasattr should return True for 'keys' method
        mock_host.groups = mock_groups

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"group": "test"})

            assert "Devices in group 'test':" in result
            assert "R1" in result
            assert "[test]" in result

    def test_list_devices_no_match(self):
        """Test when no devices match the criteria."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"role": "border"})

            assert "No devices found" in result

    def test_list_devices_with_alias_search(self):
        """Test searching devices by alias."""
        mock_host = Mock()
        mock_host.hostname = "router1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": ["核心路由器", "边界"]
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({"alias": "核心"})

            assert "R1" in result

    def test_list_devices_no_hostname(self):
        """Test device without hostname uses name."""
        mock_host = Mock()
        mock_host.hostname = None
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host.groups = []

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({})

            assert "R1 (R1)" in result

    def test_list_devices_exception(self):
        """Test exception handling."""
        with patch("olav.tools.network.get_nornir", side_effect=Exception("Connection error")):
            result = list_devices.invoke({})

            assert "Error listing devices" in result
            assert "Connection error" in result

    def test_list_devices_with_groups_list(self):
        """Test device with groups as list."""
        mock_host = Mock()
        mock_host.hostname = "10.1.1.1"
        mock_host.platform = "cisco_ios"
        mock_host.get = Mock(side_effect=lambda x, d=None: {
            "role": "core",
            "site": "lab",
            "aliases": []
        }.get(x, d))
        mock_host.groups = ["test", "lab"]

        mock_nr = Mock()
        mock_nr.inventory.hosts = {"R1": mock_host}

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = list_devices.invoke({})

            assert "[test,lab]" in result


# =============================================================================
# Test get_device_platform
# =============================================================================


class TestGetDevicePlatform:
    """Tests for get_device_platform function."""

    def test_get_device_platform_found(self):
        """Test getting platform for existing device."""
        mock_host = Mock()
        mock_host.platform = "cisco_ios"

        mock_nr = Mock()
        mock_nr.inventory.hosts.get.return_value = mock_host

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = get_device_platform.invoke({"device": "R1"})

            assert result == "Device R1 platform: cisco_ios"
            mock_nr.inventory.hosts.get.assert_called_once_with("R1")

    def test_get_device_platform_unknown(self):
        """Test getting platform when platform is None."""
        mock_host = Mock()
        mock_host.platform = None

        mock_nr = Mock()
        mock_nr.inventory.hosts.get.return_value = mock_host

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = get_device_platform.invoke({"device": "R1"})

            assert result == "Device R1 platform: unknown"

    def test_get_device_platform_not_found(self):
        """Test getting platform for non-existent device."""
        mock_nr = Mock()
        mock_nr.inventory.hosts.get.return_value = None

        with patch("olav.tools.network.get_nornir", return_value=mock_nr):
            result = get_device_platform.invoke({"device": "R999"})

            assert "Device 'R999' not found in inventory" in result

    def test_get_device_platform_exception(self):
        """Test exception handling."""
        with patch("olav.tools.network.get_nornir", side_effect=Exception("Inventory error")):
            result = get_device_platform.invoke({"device": "R1"})

            assert "Error getting device platform" in result
            assert "Inventory error" in result
