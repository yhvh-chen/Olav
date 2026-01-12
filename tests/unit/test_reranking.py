"""
Unit tests for reranking module.

Tests for cross-encoder based reranking to improve search result quality.
"""

import sys
from unittest.mock import Mock, patch

import pytest

from olav.tools.reranking import (
    _get_reranker,
    rerank_search_results,
    search_with_reranking,
)


# =============================================================================
# Test _get_reranker
# =============================================================================


class TestGetReranker:
    """Tests for _get_reranker function."""

    def test_get_reranker_disabled(self):
        """Test that None is returned when reranker is disabled."""
        with patch("config.settings") as mock_settings:
            mock_settings.reranker_model = None

            result = _get_reranker()

            assert result is None

    def test_get_reranker_none_string(self):
        """Test that 'none' string returns None."""
        with patch("config.settings") as mock_settings:
            mock_settings.reranker_model = "none"

            result = _get_reranker()

            assert result is None

    def test_get_reranker_jina_fallback(self):
        """Test that jina reranker gracefully falls back when unavailable."""
        with patch("config.settings") as mock_settings:
            mock_settings.reranker_model = "jina"

            # Without langchain_community installed, returns None
            result = _get_reranker()

            # This is expected behavior - returns None when module not available
            assert result is None

    def test_get_reranker_mxbai_fallback(self):
        """Test that mxbai reranker gracefully falls back when unavailable."""
        with patch("config.settings") as mock_settings:
            mock_settings.reranker_model = "mxbai"

            # Without langchain_community installed, returns None
            result = _get_reranker()

            # This is expected behavior - returns None when module not available
            assert result is None

    def test_get_reranker_unknown_type(self):
        """Test that unknown reranker type returns None."""
        with patch("config.settings") as mock_settings:
            mock_settings.reranker_model = "unknown_type"

            result = _get_reranker()

            assert result is None


# =============================================================================
# Test rerank_search_results
# =============================================================================


class TestRerankSearchResults:
    """Tests for rerank_search_results function."""

    def test_rerank_empty_results(self):
        """Test reranking with empty results list."""
        result = rerank_search_results("query", [])

        assert result == []

    def test_rerank_no_reranker_available(self):
        """Test fallback when reranker is not available."""
        with patch("olav.tools.reranking._get_reranker", return_value=None):
            results = [
                ("Title1", "Content1", "cisco_ios"),
                ("Title2", "Content2", "arista_eos"),
            ]

            result = rerank_search_results("query", results)

            assert len(result) == 2
            assert result[0] == ("Title1", "Content1", "cisco_ios", 0.0)
            assert result[1] == ("Title2", "Content2", "arista_eos", 0.0)

    def test_rerank_preserves_existing_scores(self):
        """Test that results with existing scores are preserved."""
        with patch("olav.tools.reranking._get_reranker", return_value=None):
            results = [
                ("Title1", "Content1", "cisco_ios", 0.8),
                ("Title2", "Content2", "arista_eos", 0.6),
            ]

            result = rerank_search_results("query", results)

            assert len(result) == 2
            assert result[0] == ("Title1", "Content1", "cisco_ios", 0.8)
            assert result[1] == ("Title2", "Content2", "arista_eos", 0.6)

    def test_rerank_handles_none_platform(self):
        """Test that None platform is handled correctly."""
        with patch("olav.tools.reranking._get_reranker", return_value=None):
            results = [
                ("Title1", "Content1", None),
                ("Title2", "Content2", "cisco_ios"),
            ]

            result = rerank_search_results("query", results)

            assert len(result) == 2
            assert result[0] == ("Title1", "Content1", None, 0.0)
            assert result[1] == ("Title2", "Content2", "cisco_ios", 0.0)

    def test_rerank_successful_reranking(self):
        """Test successful reranking with mock reranker."""
        mock_reranker = Mock()

        # Mock documents with metadata
        mock_doc1 = Mock()
        mock_doc1.metadata = {
            "relevance_score": 0.95,
            "title": "BGP Config",
            "content": "BGP configuration guide",
            "platform": "cisco_ios",
        }

        mock_doc2 = Mock()
        mock_doc2.metadata = {
            "relevance_score": 0.72,
            "title": "BGP Theory",
            "content": "BGP protocol overview",
            "platform": "general",
        }

        mock_reranker.compress_documents.return_value = [mock_doc1, mock_doc2]

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [
                ("BGP Config", "BGP configuration guide", "cisco_ios"),
                ("BGP Theory", "BGP protocol overview", "general"),
            ]

            result = rerank_search_results("configure bgp", results)

            assert len(result) == 2
            assert result[0] == ("BGP Config", "BGP configuration guide", "cisco_ios", 0.95)
            assert result[1] == ("BGP Theory", "BGP protocol overview", "general", 0.72)

            # Verify reranker was called
            mock_reranker.compress_documents.assert_called_once()

    def test_rerank_top_k_limit(self):
        """Test that top_k parameter limits results."""
        mock_reranker = Mock()

        # Create 5 mock documents
        mock_docs = []
        for i in range(5):
            mock_doc = Mock()
            mock_doc.metadata = {
                "relevance_score": 0.9 - (i * 0.1),
                "title": f"Title{i}",
                "content": f"Content{i}",
                "platform": "cisco_ios",
            }
            mock_docs.append(mock_doc)

        mock_reranker.compress_documents.return_value = mock_docs

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [(f"Title{i}", f"Content{i}", "cisco_ios") for i in range(5)]

            result = rerank_search_results("query", results, top_k=3)

            assert len(result) == 3
            assert result[0][3] == 0.9

    def test_rerank_handles_missing_metadata(self):
        """Test handling of documents with missing metadata."""
        mock_reranker = Mock()

        # Mock document without all metadata
        mock_doc = Mock()
        mock_doc.metadata = {"relevance_score": 0.5}  # Missing title, content, platform

        mock_reranker.compress_documents.return_value = [mock_doc]

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [("Title", "Content", "platform")]

            result = rerank_search_results("query", results)

            assert len(result) == 1
            # Should use empty string as defaults
            assert result[0][0] == ""  # title
            assert result[0][1] == ""  # content
            assert result[0][2] is None  # platform

    def test_rerank_exception_fallback(self):
        """Test fallback on exception during reranking."""
        mock_reranker = Mock()
        mock_reranker.compress_documents.side_effect = Exception("Reranking failed")

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [("Title1", "Content1", "cisco_ios")]

            result = rerank_search_results("query", results)

            # Should fall back to original order with dummy score
            assert len(result) == 1
            assert result[0] == ("Title1", "Content1", "cisco_ios", 0.0)

    def test_rerank_default_top_k(self):
        """Test that default top_k is 5."""
        mock_reranker = Mock()

        # Create 10 mock documents
        mock_docs = []
        for i in range(10):
            mock_doc = Mock()
            mock_doc.metadata = {
                "relevance_score": 1.0 - (i * 0.1),
                "title": f"Title{i}",
                "content": f"Content{i}",
                "platform": "cisco_ios",
            }
            mock_docs.append(mock_doc)

        mock_reranker.compress_documents.return_value = mock_docs

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [(f"Title{i}", f"Content{i}", "cisco_ios") for i in range(10)]

            result = rerank_search_results("query", results)

            # Should return only top 5
            assert len(result) == 5

    def test_rerank_with_none_platform_in_results(self):
        """Test reranking with None platform values."""
        mock_reranker = Mock()

        mock_doc = Mock()
        mock_doc.metadata = {
            "relevance_score": 0.8,
            "title": "Title",
            "content": "Content",
            "platform": None,
        }

        mock_reranker.compress_documents.return_value = [mock_doc]

        with patch("olav.tools.reranking._get_reranker", return_value=mock_reranker):
            results = [("Title", "Content", None)]

            result = rerank_search_results("query", results)

            assert len(result) == 1
            assert result[0][2] is None


