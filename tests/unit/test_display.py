"""
Unit tests for display module.

Tests for CLI display components including banners and UI elements.
"""

from unittest.mock import Mock, patch

import pytest

from olav.cli.display import (
    RICH_AVAILABLE,
    display_banner,
    get_banner,
    load_banner_from_config,
    print_error,
    print_success,
    print_welcome,
)


# =============================================================================
# Test get_banner
# =============================================================================


class TestGetBanner:
    """Tests for get_banner function."""

    def test_get_banner_default(self):
        """Test getting default banner."""
        result = get_banner("default")

        # Returns empty string if config not available
        assert isinstance(result, str)

    def test_get_banner_import_error_fallback(self):
        """Test fallback when import fails."""
        with patch("config.banners.get_banner_text", side_effect=ImportError):
            result = get_banner("test")

            assert result == ""

    def test_get_banner_key_error_fallback(self):
        """Test fallback when banner not found."""
        with patch("config.banners.get_banner_text", side_effect=KeyError):
            result = get_banner("nonexistent")

            assert result == ""


# =============================================================================
# Test load_banner_from_config
# =============================================================================


class TestLoadBannerFromConfig:
    """Tests for load_banner_from_config function."""

    def test_load_banner_file_not_exists(self, tmp_path):
        """Test when settings file doesn't exist."""
        result = load_banner_from_config(str(tmp_path / "nonexistent.json"))

        assert isinstance(result, str)

    def test_load_banner_show_banner_false(self, tmp_path):
        """Test when showBanner is set to False."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"cli": {"showBanner": false}}')

        result = load_banner_from_config(str(settings_file))

        assert result == ""

    def test_load_banner_custom_banner(self, tmp_path):
        """Test loading custom banner name."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"cli": {"showBanner": true, "banner": "custom"}}')

        with patch("olav.cli.display.get_banner", return_value="Custom Banner"):
            result = load_banner_from_config(str(settings_file))

            assert result == "Custom Banner"

    def test_load_banner_invalid_json(self, tmp_path):
        """Test handling of invalid JSON."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("invalid json")

        result = load_banner_from_config(str(settings_file))

        assert isinstance(result, str)

    def test_load_banner_missing_cli_section(self, tmp_path):
        """Test when cli section is missing."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"other": "data"}')

        with patch("olav.cli.display.get_banner", return_value="Default"):
            result = load_banner_from_config(str(settings_file))

            assert result == "Default"


# =============================================================================
# Test display_banner
# =============================================================================


class TestDisplayBanner:
    """Tests for display_banner function."""

    def test_display_banner_empty_text(self):
        """Test displaying empty banner."""
        # Should not raise any error
        display_banner("")

    def test_display_banner_without_rich(self):
        """Test banner display without rich library."""
        with patch("olav.cli.display.RICH_AVAILABLE", False):
            with patch("builtins.print") as mock_print:
                display_banner("Test Banner")

                mock_print.assert_called_once_with("Test Banner")

    def test_display_banner_with_rich(self):
        """Test banner display with rich library."""
        if not RICH_AVAILABLE:
            pytest.skip("Rich not available")

        mock_console = Mock()

        with patch("olav.cli.display.RICH_AVAILABLE", True):
            with patch("olav.cli.display.Console", return_value=mock_console):
                with patch("olav.cli.display.Text") as mock_text:
                    mock_text.from_markup.return_value = Mock()

                    display_banner("Test Banner")

                    mock_text.from_markup.assert_called_once_with("Test Banner")

    def test_display_banner_with_console(self):
        """Test banner display with provided console."""
        if not RICH_AVAILABLE:
            pytest.skip("Rich not available")

        mock_console = Mock()

        with patch("olav.cli.display.RICH_AVAILABLE", True):
            with patch("olav.cli.display.Text") as mock_text:
                mock_text.from_markup.return_value = Mock()

                display_banner("Test Banner", console=mock_console)

                # Should use provided console
                assert mock_console.print.called


# =============================================================================
# Test print_welcome
# =============================================================================


class TestPrintWelcome:
    """Tests for print_welcome function."""

    def test_print_welcome_without_rich(self):
        """Test welcome message without rich."""
        with patch("olav.cli.display.RICH_AVAILABLE", False):
            with patch("olav.cli.display.load_banner_from_config", return_value=""):
                with patch("builtins.print") as mock_print:
                    print_welcome()

                    # Verify welcome message was printed
                    assert any("Welcome to OLAV" in str(call) for call in mock_print.call_args_list)

    def test_print_welcome_with_banner(self):
        """Test welcome message with banner."""
        with patch("olav.cli.display.RICH_AVAILABLE", False):
            with patch("olav.cli.display.load_banner_from_config", return_value="Banner"):
                with patch("olav.cli.display.display_banner") as mock_display:
                    with patch("builtins.print"):
                        print_welcome()

                        mock_display.assert_called_once_with("Banner", None)


# =============================================================================
# Test print_error
# =============================================================================


class TestPrintError:
    """Tests for print_error function."""

    def test_print_error_without_console(self):
        """Test error message without console."""
        with patch("builtins.print") as mock_print:
            print_error("Test error")

            mock_print.assert_called_once_with("Error: Test error")

    def test_print_error_with_console(self):
        """Test error message with console."""
        mock_console = Mock()

        print_error("Test error", console=mock_console)

        mock_console.print.assert_called_once()


# =============================================================================
# Test print_success
# =============================================================================


class TestPrintSuccess:
    """Tests for print_success function."""

    def test_print_success_without_console(self):
        """Test success message without console."""
        with patch("builtins.print") as mock_print:
            print_success("Test success")

            mock_print.assert_called_once_with("✓ Test success")

    def test_print_success_with_console(self):
        """Test success message with console."""
        mock_console = Mock()

        print_success("Test success", console=mock_console)

        mock_console.print.assert_called_once()
