"""Unit tests for knowledge_embedder module.

Tests for generating embeddings and indexing knowledge files into DuckDB.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from olav.tools.knowledge_embedder import KnowledgeEmbedder


# =============================================================================
# Test KnowledgeEmbedder initialization
# =============================================================================


class TestKnowledgeEmbedderInit:
    """Tests for KnowledgeEmbedder initialization."""

    def test_init_with_db_path(self):
        """Test initialization with custom db_path."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            with patch("olav.tools.knowledge_embedder.RecursiveCharacterTextSplitter"):
                embedder = KnowledgeEmbedder(db_path="/custom/path/knowledge.db")

                assert embedder.db_path == "/custom/path/knowledge.db"

    def test_init_default_db_path(self):
        """Test initialization with default db_path."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test/olav"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            with patch("olav.tools.knowledge_embedder.RecursiveCharacterTextSplitter"):
                embedder = KnowledgeEmbedder()

                assert "/test/olav/data/knowledge.db" in embedder.db_path

    def test_init_creates_text_splitter(self):
        """Test that text splitter is created."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()

        assert embedder.splitter is not None


# =============================================================================
# Test _get_embeddings
# =============================================================================


class TestGetEmbeddings:
    """Tests for _get_embeddings method."""

    def test_get_embeddings_ollama(self):
        """Test getting Ollama embeddings."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            with patch("olav.tools.knowledge_embedder.RecursiveCharacterTextSplitter"):
                embedder = KnowledgeEmbedder()

                assert embedder.embeddings is not None

    def test_get_embeddings_openai(self):
        """Test getting OpenAI embeddings."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.embedding_api_key = "test-key"

            with patch("olav.tools.knowledge_embedder.RecursiveCharacterTextSplitter"):
                embedder = KnowledgeEmbedder()

                assert embedder.embeddings is not None

    def test_get_embeddings_unsupported_provider(self):
        """Test error with unsupported provider."""
        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.embedding_provider = "unsupported"

            with patch("olav.tools.knowledge_embedder.RecursiveCharacterTextSplitter"):
                with pytest.raises(ValueError, match="Unsupported embedding provider"):
                    KnowledgeEmbedder()


# =============================================================================
# Test embed_file
# =============================================================================


class TestEmbedFile:
    """Tests for embed_file method."""

    def test_embed_file_read_error(self, tmp_path):
        """Test handling of file read errors."""
        non_existent = tmp_path / "nonexistent.md"

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            count = embedder.embed_file(non_existent, source_id=1)

            assert count == 0

    def test_embed_file_not_modified(self, tmp_path):
        """Test skipping already indexed file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent here")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [1]  # Already exists

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            with patch("olav.tools.knowledge_embedder.duckdb.connect", return_value=mock_conn):
                embedder = KnowledgeEmbedder()
                count = embedder.embed_file(md_file, source_id=1)

                assert count == 0

    def test_embed_file_no_chunks(self, tmp_path):
        """Test handling when no chunks are generated."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = None  # Not indexed yet

        mock_splitter = Mock()
        mock_splitter.split_text.return_value = []  # No chunks

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.splitter = mock_splitter

            with patch("olav.tools.knowledge_embedder.duckdb.connect", return_value=mock_conn):
                count = embedder.embed_file(md_file, source_id=1)

                assert count == 0

    def test_embed_file_embedding_error(self, tmp_path):
        """Test handling of embedding generation errors."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent here" * 100)

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.execute.return_value.fetchall.return_value = []

        mock_splitter = Mock()
        mock_splitter.split_text.return_value = ["chunk1", "chunk2"]

        mock_embeddings = Mock()
        mock_embeddings.embed_query.side_effect = Exception("Embedding failed")

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings
            embedder.splitter = mock_splitter

            with patch("olav.tools.knowledge_embedder.duckdb.connect", return_value=mock_conn):
                count = embedder.embed_file(md_file, source_id=1)

                # Returns the number of chunks even if embeddings failed
                # (the actual inserts would fail, but the count is returned)
                assert count == 2

    def test_embed_file_success(self, tmp_path):
        """Test successful file embedding."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent here" * 100)

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = None  # Not indexed yet

        mock_splitter = Mock()
        mock_splitter.split_text.return_value = ["chunk1", "chunk2"]

        mock_embeddings = Mock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings
            embedder.splitter = mock_splitter

            with patch("olav.tools.knowledge_embedder.duckdb.connect", return_value=mock_conn):
                count = embedder.embed_file(md_file, source_id=1)

                assert count == 2


