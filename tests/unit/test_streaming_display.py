"""Unit tests for StreamingDisplay class.

Tests hierarchical streaming output with tool visibility,
thinking process display, and result formatting.
"""

import pytest
from io import StringIO
from unittest.mock import Mock, patch, MagicMock
from rich.console import Console

from olav.cli.display import StreamingDisplay


class TestStreamingDisplay:
    """Test suite for StreamingDisplay hierarchical output."""

    @pytest.fixture
    def console(self):
        """Create a Rich Console with string buffer for testing."""
        buffer = StringIO()
        return Console(file=buffer, force_terminal=True, width=120)

    @pytest.fixture
    def display_compact(self, console):
        """Create StreamingDisplay in compact mode (default)."""
        return StreamingDisplay(console=console, verbose=False, show_spinner=False)

    @pytest.fixture
    def display_verbose(self, console):
        """Create StreamingDisplay in verbose mode."""
        return StreamingDisplay(console=console, verbose=True, show_spinner=False)

    def test_init_default(self):
        """Test StreamingDisplay initialization with defaults."""
        display = StreamingDisplay()
        assert display.verbose is False
        assert display.show_spinner is True  # Default is True
        assert display.console is not None

    def test_init_without_rich_raises_error(self):
        """Test that StreamingDisplay raises error if Rich not available."""
        with patch("olav.cli.display.RICH_AVAILABLE", False):
            with pytest.raises(ImportError, match="Rich library required"):
                StreamingDisplay()

    def test_show_thinking_compact_mode(self, display_compact, console):
        """In compact mode, thinking should not be displayed."""
        display_compact.show_thinking("This is thinking...")
        output = console.file.getvalue()
        assert "thinking" not in output.lower()

    def test_show_thinking_verbose_mode(self, display_verbose, console):
        """In verbose mode, thinking should be displayed in dim color."""
        display_verbose.show_thinking("Agent is analyzing...")
        output = console.file.getvalue()
        # Rich markup for dim is present
        assert "Agent is analyzing" in output

    def test_show_tool_call_executing(self, display_compact, console):
        """Test tool call display with executing status."""
        display_compact.show_tool_call(
            tool_name="network_execute",
            device="R1",
            command="show ip bgp summary",
            status="executing",
        )
        output = console.file.getvalue()
        assert "network_execute" in output
        assert "R1" in output
        assert "show ip bgp summary" in output
        assert "⏳" in output  # executing icon

    def test_show_tool_call_completed(self, display_compact, console):
        """Test tool call display with completed status."""
        display_compact.show_tool_call(
            tool_name="config_backup",
            device="Core-01",
            status="completed",
        )
        output = console.file.getvalue()
        assert "config_backup" in output
        assert "Core-01" in output
        assert "✅" in output  # completed icon

    def test_show_tool_call_failed(self, display_compact, console):
        """Test tool call display with failed status."""
        display_compact.show_tool_call(
            tool_name="health_check",
            status="failed",
        )
        output = console.file.getvalue()
        assert "health_check" in output
        assert "❌" in output  # failed icon

    def test_show_tool_call_minimal(self, display_compact, console):
        """Test tool call with only tool name (no device/command)."""
        display_compact.show_tool_call(tool_name="inspect_device")
        output = console.file.getvalue()
        assert "inspect_device" in output
        # Either 🔧 or ⏳ is acceptable depending on status
        assert any(icon in output for icon in ["🔧", "⏳"])

    def test_show_result_streaming(self, display_compact, console):
        """Test result display in streaming mode (delta output)."""
        display_compact.show_result("Hello ", end="")
        display_compact.show_result("World", end="")
        output = console.file.getvalue()
        assert "Hello" in output
        assert "World" in output

    def test_show_result_finalized(self, display_compact, console):
        """Test result display with finalization."""
        display_compact.show_result("Final result", end="\n")
        output = console.file.getvalue()
        assert "Final result" in output

    def test_show_processing_status_without_spinner(self, display_compact, console):
        """Test processing status without spinner animation."""
        display_compact.show_processing_status("Loading data...")
        output = console.file.getvalue()
        assert "Loading data" in output
        assert "🔍" in output

    def test_show_processing_status_with_spinner(self, console):
        """Test processing status with spinner animation."""
        display = StreamingDisplay(console=console, show_spinner=True)
        display.show_processing_status("Executing...")
        # Spinner should be started
        assert display._current_spinner is not None
        display.stop_processing_status()
        assert display._current_spinner is None

    def test_stop_processing_status_without_spinner(self, display_compact):
        """Test stopping status when no spinner exists."""
        # Should not raise error
        display_compact.stop_processing_status()
        assert display_compact._current_spinner is None

    def test_show_error(self, display_compact, console):
        """Test error display format."""
        display_compact.show_error("Connection timeout")
        output = console.file.getvalue()
        assert "Connection timeout" in output
        assert "❌" in output

    def test_sequential_output_hierarchy(self, display_compact, console):
        """Test sequence: thinking -> tool -> result."""
        # Show thinking (shouldn't appear in compact mode)
        display_compact.show_thinking("Analyzing...")

        # Show tool call
        display_compact.show_tool_call(
            tool_name="test_tool", device="R1", command="show version"
        )

        # Show result
        display_compact.show_result("Test completed successfully")

        output = console.file.getvalue()

        # Compact mode: no thinking
        assert "Analyzing" not in output

        # But tool call and result should be present
        assert "test_tool" in output
        assert "R1" in output
        assert "Test completed successfully" in output


class TestStreamingDisplayIntegration:
    """Integration tests simulating real agent streaming."""

    @pytest.fixture
    def console(self):
        """Create a Rich Console with string buffer for testing."""
        buffer = StringIO()
        return Console(file=buffer, force_terminal=True, width=120)

    @pytest.fixture
    def display_compact(self, console):
        """Create StreamingDisplay in compact mode (default)."""
        return StreamingDisplay(console=console, verbose=False, show_spinner=False)

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent that yields structured events."""
        agent = MagicMock()
        return agent

    def test_parse_tool_call_with_valid_data(self, display_compact):
        """Test parsing tool call with device and command."""
        # This tests the internal logic when handling AIMessage with tool_calls
        tool_call = {
            "name": "network_execute",
            "args": {"device": "R2", "command": "show ip bgp"},
        }

        # Simulate what stream_agent_response does
        display_compact.show_tool_call(
            tool_name=tool_call["name"],
            device=tool_call["args"].get("device"),
            command=tool_call["args"].get("command"),
        )

        # Verify output (using mock console would be ideal)
        assert display_compact._current_spinner is None  # No spinner in non-spinner mode

    def test_output_ordering(self):
        """Test that outputs appear in correct order: tools then results."""
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=True, width=120)
        display = StreamingDisplay(console=console, verbose=False, show_spinner=False)

        # Simulate agent output sequence
        display.show_tool_call("network_execute", device="R1", command="show bgp")
        display.show_result("BGP neighbors: ")
        display.show_result("10.1.1.1 (up)", end="\n")

        output = buffer.getvalue()

        # Tool call should appear before result
        tool_pos = output.find("network_execute")
        result_pos = output.find("BGP neighbors")
        assert tool_pos < result_pos, "Tool call should appear before result"

