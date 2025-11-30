"""Document embedding service for RAG indexing.

Generates vector embeddings for document chunks and indexes them
in OpenSearch for semantic search.

Supports:
- OpenAI embeddings (text-embedding-3-small, text-embedding-ada-002)
- Local embeddings via sentence-transformers (optional)
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

from olav.core.settings import settings as env_settings
from olav.etl.document_loader import DocumentChunk, load_and_chunk_documents

logger = logging.getLogger(__name__)

# OpenSearch index configuration
DOCS_INDEX_NAME = "olav-docs"
EMBEDDING_DIMENSION = 1536  # OpenAI text-embedding-3-small


@dataclass
class EmbeddedChunk:
    """A document chunk with its embedding vector.

    Attributes:
        chunk: Original document chunk
        embedding: Vector embedding
        doc_id: Document ID for OpenSearch
    """

    chunk: DocumentChunk
    embedding: list[float]
    doc_id: str = ""

    def __post_init__(self) -> None:
        if not self.doc_id:
            # Generate stable doc_id from content hash
            content_hash = hashlib.sha256(self.chunk.content.encode("utf-8")).hexdigest()[:16]
            source = self.chunk.metadata.get("source", "unknown")
            chunk_idx = self.chunk.metadata.get("chunk_index", 0)
            self.doc_id = f"{Path(source).stem}_{chunk_idx}_{content_hash}"


class EmbeddingService:
    """Service for generating text embeddings.

    Supports OpenAI API for production use. Falls back to
    zero-vector placeholders for testing without API.

    Example:
        >>> service = EmbeddingService()
        >>> embedding = await service.embed_text("Hello world")
        >>> embeddings = await service.embed_batch(["Hello", "World"])
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> None:
        """Initialize embedding service.

        Args:
            model: OpenAI embedding model name
            api_key: OpenAI API key (defaults to env)
        """
        self.model = model
        self.api_key = api_key or env_settings.llm_api_key
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except ImportError as e:
                msg = "openai package required for embeddings"
                raise ImportError(msg) from e
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (dimension depends on model)
        """
        if not self.api_key:
            logger.warning("No API key, returning zero vector")
            return [0.0] * EMBEDDING_DIMENSION

        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return [0.0] * EMBEDDING_DIMENSION

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for API calls

        Returns:
            List of embedding vectors
        """
        if not self.api_key:
            logger.warning("No API key, returning zero vectors")
            return [[0.0] * EMBEDDING_DIMENSION for _ in texts]

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model,
                )
                batch_embeddings = [d.embedding for d in response.data]
                all_embeddings.extend(batch_embeddings)
                logger.debug(f"Embedded batch {i // batch_size + 1}")
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                all_embeddings.extend([[0.0] * EMBEDDING_DIMENSION] * len(batch))

        return all_embeddings


