---
description: Run comprehensive device inspection
argument-hint: [scope]
allowed-tools: Read, nornir_bulk_execute, list_devices, generate_report
---

Run comprehensive L1-L4 inspection on specified devices.

## Steps
1. Parse inspection scope (all, device list, or filter)
2. Use Device Inspection skill for systematic L1-L4 checks
3. Execute all inspection commands in parallel
4. Generate markdown report

## Scope Examples
- /inspect all
- /inspect R1, R2, R3
- /inspect all core routers
- /inspect devices in site:DC1
