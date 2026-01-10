---
description: Query network device status
argument-hint: [device] [query]
allowed-tools: Read, nornir_execute, list_devices, search_capabilities
---

Execute a quick network query.

## Steps
1. Parse device alias from knowledge/aliases.md
2. Use Quick Query skill to find appropriate command
3. Execute command via nornir_execute
4. Return concise, formatted results

## Examples
- /query R1 interface status
- /query all BGP neighbors
- /query S1 version
