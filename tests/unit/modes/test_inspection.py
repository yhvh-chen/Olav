"""Unit tests for Inspection Mode.

Tests cover:
- InspectionModeController initialization and configuration
- YAML config loading and parsing
- Device resolution from NetBox
- Check execution with thresholds
- Result aggregation
- Threshold evaluation
- run_inspection() convenience function
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import yaml

from olav.modes.inspection.controller import (
    InspectionModeController,
    InspectionConfig,
    InspectionResult,
    CheckConfig,
    CheckResult,
    ThresholdConfig,
    DeviceFilter,
    run_inspection,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_yaml_config():
    """Sample YAML config content."""
    return {
        "name": "Test Inspection",
        "description": "Test inspection for unit tests",
        "devices": {
            "explicit_devices": ["R1", "R2", "R3"],
        },
        "checks": [
            {
                "name": "interface_status",
                "description": "Check interface status",
                "tool": "suzieq_query",
                "enabled": True,
                "parameters": {
                    "table": "interfaces",
                    "view": "latest",
                },
            },
            {
                "name": "bgp_state",
                "description": "Check BGP session state",
                "tool": "suzieq_query",
                "enabled": True,
                "parameters": {
                    "table": "bgp",
                    "view": "latest",
                },
                "threshold": {
                    "field": "state",
                    "operator": "==",
                    "value": "Established",
                    "severity": "critical",
                    "message": "BGP session {device} not established",
                },
            },
        ],
    }


@pytest.fixture
def temp_config_file(sample_yaml_config):
    """Create a temporary YAML config file."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8"
    ) as f:
        yaml.dump(sample_yaml_config, f)
        return Path(f.name)


@pytest.fixture
def controller():
    """Create InspectionModeController instance."""
    return InspectionModeController(max_parallel_devices=5, timeout_seconds=60)


# =============================================================================
# InspectionConfig Model Tests
# =============================================================================


class TestInspectionConfig:
    """Tests for InspectionConfig Pydantic model."""
    
    def test_minimal_config(self):
        """Minimal config with just name."""
        config = InspectionConfig(name="test")
        assert config.name == "test"
        assert config.description == ""
        assert config.checks == []
        assert config.schedule is None
    
    def test_full_config(self):
        """Full config with all fields."""
        config = InspectionConfig(
            name="full test",
            description="A full test config",
            devices=DeviceFilter(explicit_devices=["R1", "R2"]),
            checks=[
                CheckConfig(
                    name="test_check",
                    tool="suzieq_query",
                    parameters={"table": "interfaces"},
                ),
            ],
            schedule="0 0 * * *",
            timeout_seconds=600,
        )
        assert config.name == "full test"
        assert len(config.devices.explicit_devices) == 2
        assert len(config.checks) == 1
        assert config.schedule == "0 0 * * *"
        assert config.timeout_seconds == 600


class TestCheckConfig:
    """Tests for CheckConfig Pydantic model."""
    
    def test_minimal_check(self):
        """Minimal check config."""
        check = CheckConfig(name="test", tool="suzieq_query")
        assert check.name == "test"
        assert check.tool == "suzieq_query"
        assert check.enabled is True
        assert check.parameters == {}
        assert check.threshold is None
    
    def test_check_with_threshold(self):
        """Check config with threshold."""
        check = CheckConfig(
            name="bgp_check",
            tool="suzieq_query",
            parameters={"table": "bgp"},
            threshold=ThresholdConfig(
                field="state",
                operator="==",
                value="Established",
                severity="critical",
            ),
        )
        assert check.threshold is not None
        assert check.threshold.field == "state"
        assert check.threshold.severity == "critical"
    
    def test_disabled_check(self):
        """Check can be disabled."""
        check = CheckConfig(name="disabled", tool="suzieq_query", enabled=False)
        assert check.enabled is False


class TestThresholdConfig:
    """Tests for ThresholdConfig Pydantic model."""
    
    def test_default_values(self):
        """Default threshold config values."""
        threshold = ThresholdConfig(field="count", value=10)
        assert threshold.field == "count"
        assert threshold.operator == ">="
        assert threshold.value == 10
        assert threshold.severity == "warning"
        assert threshold.message == ""
    
    def test_all_operators(self):
        """All operators are valid."""
        for op in [">=", "<=", ">", "<", "==", "!="]:
            threshold = ThresholdConfig(field="test", operator=op, value=1)
            assert threshold.operator == op
    
    def test_all_severities(self):
        """All severities are valid."""
        for sev in ["critical", "warning", "info"]:
            threshold = ThresholdConfig(field="test", value=1, severity=sev)
            assert threshold.severity == sev


