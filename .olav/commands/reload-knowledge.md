---
name: reload-knowledge
version: 1.0
type: command
platform: all
description: Reindex knowledge documents into the vector database
---

# Reload Knowledge Command

Reindex all knowledge documents into the vector database. Useful after adding new solutions, updating documents, or recovering from database corruption.

## Usage

```
/reload-knowledge [--incremental] [--verbose] [--reset]
```

## Options

- **--incremental, -i**: Only index new/modified files (faster incremental mode)
- **--verbose, -v**: Print detailed indexing information
- **--reset, -r**: Clear database and reindex from scratch (full rebuild)

## Examples

```
/reload-knowledge
/reload-knowledge --incremental
/reload-knowledge --verbose
/reload-knowledge --reset
```

## Indexed Directories

The command reindexes:
- `knowledge/solutions/*.md` - Troubleshooting case solutions
- `knowledge/*.md` - General knowledge documents
- `skills/*/SKILL.md` - Skill strategies and patterns

## Modes

### Normal Mode (Incremental)
```
/reload-knowledge
```
- Indexes all files
- Fast if files haven't changed
- Use after adding new documents

### Incremental Mode
```
/reload-knowledge --incremental
```
- Only reindexes modified files
- Fastest for frequent updates
- Useful in production

### Full Reset
```
/reload-knowledge --reset
```
- Clears entire database
- Reindexes all documents from scratch
- Use for database corruption recovery

## Output

Shows:
- Number of documents indexed
- Number of documents updated
- Number of documents skipped
- Total vectors in database
- Database location

## When to Use

- After adding new solution cases
- After updating skill documents
- After modifying knowledge base
- To rebuild corrupted database
- To recalculate vector embeddings

## Implementation

```python
#!/usr/bin/env python3
import sys
import argparse
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
        description="Reindex knowledge base into vector database",
        prog="/reload-knowledge"
    )
    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Only index new/modified files (incremental mode)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed indexing information"
    )
    parser.add_argument(
        "--reset",
        "-r",
        action="store_true",
        help="Clear database and reindex from scratch"
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
            verbose=args.verbose
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
```
