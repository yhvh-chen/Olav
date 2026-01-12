"""
Unit tests for report_formatter module.

Tests for Markdown report generation based on skill configuration.
"""

from unittest.mock import patch

import pytest

from olav.tools.report_formatter import (
    LANG_STRINGS,
    _format_details,
    _format_recommendations,
    _format_summary,
    _resolve_language,
    format_inspection_report,
    format_json_report,
    format_report,
    format_table_report,
)


# =============================================================================
# Test _resolve_language
# =============================================================================


class TestResolveLanguage:
    """Tests for _resolve_language function."""

    def test_resolve_en_us(self):
        """Test resolving en-US language."""
        result = _resolve_language("en-US")

        assert result == "en-US"

    def test_resolve_zh_cn(self):
        """Test resolving zh-CN language."""
        result = _resolve_language("zh-CN")

        assert result == "zh-CN"

    def test_resolve_auto_defaults_to_en(self):
        """Test that 'auto' defaults to en-US."""
        result = _resolve_language("auto")

        assert result == "en-US"


# =============================================================================
# Test _format_summary
# =============================================================================


class TestFormatSummary:
    """Tests for _format_summary function."""

    def test_format_summary_all_success(self):
        """Test summary with all successful results."""
        results = {
            "R1": [{"success": True}, {"success": True}],
            "R2": [{"success": True}],
        }

        output = _format_summary(results, LANG_STRINGS["en-US"])

        assert "## Summary" in output
        assert "R1" in output
        assert "R2" in output
        assert "✅" in output
        assert "**Overall Status**: ✅" in output

    def test_format_summary_with_errors(self):
        """Test summary with some errors."""
        results = {
            "R1": [{"success": True}, {"success": False}],
            "R2": [{"success": True}],
        }

        output = _format_summary(results, LANG_STRINGS["en-US"])

        assert "⚠️" in output
        assert "**Overall Status**: ⚠️" in output

    def test_format_summary_all_failures(self):
        """Test summary with all failures."""
        results = {
            "R1": [{"success": False}, {"success": False}],
        }

        output = _format_summary(results, LANG_STRINGS["en-US"])

        assert "❌" in output
        assert "**Overall Status**: ❌" in output

    def test_format_summary_empty_results(self):
        """Test summary with no results."""
        results = {}

        output = _format_summary(results, LANG_STRINGS["en-US"])

        assert "**Total Commands**: 0" in output

    def test_format_summary_counts(self):
        """Test that summary counts are correct."""
        results = {
            "R1": [{"success": True}, {"success": True}, {"success": False}],
        }

        output = _format_summary(results, LANG_STRINGS["en-US"])

        assert "2/3" in output
        assert "**Successful**: 2" in output
        assert "**Failed**: 1" in output


# =============================================================================
# Test _format_details
# =============================================================================


class TestFormatDetails:
    """Tests for _format_details function."""

    def test_format_details_successful_commands(self):
        """Test details with successful commands."""
        results = {
            "R1": [
                {"command": "show version", "success": True, "output": "Version 1.0"},
            ],
        }

        output = _format_details(results, LANG_STRINGS["en-US"])

        assert "## Details" in output
        assert "### R1" in output
        assert "show version" in output
        assert "✅" in output
        assert "Version 1.0" in output

    def test_format_details_failed_commands(self):
        """Test details with failed commands."""
        results = {
            "R1": [
                {"command": "show run", "success": False, "error": "Permission denied"},
            ],
        }

        output = _format_details(results, LANG_STRINGS["en-US"])

        assert "show run" in output
        assert "❌" in output
        assert "Permission denied" in output

    def test_format_details_truncates_long_output(self):
        """Test that long output is truncated."""
        long_output = "x" * 1500
        results = {
            "R1": [
                {"command": "show log", "success": True, "output": long_output},
            ],
        }

        output = _format_details(results, LANG_STRINGS["en-US"])

        assert "(truncated)" in output
        assert len(output) < len(long_output)

    def test_format_details_unknown_command(self):
        """Test handling of missing command field."""
        results = {
            "R1": [
                {"success": True, "output": "Output"},
            ],
        }

        output = _format_details(results, LANG_STRINGS["en-US"])

        assert "unknown" in output.lower()

    def test_format_details_multiple_devices(self):
        """Test details with multiple devices."""
        results = {
            "R1": [{"command": "show ver", "success": True, "output": "V1"}],
            "R2": [{"command": "show ver", "success": True, "output": "V2"}],
        }

        output = _format_details(results, LANG_STRINGS["en-US"])

        assert "### R1" in output
        assert "### R2" in output


# =============================================================================
# Test _format_recommendations
# =============================================================================


class TestFormatRecommendations:
    """Tests for _format_recommendations function."""

    def test_format_recommendations_no_issues(self):
        """Test recommendations when all commands succeed."""
        results = {
            "R1": [{"success": True}, {"success": True}],
        }

        output = _format_recommendations(results, LANG_STRINGS["en-US"], "en-US")

        assert "## Recommendations" in output
        assert "No issues found" in output
        assert "functioning normally" in output

    def test_format_recommendations_with_issues(self):
        """Test recommendations with failed commands."""
        results = {
            "R1": [
                {"success": False, "command": "show run", "error": "Timeout"},
            ],
        }

        output = _format_recommendations(results, LANG_STRINGS["en-US"], "en-US")

        assert "Issues Found: 1" in output
        assert "R1: show run failed - Timeout" in output
        assert "Suggested Actions" in output

    def test_format_recommendations_multiple_issues(self):
        """Test recommendations with multiple issues."""
        results = {
            "R1": [
                {"success": False, "command": "cmd1", "error": "err1"},
                {"success": False, "command": "cmd2", "error": "err2"},
            ],
        }

        output = _format_recommendations(results, LANG_STRINGS["en-US"], "en-US")

        assert "Issues Found: 2" in output
        assert "1. R1: cmd1 failed - err1" in output
        assert "2. R1: cmd2 failed - err2" in output

    def test_format_recommendations_chinese(self):
        """Test recommendations in Chinese."""
        results = {"R1": [{"success": True}]}

        output = _format_recommendations(results, LANG_STRINGS["zh-CN"], "zh-CN")

        assert "未发现问题" in output


