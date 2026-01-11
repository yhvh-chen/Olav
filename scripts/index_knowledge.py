#!/usr/bin/env python3
"""Index markdown files into the knowledge database.

This script is used to manually index knowledge files (vendor docs, team wiki,
learned solutions) into the knowledge database for semantic search.

Usage:
    # Initialize database and index team wiki
    python scripts/index_knowledge.py --init --source team_wiki --path ./docs/wiki/

    # Index Cisco documentation
    python scripts/index_knowledge.py --source cisco_ios_xe --path ./docs/cisco/ --platform cisco_ios

    # Index learned solutions
    python scripts/index_knowledge.py --source learned --path .olav/knowledge/solutions/

Phase 4: Knowledge Base Integration
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import settings
from olav.core.database import init_knowledge_db
from olav.tools.knowledge_embedder import KnowledgeEmbedder


def register_source(conn, source_name: str, source_path: Path, platform: str = None) -> int:
    """Register a knowledge source in the database.

    Args:
        conn: DuckDB connection
        source_name: Unique source identifier (e.g., "team_wiki", "cisco_ios_xe")
        source_path: Path to source files
        platform: Optional platform tag (e.g., "cisco_ios", "huawei_vrp")

    Returns:
        Source ID
    """
    # Check if source already exists
    existing = conn.execute(
        "SELECT id FROM knowledge_sources WHERE name = ?",
        [source_name],
    ).fetchone()

    if existing:
        source_id = existing[0]
        print(f"  Using existing source: {source_name} (ID: {source_id})")

        # Update indexed_at timestamp
        conn.execute(
            "UPDATE knowledge_sources SET indexed_at = CURRENT_TIMESTAMP WHERE id = ?",
            [source_id],
        )
        conn.commit()
        return source_id

    # Create new source
    conn.execute(
        """
        INSERT INTO knowledge_sources (name, type, base_path, platform)
        VALUES (?, ?, ?, ?)
        """,
        [source_name, "manual", str(source_path.absolute()), platform],
    )
    conn.commit()

    # Get the inserted ID (DuckDB doesn't have cursor.lastrowid)
    result = conn.execute(
        "SELECT max(id) FROM knowledge_sources WHERE name = ?",
        [source_name]
    ).fetchone()
    source_id = result[0] if result else None
    print(f"  Created new source: {source_name} (ID: {source_id})")

    return source_id


def main() -> None:
    """Main entry point for knowledge indexing."""
    parser = argparse.ArgumentParser(
        description="Index markdown files into the knowledge database",
        epilog="""
Examples:
  # Initialize database and index team wiki
  %(prog)s --init --source team_wiki --path ./docs/wiki/

  # Index Cisco documentation
  %(prog)s --source cisco_ios_xe --path ./docs/cisco/ --platform cisco_ios

  # Index learned solutions
  %(prog)s --source learned --path .olav/knowledge/solutions/
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize knowledge database (creates tables and indexes)",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source name (e.g., team_wiki, cisco_ios_xe, learned)",
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Path to markdown files or directory",
    )
    parser.add_argument(
        "--platform",
        help="Platform tag (e.g., cisco_ios, huawei_vrp, juniper_junos)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to knowledge database (default: .olav/data/knowledge.db)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Search subdirectories recursively (default: True)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test embedding connection before indexing",
    )

    args = parser.parse_args()

    # Validate path
    source_path = Path(args.path)
    if not source_path.exists():
        print(f"❌ Error: Path does not exist: {source_path}")
        sys.exit(1)

    print("\n📚 Knowledge Indexing Tool")
    print(f"   Source: {args.source}")
    print(f"   Path: {source_path.absolute()}")
    if args.platform:
        print(f"   Platform: {args.platform}")
    print()

    # Initialize database if requested
    if args.init:
        print("🔧 Initializing knowledge database...")
        db_path = args.db or str(Path(settings.agent_dir) / "data" / "knowledge.db")
        init_knowledge_db(db_path)
        print(f"✅ Initialized database at {db_path}")
        print()

    # Create embedder
    print("🤖 Initializing embedding model (this may take a moment on first run)...")
    embedder = KnowledgeEmbedder(db_path=args.db)

    # Test embedding connection if requested
    if args.test:
        print("🔍 Testing embedding connection...")
        if embedder.test_connection():
            print("✅ Embedding connection successful")
            embedding_dim = embedder.get_embedding_dimension()
            print(f"   Embedding dimension: {embedding_dim}")
        else:
            print("❌ Embedding connection failed")
            print("   Please check:")
            print("   - Ollama is running: ollama serve")
            print("   - Model is pulled: ollama pull nomic-embed-text")
            print("   - Base URL is correct: http://localhost:11434")
            sys.exit(1)
        print()

    # Register source
    import duckdb
    conn = duckdb.connect(args.db or str(Path(settings.agent_dir) / "data" / "knowledge.db"))
    try:
        source_id = register_source(conn, args.source, source_path, args.platform)
    finally:
        conn.close()

    # Index files
    print(f"📖 Indexing files from {source_path}...")
    print()

    if source_path.is_file():
        # Index single file
        count = embedder.embed_file(source_path, source_id, args.platform)
        print(f"✅ Indexed {count} chunks from {source_path.name}")
    else:
        # Index directory
        stats = embedder.embed_directory(source_path, source_id, args.platform, args.recursive)
        print()
        print("📊 Indexing Summary:")
        print(f"   Files processed: {stats['indexed'] + stats['skipped']}")
        print(f"   Chunks indexed: {stats['indexed']}")
        print(f"   Files skipped (unchanged): {stats['skipped']}")
        if stats['errors'] > 0:
            print(f"   Errors: {stats['errors']}")

    print()
    print("✅ Indexing complete!")


if __name__ == "__main__":
    main()
