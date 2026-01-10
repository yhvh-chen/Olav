# Inspection Skills Quick Reference

## Overview

Three production-ready inspection skills for network device monitoring:
- **Interface Availability** (接口可用性检查)
- **BGP Neighbor Health** (BGP邻居检查)  
- **Device Health** (设备健康检查)

All skills use the InspectionSkillLoader for automatic discovery and parsing.

---

## 1. Interface Availability Check

**File**: `.olav/skills/inspection/interface-check.md`  
**Purpose**: Verify interface status, error counts, VLAN configuration  
**Runtime**: 2-5 seconds per device

### Parameters

| Parameter | Type | Default | Required | Example |
|-----------|------|---------|----------|---------|
| `device_group` | string | - | YES | "core-routers" |
| `interface_filter` | string | * | NO | "Eth*" |
| `check_errors` | bool | true | NO | true |
| `error_threshold` | int | 100 | NO | 50 |
| `timeout` | int | 30 | NO | 60 |

### Key Checks

- ✓ Interface admin/operational status (up/up)
- ✓ CRC and overflow error counts
- ✓ Port-channel member health
- ✓ VLAN assignment validation
- ✓ Interface MTU consistency

### Acceptance Criteria

**PASS** (5 conditions):
- All interfaces admin up
- All interfaces operational up
- Error count < threshold
- No port-channel downgrade
- No VLAN conflicts

**WARNING** (3 conditions):
- Interface operational down but admin up
- Error count rising quickly (>10%/hour)
- Port-channel has inactive members

**FAIL** (3 conditions):
- Any interface unexpected down
- Multiple interfaces down
- Error count exceeds threshold

### Example Usage

```bash
# Check all interfaces on core routers
olav.py inspect interface-check --device-group core-routers

# Check only Ethernet interfaces with custom timeout
olav.py inspect interface-check --device-group core-routers \
  --interface-filter "Eth*" --timeout 60
```

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Interface Down (admin up) | Physical link issue | Check cable, check neighbor |
| High Error Count | Bad cable/duplex mismatch | Test with loopback, check speed/duplex |
| Port-Channel Down | Member links down | Check individual member interfaces |

---

## 2. BGP Neighbor Check

**File**: `.olav/skills/inspection/bgp-check.md`  
**Purpose**: Validate BGP neighbors, routing adjacency, session stability  
**Runtime**: 3-8 seconds per device (depends on neighbor count)

### Parameters

| Parameter | Type | Default | Required | Example |
|-----------|------|---------|----------|---------|
| `device_group` | string | - | YES | "core-routers" |
| `asn_filter` | string | * | NO | "65*" |
| `min_uptime` | string | 1h | NO | "7d" |
| `check_routes` | bool | true | NO | true |
| `timeout` | int | 30 | NO | 45 |

### Key Checks

- ✓ BGP neighbor state (Established)
- ✓ Prefix received/advertised counts
- ✓ BGP message statistics
- ✓ Session uptime and stability
- ✓ TTL, keepalive, hold-time parameters

### Acceptance Criteria

**PASS** (5 conditions):
- All neighbors Established
- Uptime > min_uptime
- Prefixes received > 0
- No BGP process errors
- Neighbor config matches

**WARNING** (3 conditions):
- Neighbor Idle but briefly
- Low prefix count vs expected
- Message loss or retransmission

**FAIL** (4 conditions):
- Any neighbor not Established
- Frequent state changes
- No prefixes received
- BGP process crashed

### Example Usage

```bash
# Check all BGP neighbors
olav.py inspect bgp-check --device-group core-routers

# Check only eBGP neighbors (AS 65*)
olav.py inspect bgp-check --device-group core-routers \
  --asn-filter "65*" --min-uptime 30d
```

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Neighbor Idle | Network unreachable/TCP fail | Ping neighbor, check ACL |
| Active/OpenConfirm | Config mismatch | Check AS number, MD5 auth |
| Low Prefix Count | Import filter too strict | Check route-map, prefix-list |

---

## 3. Device Health Check

**File**: `.olav/skills/inspection/device-health.md`  
**Purpose**: Monitor CPU, memory, storage, temperature, power, fans  
**Runtime**: 4-10 seconds per device

### Parameters

