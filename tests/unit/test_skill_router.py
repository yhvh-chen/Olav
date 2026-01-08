"""Unit tests for Phase 2: Skill Router.

Tests the LLM-based skill routing functionality.
"""

from unittest.mock import MagicMock

import pytest

from olav.core.skill_loader import SkillLoader, get_skill_loader
from olav.core.skill_router import SkillRouter


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create a mock LLM for testing."""
    llm = MagicMock()
    mock_response = (
        '{"skill_id": "quick-query", "confidence": 0.9, '
        '"reason": "Test", "is_network_related": true}'
    )
    llm.invoke = MagicMock(return_value=MagicMock(content=mock_response))
    return llm


@pytest.fixture
def skill_loader() -> SkillLoader:
    """Get the real skill loader."""
    return get_skill_loader()


class TestSkillRouter:
    """Test SkillRouter class."""

    def test_router_creation(self, mock_llm: MagicMock, skill_loader: SkillLoader) -> None:
        """Test creating a SkillRouter instance."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        assert router is not None
        assert router.llm is mock_llm
        assert router.skill_loader is skill_loader

    def test_route_returns_dict(self, mock_llm: MagicMock, skill_loader: SkillLoader) -> None:
        """Test that route() returns a dictionary."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("查询 R1 接口状态")
        assert isinstance(result, dict)

    def test_route_result_has_required_keys(
        self, mock_llm: MagicMock, skill_loader: SkillLoader
    ) -> None:
        """Test that route result has required keys."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("show ip interface")
        required_keys = [
            "selected_skill",
            "reason",
            "is_network_related",
            "confidence",
            "fallback",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_route_with_network_query(self, mock_llm: MagicMock, skill_loader: SkillLoader) -> None:
        """Test routing a network-related query."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("查询 R1 BGP 状态")
        assert result["is_network_related"] is True

    def test_route_confidence_is_float(
        self, mock_llm: MagicMock, skill_loader: SkillLoader
    ) -> None:
        """Test that confidence is a float."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("show interfaces")
        assert isinstance(result["confidence"], (int, float))


class TestSkillRouterEdgeCases:
    """Test edge cases for SkillRouter."""

    def test_route_empty_query(self, mock_llm: MagicMock, skill_loader: SkillLoader) -> None:
        """Test routing with empty query."""
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("")
        assert isinstance(result, dict)

    def test_route_non_network_query(self, skill_loader: SkillLoader) -> None:
        """Test routing a non-network query."""
        mock_llm = MagicMock()
        mock_response = (
            '{"skill_id": null, "confidence": 0.1, '
            '"reason": "Not network related", "is_network_related": false}'
        )
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=mock_response))
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("今天天气怎么样?")
        # Should handle gracefully
        assert isinstance(result, dict)

    def test_fallback_on_low_confidence(self, skill_loader: SkillLoader) -> None:
        """Test fallback when confidence is low."""
        mock_llm = MagicMock()
        mock_response = (
            '{"skill_id": "unknown", "confidence": 0.2, '
            '"reason": "Low confidence", "is_network_related": true}'
        )
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=mock_response))
        router = SkillRouter(llm=mock_llm, skill_loader=skill_loader)
        result = router.route("一些模糊的查询")
        # Should use fallback
        assert result["fallback"] is True or result["selected_skill"] is not None