# =============================================================================
# Test embed_directory
# =============================================================================


class TestEmbedDirectory:
    """Tests for embed_directory method."""

    def test_embed_directory_not_exists(self, tmp_path):
        """Test with non-existent directory."""
        non_existent = tmp_path / "nonexistent"

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            stats = embedder.embed_directory(non_existent, source_id=1)

            assert stats["indexed"] == 0
            assert stats["skipped"] == 0
            assert stats["errors"] == 0

    def test_embed_directory_no_md_files(self, tmp_path):
        """Test with directory containing no markdown files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            stats = embedder.embed_directory(empty_dir, source_id=1)

            assert stats["indexed"] == 0
            assert stats["skipped"] == 0

    def test_embed_directory_recursive(self, tmp_path):
        """Test recursive directory embedding."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "test1.md").write_text("# Test 1")
        (tmp_path / "subdir" / "test2.md").write_text("# Test 2")

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()

            # Mock embed_file to return counts
            with patch.object(embedder, "embed_file", return_value=2):
                stats = embedder.embed_directory(tmp_path, source_id=1, recursive=True)

                assert stats["indexed"] == 4  # 2 files * 2 chunks each
                assert stats["errors"] == 0

    def test_embed_directory_non_recursive(self, tmp_path):
        """Test non-recursive directory embedding."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "test1.md").write_text("# Test 1")
        (tmp_path / "subdir" / "test2.md").write_text("# Test 2")

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()

            # Mock embed_file to count calls
            call_count = [0]
            def mock_embed(*args):
                call_count[0] += 1
                return 1

            with patch.object(embedder, "embed_file", side_effect=mock_embed):
                stats = embedder.embed_directory(tmp_path, source_id=1, recursive=False)

                # Should only process top-level file
                assert stats["indexed"] == 1

    def test_embed_directory_with_errors(self, tmp_path):
        """Test handling of errors during directory embedding."""
        (tmp_path / "test1.md").write_text("# Test 1")
        (tmp_path / "test2.md").write_text("# Test 2")

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = str(tmp_path)
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()

            # Mock embed_file to throw error for one file
            call_count = [0]
            def mock_embed(*args):
                call_count[0] += 1
                if call_count[0] == 1:
                    return 2
                else:
                    raise Exception("Test error")

            with patch.object(embedder, "embed_file", side_effect=mock_embed):
                stats = embedder.embed_directory(tmp_path, source_id=1)

                assert stats["indexed"] == 2
                assert stats["errors"] == 1


# =============================================================================
# Test get_embedding_dimension
# =============================================================================


class TestGetEmbeddingDimension:
    """Tests for get_embedding_dimension method."""

    def test_get_embedding_dimension_ollama(self):
        """Test getting dimension for Ollama embeddings."""
        mock_embeddings = Mock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings

            dim = embedder.get_embedding_dimension()

            assert dim == 768

    def test_get_embedding_dimension_openai(self):
        """Test getting dimension for OpenAI embeddings."""
        mock_embeddings = Mock()
        mock_embeddings.embed_query.return_value = [0.1] * 1536

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.embedding_api_key = "test-key"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings

            dim = embedder.get_embedding_dimension()

            assert dim == 1536


# =============================================================================
# Test test_connection
# =============================================================================


class TestTestConnection:
    """Tests for test_connection method."""

    def test_test_connection_success(self):
        """Test successful connection test."""
        mock_embeddings = Mock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings

            result = embedder.test_connection()

            assert result is True

    def test_test_connection_failure(self):
        """Test connection test failure."""
        mock_embeddings = Mock()
        mock_embeddings.embed_query.side_effect = Exception("Connection failed")

        with patch("olav.tools.knowledge_embedder.settings") as mock_settings:
            mock_settings.agent_dir = "/test"
            mock_settings.embedding_provider = "ollama"
            mock_settings.embedding_model = "nomic-embed-text"
            mock_settings.embedding_base_url = "http://localhost:11434"

            embedder = KnowledgeEmbedder()
            embedder.embeddings = mock_embeddings

            result = embedder.test_connection()

            assert result is False
