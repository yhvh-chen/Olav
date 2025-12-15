"""
E2E Tests for Inspection Mode - YAML-driven bulk network inspections.

Tests cover:
1. YAML Configuration Loading
2. Device Resolution (NetBox filter, explicit devices)
3. Check Execution with SuzieQ Tool
4. Threshold Evaluation (>=, <=, >, <, ==, !=)
5. Report Generation
6. Debug Mode Integration
7. Parallel Execution
8. Error Handling
"""

import contextlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from olav.modes.inspection.controller import (
    CheckConfig,
    CheckResult,
    DeviceFilter,
    InspectionConfig,
    InspectionModeController,
    InspectionResult,
    ThresholdConfig,
    run_inspection,
)
from olav.modes.shared.debug import DebugContext

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_yaml_content():
    """Sample YAML inspection configuration content."""
    return """
name: BGP Health Check
description: Verify BGP session health across all routers

devices:
  explicit_devices:
    - router-dc1-01
    - router-dc1-02

checks:
  - name: bgp_session_count
    description: Check BGP session count
    tool: suzieq_query
    parameters:
      table: bgp
      columns:
        - hostname
        - peer
        - state
    threshold:
      field: count
      operator: ">="
      value: 1
      severity: critical
      message: "Device {device} has no BGP sessions"

  - name: interface_errors
    description: Check for interface errors
    tool: suzieq_query
    parameters:
      table: interfaces
      columns:
        - hostname
        - ifname
        - errorsIn
    threshold:
      field: errorsIn
      operator: "<="
      value: 100
      severity: warning
      message: "High error count: {actual} > {value}"
"""