class DocumentIndexer:
    """Index document embeddings in OpenSearch.

    Creates and manages the olav-docs index with kNN vector search.

    Example:
        >>> indexer = DocumentIndexer()
        >>> await indexer.ensure_index()
        >>> await indexer.index_chunks(embedded_chunks)
    """

    def __init__(
        self,
        opensearch_url: str | None = None,
        index_name: str = DOCS_INDEX_NAME,
    ) -> None:
        """Initialize document indexer.

        Args:
            opensearch_url: OpenSearch URL (defaults to env)
            index_name: Index name for documents
        """
        self.url = opensearch_url or env_settings.opensearch_url
        self.index_name = index_name
        self.client = OpenSearch(
            hosts=[self.url],
            http_compress=True,
            use_ssl=False,
            verify_certs=False,
        )

    def get_index_mapping(self) -> dict[str, Any]:
        """Get OpenSearch index mapping for document chunks.

        Returns:
            Index mapping with kNN vector field
        """
        return {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 100,
                },
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "content": {
                        "type": "text",
                        "analyzer": "standard",
                    },
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": EMBEDDING_DIMENSION,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24,
                            },
                        },
                    },
                    "source": {"type": "keyword"},
                    "vendor": {"type": "keyword"},
                    "document_type": {"type": "keyword"},
                    "format": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "total_chunks": {"type": "integer"},
                    "title": {"type": "text"},
                    "page_count": {"type": "integer"},
                    "indexed_at": {"type": "date"},
                },
            },
        }

    async def ensure_index(self, recreate: bool = False) -> bool:
        """Ensure the document index exists.

        Args:
            recreate: Delete and recreate if exists

        Returns:
            True if index exists/created
        """
        try:
            exists = self.client.indices.exists(index=self.index_name)

            if exists and recreate:
                logger.info(f"Deleting existing index: {self.index_name}")
                self.client.indices.delete(index=self.index_name)
                exists = False

            if not exists:
                logger.info(f"Creating index: {self.index_name}")
                self.client.indices.create(
                    index=self.index_name,
                    body=self.get_index_mapping(),
                )

            return True
        except Exception as e:
            logger.error(f"Failed to ensure index: {e}")
            return False

    async def index_chunk(self, embedded: EmbeddedChunk) -> bool:
        """Index a single embedded chunk.

        Args:
            embedded: Embedded chunk to index

        Returns:
            True if indexed successfully
        """
        from datetime import UTC, datetime

        doc = {
            "content": embedded.chunk.content,
            "embedding": embedded.embedding,
            "indexed_at": datetime.now(UTC).isoformat(),
            **embedded.chunk.metadata,
        }

        try:
            self.client.index(
                index=self.index_name,
                id=embedded.doc_id,
                body=doc,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to index chunk {embedded.doc_id}: {e}")
            return False

    async def index_chunks_bulk(
        self,
        embedded_chunks: list[EmbeddedChunk],
        batch_size: int = 100,
    ) -> tuple[int, int]:
        """Bulk index multiple embedded chunks.

        Args:
            embedded_chunks: List of embedded chunks
            batch_size: Bulk index batch size

        Returns:
            Tuple of (success_count, failure_count)
        """
        from datetime import UTC, datetime

        def generate_actions() -> Iterator[dict[str, Any]]:
            for embedded in embedded_chunks:
                yield {
                    "_index": self.index_name,
                    "_id": embedded.doc_id,
                    "_source": {
                        "content": embedded.chunk.content,
                        "embedding": embedded.embedding,
                        "indexed_at": datetime.now(UTC).isoformat(),
                        **embedded.chunk.metadata,
                    },
                }

        try:
            success, failures = helpers.bulk(
                self.client,
                generate_actions(),
                chunk_size=batch_size,
                raise_on_error=False,
            )

            failure_count = len(failures) if isinstance(failures, list) else 0
            logger.info(f"Bulk indexed: {success} success, {failure_count} failures")
            return success, failure_count
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return 0, len(embedded_chunks)

    async def search_similar(
        self,
        query_embedding: list[float],
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents using kNN.

        Args:
            query_embedding: Query vector
            k: Number of results
            filters: Optional filters (vendor, document_type)

        Returns:
            List of matching documents with scores
        """
        query: dict[str, Any] = {
            "size": k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_embedding,
                        "k": k,
                    },
                },
            },
        }

        # Add filters if provided
        if filters:
            filter_clauses = []
            for field, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {field: value}})
                else:
                    filter_clauses.append({"term": {field: value}})

            query["query"] = {
                "bool": {
                    "must": [query["query"]],
                    "filter": filter_clauses,
                },
            }

        try:
            response = self.client.search(
                index=self.index_name,
                body=query,
            )

            results = []
            for hit in response["hits"]["hits"]:
                result = hit["_source"].copy()
                result["_score"] = hit["_score"]
                result["_id"] = hit["_id"]
                # Remove embedding from results (too large)
                result.pop("embedding", None)
                results.append(result)

            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def get_stats(self) -> dict[str, Any]:
        """Get index statistics.

        Returns:
            Index stats (doc count, size, etc.)
        """
        try:
            stats = self.client.indices.stats(index=self.index_name)
            primaries = stats["indices"][self.index_name]["primaries"]
            return {
                "doc_count": primaries["docs"]["count"],
                "size_bytes": primaries["store"]["size_in_bytes"],
                "index_name": self.index_name,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}


class RAGIndexer:
    """High-level RAG indexing pipeline.

    Combines document loading, embedding, and indexing into
    a single pipeline for easy document ingestion.

    Example:
        >>> indexer = RAGIndexer()
        >>> await indexer.index_directory(Path("data/documents"))
    """

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        """Initialize RAG indexer.

        Args:
            embedding_model: OpenAI embedding model
            chunk_size: Document chunk size
            chunk_overlap: Chunk overlap
        """
        self.embedding_service = EmbeddingService(model=embedding_model)
        self.document_indexer = DocumentIndexer()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def index_directory(
        self,
        directory: Path,
        recreate_index: bool = False,
        batch_size: int = 50,
    ) -> dict[str, Any]:
        """Index all documents in a directory.

        Args:
            directory: Directory containing documents
            recreate_index: Whether to recreate the index
            batch_size: Batch size for embedding and indexing

        Returns:
            Indexing statistics
        """
        # Ensure index exists
        await self.document_indexer.ensure_index(recreate=recreate_index)

        # Load and chunk documents
        chunks = list(
            load_and_chunk_documents(
                directory,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
        )

        if not chunks:
            logger.warning(f"No documents found in {directory}")
            return {"status": "no_documents", "chunks": 0}

        logger.info(f"Loaded {len(chunks)} chunks from {directory}")

        # Embed chunks in batches
        all_embedded: list[EmbeddedChunk] = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]

            embeddings = await self.embedding_service.embed_batch(texts)

            for chunk, embedding in zip(batch, embeddings, strict=False):
                all_embedded.append(EmbeddedChunk(chunk=chunk, embedding=embedding))

            logger.info(
                f"Embedded batch {i // batch_size + 1}/{(len(chunks) + batch_size - 1) // batch_size}"
            )

        # Bulk index
        success, failures = await self.document_indexer.index_chunks_bulk(
            all_embedded,
            batch_size=batch_size,
        )

        stats = await self.document_indexer.get_stats()

        return {
            "status": "completed",
            "chunks_processed": len(chunks),
            "indexed": success,
            "failed": failures,
            "index_stats": stats,
        }

    async def search(
        self,
        query: str,
        k: int = 5,
        vendor: str | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant documents.

        Args:
            query: Search query
            k: Number of results
            vendor: Filter by vendor
            document_type: Filter by document type

        Returns:
            List of relevant document chunks
        """
        # Embed query
        query_embedding = await self.embedding_service.embed_text(query)

        # Build filters
        filters = {}
        if vendor:
            filters["vendor"] = vendor
        if document_type:
            filters["document_type"] = document_type

        # Search
        return await self.document_indexer.search_similar(
            query_embedding,
            k=k,
            filters=filters if filters else None,
        )


async def run_indexing(
    documents_dir: str | Path | None = None,
    recreate: bool = False,
) -> dict[str, Any]:
    """Run document indexing pipeline.

    Main entry point for document indexing.

    Args:
        documents_dir: Documents directory (defaults to data/documents)
        recreate: Whether to recreate the index

    Returns:
        Indexing results
    """
    from config.settings import DATA_DIR  # type: ignore

    if documents_dir is None:
        documents_dir = DATA_DIR / "documents"

    documents_dir = Path(documents_dir)

    if not documents_dir.exists():
        logger.error(f"Documents directory not found: {documents_dir}")
        return {"status": "error", "message": f"Directory not found: {documents_dir}"}

    logger.info(f"Starting document indexing from: {documents_dir}")

    indexer = RAGIndexer()
    results = await indexer.index_directory(documents_dir, recreate_index=recreate)

    logger.info(f"Indexing complete: {results}")
    return results


# CLI entry point
def main() -> None:
    """CLI entry point for document indexing."""
    import asyncio
    import sys

    recreate = "--recreate" in sys.argv

    print(f"[embedder] Starting document RAG indexing (recreate={recreate})")
    print(f"[embedder] OpenSearch URL: {env_settings.opensearch_url}")

    results = asyncio.run(run_indexing(recreate=recreate))

    print(f"[embedder] Results: {results}")


if __name__ == "__main__":  # pragma: no cover
    main()
