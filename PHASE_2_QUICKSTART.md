# Phase 2 Quick Start Guide

> **For**: OLAV v0.8 Phase 2
> **Updated**: 2026-01-07
> **Status**: ✅ Production Ready

---

## What's New in Phase 2?

### 🎯 Enhanced Skills
- **network-diagnosis.md**: Structured 5-phase troubleshooting framework
- **deep-analysis.md**: Macro/micro subagent delegation
- **device-inspection.md**: Comprehensive health check templates
- **quick-query.md**: Simple query patterns (verified)

### 📚 Knowledge Base
- **Solutions Library**: 3 real-world case studies (CRC, OSPF, BGP)
- **Network Topology**: Complete lab topology with ASCII maps
- **Device Aliases**: Enhanced device and interface aliases
- **Conventions**: Network naming and planning standards

### 🧪 Testing
- **15 New E2E Tests**: Comprehensive Phase 2 test coverage
- **Integration Tests**: Phase 1 + Phase 2 integration verified
- **Skill Recognition Tests**: Auto-routing to appropriate skills

---

## Quick Start (5 Minutes)

### 1️⃣ Initialize (First Time Only)
```bash
# Install dependencies
uv sync

# Initialize capabilities database
uv run python scripts/init_capabilities.py
```

### 2️⃣ Verify Installation
```bash
# List all devices
uv run python -m olav devices

# Expected output:
# Available devices:
# - R1 (192.168.100.101) - cisco_ios - border@lab
# - R2 (192.168.100.102) - cisco_ios - border@lab
# ... (all 7 devices)
```

### 3️⃣ Try Phase 2 Features

#### Example 1: Network Diagnosis (NEW)
```bash
uv run python -m olav query "网络很慢,帮我排查"

# Agent will:
# 1. Use network-diagnosis skill
# 2. Follow 5-phase framework
# 3. Provide structured report
# 4. Reference solutions if applicable
```

#### Example 2: Device Inspection (ENHANCED)
```bash
uv run python -m olav query "对R1进行巡检"

# Agent will:
# 1. Use device-inspection skill
# 2. Follow inspection template
# 3. Generate structured report
```

#### Example 3: Solution-Based Help (NEW)
```bash
uv run python -m olav query "接口有CRC错误怎么办"

# Agent will:
# 1. Search knowledge/solutions/
# 2. Find crc-errors.md
# 3. Provide structured troubleshooting
# 4. Reference key commands
```

#### Example 4: Knowledge-Based Query
```bash
uv run python -m olav query "核心层有哪些设备"

# Agent will:
# 1. Read knowledge/network-topology.md
# 2. List core devices (R1-R4)
# 3. Show connections
```

---

## Phase 2 Features Deep Dive

### Network Diagnosis Workflow

When you ask "为什么网络不通", the agent follows a **structured 5-phase process**:

```
Phase 1: Problem Definition (5min)
  → Collect: source, destination, symptoms, duration
  → Quick verification: ping, traceroute

Phase 2: Macro Analysis (10min)
  → Traceroute to locate fault domain
  → Check topology: OSPF/BGP neighbors
  → Assess impact scope

Phase 3: Micro Analysis (15-30min)
  → Layer 1 (Physical): interfaces, CRC, optical power
  → Layer 2 (Data Link): VLAN, MAC, STP
  → Layer 3 (Network): IP, routing, ARP
  → Layer 4 (Transport): ACL, NAT
  → Layer 5 (Application): DNS, services

Phase 4: Root Cause (5min)
  → Correlation analysis
  → Timeline analysis
  → Identify trigger event

Phase 5: Solution & Verification (10min)
  → Temporary mitigation (if needed)
  → Permanent fix
  → Verification steps
```

**Output**: Structured diagnosis report with:
- ✅ Problem description
- ✅ Fault domain location
- ✅ Layer-by-layer findings
- ✅ Root cause
- ✅ Solution steps
- ✅ Verification results

### Solutions Library

OLAV now includes **real-world troubleshooting cases**:

#### CRC Errors (`.olav/knowledge/solutions/crc-errors.md`)
- **Problem**: Network instability, intermittent packet loss
- **Root Cause**: Aging optical module (RX power -18 dBm)
- **Solution**: Replace optical module, clean fiber
- **Commands**: `show interfaces counters errors`, `show interfaces transceiver detail`

#### OSPF Flapping (`.olav/knowledge/solutions/ospf-flapping.md`)
- **Problem**: OSPF neighbor state cycling Full ↔ Init
- **Root Cause**: Hello/Dead timer mismatch (5s/20s vs 10s/40s)
- **Solution**: Synchronize timers on both ends
- **Commands**: `show ip ospf neighbor`, `show ip ospf interface`

#### BGP Issues (`.olav/knowledge/solutions/bgp-flapping.md`)
- **Problem**: BGP neighbor stuck in Idle state
- **Root Cause**: Wrong ASN configured (65002 vs 65003)
- **Solution**: Correct ASN in router configuration
- **Commands**: `show ip bgp summary`, `show logging | include BGP`

**Usage**: Agent automatically searches and references these solutions during diagnosis.

### Knowledge Base

