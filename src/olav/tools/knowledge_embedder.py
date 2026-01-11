"""Generate embeddings and index knowledge files into DuckDB.

This module provides the KnowledgeEmbedder class for:
- Generating text embeddings using Ollama (free local) or OpenAI (paid cloud)
- Chunking markdown files into smaller pieces
- Indexing embeddings into the knowledge database
- Incremental updates (only re-index changed files)

Phase 4: Knowledge Base Integration
"""

import hashlib
from pathlib import Path

import duckdb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import settings


class KnowledgeEmbedder:
    """Generate and store embeddings for knowledge base.

    Supports multiple embedding providers:
    - Ollama: Free local embeddings (recommended, using nomic-embed-text)
    - OpenAI: Cloud embeddings (requires API key, using text-embedding-3-small)

    Example:
        >>> embedder = KnowledgeEmbedder()
        >>> embedder.embed_file(Path("docs/wiki.md"), source_id=1, platform="cisco_ios")
        >>> embedder.embed_directory(Path("docs/"), source_id=2)
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize the embedder.

        Args:
            db_path: Optional path to knowledge database (uses default if not provided)
        """
        self.db_path = db_path or str(Path(settings.agent_dir) / "data" / "knowledge.db")
        self.embeddings = self._get_embeddings()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
        )

    def _get_embeddings(self):
        """Initialize embeddings based on settings.

        Returns:
            LangChain embeddings instance (OllamaEmbeddings or OpenAIEmbeddings)

        Raises:
            ValueError: If embedding provider is not supported
        """
        provider = settings.embedding_provider

        if provider == "ollama":
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                model=settings.embedding_model,  # nomic-embed-text
                base_url=settings.embedding_base_url or "http://localhost:11434",
            )
        elif provider == "openai":
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.embedding_model,  # text-embedding-3-small
                openai_api_key=settings.embedding_api_key,
            )
        else:
            raise ValueError(
                f"Unsupported embedding provider: {provider}. "
                f"Use 'ollama' (free local) or 'openai' (paid cloud)."
            )

    def embed_file(
        self,
        file_path: Path,
        source_id: int,
        platform: str | None = None,
    ) -> int:
        """Embed a single markdown file into the knowledge base.

        This function:
        1. Calculates file hash to detect changes
        2. Skips if file already indexed and unchanged
        3. Removes old chunks if file was modified
        4. Splits content into chunks
        5. Generates embeddings for each chunk
        6. Stores chunks in database

        Args:
            file_path: Path to markdown file
            source_id: Knowledge source ID from knowledge_sources table
            platform: Optional platform tag (e.g., "cisco_ios", "huawei_vrp")

        Returns:
            Number of chunks indexed

        Example:
            >>> count = embedder.embed_file(Path("docs/BGP-troubleshooting.md"), source_id=1)
            >>> print(f"Indexed {count} chunks")
        """
        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return 0

        # Calculate file hash
        file_hash = hashlib.md5(content.encode()).hexdigest()

        # Check if already indexed and unchanged
        conn = duckdb.connect(self.db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM knowledge_chunks WHERE file_path = ? AND file_hash = ?",
                [str(file_path), file_hash],
            ).fetchone()

            if existing:
                # Already indexed, skip
                return 0

            # Remove old chunks if file was modified
            conn.execute("DELETE FROM knowledge_chunks WHERE file_path = ?", [str(file_path)])

            # Split into chunks
            chunks = self.splitter.split_text(content)

            if not chunks:
                print(f"Warning: No chunks generated from {file_path}")
                return 0

            # Generate embeddings for each chunk
            for i, chunk in enumerate(chunks):
                # Extract title (first line, remove # markers)
                title = chunk.split("\n")[0].lstrip("#").strip()[:100]
                if not title:
                    title = file_path.stem

                # Generate embedding
                try:
                    embedding = self.embeddings.embed_query(chunk)
                except Exception as e:
                    print(
                        f"Warning: Could not generate embedding for chunk {i} in {file_path}: {e}"
                    )
                    continue

                # Store in database
                conn.execute(
                    """
                    INSERT INTO knowledge_chunks
                    (source_id, file_path, chunk_index, title, content, platform, embedding, file_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [source_id, str(file_path), i, title, chunk, platform, embedding, file_hash],
                )

            conn.commit()
            return len(chunks)

        except Exception as e:
            print(f"Error embedding {file_path}: {e}")
            return 0
        finally:
            conn.close()

    def embed_directory(
        self,
        directory: Path,
        source_id: int,
        platform: str | None = None,
        recursive: bool = True,
    ) -> dict[str, int]:
        """Embed all markdown files in a directory.

        Args:
            directory: Path to directory containing markdown files
            source_id: Knowledge source ID from knowledge_sources table
            platform: Optional platform tag (e.g., "cisco_ios", "huawei_vrp")
            recursive: Whether to search subdirectories (default: True)

        Returns:
            Dictionary with stats: {"indexed": count, "skipped": count, "errors": count}

        Example:
            >>> stats = embedder.embed_directory(Path("docs/cisco"), source_id=1, platform="cisco_ios")
            >>> print(f"Indexed: {stats['indexed']}, Skipped: {stats['skipped']}")
        """
        if not directory.exists():
            print(f"Error: Directory does not exist: {directory}")
            return {"indexed": 0, "skipped": 0, "errors": 0}

        # Find all markdown files
        if recursive:
            md_files = list(directory.rglob("*.md"))
        else:
            md_files = list(directory.glob("*.md"))

        if not md_files:
            print(f"Warning: No markdown files found in {directory}")
            return {"indexed": 0, "skipped": 0, "errors": 0}

        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        for md_file in md_files:
            try:
                count = self.embed_file(md_file, source_id, platform)
                if count > 0:
                    stats["indexed"] += count
                    stats["skipped"] += 0
                else:
                    stats["skipped"] += 1
            except Exception as e:
                print(f"Error embedding {md_file}: {e}")
                stats["errors"] += 1

        return stats

    def get_embedding_dimension(self) -> int:
        """Get the dimension of the embedding vectors.

        Returns:
            Embedding dimension (768 for nomic-embed-text, 1536 for text-embedding-3-small)

        Example:
            >>> dim = embedder.get_embedding_dimension()
            >>> print(f"Embedding dimension: {dim}")
        """
        # Test with a simple query
        test_vector = self.embeddings.embed_query("test")
        return len(test_vector)

    def test_connection(self) -> bool:
        """Test if embedding service is available.

        Returns:
            True if embeddings work, False otherwise

        Example:
            >>> if embedder.test_connection():
            ...     print("✅ Embeddings working")
            ... else:
            ...     print("❌ Embeddings not available")
        """
        try:
            _ = self.embeddings.embed_query("test")
            return True
        except Exception as e:
            print(f"Embedding connection test failed: {e}")
            return False
