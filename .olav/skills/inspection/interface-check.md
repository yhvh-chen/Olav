# Interface Availability Check (接口可用性检查)

## 检查目标

验证网络接口的可用性、状态和性能指标。此技能可检测:
- 接口 admin 状态 (up/down/shutdown)
- 接口 operational 状态 (up/down)
- 接口线路速率和双工模式
- 输入/输出错误和丢包计数
- 端口通道或 VLAN 配置

## 巡检参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_group` | string | (required) | 设备组名称或设备列表 |
| `interface_filter` | string | * | 接口名称过滤器 (e.g., "Eth0*", "Gi0/0*") |
| `check_errors` | boolean | true | 是否检查错误/丢包计数 |
| `error_threshold` | integer | 100 | 错误计数告警阈值 |
| `timeout` | integer | 30 | 命令执行超时时间 (秒) |

## 执行步骤

### Step 1: 获取接口列表
```
show interfaces [brief] [interface_filter]
```
**预期输出**: 接口列表及其基本状态

### Step 2: 获取接口详细信息
```
show interfaces [interface_name]
```
**预期输出**: 
- Admin status, Operational status
- 线路速率 (Line protocol)
- 输入/输出流量和错误

### Step 3: 检查 VLAN/Port-Channel 配置 (可选)
```
show vlan id [vlan_id]
show port-channel summary
```
**预期输出**: 接口归属的 VLAN 和通道组

### Step 4: 获取错误统计
```
show interfaces [interface_name] stats
show interfaces [interface_name] counters errors
```
**预期输出**: CRC 错误, 溢出错误, 帧错误等

## 验收标准

### ✅ PASS 条件
- 所有接口 admin status 为 **up**
- 所有接口 operational status 为 **up**
- 错误计数 < `error_threshold` (默认 100)
- 无端口通道降级 (所有成员 active)
- 无 VLAN 配置冲突

### ⚠️ WARNING 条件
- 某接口 operational down 但 admin up (可能环路或物理故障)
- 错误计数上升快速 (增长率 > 10% 每小时)
- 端口通道有 inactive 成员

### ❌ FAIL 条件
- 任何接口 admin status 为 down (意外中断)
- 多个接口 operational down
- 错误计数 > `error_threshold`

## 故障排查

### 问题: 接口 Down (Admin Up, Operational Down)

**可能原因**:
1. 物理链路中断 - 检查光纤/网线
2. 邻居设备故障 - ping 邻居地址
3. 协议超时 - 查看接口 log
4. STP Blocking - 检查 root port 状态

**排查命令**:
```
debug spanning-tree rstp
show lldp neighbors
show ip route
traceroute <neighbor_ip>
```

### 问题: 高错误计数

**可能原因**:
1. 坏的光纤/网线 - 更换物理线缆
2. 交叉编译配置 - 双工不匹配
3. 拥塞导致丢包 - 检查带宽使用

**排查命令**:
```
show interfaces <interface> counters errors
show lldp neighbors <interface>
show qos interface <interface> stats
```

### 问题: Port-Channel Down

**可能原因**:
1. 所有成员接口 down - 检查成员接口状态
2. LACP 协议失败 - 验证邻居配置
3. MTU 不匹配 - 检查成员 MTU 配置

**排查命令**:
```
show port-channel summary
show port-channel protocol
show etherchannel summary
```

## 检查结果示例

### Healthy Report
```
Interface Check Report - 2026-01-10 10:30 UTC

Target Group: core-routers
Interface Filter: Eth*

Results:
├── Interface Status: ✅ PASS
│   └── All 48 interfaces up/up
├── Error Count: ✅ PASS
│   └── Max errors: 3 (threshold: 100)
├── Port-Channel: ✅ PASS
│   └── 4 active channels, all members active
└── VLAN Config: ✅ PASS
    └── No conflicts detected

Overall: ✅ HEALTHY
```

### Problem Report
```
Interface Check Report - 2026-01-10 10:31 UTC

Target Group: access-switches
Interface Filter: *

Results:
├── Interface Status: ⚠️ WARNING
│   └── Eth1/1 (R1): down/down [UNEXPECTED]
│   └── Eth2/2 (S1): operational down [CHECK STP]
├── Error Count: ⚠️ WARNING
│   └── Eth3/1: 245 errors (threshold: 100)
├── Port-Channel: ❌ FAIL
│   └── Po1 degraded: 1/4 members down
└── VLAN Config: ✅ PASS

Overall: ⚠️ ACTION REQUIRED
Next Step: Check physical links and STP blocking
```

## Integration Notes

- **Device Support**: Cisco IOS, IOS-XE, Arista EOS
- **Parallelization**: Can run on 50+ devices concurrently
- **Report Destination**: `data/reports/inspection/interface-check-*.md`
- **Auto-Learning**: Report auto-embedded after generation
- **Estimated Runtime**: 2-5 seconds per device

## Related Skills

- `device-health.md` - CPU/Memory/Disk monitoring
- `bgp-check.md` - BGP adjacency verification

---

**Last Updated**: 2026-01-10  
**Status**: Phase B-1 Template