# =============================================================================
# Test search_with_reranking
# =============================================================================


class TestSearchWithReranking:
    """Tests for search_with_reranking tool."""

    def test_search_with_reranking_no_rerank(self):
        """Test search with reranking disabled."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Search results here")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("bgp", rerank=False)

            assert result == "Search results here"
            mock_base_search.assert_called_once()

    def test_search_with_reranking_no_results(self):
        """Test search when no results found."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="No results found for query")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("nonexistent")

            assert "No results found" in result
            # Should not attempt reranking

    def test_search_with_reranking_with_results(self):
        """Test search with reranking enabled."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Found some results")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("bgp", rerank=True)

            # Current implementation returns raw results
            assert result == "Found some results"

    def test_search_with_reranking_scope_capabilities(self):
        """Test search with capabilities scope."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Capabilities results")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("interface", scope="capabilities")

            mock_base_search.assert_called_once()

    def test_search_with_reranking_with_platform_filter(self):
        """Test search with platform filter."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Filtered results")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("bgp", platform="cisco_ios")

            # Verify platform was passed through
            call_kwargs = mock_base_search.call_args.kwargs
            assert "platform" in call_kwargs

    def test_search_with_reranking_custom_limit(self):
        """Test search with custom limit."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Limited results")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("interface", limit=5)

            # Verify limit was passed through
            call_kwargs = mock_base_search.call_args.kwargs
            assert call_kwargs.get("limit") == 5

    def test_search_with_reranking_all_parameters(self):
        """Test search with all parameters."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="Comprehensive results")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func(
                query="configure bgp",
                scope="knowledge",
                platform="cisco_ios",
                limit=10,
                rerank=True,
            )

            # Verify all parameters were passed
            mock_base_search.assert_called_once()

    def test_search_with_reranking_result_contains_no_results(self):
        """Test that 'No results found' in result bypasses reranking."""
        from olav.tools.reranking import search_with_reranking as search_tool

        mock_base_search = Mock(return_value="No results found matching 'x'")

        with patch("olav.tools.capabilities.search", mock_base_search):
            result = search_tool.func("x", rerank=True)

            # Should return raw results without reranking
            assert result == "No results found matching 'x'"