@pytest.fixture
def temp_yaml_file(sample_yaml_content):
    """Create a temporary YAML config file."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8"
    ) as f:
        f.write(sample_yaml_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    with contextlib.suppress(Exception):
        os.unlink(temp_path)


@pytest.fixture
def check_config():
    """Sample CheckConfig for testing."""
    return CheckConfig(
        name="bgp_count",
        description="Check BGP sessions",
        tool="suzieq_query",
        parameters={"table": "bgp"},
        threshold=ThresholdConfig(
            field="count",
            operator=">=",
            value=1,
            severity="critical",
        ),
    )


@pytest.fixture
def device_filter_explicit():
    """Device filter with explicit devices."""
    return DeviceFilter(
        explicit_devices=["router-01", "router-02"],
    )


@pytest.fixture
def device_filter_netbox():
    """Device filter with NetBox query."""
    return DeviceFilter(
        netbox_filter={"site": "dc1", "role": "router"},
    )


# =============================================================================
# YAML Configuration Loading Tests
# =============================================================================

class TestYAMLLoading:
    """Test YAML configuration parsing."""

    def test_load_valid_yaml(self, temp_yaml_file):
        """Test loading valid YAML configuration."""
        controller = InspectionModeController()
        config = controller.load_config(temp_yaml_file)

        assert isinstance(config, InspectionConfig)
        assert config.name == "BGP Health Check"
        assert len(config.checks) == 2
        assert config.checks[0].name == "bgp_session_count"
        assert config.checks[0].threshold.operator == ">="

    def test_load_yaml_file_not_found(self):
        """Test error handling for missing file."""
        controller = InspectionModeController()

        with pytest.raises(FileNotFoundError, match="Config not found"):
            controller.load_config("nonexistent.yaml")

    def test_load_yaml_empty_file(self):
        """Test error handling for empty YAML file."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write("")
            temp_path = f.name

        try:
            controller = InspectionModeController()
            with pytest.raises(ValueError, match="Empty config"):
                controller.load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_load_yaml_with_threshold(self, temp_yaml_file):
        """Test threshold parsing from YAML."""
        controller = InspectionModeController()
        config = controller.load_config(temp_yaml_file)

        threshold = config.checks[0].threshold
        assert isinstance(threshold, ThresholdConfig)
        assert threshold.field == "count"
        assert threshold.operator == ">="
        assert threshold.value == 1
        assert threshold.severity == "critical"

    def test_load_yaml_without_threshold(self):
        """Test check without threshold."""
        yaml_content = """
name: Simple Check
checks:
  - name: simple
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()
            config = controller.load_config(temp_path)

            assert config.checks[0].threshold is None
        finally:
            os.unlink(temp_path)


# =============================================================================
# Device Resolution Tests
# =============================================================================

class TestDeviceResolution:
    """Test device filtering and resolution."""

    @pytest.mark.asyncio
    async def test_resolve_explicit_devices(self, device_filter_explicit):
        """Test resolving explicit device list."""
        controller = InspectionModeController()
        devices = await controller.resolve_devices(device_filter_explicit)

        assert devices == ["router-01", "router-02"]

    @pytest.mark.asyncio
    async def test_resolve_empty_filter(self):
        """Test empty filter returns empty list."""
        controller = InspectionModeController()
        empty_filter = DeviceFilter()

        devices = await controller.resolve_devices(empty_filter)
        assert devices == []

    @pytest.mark.asyncio
    async def test_resolve_netbox_filter(self, device_filter_netbox):
        """Test NetBox query resolution."""
        controller = InspectionModeController()

        # Mock NetBox tool
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.data = [
            {"name": "router-dc1-01", "site": "dc1"},
            {"name": "router-dc1-02", "site": "dc1"},
        ]

        with patch("olav.tools.netbox_tool.NetBoxAPITool") as MockNetBox:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=mock_result)
            MockNetBox.return_value = mock_instance

            devices = await controller.resolve_devices(device_filter_netbox)

        assert "router-dc1-01" in devices
        assert "router-dc1-02" in devices

    @pytest.mark.asyncio
    async def test_resolve_netbox_error_handling(self, device_filter_netbox):
        """Test NetBox query error handling."""
        controller = InspectionModeController()

        with patch("olav.tools.netbox_tool.NetBoxAPITool") as MockNetBox:
            MockNetBox.side_effect = Exception("Connection error")

            # Should return empty list on error, not raise
            devices = await controller.resolve_devices(device_filter_netbox)
            assert devices == []

    @pytest.mark.asyncio
    async def test_explicit_takes_priority(self):
        """Test explicit devices take priority over NetBox filter."""
        controller = InspectionModeController()
        filter_with_both = DeviceFilter(
            explicit_devices=["explicit-router"],
            netbox_filter={"site": "dc1"},
        )

        devices = await controller.resolve_devices(filter_with_both)
        assert devices == ["explicit-router"]


# =============================================================================
# Check Execution Tests
# =============================================================================

class TestCheckExecution:
    """Test individual check execution."""

    @pytest.mark.asyncio
    async def test_execute_suzieq_check(self, check_config):
        """Test executing a SuzieQ-based check."""
        controller = InspectionModeController()

        mock_result = MagicMock()
        mock_result.data = [
            {"hostname": "router-01", "peer": "10.0.0.1", "state": "Established"},
        ]
        mock_result.error = None

        with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=mock_result)
            MockSuzieQ.return_value = mock_instance

            result = await controller.execute_check("router-01", check_config)

        assert isinstance(result, CheckResult)
        assert result.check_name == "bgp_count"
        assert result.device == "router-01"

    @pytest.mark.asyncio
    async def test_execute_check_unknown_tool(self):
        """Test handling of unknown tool type."""
        controller = InspectionModeController()
        check = CheckConfig(
            name="unknown_tool_check",
            tool="nonexistent_tool",
            parameters={},
        )

        result = await controller.execute_check("router-01", check)

        assert result.success is False
        assert "Unknown source" in result.error

    @pytest.mark.asyncio
    async def test_execute_check_with_exception(self, check_config):
        """Test handling of execution exception."""
        controller = InspectionModeController()

        with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(side_effect=Exception("Network error"))
            MockSuzieQ.return_value = mock_instance

            result = await controller.execute_check("router-01", check_config)

        assert result.success is False
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_execute_check_records_duration(self, check_config):
        """Test check duration is recorded."""
        controller = InspectionModeController()

        mock_result = MagicMock()
        mock_result.data = [{"count": 5}]
        mock_result.error = None

        with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=mock_result)
            MockSuzieQ.return_value = mock_instance

            result = await controller.execute_check("router-01", check_config)

        assert result.duration_ms >= 0


# =============================================================================
# Threshold Evaluation Tests
# =============================================================================

class TestThresholdEvaluation:
    """Test threshold comparison logic."""

    def test_threshold_gte_pass(self):
        """Test >= threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(10, ">=", 5)
        assert result is True

    def test_threshold_gte_fail(self):
        """Test >= threshold failing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(3, ">=", 5)
        assert result is False

    def test_threshold_gte_equal(self):
        """Test >= threshold with equal values."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(5, ">=", 5)
        assert result is True

    def test_threshold_lte_pass(self):
        """Test <= threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(50, "<=", 100)
        assert result is True

    def test_threshold_lte_fail(self):
        """Test <= threshold failing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(150, "<=", 100)
        assert result is False

    def test_threshold_gt_pass(self):
        """Test > threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(10, ">", 5)
        assert result is True

    def test_threshold_gt_fail_equal(self):
        """Test > threshold fails on equal."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(5, ">", 5)
        assert result is False

    def test_threshold_lt_pass(self):
        """Test < threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(3, "<", 5)
        assert result is True

    def test_threshold_lt_fail(self):
        """Test < threshold failing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(10, "<", 5)
        assert result is False

    def test_threshold_eq_pass(self):
        """Test == threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold("Established", "==", "Established")
        assert result is True

    def test_threshold_eq_fail(self):
        """Test == threshold failing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold("Active", "==", "Established")
        assert result is False

    def test_threshold_neq_pass(self):
        """Test != threshold passing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold("Active", "!=", "Down")
        assert result is True

    def test_threshold_neq_fail(self):
        """Test != threshold failing."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold("Down", "!=", "Down")
        assert result is False

    def test_threshold_unknown_operator(self):
        """Test unknown operator defaults to True."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold(5, "unknown", 10)
        assert result is True

    def test_threshold_type_error(self):
        """Test threshold with incompatible types returns False."""
        controller = InspectionModeController()
        result = controller._evaluate_threshold("string", ">=", 5)
        assert result is False


# =============================================================================
# Full Inspection Workflow Tests
# =============================================================================

class TestInspectionWorkflow:
    """Test complete inspection workflow."""

    @pytest.mark.asyncio
    async def test_run_inspection_full_workflow(self, temp_yaml_file):
        """Test running a complete inspection workflow."""
        controller = InspectionModeController()

        mock_result = MagicMock()
        mock_result.data = [{"hostname": "router-dc1-01", "count": 5}]
        mock_result.error = None

        with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=mock_result)
            MockSuzieQ.return_value = mock_instance

            result = await controller.run(temp_yaml_file)

        assert isinstance(result, InspectionResult)
        assert result.config_name == "BGP Health Check"
        assert result.total_devices == 2  # From sample YAML
        assert len(result.check_results) > 0

    @pytest.mark.asyncio
    async def test_run_inspection_no_devices(self):
        """Test inspection with no matching devices."""
        yaml_content = """
