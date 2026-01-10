---
description: Deep network analysis with customizable workflow
argument-hint: [source] [destination] [--error "desc"] [--plan] [--interactive]
allowed-tools: nornir_execute, list_devices, task, write_todos
model: opus
---

## Deep Network Analysis

Analyze network path from $1 to $2

### Options

**--error "description"**
Provide error description to guide diagnosis

**--plan**
Show analysis plan before execution

**--interactive**
Pause after each step for feedback

### Analysis Methodology

#### Phase 1: Macro Analysis
Determine fault domain:
- Trace path from $1 to $2
- Identify all intermediate devices
- Check BGP/OSPF neighbor status
- Determine fault domain

#### Phase 2: Micro Analysis
Locate specific root cause:
- TCP/IP layer-by-layer troubleshooting on identified problem device
- Physical layer: interface status, CRC errors, optical power
- Data link layer: VLAN, MAC table, STP
- Network layer: IP config, routing, ARP

#### Phase 3: Synthesis
- Combine macro and micro analysis results
- Identify root cause
- Provide actionable recommendations

Follow skill methodology: @skills/deep-analysis/SKILL.md

### Examples
```
/analyze R1 R5
/analyze R1 R5 --error "ping fails with 50% packet loss"
/analyze 10.1.1.1 10.5.1.1 --plan
/analyze Server1 Database1 --interactive --error "connection timeout"
```
