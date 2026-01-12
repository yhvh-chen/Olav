"""Unit tests for inspection_tools module.

Tests for Phase 5 Inspection Tools - device inspection workflows.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from olav.tools.inspection_tools import (
    InspectionReport,
    InspectionResult,
    InspectionScope,
    generate_report,
    nornir_bulk_execute,
    parse_inspection_scope,
    parse_skill_frontmatter,
)


# =============================================================================
# Test InspectionScope data model
# =============================================================================


class TestInspectionScope:
    """Tests for InspectionScope data model."""

    def test_inspection_scope_creation(self):
        """Test creating InspectionScope."""
        scope = InspectionScope(
            devices=["R1", "R2"],
            filters={"role": "core"},
            description="Core routers"
        )

        assert scope.devices == ["R1", "R2"]
        assert scope.filters == {"role": "core"}
        assert scope.description == "Core routers"

    def test_inspection_scope_default_filters(self):
        """Test InspectionScope with default filters."""
        scope = InspectionScope(
            devices=["R1"],
            description="Single device"
        )

        assert scope.filters == {}


# =============================================================================
# Test InspectionResult data model
# =============================================================================


class TestInspectionResult:
    """Tests for InspectionResult data model."""

    def test_inspection_result_success(self):
        """Test InspectionResult for successful execution."""
        result = InspectionResult(
            device="R1",
            command="show version",
            success=True,
            output="Cisco IOS Software...",
            duration_ms=150
        )

        assert result.device == "R1"
        assert result.command == "show version"
        assert result.success is True
        assert result.error is None

    def test_inspection_result_failure(self):
        """Test InspectionResult for failed execution."""
        result = InspectionResult(
            device="R2",
            command="show run",
            success=False,
            error="Connection timeout"
        )

        assert result.success is False
        assert result.output is None
        assert result.error == "Connection timeout"


# =============================================================================
# Test InspectionReport data model
# =============================================================================


class TestInspectionReport:
    """Tests for InspectionReport data model."""

    def test_inspection_report_creation(self):
        """Test creating InspectionReport."""
        result1 = InspectionResult(
            device="R1",
            command="show version",
            success=True,
            output="Output"
        )

        report = InspectionReport(
            inspection_type="health-check",
            timestamp="2025-01-11 10:00:00",
            devices=["R1", "R2"],
            results=[result1],
            summary={"total": 1, "passed": 1},
            recommendations=["Check CPU usage"]
        )

        assert report.inspection_type == "health-check"
        assert len(report.results) == 1
        assert len(report.recommendations) == 1


# =============================================================================
# Test nornir_bulk_execute
# =============================================================================


class TestNornirBulkExecute:
    """Tests for nornir_bulk_execute function."""

    @patch("olav.tools.inspection_tools.InitNornir")
    def test_execute_all_devices(self, mock_init_nornir):
        """Test executing commands on all devices."""
        # Mock Nornir setup
        mock_nr = Mock()
        mock_host = Mock()
        mock_host.name = "R1"

        mock_result = Mock()
        mock_result.failed = False
        mock_result.result = "Cisco IOS Software..."

        mock_nr.run.return_value = {"R1": mock_result}
        mock_nr.filter.return_value = mock_nr
        mock_init_nornir.return_value = mock_nr

        with patch("olav.tools.inspection_tools.settings") as mock_settings:
            mock_settings.agent_dir = "/test/olav"

            from olav.tools.inspection_tools import nornir_bulk_execute as bulk_exec
            result = bulk_exec.func("all", ["show version"])

        assert "R1" in result
        assert len(result["R1"]) == 1
        assert result["R1"][0]["success"] is True

    @patch("olav.tools.inspection_tools.InitNornir")
    def test_execute_specific_devices(self, mock_init_nornir):
        """Test executing on specific device list."""
        mock_nr = Mock()
        mock_host = Mock()
        mock_host.name = "R1"

        mock_result = Mock()
        mock_result.failed = False
        mock_result.result = "Output"

        # Create a mock that can be used as filter result
        mock_nr_filtered = Mock()
        mock_nr_filtered.run.return_value = {"R1": mock_result}

        # Mock filter to return the filtered nornir
        def filter_side_effect(filter_func):
            # Check if our test device passes the filter
            if filter_func(mock_host):
                return mock_nr_filtered
            return Mock()

        mock_nr.filter.side_effect = filter_side_effect
        mock_init_nornir.return_value = mock_nr

        with patch("olav.tools.inspection_tools.settings") as mock_settings:
            mock_settings.agent_dir = "/test/olav"

            from olav.tools.inspection_tools import nornir_bulk_execute as bulk_exec
            result = bulk_exec.func(["R1"], ["show version"])

        assert "R1" in result

    @patch("olav.tools.inspection_tools.InitNornir")
    def test_execute_with_failure(self, mock_init_nornir):
        """Test execution with failed device."""
        mock_nr = Mock()
        mock_host = Mock()
        mock_host.name = "R1"

        mock_result = Mock()
        mock_result.failed = True
        mock_result.exception = Exception("Connection refused")

        mock_nr_filtered = Mock()
        mock_nr_filtered.run.return_value = {"R1": mock_result}

        def filter_side_effect(filter_func):
            if filter_func(mock_host):
                return mock_nr_filtered
            return Mock()

        mock_nr.filter.side_effect = filter_side_effect
        mock_init_nornir.return_value = mock_nr

        with patch("olav.tools.inspection_tools.settings") as mock_settings:
            mock_settings.agent_dir = "/test/olav"

            from olav.tools.inspection_tools import nornir_bulk_execute as bulk_exec
            result = bulk_exec.func(["R1"], ["show version"])

        assert result["R1"][0]["success"] is False
        assert "Connection refused" in result["R1"][0]["error"]

    @patch("olav.tools.inspection_tools.InitNornir")
    def test_execute_handles_exception(self, mock_init_nornir):
        """Test that InitNornir exceptions are handled."""
        mock_init_nornir.side_effect = Exception("Config file not found")

        from olav.tools.inspection_tools import nornir_bulk_execute as bulk_exec
        result = bulk_exec.func("all", ["show version"])

        assert "error" in result
        # result["error"] is a list of error strings
        assert any("Bulk execution failed" in err for err in result["error"])


# =============================================================================
# Test parse_inspection_scope
# =============================================================================


class TestParseInspectionScope:
    """Tests for parse_inspection_scope function."""

    def test_parse_scope_all(self):
        """Test parsing 'all' scope."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("all")

        assert result["devices"] == ["all"]
        assert result["description"] == "All devices"
        assert result["filters"] == {}

    def test_parse_scope_comma_separated(self):
        """Test parsing comma-separated device names."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("R1, R2, R5")

        assert result["devices"] == ["R1", "R2", "R5"]
        assert "3 devices" in result["description"]

    def test_parse_scope_range(self):
        """Test parsing device range."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("R1-R5")

        assert result["devices"] == ["R1", "R2", "R3", "R4", "R5"]
        assert "5 devices" in result["description"]

    def test_parse_scope_range_different_prefixes(self):
        """Test range with different prefixes (should not match)."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("R1-S5")

        # Different prefixes, should not parse as range
        assert result["devices"] == ["R1-S5"]

    def test_parse_scope_role_filter(self):
        """Test parsing role-based filter."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("all core routers")

        assert result["devices"] == ["all"]
        assert result["filters"]["role"] == "core"
        assert "core" in result["description"].lower()

    def test_parse_scope_site_filter(self):
        """Test parsing site attribute filter."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("devices in site:DC1")

        assert result["devices"] == ["all"]
        assert result["filters"]["site"] == "DC1"
        assert "site=DC1" in result["description"]

    def test_parse_scope_tag_filter(self):
        """Test parsing tag attribute filter."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("devices with tag:production")

        assert result["devices"] == ["all"]
        assert result["filters"]["tag"] == "production"

    def test_parse_scope_single_device(self):
        """Test parsing single device name."""
        from olav.tools.inspection_tools import parse_inspection_scope as parse_scope
        result = parse_scope.func("R1")

        assert result["devices"] == ["R1"]
        assert "R1" in result["description"]