class TestDeviceFilter:
    """Tests for DeviceFilter Pydantic model."""
    
    def test_empty_filter(self):
        """Empty filter."""
        df = DeviceFilter()
        assert df.netbox_filter == {}
        assert df.explicit_devices == []
    
    def test_explicit_devices(self):
        """Explicit devices list."""
        df = DeviceFilter(explicit_devices=["R1", "R2"])
        assert df.explicit_devices == ["R1", "R2"]
    
    def test_netbox_filter(self):
        """NetBox filter dict."""
        df = DeviceFilter(netbox_filter={"tag": "core", "site": "dc1"})
        assert df.netbox_filter == {"tag": "core", "site": "dc1"}


# =============================================================================
# CheckResult Model Tests
# =============================================================================


class TestCheckResult:
    """Tests for CheckResult dataclass."""
    
    def test_minimal_result(self):
        """Minimal check result."""
        result = CheckResult(
            device="R1",
            check_name="test",
            success=True,
        )
        assert result.device == "R1"
        assert result.check_name == "test"
        assert result.success is True
        assert result.threshold_violated is False
        assert result.error is None
    
    def test_failed_result_with_error(self):
        """Failed result with error message."""
        result = CheckResult(
            device="R1",
            check_name="test",
            success=False,
            error="Connection timeout",
            duration_ms=5000.0,
        )
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.duration_ms == 5000.0
    
    def test_threshold_violation(self):
        """Result with threshold violation."""
        result = CheckResult(
            device="R1",
            check_name="bgp_check",
            success=False,
            actual_value="Idle",
            threshold_violated=True,
            severity="critical",
            message="BGP not established",
        )
        assert result.threshold_violated is True
        assert result.severity == "critical"
        assert "not established" in result.message


# =============================================================================
# InspectionResult Model Tests
# =============================================================================


class TestInspectionResult:
    """Tests for InspectionResult dataclass."""
    
    def test_minimal_result(self):
        """Minimal inspection result."""
        result = InspectionResult(
            config_name="test",
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:00:30",
        )
        assert result.config_name == "test"
        assert result.total_devices == 0
        assert result.total_checks == 0
    
    def test_duration_calculation(self):
        """Duration is calculated correctly."""
        result = InspectionResult(
            config_name="test",
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:01:00",
        )
        assert result.duration_seconds == 60.0
    
    def test_has_critical(self):
        """has_critical property works."""
        result = InspectionResult(
            config_name="test",
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:00:30",
            critical_violations=[
                CheckResult(device="R1", check_name="bgp", success=False)
            ],
        )
        assert result.has_critical is True
        
        result2 = InspectionResult(
            config_name="test",
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:00:30",
        )
        assert result2.has_critical is False
    
    def test_to_markdown(self):
        """to_markdown() generates valid markdown."""
        result = InspectionResult(
            config_name="Daily Core Check",
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:01:00",
            total_devices=10,
            devices_passed=9,
            devices_failed=1,
            total_checks=30,
            checks_passed=28,
            checks_failed=2,
            critical_violations=[
                CheckResult(
                    device="R1",
                    check_name="bgp_check",
                    success=False,
                    message="BGP down",
                ),
            ],
            warning_violations=[
                CheckResult(
                    device="R2",
                    check_name="interface_errors",
                    success=False,
                    message="High error count",
                ),
            ],
        )
        
        md = result.to_markdown()
        
        assert "# 📋 Inspection Report" in md
        assert "Daily Core Check" in md
        assert "60.0s" in md
        assert "9/10" in md  # devices
        assert "28/30" in md  # checks
        assert "🔴 Critical Violations" in md
        assert "R1" in md
        assert "🟡 Warnings" in md
        assert "R2" in md


# =============================================================================
# InspectionModeController Tests
# =============================================================================


class TestInspectionModeController:
    """Tests for InspectionModeController."""
    
    def test_initialization(self, controller):
        """Controller initializes with correct parameters."""
        assert controller.max_parallel_devices == 5
        assert controller.timeout_seconds == 60
    
    def test_default_initialization(self):
        """Default initialization values."""
        ctrl = InspectionModeController()
        assert ctrl.max_parallel_devices == 10
        assert ctrl.timeout_seconds == 300
    
    def test_load_config_file_not_found(self, controller):
        """load_config raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            controller.load_config("/nonexistent/path.yaml")
    
    def test_load_config_empty_file(self, controller):
        """load_config raises ValueError for empty file."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write("")
            path = Path(f.name)
        
        with pytest.raises(ValueError, match="Empty config"):
            controller.load_config(path)
    
    def test_load_config_valid(self, controller, temp_config_file):
        """load_config parses valid YAML correctly."""
        config = controller.load_config(temp_config_file)
        
        assert config.name == "Test Inspection"
        assert len(config.devices.explicit_devices) == 3
        assert len(config.checks) == 2
        assert config.checks[0].name == "interface_status"
        assert config.checks[1].threshold is not None
    
    def test_load_config_with_threshold(self, controller, temp_config_file):
        """load_config parses threshold correctly."""
        config = controller.load_config(temp_config_file)
        
        bgp_check = config.checks[1]
        assert bgp_check.threshold is not None
        assert bgp_check.threshold.field == "state"
        assert bgp_check.threshold.operator == "=="
        assert bgp_check.threshold.value == "Established"


