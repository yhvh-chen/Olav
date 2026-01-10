# BGP Neighbor Adjacency Check (BGP邻居检查)

## 检查目标

验证 BGP 邻居关系的健康状态。此技能可检测:
- BGP 邻居是否建立 (Established)
- BGP 会话 uptime 和 message 统计
- 路由前缀统计 (advertised/received)
- 邻居配置一致性
- BGP 进程和协议错误

## 巡检参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_group` | string | (required) | 设备组名称或设备列表 |
| `asn_filter` | string | * | AS 号码过滤器 (e.g., "65000*") |
| `min_uptime` | string | 1h | 邻居最小在线时长 |
| `check_routes` | boolean | true | 是否验证路由前缀数量 |
| `timeout` | integer | 30 | 命令执行超时 (秒) |

## 执行步骤

### Step 1: 获取 BGP 路由器 ID 和 AS 号
```
show ip bgp summary
show bgp summary
```
**预期输出**: 
- BGP Router ID
- 本地 AS 号
- 邻居计数统计

### Step 2: 获取所有邻居及其状态
```
show ip bgp neighbors [brief]
show bgp neighbors [brief]
```
**预期输出**:
- 邻居 IP 地址
- 邻居 AS 号
- 状态 (Established / OpenSent / Idle / etc.)
- Uptime

### Step 3: 获取单个邻居详细信息
```
show ip bgp neighbors <neighbor_ip>
show bgp neighbors <neighbor_ip>
```
**预期输出**:
- 会话状态和持续时间
- 已发送和接收的消息数
- 已公告和接收的前缀数
- 本地和远程地址
- 配置的 TTL, keepalive, hold time

### Step 4: 验证路由前缀
```
show ip bgp [address-family] [summary]
show ip bgp afi-safi summary
```
**预期输出**: 已学习的路由前缀总数

### Step 5: 检查 BGP 错误和 warnings
```
show ip bgp process
show bgp process detail
```
**预期输出**: BGP 进程状态和任何配置警告

## 验收标准

### ✅ PASS 条件
- 所有邻居状态为 **Established**
- 邻居 uptime > `min_uptime` (默认 1 小时)
- 已接收的前缀数 > 0
- 无 BGP 进程错误
- 邻居配置参数匹配 (AS 号, 认证, AFI)

### ⚠️ WARNING 条件
- 邻居状态 **Idle** 且持续时间短 (< 5 分钟)
  - 可能是瞬间中断, 观察趋势
- 已接收前缀数明显低于预期
  - 检查 import filter 或 policy
- 消息丢失或重传频繁
  - 可能是网络问题或处理延迟

### ❌ FAIL 条件
- 任何邻居状态 **不是 Established**
- 邻居 uptime < 1 分钟 (反复振荡)
- 未接收任何前缀 (可能配置问题)
- BGP 进程崩溃或重启

## 故障排查

### 问题: 邻居 Idle

**可能原因**:
1. 网络不可达 - ping 邻居地址
2. TCP 建立失败 - 检查 ACL/firewall
3. 配置错误 - 检查 neighbor 声明
4. 资源耗尽 - 检查 memory/CPU

**排查命令**:
```
ping <neighbor_ip>
traceroute <neighbor_ip>
show ip bgp neighbors <neighbor_ip>
show ip bgp neighbors <neighbor_ip> received-routes
show bgp neighbors <neighbor_ip> advertised-routes
```

### 问题: Active (接不接受 / OpenConfirm 等)

**可能原因**:
1. 邻居配置不一致
   - Local AS 不匹配
   - Hold time 冲突
2. 认证失败 (MD5)
   - 密钥不匹配
   - 字符编码问题
3. 协议版本不匹配

**排查命令**:
```
show ip bgp neighbors <neighbor_ip> detail
show bgp neighbors <neighbor_ip> capability
debug ip bgp keepalives
```

### 问题: 前缀数量过少

**可能原因**:
1. 邻居不发送前缀
   - 邻居配置 null import policy
2. 本地 import filter 太严格
   - 检查 prefix list 或 route-map
3. 邻居 down 或重启

**排查命令**:
```
show ip bgp neighbors <neighbor_ip> received-routes
show ip bgp neighbors <neighbor_ip> advertised-routes
show ip prefix-list
show route-map
```

## 检查结果示例

### Healthy Report
```
BGP Neighbor Check Report - 2026-01-10 10:45 UTC

Target Group: core-routers
ASN Filter: 65*

BGP Process: ✅ HEALTHY
├── Router ID: 10.0.0.1
├── Local AS: 65000
└── Uptime: 42 days, 5:30:15

Neighbor Status:
├── 10.0.0.2 (AS 65001): ✅ Established
│   ├── Uptime: 35 days
│   ├── Received: 2500 prefixes
│   ├── Advertised: 500 prefixes
│   └── Messages sent: 45,234 / received: 45,101
│
├── 10.0.0.3 (AS 65002): ✅ Established
│   ├── Uptime: 28 days
│   ├── Received: 1800 prefixes
│   ├── Advertised: 500 prefixes
│   └── Messages sent: 38,900 / received: 38,856
│
└── 10.1.0.1 (AS 65100): ✅ Established
    ├── Uptime: 14 days
    ├── Received: 3200 prefixes
    ├── Advertised: 500 prefixes
    └── Messages sent: 12,567 / received: 12,451

Overall: ✅ HEALTHY (3 established, 0 down)
Next: Verify prefix learning trends
```

### Problem Report
```
BGP Neighbor Check Report - 2026-01-10 10:46 UTC

Target Group: access-routers
ASN Filter: 65*

BGP Process: ⚠️ WARNING
├── Router ID: 10.2.0.1
├── Local AS: 65010
└── Uptime: 2 days, 3:15:22

Neighbor Status:
├── 10.2.0.2 (AS 65011): ❌ IDLE (waiting for keepalive)
│   ├── Last connected: 5 seconds ago
│   ├── Hold time: 180 seconds
│   └── Message: Connection reset by peer
│
├── 10.2.0.3 (AS 65012): ⚠️ ACTIVE (retry in progress)
│   ├── Last state change: 3 seconds ago
│   ├── Hold time: 180 seconds
│   └── Action: Verify authentication settings
│
└── 10.3.0.1 (AS 65100): ✅ Established
    ├── Uptime: 2 days
    ├── Received: 150 prefixes
    └── ⚠️ Low prefix count - check policy

Overall: ❌ ACTION REQUIRED
Issues: 1 idle + 1 active neighbor, 1 low prefix count
Next Step: Check network connectivity and BGP logs
```

## Integration Notes

- **Device Support**: Cisco IOS, IOS-XE, Arista EOS, Juniper JunOS
- **Parallelization**: Can run on 100+ devices concurrently
- **Report Destination**: `data/reports/inspection/bgp-check-*.md`
- **Auto-Learning**: Report auto-embedded after generation
- **Estimated Runtime**: 3-8 seconds per device (depends on neighbor count)

## Related Skills

- `interface-check.md` - Physical link verification
- `device-health.md` - BGP process resource monitoring

---

**Last Updated**: 2026-01-10  
**Status**: Phase B-1 Template