name: Empty Device Test
devices:
  netbox_filter:
    site: nonexistent
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()

            with patch("olav.tools.netbox_tool.NetBoxAPITool") as MockNetBox:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=MagicMock(error=None, data=[]))
                MockNetBox.return_value = mock_instance

                result = await controller.run(temp_path)

            assert result.total_devices == 0
            assert len(result.check_results) == 0
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_run_inspection_with_violations(self):
        """Test inspection detects threshold violations."""
        yaml_content = """
name: Violation Test
devices:
  explicit_devices:
    - router-01
checks:
  - name: error_check
    tool: suzieq_query
    parameters:
      table: interfaces
    threshold:
      field: errorsIn
      operator: "<="
      value: 10
      severity: critical
      message: "High errors: {actual}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()

            # Return high error count to trigger violation
            mock_result = MagicMock()
            mock_result.data = {"errorsIn": 500}  # Above threshold
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            # Should have critical violation
            assert len(result.critical_violations) > 0
            assert result.has_critical is True
        finally:
            os.unlink(temp_path)


# =============================================================================
# Report Generation Tests
# =============================================================================

class TestReportGeneration:
    """Test inspection report generation."""

    def test_generate_markdown_report(self):
        """Test generating Markdown format report."""
        result = InspectionResult(
            config_name="Test Inspection",
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T10:01:00",
            total_devices=3,
            devices_passed=2,
            devices_failed=1,
            total_checks=6,
            checks_passed=5,
            checks_failed=1,
            check_results=[
                CheckResult(
                    device="router-01",
                    check_name="check1",
                    success=True,
                ),
            ],
            critical_violations=[
                CheckResult(
                    device="router-02",
                    check_name="error_check",
                    success=False,
                    threshold_violated=True,
                    severity="critical",
                    message="High error count",
                ),
            ],
        )

        markdown = result.to_markdown()

        assert "# 📋 Inspection Report: Test Inspection" in markdown
        assert "Devices" in markdown
        assert "Critical" in markdown
        assert "router-02" in markdown

    def test_result_duration_calculation(self):
        """Test duration calculation from timestamps."""
        result = InspectionResult(
            config_name="Test",
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T10:00:30",
            total_devices=1,
        )

        assert result.duration_seconds == 30.0

    def test_has_critical_property(self):
        """Test has_critical property."""
        # No violations
        result = InspectionResult(
            config_name="Test",
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T10:00:30",
        )
        assert result.has_critical is False

        # With critical violation
        result_with_critical = InspectionResult(
            config_name="Test",
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T10:00:30",
            critical_violations=[
                CheckResult(
                    device="router-01",
                    check_name="test",
                    success=False,
                    severity="critical",
                ),
            ],
        )
        assert result_with_critical.has_critical is True


# =============================================================================
# Debug Mode Integration Tests
# =============================================================================

class TestDebugIntegration:
    """Test debug mode integration with inspection mode."""

    @pytest.mark.asyncio
    async def test_inspection_with_debug_context(self):
        """Test inspection records debug information when enabled."""
        yaml_content = """
