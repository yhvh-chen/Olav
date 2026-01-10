---
name: Health Check
description: Execute device health check across CPU, memory, uptime, and interface status. Use when user asks for "health check", "device status", "system resources", or "quick health status".
version: 1.0.0

# OLAV Extended Fields
intent: inspect
complexity: simple

# Output Configuration
output:
  format: markdown
  language: auto
  sections:
    - summary
    - details
    - recommendations
---

# Device Health Check

## Applicable Scenarios
- Quick device health status check
- System resource monitoring (CPU, memory)
- Device uptime and availability check
- Interface status verification
- Regular health monitoring baseline

## Identification Signals
User questions contain: "health", "status", "resources", "cpu", "memory", "uptime", "check"

## Execution Strategy
1. **List devices** using list_devices (default group or specified)
2. **Execute essential health commands** on each device:
   - System information (uptime, version)
   - CPU and memory utilization
   - Interface status
   - Error counters
3. **Generate health report** with device status summary
4. **Highlight critical issues** if found

## Health Check Commands

### System Information
- `show version` - Device model, serial, IOS version, uptime
- `show clock` - Current system time (verify NTP sync)

### Resource Utilization
- `show processes cpu sorted` - CPU usage by process
- `show memory statistics` - Memory usage (Processor Pool, IOS Process)

### Interface Status
- `show interfaces summary` - Port status overview
- `show interfaces status` - Quick interface state view
- `show interfaces counters errors` - Interface error counts

### Health Indicators
- `show system uptime` - System uptime information
- `show environment all` - Temperature, power, fan status (if available)

## Report Format

### Executive Summary
```
📊 Health Check Report
Inspection Time: 2026-01-08 14:30:00
Total Devices: 8
Overall Status: ✅ OK

Device Status Summary:
├─ R1 (10.1.1.1)     ✅ OK        Uptime: 45d 12h    CPU: 12%    Memory: 65%
├─ R2 (10.1.1.2)     ✅ OK        Uptime: 30d 05h    CPU:  8%    Memory: 72%
├─ R3 (10.1.1.3)     ⚠️ WARNING   Uptime: 02d 18h    CPU: 45%    Memory: 88%
├─ R4 (10.1.1.4)     ✅ OK        Uptime: 12d 22h    CPU:  5%    Memory: 61%
├─ S1 (10.2.1.1)     ✅ OK        Uptime: 365d 00h   CPU:  2%    Memory: 58%
├─ S2 (10.2.1.2)     ✅ OK        Uptime: 182d 14h   CPU:  3%    Memory: 59%
├─ S3 (10.2.1.3)     ✅ OK        Uptime: 92d 08h    CPU:  4%    Memory: 64%
└─ C1 (10.3.1.1)     ✅ OK        Uptime: 45d 03h    CPU:  6%    Memory: 71%
```

### Device Details
For each device:
- **System**: Model, Version, Uptime, Management IP
- **Resources**: CPU Usage, Memory Utilization, Processor Pool
- **Interfaces**: Total Ports, Up/Down Count, Error Count
- **Health**: Status (OK/WARNING/CRITICAL), Alerts

### Recommendations
- Devices with high CPU/memory utilization (>80%)
- Devices with short uptime (potential recent reboot)
- Interfaces with high error rates
- Devices requiring maintenance or optimization

## Status Indicators
- ✅ **OK** - All metrics normal (CPU <50%, Mem <75%, Uptime >7d)
- ⚠️ **WARNING** - One metric abnormal (CPU 50-80%, Mem 75-90%, Uptime 2-7d)
- 🔴 **CRITICAL** - Multiple abnormal metrics or high load (CPU >80%, Mem >90%)

## Usage Examples
```
User: "Can you check device health?"
→ Executes health check on default device group
→ Returns system resources and status summary

User: "Health check for core routers"
→ Executes on 'core' device group
→ Focuses on critical infrastructure status

User: "Show me device status, especially CPU and memory"
→ Prioritizes resource utilization metrics
→ Highlights devices with high utilization
```

## Output Examples

### High-Performance Output (with data):
```
## Device Health Check Report (test group)

**Inspection Time**: 2026-01-08 14:30:00
**Total Devices**: 8
**Overall Status**: ✅ OK (7 healthy, 1 warning)

### Summary
- **Devices**: 8 total
  - ✅ OK: 7 devices (87.5%)
  - ⚠️ WARNING: 1 device (12.5%)
  - 🔴 CRITICAL: 0 devices

- **Key Metrics**:
  - Average CPU: 12%
  - Average Memory: 68%
  - Min Uptime: 2 days
  - Max Uptime: 365 days

### Device Details

#### R1 (10.1.1.1) - ✅ OK
- **System**: Cisco IOS XE 16.12.04, Uptime: 45 days 12 hours
- **Resources**: CPU: 12%, Memory: 2048MB/3072MB (67%)
- **Interfaces**: 48 ports, 46 up, 2 down, 0 errors
- **Status**: Healthy

#### R3 (10.1.1.3) - ⚠️ WARNING
- **System**: Cisco IOS XE 16.12.04, Uptime: 2 days 18 hours
- **Resources**: CPU: 45%, Memory: 2688MB/3072MB (88%)
- **Interfaces**: 48 ports, 45 up, 3 down, 5 errors
- **Status**: Recent reload detected, high memory utilization

### Recommendations
1. **R3**: Monitor CPU and memory usage - consider scheduling reload during maintenance window
2. **General**: All devices healthy, no immediate action required
```

### Minimal Output (placeholder when no device data):
```
## Device Health Check Report

**Inspection Time**: 2026-01-08
**Total Devices**: Unknown

[Health check summary would be populated here with actual device data]

Please ensure network connectivity to devices before running health check.
```
