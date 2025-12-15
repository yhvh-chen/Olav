# Log Inspection Design

## Overview

This document describes the design for log-based inspection in OLAV, enabling proactive fault discovery through OpenSearch syslog analysis.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Inspection    │     │   Admin Review   │     │  Expert Mode   │
│  (Scheduled)    │────▶│  (Log Summary)   │────▶│  (On-demand)   │
└─────────────────┘     └──────────────────┘     └────────────────┘
        │                        │                       │
        ▼                        ▼                       ▼
  Search keywords        Display: 5 anomalies      Admin selects issue
  DOWN/ERROR             - R1: BGP DOWN (3x)       → "Analyze R1 BGP"
  Aggregate & dedupe     - R2: Interface flapping  → Expert deep dive
                         - ...
```

## Design Principles

1. **Human-in-the-Loop**: Admin reviews log summary before triggering Expert analysis
2. **Aggregation**: Deduplicate events to avoid alert fatigue
3. **Separation of Concerns**: Inspection discovers, Expert analyzes
4. **Audit-Friendly**: Clear reports for compliance

## Implementation

### Phase 1: Log Summary Inspection

A new inspection type `log-summary` that:
1. Searches OpenSearch `syslog-raw` index for keywords
2. Aggregates by device + event type
3. Deduplicates within time window
4. Generates Markdown summary report

#### YAML Configuration

```yaml
# config/inspections/log-summary.yaml
name: log-summary
description: Daily log summary for fault discovery
type: log-summary

search:
  index: syslog-raw
  time_range: "24h"
  keywords:
    critical:
      - "DOWN"
      - "FAILED"
      - "ERROR"
      - "CRITICAL"
      - "NEIGHBOR.*LOST"
    warning:
      - "WARNING"
      - "THRESHOLD"
      - "FLAPPING"
      - "TIMEOUT"

aggregation:
  group_by:
    - device_ip
    - keyword_category
  dedupe_window: "5m"
  max_events_per_group: 10

output:
  format: markdown
  sections:
    - critical_events
    - warning_events
    - affected_devices
    - suggested_commands
```

### Phase 2: Expert Mode Integration

Admin reviews the log summary report and manually triggers Expert analysis:

```bash
# After reviewing log summary
olav -E -q "Analyze R1 BGP neighbor flapping root cause"
```

Expert mode's Round 0 automatically fetches related syslog context.

## Report Format

```markdown
📋 Daily Log Summary (2025-12-08)
═══════════════════════════════════════════════════════════════

🔴 Critical Events (3)
┌──────────┬─────────────────────────────┬───────┬────────────┐
│ Device   │ Event                       │ Count │ Last Seen  │
├──────────┼─────────────────────────────┼───────┼────────────┤
│ R1       │ BGP NEIGHBOR DOWN           │ 5     │ 07:45:23   │
│ SW2      │ INTERFACE Gi0/1 DOWN        │ 12    │ 08:02:11   │
│ FW1      │ HA FAILOVER                 │ 1     │ 06:30:00   │
└──────────┴─────────────────────────────┴───────┴────────────┘

🟡 Warnings (8)
┌──────────┬─────────────────────────────┬───────┬────────────┐
│ Device   │ Event                       │ Count │ Last Seen  │
├──────────┼─────────────────────────────┼───────┼────────────┤
│ R3       │ CPU THRESHOLD               │ 3     │ 08:15:00   │
│ SW1      │ INTERFACE FLAPPING          │ 7     │ 07:50:22   │
└──────────┴─────────────────────────────┴───────┴────────────┘

📊 Affected Devices: R1, R3, SW1, SW2, FW1

💡 Suggested Commands:
   olav -E -q "Analyze R1 BGP neighbor DOWN events"
   olav -E -q "Investigate SW2 Gi0/1 interface flapping"
   olav -E -q "Check FW1 HA failover cause"
```

## CLI Usage

```bash
# Run log summary inspection
olav inspect run log-summary

# Run with custom time range
olav inspect run log-summary --hours 48

# View generated report
olav report show <report-id>

# Follow up with Expert analysis
olav -E -q "Analyze R1 BGP neighbor DOWN events"
```

## Data Flow

```
fluent-bit ──▶ OpenSearch (syslog-raw)
                    │
                    ▼
            ┌───────────────┐
            │  Inspection   │
            │  log-summary  │
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  Aggregation  │
            │  & Dedupe     │
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  Report Gen   │
            │  (Markdown)   │
            └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ Admin Review  │
            └───────────────┘
                    │
                    ▼ (manual trigger)
            ┌───────────────┐
            │  Expert Mode  │
            │  Deep Dive    │
            └───────────────┘
```

## Known Issues to Fix

### Expert Mode Syslog Import Path

The current Expert mode has an incorrect import path:

```python
# Current (incorrect)
from olav.tools.opensearch_tool import SyslogSearchTool

# Should be
from olav.tools.syslog_tool import SyslogSearchTool
```

**Files to fix:**
- `src/olav/modes/expert/supervisor.py` (line 285)

## Future Enhancements

1. **Scheduled Execution**: Integrate with system scheduler (cron/Windows Task Scheduler)
2. **Email/Slack Notifications**: Send summary to admin channels
3. **Trend Analysis**: Compare with historical baselines
4. **Custom Keywords**: Allow per-device keyword configuration