| Parameter | Type | Default | Required | Example |
|-----------|------|---------|----------|---------|
| `device_group` | string | - | YES | "all-devices" |
| `cpu_warning_threshold` | int | 75 | NO | 80 |
| `cpu_critical_threshold` | int | 90 | NO | 95 |
| `memory_warning_threshold` | int | 80 | NO | 85 |
| `memory_critical_threshold` | int | 95 | NO | 98 |
| `disk_warning_threshold` | int | 85 | NO | 90 |
| `disk_critical_threshold` | int | 95 | NO | 99 |
| `min_uptime` | string | 7d | NO | 30d |
| `timeout` | int | 30 | NO | 45 |

### Key Checks

- ✓ CPU utilization (current + 1/5/60-min avg)
- ✓ Memory usage (total/used/available)
- ✓ Storage space utilization
- ✓ Temperature sensors
- ✓ Power supply status
- ✓ Fan operational status
- ✓ System uptime
- ✓ Error log analysis

### Acceptance Criteria

**PASS** (8 conditions):
- CPU < warning threshold
- Memory < warning threshold
- Disk < warning threshold
- All power supplies normal
- All fans normal
- Temperature in range
- No critical errors in 24h
- Uptime > min_uptime

**WARNING** (7 conditions):
- CPU in warning range
- Memory in warning range
- Disk in warning range
- Fan degraded/noisy
- Temperature near limit
- Recent serious error
- Uptime < min_uptime

**FAIL** (8 conditions):
- CPU > critical threshold
- Memory > critical threshold
- Disk > critical threshold
- Power supply failed
- Fan failure
- Temperature exceeded
- Multiple critical errors
- Frequent reboots

### Example Usage

```bash
# Check all device health
olav.py inspect device-health --device-group all-devices

# Custom thresholds for high-performance devices
olav.py inspect device-health --device-group core-routers \
  --cpu-warning-threshold 85 --memory-warning-threshold 90
```

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| High CPU | BGP convergence, data surge | Check top processes, reduce config |
| High Memory | Large routing table, memory leak | Add memory, split routes |
| Low Disk Space | Old logs/core dumps | Clear logs, delete core files |
| Fan Failure | Bearing failure or dust | Clean device, replace fan |

---

## Using InspectionSkillLoader

### Python API

```python
from src.olav.tools.inspection_skill_loader import InspectionSkillLoader

# Initialize loader (auto-finds .olav/skills/inspection/)
loader = InspectionSkillLoader()

# Discover available skills
skills = loader.discover_skills()  # Returns: list[Path]
# Output: [Path('.olav/skills/inspection/interface-check.md'), ...]

# Load a specific skill
skill = loader.load_skill(Path('.olav/skills/inspection/interface-check.md'))
print(f"Skill: {skill.name}")
print(f"Parameters: {[p.name for p in skill.parameters]}")

# Load all skills
all_skills = loader.load_all_skills()  # Returns: dict[str, SkillDefinition]
# Output: {
#   'interface-check': SkillDefinition(...),
#   'bgp-check': SkillDefinition(...),
#   'device-health': SkillDefinition(...)
# }

# Get human-readable summary
summary = loader.get_skill_summary(skill)
print(summary)
```

### Data Access Patterns

```python
# Access skill metadata
skill = loader.load_skill(Path('.olav/skills/inspection/interface-check.md'))

# Parameters
for param in skill.parameters:
    print(f"- {param.name}: {param.type} (required={param.required})")

# Execution steps
for i, step in enumerate(skill.steps, 1):
    print(f"Step {i}: {step}")

# Acceptance criteria
for condition in skill.acceptance_criteria['pass']:
    print(f"✅ {condition}")
for condition in skill.acceptance_criteria['warning']:
    print(f"⚠️ {condition}")
for condition in skill.acceptance_criteria['fail']:
    print(f"❌ {condition}")

# Troubleshooting
for problem, solutions in skill.troubleshooting.items():
    print(f"Problem: {problem}")
    for solution in solutions:
        print(f"  → {solution}")

# Platform support
print(f"Supported on: {', '.join(skill.platform_support)}")

# Estimated runtime
print(f"Estimated runtime: {skill.estimated_runtime}")
```

---

## Adding New Skills

### 1. Create Markdown File

Create `.olav/skills/inspection/your-skill-name.md` with required sections:

```markdown
# Your Skill Name (中文名称)

## 检查目标
Description of what you're checking...

## 巡检参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_group` | string | (required) | 设备组 |

