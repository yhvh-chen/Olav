---
description: Backup device configurations with filtering
argument-hint: [filter] [type] [--commands "cmd1,cmd2"]
allowed-tools: nornir_execute, list_devices, save_device_config, Bash(echo:*)
model: sonnet
---

## Backup Network Configurations

Target devices: $1
Backup type: $2

### Supported Filters
- `role:core` - Devices with role="core"
- `site:lab` - Devices at site="lab"
- `group:test` - Devices in "test" group
- `R1,R2,R3` - Specific device list
- `all` - All devices

### Backup Types
- `running` - Running configuration (show running-config)
- `startup` - Startup configuration (show startup-config)
- `all` - Both running and startup
- `custom` - Use --commands parameter

### Workflow
1. Parse filter from $1 to identify target devices
2. Call list_devices() to get matching devices
3. For each device:
   - Execute backup command via nornir_execute()
   - Save output via save_device_config()
4. Report summary of backed up configurations

Follow skill methodology: @skills/config-backup/SKILL.md

### Examples
```
/backup role:core running
/backup R1,R2 all
/backup all custom --commands "show mac address-table,show arp"
/backup SW1 custom --commands "show vlan,show interfaces trunk"
```
