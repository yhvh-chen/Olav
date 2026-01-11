#!/usr/bin/env python3
"""
Search knowledge base - query unified FTS + Vector knowledge database.

Usage: /search-knowledge <query> [--type <type>] [--limit <limit>]

Searches the unified knowledge base combining:
- Full-Text Search (FTS) for keyword matching
- Vector search (HNSW) for semantic similarity

Examples:
    /search-knowledge "optical module aging"
    /search-knowledge "BGP neighbor flapping" --limit 5
    /search-knowledge "CRC errors" --type solution
    /search-knowledge "interface errors" --type both

Options:
    --type        Search type: knowledge, solution, or both (default: both)
    --limit       Maximum results to return (default: 5)
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
    """Search unified knowledge base."""
    parser = argparse.ArgumentParser(
        description="Search unified knowledge database (FTS + Vector)",
        prog="/search-knowledge"
    )
    parser.add_argument("query", help="Search query (e.g., 'optical module aging')")
    parser.add_argument(
        "--type",
        "-t",
        dest="search_type",
        default="both",
        choices=["knowledge", "solution", "both"],
        help="Search type (default: both)"
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=5,
        help="Maximum results to return (default: 5)"
    )

    args = parser.parse_args()

    try:
        from olav.tools.capabilities import search_knowledge

        result = search_knowledge.invoke({
            "query": args.query,
            "search_type": args.search_type,
            "limit": args.limit,
        })

        print(result)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
