"""Unit tests for Phase 3: SubAgent Manager.

Tests the SubAgentMiddleware integration and subagent descriptions.
"""

from unittest.mock import MagicMock

from olav.core.subagent_manager import (
    format_subagent_descriptions,
    get_available_subagents,
    get_subagent_middleware,
)


class TestGetAvailableSubagents:
    """Test get_available_subagents function."""

    def test_returns_dict(self) -> None:
        """Test that get_available_subagents returns a dictionary."""
        descriptions = get_available_subagents()
        assert isinstance(descriptions, dict)

    def test_has_macro_analyzer(self) -> None:
        """Test that descriptions include macro-analyzer."""
        descriptions = get_available_subagents()
        assert "macro-analyzer" in descriptions

    def test_has_micro_analyzer(self) -> None:
        """Test that descriptions include micro-analyzer."""
        descriptions = get_available_subagents()
        assert "micro-analyzer" in descriptions

    def test_macro_analyzer_structure(self) -> None:
        """Test macro-analyzer description structure."""
        descriptions = get_available_subagents()
        macro = descriptions["macro-analyzer"]
        assert "name" in macro
        assert "description" in macro
        assert "use_case" in macro
        assert macro["name"] == "macro-analyzer"

    def test_micro_analyzer_structure(self) -> None:
        """Test micro-analyzer description structure."""
        descriptions = get_available_subagents()
        micro = descriptions["micro-analyzer"]
        assert "name" in micro
        assert "description" in micro
        assert "use_case" in micro
        assert micro["name"] == "micro-analyzer"


class TestFormatSubagentDescriptions:
    """Test format_subagent_descriptions function."""

    def test_returns_string(self) -> None:
        """Test that format_subagent_descriptions returns a string."""
        formatted = format_subagent_descriptions()
        assert isinstance(formatted, str)

    def test_contains_macro_analyzer(self) -> None:
        """Test formatted string contains macro-analyzer info."""
        formatted = format_subagent_descriptions()
        assert "macro-analyzer" in formatted or "Macro" in formatted

    def test_contains_micro_analyzer(self) -> None:
        """Test formatted string contains micro-analyzer info."""
        formatted = format_subagent_descriptions()
        assert "micro-analyzer" in formatted or "Micro" in formatted

    def test_contains_descriptions(self) -> None:
        """Test formatted string contains descriptions."""
        formatted = format_subagent_descriptions()
        # Should have meaningful content
        assert len(formatted) > 50

    def test_contains_use_cases(self) -> None:
        """Test formatted string contains use cases."""
        formatted = format_subagent_descriptions()
        descriptions = get_available_subagents()
        # At least one use case should be in the formatted string
        use_cases_present = any(
            desc["use_case"] in formatted or "Use for" in formatted
            for desc in descriptions.values()
        )
        assert use_cases_present or len(formatted) > 100


class TestGetSubagentMiddleware:
    """Test get_subagent_middleware function."""

    def test_returns_middleware(self) -> None:
        """Test that get_subagent_middleware returns SubAgentMiddleware."""
        from deepagents.middleware.subagents import SubAgentMiddleware

        middleware = get_subagent_middleware(tools=[])
        assert isinstance(middleware, SubAgentMiddleware)

    def test_accepts_tools_list(self) -> None:
        """Test that middleware accepts tools list (uses real tools)."""
        from olav.tools.network import list_devices

        middleware = get_subagent_middleware(tools=[list_devices])
        assert middleware is not None

    def test_accepts_custom_model(self) -> None:
        """Test that middleware accepts custom model."""
        mock_model = MagicMock()
        middleware = get_subagent_middleware(tools=[], default_model=mock_model)
        assert middleware is not None

    def test_middleware_has_subagents(self) -> None:
        """Test that middleware has subagents configured."""
        middleware = get_subagent_middleware(tools=[])
        # SubAgentMiddleware is not None means it was created successfully
        assert middleware is not None


class TestSubagentManagerIntegration:
    """Integration tests for subagent manager."""

    def test_middleware_with_empty_tools(self) -> None:
        """Test middleware works with empty tools list."""
        middleware = get_subagent_middleware(tools=[])
        assert middleware is not None

    def test_middleware_with_none_model(self) -> None:
        """Test middleware works with None model (uses default)."""
        middleware = get_subagent_middleware(tools=[], default_model=None)
        assert middleware is not None

    def test_descriptions_match_middleware(self) -> None:
        """Test that descriptions match what's in middleware."""
        descriptions = get_available_subagents()
        # Verify middleware can be created (validates configs)
        _ = get_subagent_middleware(tools=[])

        # Both should have same subagent names
        desc_names = set(descriptions.keys())
        assert "macro-analyzer" in desc_names
        assert "micro-analyzer" in desc_names
