---
name: sync-knowledge
version: 1.0
type: command
platform: all
description: Synchronize knowledge database with filesystem and cleanup orphaned vectors
---

# Sync Knowledge Command

Synchronize the knowledge database with the filesystem. Detects deleted files, removes orphaned vector records, and verifies database consistency.

## Usage

```
/sync-knowledge [--cleanup] [--verbose] [--report]
```

## Options

- **--cleanup, -c**: Remove orphaned vectors from deleted files
- **--verbose, -v**: Print detailed sync information
- **--report, -r**: Generate detailed sync report to file

## Examples

```
/sync-knowledge
/sync-knowledge --cleanup
/sync-knowledge --verbose --report
```

## What It Does

1. **Scans filesystem**: Identifies all knowledge documents
2. **Checks database**: Compares with database records
3. **Detects changes**:
   - New files: Marks for indexing
   - Modified files: Marks for reindexing
   - Deleted files: Marks for cleanup
4. **Cleans orphans**: Optionally removes vectors for deleted documents
5. **Verifies consistency**: Checks for database anomalies

## Sync Report

Generated with `--report` option shows:
- File-by-file sync status
- Detected inconsistencies
- Orphaned vector records
- Recommendations for fixes

## When to Use

- After deleting solution documents
- Before backup or migration
- After failed indexing operations
- Routine maintenance (weekly/monthly)
- To verify database consistency
- When search results seem incorrect

## Cleanup Mode

```
/sync-knowledge --cleanup
```

Automatically:
- Identifies vectors for deleted files
- Removes orphaned vectors
- Logs all cleanup operations
- Verifies removal success

## Output

Shows:
- Files checked
- Files modified
- Files deleted
- Orphaned vectors removed
- Consistency issues found

## Implementation

```python
#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()


def main():
    """Sync knowledge base with filesystem."""
    parser = argparse.ArgumentParser(
        description="Synchronize knowledge database with filesystem",
        prog="/sync-knowledge"
    )
    parser.add_argument(
        "--cleanup",
        "-c",
        action="store_true",
        help="Remove orphaned vectors from deleted files"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed sync information"
    )
    parser.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Generate sync report to file"
    )
    
    args = parser.parse_args()
    
    try:
        from config.settings import settings
        
        print(f"🔄 Syncing knowledge base from {settings.agent_dir}/knowledge/")
        
        # Run sync
        from scripts.sync_knowledge import sync_knowledge_database
        
        stats = sync_knowledge_database(
            agent_dir=settings.agent_dir,
            cleanup=args.cleanup,
            verbose=args.verbose,
            generate_report=args.report
        )
        
        # Print results
        print("\n✅ Knowledge base sync complete!")
        print(f"   Files checked: {stats.get('files_checked', 0)}")
        print(f"   Files modified: {stats.get('files_modified', 0)}")
        print(f"   Files deleted: {stats.get('files_deleted', 0)}")
        print(f"   Orphaned vectors removed: {stats.get('orphans_removed', 0)}")
        print(f"   Consistency issues: {stats.get('consistency_issues', 0)}")
        
        if args.report:
            report_path = Path(settings.agent_dir) / "data" / f"sync_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            print(f"   Detailed report: {report_path}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error syncing knowledge base: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```
