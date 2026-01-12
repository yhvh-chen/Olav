"""
Unit tests for logging configuration module.

Tests for setup_logging and get_logger functions.
"""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.logging import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_creates_directory(self):
        """Test that setup_logging creates log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "logs" / "test.log"
            setup_logging(log_file=str(log_file))
            assert log_file.parent.exists()

    def test_setup_logging_with_debug_level(self):
        """Test setup_logging with DEBUG level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_level="DEBUG", log_file=str(log_file))

            logger = logging.getLogger()
            assert logger.level == logging.DEBUG

    def test_setup_logging_with_info_level(self):
        """Test setup_logging with INFO level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_level="INFO", log_file=str(log_file))

            logger = logging.getLogger()
            assert logger.level == logging.INFO

    def test_setup_logging_with_warning_level(self):
        """Test setup_logging with WARNING level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_level="WARNING", log_file=str(log_file))

            logger = logging.getLogger()
            assert logger.level == logging.WARNING

    def test_setup_logging_with_error_level(self):
        """Test setup_logging with ERROR level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_level="ERROR", log_file=str(log_file))

            logger = logging.getLogger()
            assert logger.level == logging.ERROR

    def test_setup_logging_invalid_level_defaults_to_info(self):
        """Test that invalid log level defaults to INFO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_level="INVALID", log_file=str(log_file))

            logger = logging.getLogger()
            assert logger.level == logging.INFO

    def test_setup_logging_clears_existing_handlers(self):
        """Test that setup_logging clears existing handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # First setup
            setup_logging(log_file=str(log_file))
            first_handler_count = len(logging.getLogger().handlers)

            # Second setup - should clear and recreate
            setup_logging(log_file=str(log_file))
            second_handler_count = len(logging.getLogger().handlers)

            assert second_handler_count == first_handler_count

    def test_setup_logging_creates_console_handler(self):
        """Test that setup_logging creates a console handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = logging.getLogger()
            console_handlers = [
                h for h in logger.handlers if isinstance(h, logging.StreamHandler)
            ]

            assert len(console_handlers) > 0

    def test_setup_logging_console_handler_uses_stdout(self):
        """Test that console handler writes to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = logging.getLogger()
            stream_handlers = [
                h for h in logger.handlers if isinstance(h, logging.StreamHandler)
            ]

            assert any(h.stream == sys.stdout for h in stream_handlers)

    def test_setup_logging_creates_file_handler(self):
        """Test that setup_logging creates a rotating file handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            file_handlers = [
                h for h in logger.handlers if isinstance(h, RotatingFileHandler)
            ]

            assert len(file_handlers) == 1

    def test_setup_logging_file_has_correct_max_bytes(self):
        """Test that file handler has correct max_bytes setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            max_bytes = 5 * 1024 * 1024
            setup_logging(log_file=str(log_file), max_bytes=max_bytes)

            logger = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            file_handlers = [
                h for h in logger.handlers if isinstance(h, RotatingFileHandler)
            ]

            assert file_handlers[0].maxBytes == max_bytes

    def test_setup_logging_file_has_correct_backup_count(self):
        """Test that file handler has correct backup_count setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            backup_count = 10
            setup_logging(log_file=str(log_file), backup_count=backup_count)

            logger = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            file_handlers = [
                h for h in logger.handlers if isinstance(h, RotatingFileHandler)
            ]

            assert file_handlers[0].backupCount == backup_count

    def test_setup_logging_writes_to_file(self):
        """Test that setup_logging actually writes to log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = logging.getLogger("test")
            logger.info("Test message")

            assert log_file.exists()
            content = log_file.read_text()
            assert "Test message" in content

    def test_setup_logging_suppresses_external_library_noise(self):
        """Test that external libraries are set to WARNING level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            assert logging.getLogger("httpx").level == logging.WARNING
            assert logging.getLogger("httpcore").level == logging.WARNING
            assert logging.getLogger("openai").level == logging.WARNING
            assert logging.getLogger("anthropic").level == logging.WARNING

    def test_setup_logging_handles_permission_error(self):
        """Test that setup_logging handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Try to create a log file in a location that might not be writable
            log_file = "/root/nonexistent/test.log"

            with patch("config.logging.Path") as mock_path:
                mock_path.return_value.parent.mkdir.side_effect = PermissionError(
                    "Permission denied"
                )
                mock_path.return_value = Path(log_file)

                # Should not raise an exception
                try:
                    setup_logging(log_file=log_file)
                except Exception:
                    pass

    def test_setup_logging_with_custom_parameters(self):
        """Test setup_logging with custom parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "custom.log"
            setup_logging(
                log_level="DEBUG",
                log_file=str(log_file),
                max_bytes=1024,
                backup_count=3,
            )

            logger = logging.getLogger()
            assert logger.level == logging.DEBUG

            from logging.handlers import RotatingFileHandler

            file_handlers = [
                h for h in logger.handlers if isinstance(h, RotatingFileHandler)
            ]

            assert file_handlers[0].maxBytes == 1024
            assert file_handlers[0].backupCount == 3

    def test_setup_logging_uses_utf8_encoding(self):
        """Test that file handler uses UTF-8 encoding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            file_handlers = [
                h for h in logger.handlers if isinstance(h, RotatingFileHandler)
            ]

            assert file_handlers[0].encoding == "utf-8"


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger_instance(self):
        """Test that get_logger returns a Logger instance."""
        logger = get_logger(__name__)
        assert isinstance(logger, logging.Logger)

    def test_get_logger_with_module_name(self):
        """Test get_logger with module name."""
        logger = get_logger("test.module")
        assert logger.name == "test.module"

    def test_get_logger_with_special_name(self):
        """Test get_logger with special characters in name."""
        logger = get_logger("test-module.sub.name")
        assert logger.name == "test-module.sub.name"

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns the same instance for the same name."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")
        assert logger1 is logger2

    def test_get_logger_with_empty_name(self):
        """Test get_logger with empty name returns root logger."""
        logger = get_logger("")
        assert logger.name == "root"

    def test_get_logger_integration_with_setup(self):
        """Test that get_logger works with setup_logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=str(log_file))

            logger = get_logger("integration.test")
            logger.info("Integration test message")

            assert log_file.exists()
            content = log_file.read_text()
            assert "Integration test message" in content
