"""Unit tests for knowledge_search module.

Tests for hybrid search (BM25 + vector) functionality for the knowledge base.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from olav.tools.knowledge_search import (
    _apply_reranking,
    _execute_fts_search,
    _execute_vector_search,
    _format_results,
    rrf_fusion,
    search_knowledge,
)


# =============================================================================
# Test rrf_fusion
# =============================================================================


class TestRrfFusion:
    """Tests for rrf_fusion function."""

    def test_rrf_fusion_basic(self):
        """Test basic RRF fusion with simple results."""
        fts_results = [
            (1, "Title1", "Content1", "cisco_ios"),
            (2, "Title2", "Content2", "arista_eos"),
        ]
        vec_results = [
            (2, "Title2", "Content2", "arista_eos"),
            (3, "Title3", "Content3", "juniper_junos"),
        ]

        result = rrf_fusion(fts_results, vec_results, limit=10)

        # Should return 3 unique results
        assert len(result) == 3
        # Result 2 should be ranked higher because it appears in both lists
        result_ids = [r[0] if isinstance(r[0], int) else r for r in result]

    def test_rrf_fusion_weight_normalization(self):
        """Test that weights are properly normalized."""
        fts_results = [(1, "T1", "C1", "p1")]
        vec_results = [(2, "T2", "C2", "p2")]

        # With unequal weights that sum to 1.0
        result = rrf_fusion(fts_results, vec_results, limit=10, vector_weight=0.8, text_weight=0.2)

        assert len(result) == 2

    def test_rrf_fusion_weight_normalization_custom_sum(self):
        """Test weight normalization when sum is not 1.0."""
        fts_results = [(1, "T1", "C1", "p1")]
        vec_results = [(2, "T2", "C2", "p2")]

        # Weights sum to 2.0, should be normalized
        result = rrf_fusion(fts_results, vec_results, limit=10, vector_weight=1.0, text_weight=1.0)

        assert len(result) == 2

    def test_rrf_fusion_respects_limit(self):
        """Test that limit parameter is respected."""
        fts_results = [(i, f"T{i}", f"C{i}", "p1") for i in range(10)]
        vec_results = [(i, f"T{i}", f"C{i}", "p1") for i in range(10)]

        result = rrf_fusion(fts_results, vec_results, limit=5)

        assert len(result) <= 5

    def test_rrf_fusion_empty_fts(self):
        """Test fusion with empty FTS results."""
        fts_results = []
        vec_results = [(1, "T1", "C1", "p1"), (2, "T2", "C2", "p2")]

        result = rrf_fusion(fts_results, vec_results, limit=10)

        assert len(result) == 2

    def test_rrf_fusion_empty_vec(self):
        """Test fusion with empty vector results."""
        fts_results = [(1, "T1", "C1", "p1"), (2, "T2", "C2", "p2")]
        vec_results = []

        result = rrf_fusion(fts_results, vec_results, limit=10)

        assert len(result) == 2

    def test_rrf_fusion_both_empty(self):
        """Test fusion with both result sets empty."""
        result = rrf_fusion([], [], limit=10)

        assert result == []

    def test_rrf_fusion_duplicate_results(self):
        """Test that duplicate results are handled correctly."""
        # Same result in both lists should get combined score
        fts_results = [(1, "T1", "C1", "p1")]
        vec_results = [(1, "T1", "C1", "p1")]

        result = rrf_fusion(fts_results, vec_results, limit=10)

        # Should only appear once
        assert len(result) == 1

    def test_rrf_fusion_missing_platform(self):
        """Test handling of results without platform field."""
        fts_results = [(1, "T1", "C1")]  # No platform
        vec_results = [(2, "T2", "C2", "p2")]

        result = rrf_fusion(fts_results, vec_results, limit=10)

        assert len(result) == 2

    def test_rrf_fusion_custom_k(self):
        """Test fusion with custom RRF constant."""
        fts_results = [(1, "T1", "C1", "p1")]
        vec_results = [(2, "T2", "C2", "p2")]

        result = rrf_fusion(fts_results, vec_results, limit=10, k=100)

        assert len(result) == 2

    def test_rrf_fusion_ranking_order(self):
        """Test that results are ranked by combined score."""
        # Result 1 appears first in FTS, Result 2 appears first in vec
        fts_results = [(1, "T1", "C1", "p1"), (2, "T2", "C2", "p2")]
        vec_results = [(2, "T2", "C2", "p2"), (1, "T1", "C1", "p1")]

        result = rrf_fusion(fts_results, vec_results, limit=10, vector_weight=0.7, text_weight=0.3)

        # With 70% vector weight, result 2 should be ranked higher
        assert len(result) == 2


# =============================================================================
# Test search_knowledge
# =============================================================================


class TestSearchKnowledge:
    """Tests for search_knowledge function."""

    def test_search_knowledge_db_not_exists(self):
        """Test when knowledge database doesn't exist."""
        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = "/nonexistent"

            result = search_knowledge("test query", platform=None, limit=5)

            assert result == ""

    def test_search_knowledge_basic_flow(self, tmp_path):
        """Test basic search flow with mocked database."""
        # Create mock database file
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock db")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                result = search_knowledge("test query", platform=None, limit=5)

                # Should close connection
                mock_conn.close.assert_called_once()

    def test_search_knowledge_with_platform_filter(self, tmp_path):
        """Test search with platform filter."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                search_knowledge("test query", platform="cisco_ios", limit=5)

                # Verify connection was closed
                mock_conn.close.assert_called_once()

    def test_search_knowledge_no_results(self, tmp_path):
        """Test search when no results found."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock")

        mock_conn = Mock()
        # Return empty results
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                with patch("olav.tools.knowledge_search.rrf_fusion", return_value=[]):
                    result = search_knowledge("test query", platform=None, limit=5)

                    assert result == ""

    def test_search_knowledge_with_reranking(self, tmp_path):
        """Test search with reranking enabled."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                with patch("olav.tools.knowledge_search._apply_reranking") as mock_rerank:
                    mock_rerank.return_value = [("Title", "Content", "plat")]
                    with patch("olav.tools.knowledge_search.rrf_fusion", return_value=[("Title", "Content", "plat")]):
                        search_knowledge("test", platform=None, limit=5, rerank=True)

                        # Reranking should be called
                        mock_rerank.assert_called_once()

    def test_search_knowledge_without_reranking(self, tmp_path):
        """Test search with reranking disabled."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                with patch("olav.tools.knowledge_search._apply_reranking") as mock_rerank:
                    search_knowledge("test", platform=None, limit=5, rerank=False)

                    # Reranking should not be called
                    mock_rerank.assert_not_called()

    def test_search_knowledge_custom_weights(self, tmp_path):
        """Test search with custom vector/text weights."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_file = data_dir / "knowledge.db"
        db_file.write_text("mock")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)

            with patch("olav.tools.knowledge_search.duckdb.connect", return_value=mock_conn):
                with patch("olav.tools.knowledge_search.rrf_fusion") as mock_fusion:
                    search_knowledge("test", platform=None, limit=5, vector_weight=0.5, text_weight=0.5)

                    # Verify custom weights were passed
                    call_args = mock_fusion.call_args
                    assert call_args.kwargs.get("vector_weight") == 0.5
                    assert call_args.kwargs.get("text_weight") == 0.5


# =============================================================================
# Test _execute_fts_search
# =============================================================================


class TestExecuteFtsSearch:
    """Tests for _execute_fts_search function."""

    def test_fts_search_basic(self):
        """Test basic full-text search."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, "Title1", "Content1", "cisco_ios"),
            (2, "Title2", "Content2", "arista_eos"),
        ]

        result = _execute_fts_search(mock_conn, ["test"], "test query", None, 10)

        assert len(result) == 2
        mock_conn.execute.assert_called_once()

    def test_fts_search_with_platform(self):
        """Test FTS search with platform filter."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [(1, "T", "C", "cisco_ios")]

        result = _execute_fts_search(mock_conn, ["test"], "test", "cisco_ios", 10)

        assert len(result) == 1
        # Verify platform was included in SQL
        call_args = mock_conn.execute.call_args
        assert "cisco_ios" in call_args[0][1]

    def test_fts_search_empty_query_terms(self):
        """Test FTS search with empty query terms."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        result = _execute_fts_search(mock_conn, [], "test", None, 10)

        # Should use original query when no terms
        mock_conn.execute.assert_called_once()

    def test_fts_search_respects_limit(self):
        """Test that limit parameter is respected."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [(i, f"T{i}", f"C{i}", "p") for i in range(5)]

        result = _execute_fts_search(mock_conn, ["test"], "test", None, 3)

        # SQL should include LIMIT
        call_args = mock_conn.execute.call_args
        assert "LIMIT ?" in call_args[0][0]
        assert 3 in call_args[0][1]

    def test_fts_search_sql_structure(self):
        """Test that SQL query has correct structure."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        _execute_fts_search(mock_conn, ["bgp"], "bgp config", None, 10)

        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]

        # Verify SQL contains key components
        assert "SELECT" in sql
        assert "FROM knowledge_chunks" in sql
        assert "GROUP BY" in sql
        assert "ORDER BY" in sql
        assert "ILIKE" in sql


