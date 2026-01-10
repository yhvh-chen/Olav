---
name: backup
version: 1.0.0
type: workflow
platform: all
description: Backup device configurations with filtering
---

# Backup Workflow

## Usage
```
/backup [filter] [type] [--commands "cmd1,cmd2"]
```

## Filters
- `role:core` - Devices with role="core"
- `site:lab` - Devices at site="lab"
- `group:test` - Devices in "test" group
- `R1,R2,R3` - Specific device list
- `all` - All devices

## Backup Types
- `running` - show running-config
- `startup` - show startup-config
- `all` - Both running and startup
- `custom` - Use --commands parameter

## Examples
```
/backup role:core running
/backup site:lab all
/backup all custom --commands "show version,show vlan"
```

Follow skill methodology: @skills/config-backup/SKILL.md