# =============================================================================
# Test generate_report
# =============================================================================


class TestGenerateReport:
    """Tests for generate_report function."""

    @patch("olav.tools.inspection_tools.format_report")
    @patch("olav.tools.inspection_tools.get_skill_loader")
    def test_generate_report_no_skill(self, mock_get_loader, mock_format):
        """Test report generation without skill (uses defaults)."""
        mock_loader = Mock()
        mock_loader.load.return_value = None
        mock_get_loader.return_value = mock_loader
        mock_format.return_value = "# Report\n\nContent"

        results = {
            "R1": [{"command": "show version", "success": True, "output": "Output"}]
        }

        from olav.tools.inspection_tools import generate_report as gen_report
        report = gen_report.func(results, skill_id="nonexistent")

        assert report == "# Report\n\nContent"
        mock_format.assert_called_once()

    @patch("olav.tools.inspection_tools.format_report")
    @patch("olav.tools.inspection_tools.get_skill_loader")
    def test_generate_report_with_skill(self, mock_get_loader, mock_format):
        """Test report generation with skill configuration."""
        mock_skill = Mock()
        mock_skill.frontmatter = {
            "output": {
                "format": "markdown",
                "language": "en-US",
                "sections": ["summary", "details"]
            }
        }

        mock_loader = Mock()
        mock_loader.load.return_value = mock_skill
        mock_get_loader.return_value = mock_loader
        mock_format.return_value = "# Custom Report\n\nContent"

        results = {"R1": [{"command": "show version", "success": True, "output": "Output"}]}

        from olav.tools.inspection_tools import generate_report as gen_report
        report = gen_report.func(results, skill_id="custom-skill")

        assert "# Custom Report" in report

    @patch("olav.tools.inspection_tools.format_report")
    @patch("olav.tools.inspection_tools.get_skill_loader")
    def test_generate_report_saves_to_file(self, mock_get_loader, mock_format, tmp_path):
        """Test saving report to file."""
        mock_loader = Mock()
        mock_loader.load.return_value = None
        mock_get_loader.return_value = mock_loader
        mock_format.return_value = "# Report\n\nContent here"

        results = {"R1": [{"command": "show version", "success": True, "output": "Output"}]}
        output_file = tmp_path / "report.md"

        from olav.tools.inspection_tools import generate_report as gen_report
        result = gen_report.func(
            results,
            skill_id="test",
            output_path=str(output_file)
        )

        assert "Report saved to:" in result
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Report" in content

    @patch("olav.tools.inspection_tools.format_report")
    @patch("olav.tools.inspection_tools.get_skill_loader")
    def test_generate_report_creates_directories(self, mock_get_loader, mock_format, tmp_path):
        """Test that parent directories are created."""
        mock_loader = Mock()
        mock_loader.load.return_value = None
        mock_get_loader.return_value = mock_loader
        mock_format.return_value = "Report content"

        results = {"R1": [{"command": "show version", "success": True, "output": "Output"}]}
        output_file = tmp_path / "reports" / "nested" / "report.md"

        from olav.tools.inspection_tools import generate_report as gen_report
        gen_report.func(results, skill_id="test", output_path=str(output_file))

        assert output_file.parent.exists()


