"""Document indexing tools for Agent use.

Provides LangChain tools for synchronous document indexing.
Documents are indexed immediately when the tool is called.

Tools:
- index_document: Index a single document to RAG knowledge base
- index_directory: Index a directory of documents

Note: These tools execute synchronously and may take time for large files.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Valid file extensions for indexing
VALID_EXTENSIONS = {".pdf", ".md", ".txt", ".yaml", ".yml"}


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create new loop for nested async
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool
def index_document(
    file_path: str,
    vendor: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    """Index a document to the RAG knowledge base.

    Use this tool when the user wants to add a document to the searchable
    knowledge base. The document will be indexed immediately.

    Supported formats: PDF, Markdown (.md), YAML, Text (.txt)

    Args:
        file_path: Path to the document file (absolute or relative to data/documents)
        vendor: Optional vendor tag (cisco, arista, juniper, etc.)
        document_type: Optional document type (manual, configuration, rfc, etc.)

    Returns:
        Dictionary with indexing result and statistics

    Example:
        >>> index_document("cisco/nxos_config_guide.pdf", vendor="cisco")
        {"status": "success", "chunks_indexed": 45, "message": "..."}
    """
    # Normalize path
    path = Path(file_path)
    if not path.is_absolute():
        from config.settings import DATA_DIR

        path = DATA_DIR / "documents" / file_path

    # Validate file exists
    if not path.exists():
        return {
            "status": "error",
            "message": f"File not found: {file_path}",
            "chunks_indexed": 0,
        }

    # Validate file type
    if path.suffix.lower() not in VALID_EXTENSIONS:
        return {
            "status": "error",
            "message": f"Unsupported file type: {path.suffix}. Supported: {VALID_EXTENSIONS}",
            "chunks_indexed": 0,
        }

    async def _index() -> dict[str, Any]:
        try:
            from olav.etl.document_indexer import DocumentIndexer, EmbeddingService
            from olav.etl.document_loader import load_and_chunk_documents

            # Load and chunk document
            logger.info(f"Loading document: {path}")
            chunks = load_and_chunk_documents(
                [path],
                default_vendor=vendor,
                default_doc_type=document_type,
            )

            if not chunks:
                return {
                    "status": "error",
                    "message": f"Failed to load or chunk document: {path.name}",
                    "chunks_indexed": 0,
                }

            # Embed and index
            logger.info(f"Embedding {len(chunks)} chunks...")
            embedding_service = EmbeddingService()

            # Embed all chunks
            texts = [c.content for c in chunks]
            embeddings = await embedding_service.embed_batch(texts)

            # Create embedded chunks
            from olav.etl.document_indexer import EmbeddedChunk

            embedded_chunks = [
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    embedding=emb,
                    metadata=chunk.metadata,
                )
                for chunk, emb in zip(chunks, embeddings, strict=False)
            ]

            # Index to OpenSearch
            logger.info(f"Indexing {len(embedded_chunks)} chunks to OpenSearch...")
            indexer = DocumentIndexer()
            await indexer.ensure_index()
            success, failed = await indexer.index_chunks_bulk(embedded_chunks)

            return {
                "status": "success" if failed == 0 else "partial",
                "message": f"Indexed {success} chunks from '{path.name}'",
                "file": str(path),
                "chunks_indexed": success,
                "chunks_failed": failed,
                "vendor": vendor,
                "document_type": document_type,
            }

        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Indexing failed: {e!s}",
                "chunks_indexed": 0,
            }

    return _run_async(_index())


@tool
def index_directory(
    directory_path: str,
    pattern: str = "*",
    recursive: bool = True,
    vendor: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    """Index a directory of documents to the RAG knowledge base.

    Use this tool when the user wants to index multiple documents at once.
    All matching documents in the directory will be processed.

    Args:
        directory_path: Path to directory (absolute or relative to data/documents)
        pattern: File pattern to match (e.g., "*.pdf", "cisco_*")
        recursive: Whether to search subdirectories
        vendor: Optional vendor tag for all documents
        document_type: Optional document type for all documents

    Returns:
        Dictionary with indexing statistics

    Example:
        >>> index_directory("vendor_docs/cisco", pattern="*.pdf", vendor="cisco")
        {"status": "success", "files_processed": 15, "total_chunks": 450}
    """
    # Normalize path
    path = Path(directory_path)
    if not path.is_absolute():
        from config.settings import DATA_DIR

        path = DATA_DIR / "documents" / directory_path

    # Validate directory exists
    if not path.exists():
        return {
            "status": "error",
            "message": f"Directory not found: {directory_path}",
            "files_processed": 0,
        }

    if not path.is_dir():
        return {
            "status": "error",
            "message": f"Not a directory: {directory_path}",
            "files_processed": 0,
        }

    # Find matching files
    files = list(path.rglob(pattern)) if recursive else list(path.glob(pattern))

    matching_files = [f for f in files if f.suffix.lower() in VALID_EXTENSIONS and f.is_file()]

    if not matching_files:
        return {
            "status": "error",
            "message": f"No matching documents found in {directory_path} with pattern '{pattern}'",
            "files_processed": 0,
        }

    async def _index_all() -> dict[str, Any]:
        try:
            from olav.etl.document_indexer import (
                DocumentIndexer,
                EmbeddedChunk,
                EmbeddingService,
            )
            from olav.etl.document_loader import load_and_chunk_documents

            # Load and chunk all documents
            logger.info(f"Loading {len(matching_files)} documents from {path}...")
            all_chunks = load_and_chunk_documents(
                matching_files,
                default_vendor=vendor,
                default_doc_type=document_type,
            )

            if not all_chunks:
                return {
                    "status": "error",
                    "message": "Failed to load any documents",
                    "files_processed": 0,
                }

            # Embed all chunks (in batches for efficiency)
            logger.info(f"Embedding {len(all_chunks)} chunks...")
            embedding_service = EmbeddingService()

            texts = [c.content for c in all_chunks]
            embeddings = await embedding_service.embed_batch(texts)

            # Create embedded chunks
            embedded_chunks = [
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    embedding=emb,
                    metadata=chunk.metadata,
                )
                for chunk, emb in zip(all_chunks, embeddings, strict=False)
            ]

            # Index to OpenSearch
            logger.info(f"Indexing {len(embedded_chunks)} chunks to OpenSearch...")
            indexer = DocumentIndexer()
            await indexer.ensure_index()
            success, failed = await indexer.index_chunks_bulk(embedded_chunks)

            return {
                "status": "success" if failed == 0 else "partial",
                "message": f"Indexed {success} chunks from {len(matching_files)} files",
                "directory": str(path),
                "files_found": len(matching_files),
                "files_processed": len(matching_files),
                "total_chunks": success,
                "chunks_failed": failed,
                "vendor": vendor,
                "document_type": document_type,
            }

        except Exception as e:
            logger.error(f"Directory indexing failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Indexing failed: {e!s}",
                "files_processed": 0,
            }

    return _run_async(_index_all())


# Export tool list for agent registration
INDEXING_TOOLS = [
    index_document,
    index_directory,
]
