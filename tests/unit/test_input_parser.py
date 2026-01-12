"""
Unit tests for input_parser module.

Tests for parsing user input, file references, shell commands, and multi-line detection.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from olav.cli.input_parser import (
    detect_multiline,
    expand_file_references,
    execute_shell_command,
    parse_input,
    strip_code_blocks,
)


# =============================================================================
# Test expand_file_references
# =============================================================================


class TestExpandFileReferences:
    """Tests for expand_file_references function."""

    def test_expand_existing_file(self, tmp_path):
        """Test expanding a reference to an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("File content here")

        result = expand_file_references("@test.txt", tmp_path)

        assert ".txt" in result or "```" in result
        assert "File content here" in result

    def test_expand_file_with_extension(self, tmp_path):
        """Test that file extension is used in code block."""
        test_file = tmp_path / "config.py"
        test_file.write_text("print('hello')")

        result = expand_file_references("@config.py", tmp_path)

        assert "```" in result
        assert "print('hello')" in result

    def test_expand_nonexistent_file(self, tmp_path):
        """Test that references to nonexistent files are kept."""
        result = expand_file_references("@nonexistent.txt", tmp_path)

        assert result == "@nonexistent.txt"

    def test_expand_multiple_references(self, tmp_path):
        """Test expanding multiple file references in one text."""
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")

        result = expand_file_references("Check @file1.txt and @file2.txt", tmp_path)

        assert "Content 1" in result
        assert "Content 2" in result

    def test_expand_absolute_path(self, tmp_path):
        """Test expanding absolute file paths."""
        test_file = tmp_path / "absolute.txt"
        test_file.write_text("Absolute content")

        result = expand_file_references(f"@{test_file}", tmp_path)

        assert "Absolute content" in result

    def test_expand_file_read_error_fallback(self, tmp_path):
        """Test fallback when file has encoding issues."""
        test_file = tmp_path / "encoding.txt"
        test_file.write_text("Content")

        with patch.object(Path, "read_text", side_effect=[UnicodeDecodeError("utf-8", b"", 0, 1, ""), "Content"]):
            result = expand_file_references("@encoding.txt", tmp_path)

        # Should fallback to reading without encoding
        assert "Content" in result

    def test_expand_file_complete_failure(self, tmp_path):
        """Test that reference is kept when file can't be read at all."""
        test_file = tmp_path / "error.txt"
        test_file.write_text("Content")

        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            result = expand_file_references("@error.txt", tmp_path)

        assert result == "@error.txt"

    def test_expand_without_base_dir(self, tmp_path):
        """Test expansion without base_dir doesn't error."""
        # When base_dir is None, it uses Path.cwd() internally
        # Just verify it doesn't crash and returns something
        result = expand_file_references("@somefile.txt", None)

        # File won't exist, so reference should be kept
        assert result is not None
        assert "@" in result or result == "@somefile.txt"


# =============================================================================
# Test parse_input
# =============================================================================


class TestParseInput:
    """Tests for parse_input function."""

    def test_parse_plain_text(self):
        """Test parsing plain text input."""
        text, is_shell, shell_cmd = parse_input("ping 8.8.8.8")

        assert text == "ping 8.8.8.8"
        assert is_shell is False
        assert shell_cmd is None

    def test_parse_shell_command(self):
        """Test parsing shell command (!command)."""
        text, is_shell, shell_cmd = parse_input("!ping 8.8.8.8")

        assert text == "!ping 8.8.8.8"
        assert is_shell is True
        assert shell_cmd == "ping 8.8.8.8"

    def test_parse_shell_command_spaces(self):
        """Test shell command with leading spaces."""
        text, is_shell, shell_cmd = parse_input("!  ls -la")

        assert is_shell is True
        assert shell_cmd == "ls -la"

    def test_parse_with_file_reference(self, tmp_path):
        """Test parsing with file reference."""
        test_file = tmp_path / "config.txt"
        test_file.write_text("config content")

        # parse_input only takes one argument (text)
        # File expansion happens internally but without base_dir context in this case
        text, is_shell, shell_cmd = parse_input("@config.txt")

        assert is_shell is False
        assert shell_cmd is None
        # Without base_dir, file won't be found, so reference is kept
        assert "@config.txt" in text or "config content" in text

    def test_parse_with_whitespace(self):
        """Test that input is stripped."""
        text, is_shell, shell_cmd = parse_input("  ping 8.8.8.8  ")

        assert text == "ping 8.8.8.8"
        assert is_shell is False