class TestDeviceResolution:
    """Tests for device resolution."""
    
    @pytest.mark.asyncio
    async def test_resolve_explicit_devices(self, controller):
        """Explicit devices are returned as-is."""
        df = DeviceFilter(explicit_devices=["R1", "R2", "R3"])
        devices = await controller.resolve_devices(df)
        assert devices == ["R1", "R2", "R3"]
    
    @pytest.mark.asyncio
    async def test_resolve_empty_filter(self, controller):
        """Empty filter returns empty list."""
        df = DeviceFilter()
        devices = await controller.resolve_devices(df)
        assert devices == []
    
    @pytest.mark.asyncio
    async def test_resolve_netbox_filter(self, controller):
        """NetBox filter queries NetBox API."""
        df = DeviceFilter(netbox_filter={"tag": "core"})
        
        with patch('olav.tools.netbox_tool.NetBoxAPITool') as MockNetBox:
            mock_netbox = MagicMock()
            mock_result = MagicMock()
            mock_result.error = None
            mock_result.data = [
                {"name": "core-rtr-1"},
                {"name": "core-rtr-2"},
            ]
            mock_netbox.execute = AsyncMock(return_value=mock_result)
            MockNetBox.return_value = mock_netbox
            
            devices = await controller.resolve_devices(df)
            
            assert devices == ["core-rtr-1", "core-rtr-2"]


class TestThresholdEvaluation:
    """Tests for threshold evaluation logic."""
    
    def test_greater_than_or_equal(self, controller):
        """'>=' operator works correctly."""
        assert controller._evaluate_threshold(10, ">=", 5) is True
        assert controller._evaluate_threshold(5, ">=", 5) is True
        assert controller._evaluate_threshold(4, ">=", 5) is False
    
    def test_less_than_or_equal(self, controller):
        """'<=' operator works correctly."""
        assert controller._evaluate_threshold(5, "<=", 10) is True
        assert controller._evaluate_threshold(5, "<=", 5) is True
        assert controller._evaluate_threshold(6, "<=", 5) is False
    
    def test_greater_than(self, controller):
        """'>' operator works correctly."""
        assert controller._evaluate_threshold(10, ">", 5) is True
        assert controller._evaluate_threshold(5, ">", 5) is False
    
    def test_less_than(self, controller):
        """'<' operator works correctly."""
        assert controller._evaluate_threshold(4, "<", 5) is True
        assert controller._evaluate_threshold(5, "<", 5) is False
    
    def test_equals(self, controller):
        """'==' operator works correctly."""
        assert controller._evaluate_threshold("Established", "==", "Established") is True
        assert controller._evaluate_threshold("Idle", "==", "Established") is False
        assert controller._evaluate_threshold(10, "==", 10) is True
    
    def test_not_equals(self, controller):
        """'!=' operator works correctly."""
        assert controller._evaluate_threshold("Idle", "!=", "Established") is True
        assert controller._evaluate_threshold("Established", "!=", "Established") is False
    
    def test_unknown_operator(self, controller):
        """Unknown operator returns True (pass)."""
        assert controller._evaluate_threshold(10, "??", 5) is True
    
    def test_comparison_error_returns_false(self, controller):
        """Comparison error returns False."""
        # Comparing incompatible types
        assert controller._evaluate_threshold("string", ">=", 5) is False


class TestCheckExecution:
    """Tests for check execution."""
    
    @pytest.mark.asyncio
    async def test_execute_check_unknown_tool(self, controller):
        """Unknown tool returns error result."""
        check = CheckConfig(
            name="unknown_check",
            tool="unknown_tool",
        )
        
        result = await controller.execute_check("R1", check)
        
        assert result.success is False
        assert "Unknown tool" in result.error
        assert result.device == "R1"
        assert result.check_name == "unknown_check"
    
    @pytest.mark.asyncio
    async def test_execute_check_success(self, controller):
        """Successful check execution."""
        check = CheckConfig(
            name="interface_check",
            tool="suzieq_query",
            parameters={"table": "interfaces"},
        )
        
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = [{"interface": "eth0", "state": "up"}]
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await controller.execute_check("R1", check)
            
            assert result.success is True
            assert result.device == "R1"
            assert result.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_execute_check_with_threshold_violation(self, controller):
        """Check with threshold violation."""
        check = CheckConfig(
            name="bgp_check",
            tool="suzieq_query",
            parameters={"table": "bgp"},
            threshold=ThresholdConfig(
                field="state",
                operator="==",
                value="Established",
                severity="critical",
                message="BGP {device} state is {actual}, expected {value}",
            ),
        )
        
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = {"state": "Idle"}  # Wrong state
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await controller.execute_check("R1", check)
            
            assert result.success is False
            assert result.threshold_violated is True
            assert result.severity == "critical"
            assert "Idle" in result.message


