---
name: search-knowledge
version: 1.0
type: command
platform: all
description: Query unified FTS + Vector knowledge database with semantic search
---

# Search Knowledge Command

Search the unified knowledge base combining Full-Text Search (FTS) and Vector search (HNSW) for both keyword and semantic matching.

## Usage

```
/search-knowledge <query> [--type <type>] [--limit <limit>]
```

## Arguments

- **query**: Search query (e.g., 'optical module aging', 'BGP neighbor flapping')

## Options

- **--type, -t**: Search type - knowledge, solution, or both (default: both)
- **--limit, -l**: Maximum results to return (default: 5)

## Examples

```
/search-knowledge "optical module aging"
/search-knowledge "BGP neighbor flapping" --limit 5
/search-knowledge "CRC errors" --type solution
/search-knowledge "interface errors" --type both
```

## Search Types

- **knowledge**: Search general knowledge documents and notes
- **solution**: Search successful troubleshooting cases
- **both**: Search both knowledge and solutions (default)

## Features

- **FTS (Full-Text Search)**: Keyword matching for exact terms
- **Vector Search (HNSW)**: Semantic similarity for related concepts
- **Hybrid Results**: Combines both methods for comprehensive search
- **Relevance Ranking**: Results ranked by relevance score

## Output Format

Results include:
- Document title or case name
- Relevance score (0-1, higher = more relevant)
- Snippet of matching content
- Source path (knowledge/, solutions/, etc.)

## Implementation

```python
#!/usr/bin/env python3
import sys
import json
import argparse
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
```