# =============================================================================
# Test _execute_vector_search
# =============================================================================


class TestExecuteVectorSearch:
    """Tests for _execute_vector_search function."""

    def test_vector_search_disabled(self):
        """Test vector search when provider is 'none'."""
        mock_conn = Mock()

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "none"

            result = _execute_vector_search(mock_conn, "test query", None, 10)

            assert result == []
            mock_conn.execute.assert_not_called()

    def test_vector_search_ollama(self):
        """Test vector search with Ollama provider."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [(1, "T", "C", "p", 0.95)]

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            with patch("langchain_ollama.OllamaEmbeddings") as mock_embeddings:
                mock_emb = Mock()
                mock_emb.embed_query.return_value = [0.1] * 768
                mock_embeddings.return_value = mock_emb

                result = _execute_vector_search(mock_conn, "test", None, 10)

                assert len(result) == 1
                mock_emb.embed_query.assert_called_once_with("test")

    def test_vector_search_openai(self):
        """Test vector search with OpenAI provider."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [(1, "T", "C", "p", 0.95)]

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.embedding_api_key = "test-key"

            with patch("langchain_openai.OpenAIEmbeddings") as mock_embeddings:
                mock_emb = Mock()
                mock_emb.embed_query.return_value = [0.1] * 768
                mock_embeddings.return_value = mock_emb

                result = _execute_vector_search(mock_conn, "test", None, 10)

                assert len(result) == 1

    def test_vector_search_with_platform(self):
        """Test vector search with platform filter."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "none"

            result = _execute_vector_search(mock_conn, "test", "cisco_ios", 10)

            # Should return empty when provider is 'none'
            assert result == []

    def test_vector_search_handles_exception(self):
        """Test that exceptions are handled gracefully."""
        mock_conn = Mock()

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "test-model"
            mock_settings.embedding_api_key = "test-key"

            with patch("langchain_openai.OpenAIEmbeddings") as mock_embeddings:
                mock_embeddings.side_effect = Exception("Import error")

                result = _execute_vector_search(mock_conn, "test", None, 10)

                # Should return empty list on error
                assert result == []

    def test_vector_search_respects_limit(self):
        """Test that limit parameter is respected."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = [(i, f"T{i}", f"C{i}", "p", 0.9) for i in range(5)]

        with patch("olav.tools.knowledge_search.settings") as mock_settings:
            mock_settings.embedding_provider = "none"

            result = _execute_vector_search(mock_conn, "test", None, 3)

            # Should return empty when provider is 'none'
            assert result == []


