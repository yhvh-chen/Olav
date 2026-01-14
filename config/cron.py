"""Cron Trigger Configuration

User-editable cron configuration for scheduled tasks.
Edit this file to customize your automation schedule.

## How to Use

1. Enable cron scheduling in .env:
   ```
   ENABLE_CRON=true
   ```

2. Edit the schedule below using standard cron syntax:
   ```
   * * * * * - Run every minute
   0 * * * * - Run every hour
   0 6 * * * - Run daily at 6:00 AM
   0 6 * * 1 - Run every Monday at 6:00 AM
   ```

3. Restart OLAV for changes to take effect

## Scheduled Tasks

Tasks are defined in .olav/workflows/*.md files.
Each workflow can specify a default schedule, which you can override here.
"""

# =============================================================================
# Cron Schedule Configuration
# =============================================================================

CRON_SCHEDULES = {
    # Daily network snapshot (formerly daily-sync)
    "network-snapshot": {
        "enabled": True,
        "schedule": "0 6 * * *",  # 6:00 AM daily
        "workflow": "daily-run",
        "args": {
            "group": "all",  # Device group to snapshot
            "stages": ["snapshot", "topology", "inspect", "logs"],  # Full pipeline
        },
    },
    
    # Weekly health report
    "weekly-health-report": {
        "enabled": False,  # Disabled by default
        "schedule": "0 9 * * 1",  # 9:00 AM every Monday
        "workflow": "health-report",
        "args": {
            "group": "all",
            "format": "pdf",  # or "markdown"
        },
    },
    
    # Monthly configuration backup
    "monthly-config-backup": {
        "enabled": False,
        "schedule": "0 2 1 * *",  # 2:00 AM on 1st of each month
        "workflow": "config-backup",
        "args": {
            "group": "core",  # Only backup core devices
            "archive": True,
        },
    },
    
    # Snapshot retention cleanup (weekly)
    "snapshot-cleanup": {
        "enabled": True,
        "schedule": "0 3 * * 0",  # 3:00 AM every Sunday
        "workflow": "retention-cleanup",
        "args": {
            "retention_days": 30,
        },
    },
}


# =============================================================================
# Advanced Configuration
# =============================================================================

# Maximum concurrent cron jobs
MAX_CONCURRENT_JOBS = 1

# Job timeout (seconds) - kill job if it runs longer than this
JOB_TIMEOUT = 3600  # 1 hour

# Send notifications on job failure
NOTIFY_ON_FAILURE = True

# Log directory for cron job execution
CRON_LOG_DIR = ".olav/logs/cron"