name: Debug Test
devices:
  explicit_devices:
    - router-01
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()
            debug_ctx = DebugContext(enabled=True)

            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                await controller.run(temp_path, debug_context=debug_ctx)

            # Debug context should have recorded graph states
            output = debug_ctx.output
            assert len(output.graph_states) > 0
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_inspection_without_debug(self):
        """Test inspection works correctly without debug context."""
        yaml_content = """
name: No Debug Test
devices:
  explicit_devices:
    - router-01
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()

            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            assert result is not None
            assert isinstance(result, InspectionResult)
            assert result.debug_output is None
        finally:
            os.unlink(temp_path)


# =============================================================================
# Parallel Execution Tests
# =============================================================================

class TestParallelExecution:
    """Test parallel check execution."""

    @pytest.mark.asyncio
    async def test_parallel_device_checks(self):
        """Test checks are executed in parallel across devices."""
        yaml_content = """
name: Parallel Test
devices:
  explicit_devices:
    - router-01
    - router-02
    - router-03
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController(max_parallel_devices=10)

            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            # Should have results for all 3 devices
            assert result.total_devices == 3
            assert len(result.check_results) == 3
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parallel_with_semaphore_limit(self):
        """Test parallel execution respects semaphore limit."""
        yaml_content = """
name: Semaphore Test
devices:
  explicit_devices:
    - router-01
    - router-02
    - router-03
    - router-04
    - router-05
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            # Limit to 2 parallel devices
            controller = InspectionModeController(max_parallel_devices=2)

            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            # Should still complete all devices
            assert result.total_devices == 5
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parallel_execution_with_failures(self):
        """Test parallel execution handles individual failures gracefully."""
        yaml_content = """
name: Mixed Results Test
devices:
  explicit_devices:
    - router-01
    - router-02
    - router-03
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()
            call_count = [0]  # Use list for closure

            async def mock_execute(**kwargs):
                call_count[0] += 1
                if call_count[0] == 2:
                    msg = "Simulated failure"
                    raise Exception(msg)
                return MagicMock(data=[{"count": 5}], error=None)

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = mock_execute
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            # Should complete despite one failure
            assert result.total_devices == 3
            # Should have mix of success and failure
            assert result.devices_failed >= 1
        finally:
            os.unlink(temp_path)


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunction:
    """Test run_inspection convenience function."""

    @pytest.mark.asyncio
    async def test_run_inspection_function(self):
        """Test run_inspection convenience function."""
        yaml_content = """
name: Convenience Test
devices:
  explicit_devices:
    - router-01
checks:
  - name: test_check
    tool: suzieq_query
    parameters:
      table: bgp
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await run_inspection(temp_path)

            assert isinstance(result, InspectionResult)
            assert result.config_name == "Convenience Test"
        finally:
            os.unlink(temp_path)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_threshold_with_zero_value(self):
        """Test threshold evaluation with zero value."""
        controller = InspectionModeController()

        result = controller._evaluate_threshold(0, "==", 0)
        assert result is True

        result = controller._evaluate_threshold(0, ">=", 0)
        assert result is True

    def test_threshold_with_negative_value(self):
        """Test threshold evaluation with negative value."""
        controller = InspectionModeController()

        result = controller._evaluate_threshold(-5, "<", 0)
        assert result is True

    def test_check_config_defaults(self):
        """Test CheckConfig default values."""
        check = CheckConfig(
            name="minimal",
            tool="suzieq_query",
            parameters={},
        )

        assert check.description == ""
        assert check.enabled is True
        assert check.threshold is None

    def test_device_filter_defaults(self):
        """Test DeviceFilter default values."""
        device_filter = DeviceFilter()

        assert device_filter.explicit_devices == []
        assert device_filter.netbox_filter == {}

    def test_inspection_config_defaults(self):
        """Test InspectionConfig default values."""
        config = InspectionConfig(name="Test")

        assert config.description == ""
        assert config.timeout_seconds == 300
        assert config.schedule is None

    @pytest.mark.asyncio
    async def test_disabled_check_skipped(self):
        """Test disabled checks are skipped."""
        yaml_content = """
name: Disabled Check Test
devices:
  explicit_devices:
    - router-01
checks:
  - name: enabled_check
    tool: suzieq_query
    enabled: true
    parameters:
      table: bgp
  - name: disabled_check
    tool: suzieq_query
    enabled: false
    parameters:
      table: interfaces
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            controller = InspectionModeController()

            mock_result = MagicMock()
            mock_result.data = [{"count": 5}]
            mock_result.error = None

            with patch("olav.tools.suzieq_tool.SuzieQTool") as MockSuzieQ:
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value=mock_result)
                MockSuzieQ.return_value = mock_instance

                result = await controller.run(temp_path)

            # Only enabled check should run
            assert result.total_checks == 1
            assert result.check_results[0].check_name == "enabled_check"
        finally:
            os.unlink(temp_path)