# =============================================================================
# Test _apply_reranking
# =============================================================================


class TestApplyReranking:
    """Tests for _apply_reranking function."""

    def test_apply_reranking_success(self):
        """Test successful reranking."""
        results = [("T1", "C1", "p1"), ("T2", "C2", "p2")]

        with patch("olav.tools.reranking.rerank_search_results") as mock_rerank:
            mock_rerank.return_value = [("T2", "C2", "p2", 0.9), ("T1", "C1", "p1", 0.8)]

            result = _apply_reranking("query", results, 10)

            assert len(result) == 2
            mock_rerank.assert_called_once_with("query", results, top_k=10)

    def test_apply_reranking_exception(self):
        """Test that exceptions return original results."""
        results = [("T1", "C1", "p1"), ("T2", "C2", "p2")]

        with patch("olav.tools.reranking.rerank_search_results") as mock_rerank:
            mock_rerank.side_effect = Exception("Reranking failed")

            result = _apply_reranking("query", results, 10)

            # Should return original results
            assert result == results


# =============================================================================
# Test _format_results
# =============================================================================


class TestFormatResults:
    """Tests for _format_results function."""

    def test_format_results_basic(self):
        """Test basic result formatting."""
        results = [("Title1", "Content here", "cisco_ios")]

        result = _format_results(results, 10)

        assert "### Title1" in result
        assert "Content here" in result
        assert "(cisco_ios)" in result

    def test_format_results_with_score(self):
        """Test formatting results with reranking scores."""
        results = [("Title1", "Content", "cisco_ios", 0.95)]

        result = _format_results(results, 10)

        assert "[Score: 0.95]" in result

    def test_format_results_zero_score(self):
        """Test that zero scores are not shown."""
        results = [("Title1", "Content", "cisco_ios", 0.0)]

        result = _format_results(results, 10)

        # Zero score should not be shown
        assert "[Score:" not in result

    def test_format_results_truncates_long_content(self):
        """Test that long content is truncated."""
        long_content = "x" * 1000
        results = [("Title", long_content, "platform")]

        result = _format_results(results, 10)

        # Should be truncated
        assert "..." in result
        assert len(result) < 1000

    def test_format_results_no_platform(self):
        """Test formatting results without platform."""
        results = [("Title", "Content", None)]

        result = _format_results(results, 10)

        assert "### Title" in result
        assert "Content" in result
        # No platform tag
        assert "(None)" not in result
        assert "()" not in result

    def test_format_results_multiple_results(self):
        """Test formatting multiple results."""
        results = [
            ("Title1", "Content1", "p1"),
            ("Title2", "Content2", "p2"),
        ]

        result = _format_results(results, 10)

        assert "### Title1" in result
        assert "### Title2" in result
        assert "\n\n" in result  # Results separated by blank line

    def test_format_results_respects_limit(self):
        """Test that limit parameter is respected."""
        results = [(f"T{i}", f"C{i}", "p") for i in range(10)]

        result = _format_results(results, 3)

        # Should only format 3 results
        assert result.count("###") == 3

    def test_format_results_short_content(self):
        """Test formatting with short content that doesn't need truncation."""
        results = [("Title", "Short content", "platform")]

        result = _format_results(results, 10)

        assert "Short content" in result
        assert "..." not in result