# =============================================================================
# Test format_inspection_report
# =============================================================================


class TestFormatInspectionReport:
    """Tests for format_inspection_report function."""

    def test_format_report_default_config(self):
        """Test report with default configuration."""
        results = {"R1": [{"success": True}]}
        skill_config = {}

        with patch("olav.tools.report_formatter.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2025-01-11 12:00:00"
            mock_datetime.now.return_value.isoformat.return_value = "2025-01-11T12:00:00"

            output = format_inspection_report(results, skill_config)

            assert "# Inspection Report" in output
            assert "**Inspection Time**: 2025-01-11 12:00:00" in output
            assert "**Type**: Network Inspection" in output
            assert "**Total Devices**: 1" in output

    def test_format_report_chinese_language(self):
        """Test report in Chinese."""
        results = {"R1": [{"success": True}]}
        skill_config = {"output": {"language": "zh-CN"}}

        output = format_inspection_report(results, skill_config)

        assert "巡检报告" in output
        assert "设备总数" in output

    def test_format_report_custom_sections(self):
        """Test report with custom sections."""
        results = {"R1": [{"success": True}]}
        skill_config = {"output": {"sections": ["summary"]}}

        output = format_inspection_report(results, skill_config)

        assert "## Summary" in output
        assert "## Details" not in output

    def test_format_report_all_sections(self):
        """Test report with all sections."""
        results = {
            "R1": [
                {"success": True, "command": "show ver", "output": "V1"},
                {"success": False, "command": "show run", "error": "Err"},
            ],
        }
        skill_config = {"output": {"sections": ["summary", "details", "recommendations"]}}

        output = format_inspection_report(results, skill_config)

        assert "## Summary" in output
        assert "## Details" in output
        assert "## Recommendations" in output

    def test_format_report_custom_inspection_type(self):
        """Test report with custom inspection type."""
        results = {"R1": [{"success": True}]}
        skill_config = {}

        output = format_inspection_report(results, skill_config, "L1-L4 Inspection")

        assert "**Type**: L1-L4 Inspection" in output


# =============================================================================
# Test format_json_report
# =============================================================================


class TestFormatJsonReport:
    """Tests for format_json_report function."""

    def test_format_json_report_structure(self):
        """Test JSON report has correct structure."""
        results = {
            "R1": [
                {"success": True, "command": "show ver"},
                {"success": False, "command": "show run"},
            ],
        }

        with patch("olav.tools.report_formatter.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-01-11T12:00:00"

            output = format_json_report(results, {})

            import json

            data = json.loads(output)

            assert "timestamp" in data
            assert data["total_devices"] == 1
            assert "R1" in data["devices"]
            assert data["devices"]["R1"]["total_commands"] == 2
            assert data["devices"]["R1"]["successful"] == 1
            assert data["devices"]["R1"]["failed"] == 1

    def test_format_json_report_empty_results(self):
        """Test JSON report with no results."""
        results = {}

        output = format_json_report(results, {})

        import json

        data = json.loads(output)

        assert data["total_devices"] == 0
        assert data["devices"] == {}


# =============================================================================
# Test format_table_report
# =============================================================================


class TestFormatTableReport:
    """Tests for format_table_report function."""

    def test_format_table_english(self):
        """Test table format in English."""
        results = {
            "R1": [
                {"success": True},
                {"success": True},
                {"success": False},
            ],
        }

        output = format_table_report(results, {})

        assert "| Device | Status |" in output
        assert "| R1 | ⚠️ |" in output
        assert "| 3 | 2 | 1 |" in output

    def test_format_table_chinese(self):
        """Test table format in Chinese."""
        results = {"R1": [{"success": True}]}

        skill_config = {"output": {"language": "zh-CN"}}
        output = format_table_report(results, skill_config)

        assert "| 设备 |" in output or "| Device |" in output

    def test_format_table_all_success(self):
        """Test table with all successes."""
        results = {"R1": [{"success": True}]}

        output = format_table_report(results, {})

        assert "✅" in output

    def test_format_table_all_failures(self):
        """Test table with all failures."""
        results = {"R1": [{"success": False}]}

        output = format_table_report(results, {})

        assert "❌" in output


# =============================================================================
# Test format_report (main entry point)
# =============================================================================


class TestFormatReport:
    """Tests for format_report main entry point."""

    def test_format_report_markdown_default(self):
        """Test format_report defaults to markdown."""
        results = {"R1": [{"success": True}]}
        skill_config = {}

        output = format_report(results, skill_config)

        assert "# Inspection Report" in output

    def test_format_report_json_format(self):
        """Test format_report with JSON format."""
        results = {"R1": [{"success": True}]}
        skill_config = {"output": {"format": "json"}}

        output = format_report(results, skill_config)

        import json

        data = json.loads(output)
        assert "timestamp" in data

    def test_format_report_table_format(self):
        """Test format_report with table format."""
        results = {"R1": [{"success": True}]}
        skill_config = {"output": {"format": "table"}}

        output = format_report(results, skill_config)

        assert "| Device |" in output or "| 设备 |" in output

    def test_format_report_custom_inspection_type(self):
        """Test format_report with custom type."""
        results = {"R1": [{"success": True}]}
        skill_config = {}

        output = format_report(results, skill_config, "Health Check")

        assert "Health Check" in output