# =============================================================================
# Test execute_shell_command
# =============================================================================


class TestExecuteShellCommand:
    """Tests for execute_shell_command function."""

    def test_execute_successful_command(self):
        """Test successful command execution."""
        success, stdout, stderr, code = execute_shell_command("echo hello")

        assert success is True
        assert "hello" in stdout
        assert code == 0

    def test_execute_failing_command(self):
        """Test command that fails."""
        success, stdout, stderr, code = execute_shell_command("ls /nonexistent")

        assert success is False
        assert code != 0

    def test_execute_timeout(self):
        """Test command timeout handling."""
        # Use a command that will timeout
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 30)):
            success, stdout, stderr, code = execute_shell_command("sleep 100")

            assert success is False
            assert "timed out" in stderr
            assert code == -1

    def test_execute_exception(self):
        """Test exception handling during command execution."""
        with patch("subprocess.run", side_effect=Exception("System error")):
            success, stdout, stderr, code = execute_shell_command("test")

            assert success is False
            assert "System error" in stderr
            assert code == -1


# =============================================================================
# Test detect_multiline
# =============================================================================


class TestDetectMultiline:
    """Tests for detect_multiline function."""

    def test_detect_newlines(self):
        """Test detection of newlines."""
        assert detect_multiline("line1\nline2") is True

    def test_detect_trailing_backslash(self):
        """Test detection of trailing backslash."""
        assert detect_multiline("command \\") is True

    def test_detect_code_blocks(self):
        """Test detection of code blocks."""
        assert detect_multiline("```python\ncode\n```") is True

    def test_detect_single_line(self):
        """Test single line input."""
        assert detect_multiline("single line") is False

    def test_detect_empty_string(self):
        """Test empty string."""
        assert detect_multiline("") is False

    def test_detect_backslash_not_at_end(self):
        """Test backslash in middle of line."""
        assert detect_multiline("path\\to\\file") is False


# =============================================================================
# Test strip_code_blocks
# =============================================================================


class TestStripCodeBlocks:
    """Tests for strip_code_blocks function."""

    def test_strip_python_code_block(self):
        """Test stripping Python code block."""
        result = strip_code_blocks("```python\nprint('hello')\n```")

        assert result == "print('hello')"

    def test_strip_text_code_block(self):
        """Test stripping generic code block."""
        result = strip_code_blocks("```\nsome text\n```")

        assert result == "some text"

    def test_strip_with_language_only(self):
        """Test code block with only language specifier."""
        result = strip_code_blocks("```bash\nls -la\n```")

        assert result == "ls -la"

    def test_strip_unmatched_backticks(self):
        """Test that unmatched backticks are not stripped."""
        result = strip_code_blocks("```python\ncode")

        assert "```python" in result

    def test_strip_no_code_block(self):
        """Test text without code blocks."""
        result = strip_code_blocks("just regular text")

        assert result == "just regular text"

    def test_strip_leading_trailing_whitespace(self):
        """Test that whitespace is stripped."""
        result = strip_code_blocks("  ```python\ncode\n```  ")

        assert result == "code"

    def test_strip_empty_code_block(self):
        """Test empty code block."""
        result = strip_code_blocks("```\n```")

        assert result == ""

    def test_strip_multiple_lines_in_block(self):
        """Test multi-line content in code block."""
        result = strip_code_blocks("```text\nline1\nline2\nline3\n```")

        assert result == "line1\nline2\nline3"

    def test_strip_preserves_internal_newlines(self):
        """Test that internal newlines are preserved."""
        result = strip_code_blocks("```python\nfor i in range(10):\n    print(i)\n```")

        assert "for i in range(10):" in result
        assert "    print(i)" in result