# =============================================================================
# Test parse_skill_frontmatter
# =============================================================================


class TestParseSkillFrontmatter:
    """Tests for parse_skill_frontmatter function."""

    def test_parse_no_frontmatter(self, tmp_path):
        """Test parsing file without frontmatter."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("# Skill Title\n\nContent here")

        result = parse_skill_frontmatter(skill_file)

        assert result["frontmatter"] == {}
        assert "Content here" in result["content"]

    def test_parse_with_frontmatter(self, tmp_path):
        """Test parsing file with YAML frontmatter."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text(
            """---
format: markdown
language: en-US
---
# Skill Title

Content here"""
        )

        result = parse_skill_frontmatter(skill_file)

        assert result["frontmatter"]["format"] == "markdown"
        assert result["frontmatter"]["language"] == "en-US"
        assert "# Skill Title" in result["content"]

    def test_parse_frontmatter_key_value(self, tmp_path):
        """Test parsing key-value pairs in frontmatter."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text(
            """---
name: Interface Check
type: inspection
complexity: low
---

Content"""
        )

        result = parse_skill_frontmatter(skill_file)

        assert result["frontmatter"]["name"] == "Interface Check"
        assert result["frontmatter"]["type"] == "inspection"
        assert result["frontmatter"]["complexity"] == "low"

    def test_parse_incomplete_frontmatter(self, tmp_path):
        """Test file with incomplete frontmatter markers."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("---\nname: Test\nContent")

        result = parse_skill_frontmatter(skill_file)

        # Should return content as-is since frontmatter is incomplete
        assert "Content" in result["content"]

    def test_parse_empty_frontmatter(self, tmp_path):
        """Test file with empty frontmatter."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text(
            """---
---
# Skill

Content"""
        )

        result = parse_skill_frontmatter(skill_file)

        assert result["frontmatter"] == {}
        assert "# Skill" in result["content"]