## 执行步骤
### Step 1: Description
Commands...

### Step 2: Description
Commands...

## 验收标准
### ✅ PASS 条件
- Condition 1
- Condition 2

### ⚠️ WARNING 条件
- Condition 1

### ❌ FAIL 条件
- Condition 1

## 故障排查
### 问题: Issue Title
**原因**: Root causes
**解决**: Solutions

## Integration Notes
- **Device Support**: Platform1, Platform2
- **Estimated Runtime**: X-Y seconds per device
- **Report Destination**: data/reports/inspection/...
```

### 2. Test Your Skill

```python
from src.olav.tools.inspection_skill_loader import InspectionSkillLoader

loader = InspectionSkillLoader()
skill = loader.load_skill(Path('.olav/skills/inspection/your-skill-name.md'))

# Verify all sections are present
assert skill.name is not None
assert len(skill.parameters) > 0
assert len(skill.steps) > 0
assert len(skill.acceptance_criteria['pass']) > 0
assert len(skill.troubleshooting) > 0

print(f"✅ Skill '{skill.name}' loaded successfully!")
```

### 3. Use with InspectorAgent

Once Phase B-3 is complete, use:

```bash
olav.py inspect your-skill-name --device-group <group> [options]
```

---

## Common Patterns

### Parameter Filtering

```bash
# Interface check with filter
olav.py inspect interface-check --device-group core \
  --interface-filter "Eth[0-9]*"

# BGP check with AS number filter
olav.py inspect bgp-check --device-group all \
  --asn-filter "65[01]*"
```

### Custom Thresholds

```bash
# Device health with strict thresholds
olav.py inspect device-health --device-group prod \
  --cpu-warning-threshold 60 \
  --memory-warning-threshold 70
```

### Timeout Configuration

```bash
# Longer timeout for slow networks
olav.py inspect interface-check --device-group remote \
  --timeout 120
```

---

## Integration with Knowledge Base

All inspection reports are automatically embedded using Phase A-1 (Report Auto-Embedding):

1. **Skill Execution** → Report generated
2. **Auto-Embed** → Report embedded to knowledge base
3. **Search** → Future similar issues found via Phase A-2 (Hybrid Search)
4. **Rerank** → Results ranked by relevance via Phase A-3 (Reranking)

Example: If interface-check found CRC errors on link X, future CRC issues will surface this report through search.

---

## Testing & Validation

### Unit Tests

```bash
# Test skill loader
uv run pytest tests/test_inspection_skill_loader.py -v

# Expected: 21 tests passing
```

### Manual Validation

```bash
# Check loader can find skills
python src/olav/tools/inspection_skill_loader.py

# Expected output:
# ✅ Loaded skill: interface-check
# ✅ Loaded skill: bgp-check
# ✅ Loaded skill: device-health
```

---

## Troubleshooting the Loader

### Problem: Skill not found

**Check**:
1. File is in `.olav/skills/inspection/` directory
2. File name ends with `.md`
3. File is not named `README.md`

### Problem: Parameters not extracted

**Check**:
1. Parameter table has correct header: `| 参数 | 类型 | 默认值 | 说明 |`
2. Table rows are properly formatted with `|` delimiters
3. Section header is exactly: `## 巡检参数`

### Problem: Criteria not extracted

**Check**:
1. Section header: `## 验收标准`
2. PASS section: `### ✅ PASS 条件`
3. WARNING section: `### ⚠️ WARNING 条件`
4. FAIL section: `### ❌ FAIL 条件`
5. Each condition is a bullet point starting with `-` or `*`

---

## References

- **Design**: [DESIGN_V0.81.md](DESIGN_V0.81.md#phase-b)
- **Completion Summary**: [docs/PHASE_B_COMPLETION_SUMMARY.md](docs/PHASE_B_COMPLETION_SUMMARY.md)
- **Progress Dashboard**: [PROGRESS_DASHBOARD.md](PROGRESS_DASHBOARD.md)
- **Loader Code**: [src/olav/tools/inspection_skill_loader.py](src/olav/tools/inspection_skill_loader.py)
- **Loader Tests**: [tests/test_inspection_skill_loader.py](tests/test_inspection_skill_loader.py)

---

**Last Updated**: 2026-01-10  
**Status**: Production Ready ✅  
**Next Phase**: B-3 InspectorAgent (pending)
