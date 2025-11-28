"""Document embedding initialization service.

Indexes documents from the data/documents directory into OpenSearch
for vector similarity search. Supports PDF, Markdown, and text files.

Usage:
    python -m olav.etl.embedder [--recreate]

The --recreate flag will delete and recreate the index.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from config.settings import DATA_DIR  # type: ignore

from olav.core.settings import settings as env_settings  # type: ignore


def main() -> None:
    """Run document indexing pipeline."""
    from olav.etl.document_indexer import run_indexing

    docs_dir = Path(os.getenv("DOCUMENTS_DIR", str(DATA_DIR / "documents")))
    recreate = "--recreate" in sys.argv

    print("[embedder] Starting document RAG indexing")
    print(f"[embedder] Environment: {env_settings.environment}")
    print(f"[embedder] Documents directory: {docs_dir}")
    print(f"[embedder] OpenSearch URL: {env_settings.opensearch_url}")
    print(f"[embedder] Recreate index: {recreate}")

    if not docs_dir.exists():
        print(f"[embedder] Documents directory not found: {docs_dir}")
        return

    # Count files
    files = [p for p in docs_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
    print(f"[embedder] Found {len(files)} document files:")
    for p in files[:20]:
        print(f" - {p.relative_to(docs_dir)}")
    if len(files) > 20:
        print(f"[embedder] ... ({len(files) - 20} more)")

    if not files:
        print("[embedder] No documents to index. Add files to data/documents/")
        return

    # Run indexing
    results = asyncio.run(run_indexing(docs_dir, recreate=recreate))

    print("[embedder] Indexing complete:")
    print(f"  Status: {results.get('status', 'unknown')}")
    print(f"  Chunks processed: {results.get('chunks_processed', 0)}")
    print(f"  Indexed: {results.get('indexed', 0)}")
    print(f"  Failed: {results.get('failed', 0)}")

    if "index_stats" in results:
        stats = results["index_stats"]
        print(f"  Index doc count: {stats.get('doc_count', 'N/A')}")


if __name__ == "__main__":  # pragma: no cover
    main()
