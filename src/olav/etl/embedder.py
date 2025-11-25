"""Document embedding initialization service.

Scans the documents directory and reports discovered files. Placeholder
implementation so the embedder container starts successfully. Extend later
with real RAG indexing logic (OpenSearch vector ingest, chunking, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path

from config.settings import DATA_DIR  # type: ignore

from olav.core.settings import settings as env_settings  # type: ignore


def main() -> None:
    docs_dir = Path(os.getenv("DOCUMENTS_DIR", str(DATA_DIR / "documents")))
    if not docs_dir.exists():
        print(f"[embedder] Documents directory not found: {docs_dir}")
        return

    files = [p for p in docs_dir.rglob("*") if p.is_file()]
    print(f"[embedder] Environment: {env_settings.environment}")
    print(f"[embedder] Found {len(files)} document files in {docs_dir}:")
    for p in files[:50]:  # limit output
        print(f" - {p.relative_to(docs_dir)}")
    if len(files) > 50:
        print(f"[embedder] ... ({len(files) - 50} more)")
    print("[embedder] Placeholder complete. Ready for indexing extension.")


if __name__ == "__main__":  # pragma: no cover
    main()