#### Network Topology (`.olav/knowledge/network-topology.md`)
Complete lab topology including:
- Device inventory (R1-R4, SW1-SW3)
- Connection relationships with ASCII map
- IP address planning (management, P2P, Loopbacks)
- VLAN planning (VLAN 10/20/30)
- OSPF configuration details
- Service configuration (DNS, NTP, SNMP)

#### Device Aliases (`.olav/knowledge/aliases.md`)
Quick shortcuts for common queries:
- "核心路由器" → R1, R2, R3, R4
- "核心交换机" → SW1, SW2
- "办公网" → VLAN 10
- "主链路" → Ethernet0/0, Ethernet0/1

---

## Test Phase 2

### Run E2E Tests
```bash
# Run all Phase 2 tests
uv run pytest tests/e2e/test_phase2_skills.py -v -m phase2

# Expected: 15 tests pass
```

### Manual Test Scenarios

#### Scenario 1: Quick Query
```bash
uv run python -m olav query "R1的接口状态"

# Verify:
# - Uses smart_query
# - Returns interface status
# - No complex analysis (quick-query skill)
```

#### Scenario 2: Structured Diagnosis
```bash
uv run python -m olav query "网络时断时续"

# Verify:
# - Uses network-diagnosis skill
# - Follows 5-phase framework
# - Provides structured report
```

#### Scenario 3: Device Inspection
```bash
uv run python -m olav query "巡检R1"

# Verify:
# - Uses device-inspection skill
# - Follows template
# - Generates report
```

#### Scenario 4: Knowledge Query
```bash
uv run python -m olav query "CRC错误怎么排查"

# Verify:
# - Searches solutions/
# - References crc-errors.md
# - Provides troubleshooting steps
```

---

## Configuration Files

### Key Files for Phase 2

| File | Purpose |
|------|---------|
| `.olav/skills/*.md` | Task execution strategies |
| `.olav/knowledge/solutions/*.md` | Historical cases |
| `.olav/knowledge/network-topology.md` | Network topology |
| `.olav/knowledge/aliases.md` | Device shortcuts |
| `.olav/capabilities.db` | Command library |

### Adding Your Own Content

#### Add a Solution Case
```bash
# Create new solution
cat > .olav/knowledge/solutions/my-case.md << 'EOF'
# 案例: [问题标题]

## 问题描述
[症状描述]

## 排查过程
1. [步骤1]
2. [步骤2]

## 根因
[根本原因]

## 解决方案
[修复方法]

## 关键命令
- command1
- command2

## 标签
#标签1 #标签2
EOF
```

#### Add Device Alias
```bash
# Edit aliases.md
vi .olav/knowledge/aliases.md

# Add line:
# | 我的设备 | R5 | device | cisco_ios | My test device |
```

---

## Troubleshooting

### Issue: Agent doesn't recognize skill
**Solution**: Check frontmatter in `.olav/skills/*.md`:
```yaml
---
id: skill-name
enabled: true  # Must be true
---
```

### Issue: Solutions not found
**Solution**: Verify files exist:
```bash
ls -la .olav/knowledge/solutions/
# Should see: crc-errors.md, ospf-flapping.md, bgp-flapping.md
```

### Issue: Tests fail
**Solution**: Run with debug output:
```bash
uv run pytest tests/e2e/test_phase2_skills.py -v -s
```

---

## Performance Tips

### Optimize Query Speed
1. **Use smart_query directly** for simple queries
2. **Use batch_query** for multiple devices
3. **Avoid** asking for "all information" (too broad)
4. **Be specific** with intent (e.g., "BGP邻居" not "所有路由协议")

### Efficient Diagnosis
1. **Provide context**: "R1到R3的网络不通" (better than "网络不通")
2. **Describe symptoms**: "丢包率15%" (helps agent focus)
3. **Mention recent changes**: "升级IOS后BGP无法建立" (narrows search)

---

## Next Steps

### Learn More
- 📖 [DESIGN_V0.8.md](DESIGN_V0.8.md) - Complete design documentation
- 📖 [PHASE_2_COMPLETION_SUMMARY.md](PHASE_2_COMPLETION_SUMMARY.md) - Detailed deliverables
- 📖 [CLI User Guide](CLI_USER_GUIDE.md) - All CLI commands

### Phase 3 Preview (Coming Soon)
- Subagent implementation (macro/micro analyzers)
- Auto-learning from successful cases
- NetBox/Zabbix integration
- Real device testing

### Contribute
- Add more solutions to `.olav/knowledge/solutions/`
- Enhance skills with new patterns
- Update topology for your network
- Share feedback via GitHub issues

---

## Summary

Phase 2 delivers **production-ready** network troubleshooting capabilities:

✅ **Structured Diagnosis**: 5-phase framework for systematic troubleshooting
✅ **Solutions Library**: Real-world cases with proven solutions
✅ **Enhanced Knowledge**: Complete topology, aliases, conventions
✅ **Comprehensive Testing**: 15 E2E tests ensuring quality
✅ **Phase 1 Integration**: Seamless compatibility with existing features

**Ready to use**: `uv run python -m olav query "YOUR QUESTION"`

---

*Last Updated: 2026-01-07*
*Phase 2 Status: ✅ COMPLETE*
