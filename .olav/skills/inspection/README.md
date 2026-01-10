# Inspection Skills (巡检技能)

This directory contains **batch inspection skill definitions** for OLAV's InspectorAgent.

## Skill Structure

Each inspection skill is a Markdown file that defines:
- **检查目标**: What to inspect (interface availability, BGP state, device health, etc.)
- **巡检参数**: Configurable parameters (scope, thresholds, timeout)
- **执行步骤**: Step-by-step commands to run on devices
- **验收标准**: Pass/fail criteria and expected results
- **故障排查**: Common issues and resolutions

## Example Skill Structure

```markdown
# Skill: Interface Availability Check

## 检查目标
验证网络接口的可用性和状态。

## 巡检参数
- `device_group`: 设备组 (required)
- `interface_filter`: 接口过滤器 (optional, e.g., "Eth*")
- `timeout`: 命令超时时间 (default: 30s)

## 执行步骤
1. 获取接口列表
2. 检查每个接口的 admin 和 operational 状态
3. 对比预期状态
4. 记录差异

## 验收标准
- ✅ 所有接口 admin status 为 up
- ✅ 所有接口 operational status 为 up
- ✅ 无 error/discard 计数增长

## 故障排查
如果接口 down:
- 检查物理连接
- 检查 Layer 2 配置 (STP, port-channel)
- 查看接口 log
```

## Available Skills

### 1. Interface Availability Check (接口可用性检查)
- **File**: `interface-check.md`
- **Purpose**: Verify interface up/up status, error counts, VLAN config
- **Scope**: Single interface, interface group, or pattern filter (e.g., "Eth*", "Gi0/0*")
- **Output**: Interface status report with error analysis and troubleshooting
- **Platform**: Cisco IOS/IOS-XE, Arista EOS
- **Key Checks**: Admin/Operational status, CRC/overflow errors, port-channel health, VLAN validation
- **Parameters**: `device_group` (required), `interface_filter`, `check_errors`, `error_threshold`, `timeout`
- **Typical Runtime**: 2-5 seconds per device
- **Status**: ✅ Production Ready

### 2. BGP Neighbor Check (BGP邻居检查)
- **File**: `bgp-check.md`
- **Purpose**: Verify BGP adjacency, route prefix counts, session stability
- **Scope**: All neighbors, filter by AS number, or specific neighbor IP
- **Output**: BGP neighbor report with message statistics and prefix analysis
- **Platform**: Cisco IOS/IOS-XE, Arista EOS, Juniper JunOS
- **Key Checks**: Neighbor state (Established), prefix received/advertised, uptime, TTL/keepalive/hold-time parameters
- **Parameters**: `device_group` (required), `asn_filter`, `min_uptime`, `check_routes`, `timeout`
- **Typical Runtime**: 3-8 seconds per device
- **Status**: ✅ Production Ready

### 3. Device Health Check (设备健康检查)
- **File**: `device-health.md`
- **Purpose**: Monitor CPU, memory, storage, temperature, power, fans
- **Scope**: Full system health or specific resource class
- **Output**: Device health status report with resource utilization trends and alerts
- **Platform**: Cisco IOS/IOS-XE/NX-OS, Arista EOS, Juniper JunOS
- **Key Checks**: CPU/Memory/Disk usage percentage, power supply/fan operational status, temperature sensors, system uptime
- **Parameters**: `device_group` (required), `cpu_warning_threshold`, `memory_warning_threshold`, `disk_warning_threshold`, `min_uptime`, etc.
- **Typical Runtime**: 4-10 seconds per device
- **Status**: ✅ Production Ready

## How InspectorAgent Uses These Skills

```
User Input: "/inspect interface-check --device-group core-routers"
    ↓
InspectorAgent loads: interface-check.md
    ↓
HITL Approval: "巡检参数 OK? ✓"
    ↓
Parallel Execution on all devices in group
    ↓
Result Aggregation (pass/fail stats)
    ↓
Report Generation → Auto-embedded to knowledge base
    ↓
Future Similar Issues → Knowledge base search finds this report
```

## Adding New Skills

1. Create a new `.md` file in this directory
2. Follow the template structure above
3. Define clear parameters and acceptance criteria
4. Include common troubleshooting steps
5. Test with InspectorAgent in dry-run mode

## Integration Points

- **Phase B-3**: InspectorAgent reads skills from this directory
- **Phase A-1**: Inspection reports auto-embedded for future searches
- **Tools**: nornir integration via `src/olav/tools/network.py`

---

See [OLAV Design Doc](../../DESIGN_V0.81.md#phase-b) for Phase B roadmap.
