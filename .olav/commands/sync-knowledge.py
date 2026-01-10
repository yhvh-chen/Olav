#!/usr/bin/env python3
"""
Sync knowledge base - synchronize database with filesystem, detect and clean deletions.

Usage: /sync-knowledge [--cleanup] [--verbose] [--report]

Synchronizes knowledge database with filesystem:
- Detects deleted files
- Removes orphaned vector records
- Updates modified documents
- Verifies database consistency

Examples:
    /sync-knowledge
    /sync-knowledge --cleanup
    /sync-knowledge --verbose --report

Options:
    --cleanup       Remove orphaned vectors (detected but not deleted)
    --verbose       Print detailed sync information
    --report        Generate sync report to file
"""
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
