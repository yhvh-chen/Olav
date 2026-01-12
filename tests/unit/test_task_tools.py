"""
Unit tests for task_tools module.

Tests for task delegation tools for OLAV workflows.
"""

from unittest.mock import Mock, patch

import pytest

from olav.tools.task_tools import (
    delegate_task,
    get_task_middleware,
)


# =============================================================================
# Test get_task_middleware
# =============================================================================


class TestGetTaskMiddleware:
    """Tests for get_task_middleware function."""

    def test_get_task_middleware_creates_instance(self):
        """Test that middleware is created on first call."""
        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {}

        with patch("olav.tools.task_tools.get_subagent_middleware", return_value=mock_middleware) as mock_get:
            # Reset global state
            import olav.tools.task_tools
            olav.tools.task_tools._subagent_middleware = None

            result = get_task_middleware()

            assert result == mock_middleware
            mock_get.assert_called_once()

            # Check that tools were passed
            call_args = mock_get.call_args.kwargs
            assert "tools" in call_args

    def test_get_task_middleware_returns_cached_instance(self):
        """Test that middleware is cached on subsequent calls."""
        mock_middleware = Mock()

        with patch("olav.tools.task_tools.get_subagent_middleware", return_value=mock_middleware):
            # Reset global state
            import olav.tools.task_tools
            olav.tools.task_tools._subagent_middleware = None

            # First call
            result1 = get_task_middleware()

            # Second call should return cached instance
            result2 = get_task_middleware()

            assert result1 is result2

    def test_get_task_middleware_includes_network_tools(self):
        """Test that network tools are included in middleware."""
        mock_middleware = Mock()

        with patch("olav.tools.task_tools.get_subagent_middleware", return_value=mock_middleware) as mock_get:
            # Reset global state
            import olav.tools.task_tools
            olav.tools.task_tools._subagent_middleware = None

            get_task_middleware()

            # Verify tools list includes list_devices and nornir_execute
            call_args = mock_get.call_args.kwargs
            tools = call_args["tools"]
            tool_names = [t.name for t in tools]

            assert "list_devices" in tool_names
            assert "nornir_execute" in tool_names


# =============================================================================
# Test delegate_task
# =============================================================================


class TestDelegateTask:
    """Tests for delegate_task tool."""

    def test_delegate_task_success(self):
        """Test successful task delegation."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_result = {
            "messages": [
                {"role": "user", "content": "Task"},
                {"role": "assistant", "content": "Task completed successfully"},
            ]
        }
        mock_subagent_graph.invoke.return_value = mock_result

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Analyze network")

            assert "Task completed successfully" in result
            mock_subagent_graph.invoke.assert_called_once()

    def test_delegate_task_unknown_subagent_type(self):
        """Test delegation to unknown subagent type."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": Mock()
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("unknown-type", "Do something")

            assert "Error: Unknown subagent type" in result
            assert "unknown-type" in result

    def test_delegate_task_no_subagent_graphs_attr(self):
        """Test middleware without subagent_graphs attribute."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_middleware = Mock(spec=[])  # No subagent_graphs attribute

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            assert "Error: Subagent middleware not properly configured" in result

    def test_delegate_task_invoke_returns_none(self):
        """Test when subagent invoke returns None."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = None

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            assert "Subagent completed but produced no output" in result

    def test_delegate_task_result_has_no_messages(self):
        """Test when result doesn't have messages key."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = {"other_key": "value"}

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            assert "Subagent completed but produced no output" in result

    def test_delegate_task_empty_messages_list(self):
        """Test when messages list is empty."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = {"messages": []}

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            # Empty messages list causes IndexError which is caught by exception handler
            assert "Error delegating task" in result

    def test_delegate_task_final_message_no_content(self):
        """Test when final message has no content key."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = {
            "messages": [
                {"role": "assistant"}  # No content key
            ]
        }

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            assert "No content from subagent" in result

    def test_delegate_task_exception_handling(self):
        """Test that exceptions are caught and returned as error messages."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.side_effect = Exception("Subagent failed")

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("macro-analyzer", "Do something")

            assert "Error delegating task" in result
            assert "Subagent failed" in result

    def test_delegate_task_passes_initial_state(self):
        """Test that initial state is passed correctly to subagent."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = {
            "messages": [{"role": "assistant", "content": "Done"}]
        }

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "micro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            delegate_tool.func("micro-analyzer", "Test task description")

            # Verify invoke was called with correct state structure
            call_args = mock_subagent_graph.invoke.call_args
            initial_state = call_args[0][0]

            assert "messages" in initial_state
            assert len(initial_state["messages"]) == 1
            assert initial_state["messages"][0]["role"] == "user"
            assert initial_state["messages"][0]["content"] == "Test task description"
            assert initial_state["tool_call_id"] is None

    def test_delegate_task_with_multiple_available_subagents(self):
        """Test with multiple subagent types available."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_macro_graph = Mock()
        mock_macro_graph.invoke.return_value = {
            "messages": [{"role": "assistant", "content": "Macro done"}]
        }

        mock_micro_graph = Mock()
        mock_micro_graph.invoke.return_value = {
            "messages": [{"role": "assistant", "content": "Micro done"}]
        }

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_macro_graph,
            "micro-analyzer": mock_micro_graph,
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            # Test macro-analyzer
            result1 = delegate_tool.func("macro-analyzer", "Task 1")
            assert "Macro done" in result1

            # Test micro-analyzer
            result2 = delegate_tool.func("micro-analyzer", "Task 2")
            assert "Micro done" in result2

    def test_delegate_task_error_message_includes_available_types(self):
        """Test that error message lists available subagent types."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": Mock(),
            "micro-analyzer": Mock(),
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            result = delegate_tool.func("invalid-type", "Do something")

            assert "Error: Unknown subagent type" in result
            assert "macro-analyzer" in result
            assert "micro-analyzer" in result

    def test_delegate_task_complex_task_description(self):
        """Test with complex task description."""
        from olav.tools.task_tools import delegate_task as delegate_tool

        mock_subagent_graph = Mock()
        mock_subagent_graph.invoke.return_value = {
            "messages": [{"role": "assistant", "content": "Analysis complete"}]
        }

        mock_middleware = Mock()
        mock_middleware.subagent_graphs = {
            "macro-analyzer": mock_subagent_graph
        }

        with patch("olav.tools.task_tools.get_task_middleware", return_value=mock_middleware):
            task = "Analyze the path from R1 to R3 through R2, checking for any routing issues"
            result = delegate_tool.func("macro-analyzer", task)

            assert "Analysis complete" in result
            # Verify the full task description was passed
            call_args = mock_subagent_graph.invoke.call_args
            initial_state = call_args[0][0]
            assert initial_state["messages"][0]["content"] == task
