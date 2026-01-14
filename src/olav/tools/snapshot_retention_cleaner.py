"""Snapshot Retention Cleaner for OLAV v0.8.2+

Automatically clean up old snapshot data based on retention policy.

Usage:
    # Clean snapshots older than 30 days (default)
    uv run python -m olav.tools.snapshot_retention_cleaner
    
    # Custom retention period
    uv run python -m olav.tools.snapshot_retention_cleaner --days 60
    
    # Dry run (show what would be deleted)
    uv run python -m olav.tools.snapshot_retention_cleaner --dry-run
"""

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from config.paths import RETENTION_DAYS, SNAPSHOT_SYNC_DIR


def clean_old_snapshots(retention_days: int = RETENTION_DAYS, dry_run: bool = False) -> dict[str, int]:
    """Clean up snapshots older than retention period.
    
    Args:
        retention_days: Number of days to retain snapshots
        dry_run: If True, only report what would be deleted
        
    Returns:
        Dictionary with cleanup statistics
    """
    if not SNAPSHOT_SYNC_DIR.exists():
        return {"deleted": 0, "retained": 0, "freed_bytes": 0}
    
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    retained_count = 0
    freed_bytes = 0
    
    print(f"Retention policy: {retention_days} days")
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')}")
    print(f"Scanning: {SNAPSHOT_SYNC_DIR}")
    print("-" * 60)
    
    # Iterate through date-named directories (YYYY-MM-DD format)
    for snapshot_dir in sorted(SNAPSHOT_SYNC_DIR.iterdir()):
        if not snapshot_dir.is_dir():
            continue
            
        # Skip 'latest' symlink
        if snapshot_dir.name == "latest":
            continue
            
        # Parse date from directory name
        try:
            snapshot_date = datetime.strptime(snapshot_dir.name, "%Y-%m-%d")
        except ValueError:
            print(f"⚠️  Skipping non-date directory: {snapshot_dir.name}")
            continue
        
        # Check if snapshot is older than cutoff
        if snapshot_date < cutoff_date:
            size_bytes = sum(f.stat().st_size for f in snapshot_dir.rglob("*") if f.is_file())
            size_mb = size_bytes / (1024 * 1024)
            
            if dry_run:
                print(f"🗑️  Would delete: {snapshot_dir.name} ({size_mb:.1f} MB)")
            else:
                print(f"🗑️  Deleting: {snapshot_dir.name} ({size_mb:.1f} MB)")
                shutil.rmtree(snapshot_dir)
            
            deleted_count += 1
            freed_bytes += size_bytes
        else:
            retained_count += 1
            print(f"✅ Retaining: {snapshot_dir.name}")
    
    print("-" * 60)
    print(f"\nSummary:")
    print(f"  Deleted: {deleted_count} snapshots")
    print(f"  Retained: {retained_count} snapshots")
    print(f"  Freed space: {freed_bytes / (1024 * 1024):.1f} MB")
    
    if dry_run and deleted_count > 0:
        print(f"\n💡 This was a dry run. Use without --dry-run to actually delete.")
    
    return {
        "deleted": deleted_count,
        "retained": retained_count,
        "freed_bytes": freed_bytes,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Clean up old network snapshots based on retention policy"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=RETENTION_DAYS,
        help=f"Retention period in days (default: {RETENTION_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    
    args = parser.parse_args()
    
    clean_old_snapshots(retention_days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
