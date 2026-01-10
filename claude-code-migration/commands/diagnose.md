---
description: Diagnose network connectivity issues
argument-hint: [source] [destination]
allowed-tools: Read, nornir_execute, list_devices, search_capabilities
---

Diagnose network connectivity issues between two points.

## Steps
1. Identify source and destination devices/IPs
2. Use Deep Analysis skill for systematic troubleshooting
3. Execute diagnostic commands (ping, traceroute, route checks)
4. Analyze results and provide recommendations

## Examples
- /diagnose R1 to R5
- /diagnose 10.1.1.1 to 10.5.1.1
- /diagnose Server1 cannot reach Database1