class TestFullInspectionRun:
    """Tests for full inspection runs."""
    
    @pytest.mark.asyncio
    async def test_run_no_devices(self, controller, sample_yaml_config):
        """Run with no devices returns empty result."""
        # Config with empty devices
        sample_yaml_config["devices"] = {"explicit_devices": []}
        
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            yaml.dump(sample_yaml_config, f)
            config_path = Path(f.name)
        
        result = await controller.run(config_path)
        
        assert result.total_devices == 0
        assert result.total_checks == 0
    
    @pytest.mark.asyncio
    async def test_run_with_devices(self, controller, temp_config_file):
        """Run with devices executes checks."""
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = [{"interface": "eth0", "state": "up"}]
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await controller.run(temp_config_file)
            
            assert result.total_devices == 3  # R1, R2, R3
            assert result.total_checks > 0
            assert result.config_name == "Test Inspection"
    
    @pytest.mark.asyncio
    async def test_run_with_debug(self, temp_config_file):
        """Run with debug context captures state."""
        from olav.modes.shared.debug import DebugContext
        
        controller = InspectionModeController()
        
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            async with DebugContext(enabled=True) as debug_ctx:
                result = await controller.run(temp_config_file, debug_ctx)
                
                assert result.debug_output is not None


# =============================================================================
# run_inspection() Function Tests
# =============================================================================


class TestRunInspection:
    """Tests for run_inspection() convenience function."""
    
    @pytest.mark.asyncio
    async def test_basic_call(self, temp_config_file):
        """run_inspection() works with minimal args."""
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await run_inspection(temp_config_file)
            
            assert isinstance(result, InspectionResult)
            assert result.config_name == "Test Inspection"
    
    @pytest.mark.asyncio
    async def test_with_debug_enabled(self, temp_config_file):
        """run_inspection() works with debug=True."""
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await run_inspection(temp_config_file, debug=True)
            
            assert isinstance(result, InspectionResult)
    
    @pytest.mark.asyncio
    async def test_with_max_parallel(self, temp_config_file):
        """run_inspection() respects max_parallel."""
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            # Should work with custom max_parallel
            result = await run_inspection(
                temp_config_file,
                max_parallel=2,
            )
            
            assert isinstance(result, InspectionResult)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_check_execution_exception(self, controller):
        """Check execution handles exceptions gracefully."""
        check = CheckConfig(
            name="failing_check",
            tool="suzieq_query",
            parameters={"table": "interfaces"},
        )
        
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_tool.execute = AsyncMock(side_effect=Exception("Connection failed"))
            MockTool.return_value = mock_tool
            
            result = await controller.execute_check("R1", check)
            
            assert result.success is False
            assert "Connection failed" in result.error
    
    @pytest.mark.asyncio
    async def test_disabled_checks_skipped(self, controller):
        """Disabled checks are not executed."""
        yaml_content = {
            "name": "Test",
            "devices": {"explicit_devices": ["R1"]},
            "checks": [
                {
                    "name": "enabled_check",
                    "tool": "suzieq_query",
                    "enabled": True,
                },
                {
                    "name": "disabled_check",
                    "tool": "suzieq_query",
                    "enabled": False,
                },
            ],
        }
        
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            yaml.dump(yaml_content, f)
            config_path = Path(f.name)
        
        with patch('olav.tools.suzieq_tool.SuzieQTool') as MockTool:
            mock_tool = MagicMock()
            mock_result = MagicMock()
            mock_result.data = []
            mock_tool.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool
            
            result = await controller.run(config_path)
            
            # Only 1 enabled check x 1 device = 1 total check
            assert result.total_checks == 1
    
    def test_threshold_with_list_result(self, controller):
        """Threshold on list result uses length."""
        # Simulate list result - threshold checks list length
        check = CheckConfig(
            name="count_check",
            tool="suzieq_query",
            threshold=ThresholdConfig(
                field="count",
                operator=">=",
                value=3,
                severity="warning",
            ),
        )
        
        # This tests the _evaluate_threshold internal logic
        # When result is a list, actual_value becomes len(result)
        list_result = [1, 2, 3, 4, 5]
        assert controller._evaluate_threshold(len(list_result), ">=", 3) is True
