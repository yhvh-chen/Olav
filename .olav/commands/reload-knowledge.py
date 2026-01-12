#!/usr/bin/env python3
"""
Reload knowledge base - reindex knowledge documents into the database.

Usage: /reload-knowledge [--incremental] [--verbose]

Reindexes all knowledge documents in:
- knowledge/solutions/*.md - Troubleshooting case solutions
- knowledge/*.md - General knowledge documents
- skills/*/SKILL.md - Skill strategies and patterns

Examples:
    /reload-knowledge
    /reload-knowledge --incremental
    /reload-knowledge --verbose

Options:
    --incremental    Only index new/modified files (faster)
    --verbose        Print detailed indexing information
    --reset          Clear database and reindex from scratch
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()


def main():
    """Reload and reindex knowledge base."""
    parser = argparse.ArgumentParser(
        description="Reindex knowledge base into vector database", prog="/reload-knowledge"
    )
    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Only index new/modified files (incremental mode)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed indexing information"
    )
    parser.add_argument(
        "--reset", "-r", action="store_true", help="Clear database and reindex from scratch"
    )

    args = parser.parse_args()

    try:
        from config.settings import settings
        from olav.tools.knowledge_embedder import index_knowledge_documents

        print(f"📚 Reloading knowledge base from {settings.agent_dir}/knowledge/")

        # Index documents
        stats = index_knowledge_documents(
            agent_dir=settings.agent_dir,
            incremental=args.incremental,
            reset=args.reset,
            verbose=args.verbose,
        )

        # Print results
        print("\n✅ Knowledge base reload complete!")
        print(f"   Documents indexed: {stats.get('indexed', 0)}")
        print(f"   Documents updated: {stats.get('updated', 0)}")
        print(f"   Documents skipped: {stats.get('skipped', 0)}")
        print(f"   Total vectors: {stats.get('total_vectors', 0)}")
        print(f"   Database location: {settings.agent_dir}/data/knowledge.db")

        return 0

    except Exception as e:
        print(f"❌ Error reloading knowledge base: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
