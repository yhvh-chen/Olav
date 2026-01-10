# Device Health Check (设备健康检查)

## 检查目标

监控网络设备的系统资源和运行健康状态。此技能可检测:
- CPU 使用率
- 内存 (RAM) 使用情况
- 存储 (Flash) 空间使用率
- 设备温度
- Power supply 状态
- Fan 运行状态
- 系统正常运行时间 (uptime)

## 巡检参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_group` | string | (required) | 设备组名称或设备列表 |
| `cpu_warning_threshold` | integer | 75 | CPU 警告阈值 (%) |
| `cpu_critical_threshold` | integer | 90 | CPU 紧急阈值 (%) |
| `memory_warning_threshold` | integer | 80 | 内存警告阈值 (%) |
| `memory_critical_threshold` | integer | 95 | 内存紧急阈值 (%) |
| `disk_warning_threshold` | integer | 85 | 磁盘警告阈值 (%) |
| `disk_critical_threshold` | integer | 95 | 磁盘紧急阈值 (%) |
| `min_uptime` | string | 7d | 最小运行时长 |
| `timeout` | integer | 30 | 命令执行超时 (秒) |

## 执行步骤

### Step 1: 获取设备基本信息
```
show version
show system
show hostname
```
**预期输出**:
- 设备型号和序列号
- 操作系统版本
- 运行时间 (uptime)
- 最后重启原因

### Step 2: 获取 CPU 使用率
```
show processes cpu [sorted]
show cpu utilization
show system cpu
```
**预期输出**:
- 当前 CPU 使用率
- 1 分钟/5 分钟/60 分钟平均值
- 进程级别的 CPU 统计

### Step 3: 获取内存使用情况
```
show memory
show processes memory [sorted]
show system memory
```
**预期输出**:
- 总内存大小
- 已用内存
- 可用内存
- 缓冲/缓存内存
- 进程内存使用排行

### Step 4: 获取存储空间使用
```
show flash:
show disk0:
dir [all-filesystems]
```
**预期输出**:
- Flash 总容量
- 已用空间
- 可用空间
- 文件列表

### Step 5: 获取硬件状态
```
show environment
show environment power
show environment temperature
show env all
```
**预期输出**:
- Power supply 状态 (normal/failing)
- Fan 状态 (normal/failing)
- 温度传感器读数
- 告警和警告状态

### Step 6: 检查系统日志错误
```
show logging
show log | include ERROR|CRITICAL
show system log summary
```
**预期输出**: 最近的错误和紧急日志条目

## 验收标准

### ✅ PASS 条件
- CPU 使用率 < `cpu_warning_threshold` (默认 75%)
- 内存使用率 < `memory_warning_threshold` (默认 80%)
- Flash 使用率 < `disk_warning_threshold` (默认 85%)
- 所有 Power supply 正常
- 所有 Fan 运行正常
- 温度在正常范围内
- 最近 24 小时无致命错误
- Uptime > `min_uptime` (默认 7 天)

### ⚠️ WARNING 条件
- CPU 使用率 `cpu_warning_threshold` 到 `cpu_critical_threshold`
- 内存使用率 `memory_warning_threshold` 到 `memory_critical_threshold`
- Flash 使用率 `disk_warning_threshold` 到 `disk_critical_threshold`
- 某个 Fan 降速或噪声异常
- 温度接近但未超过最大限制
- 最近 7 天有严重错误但设备仍运行
- Uptime < `min_uptime` (最近重启过)

### ❌ FAIL 条件
- CPU 使用率 > `cpu_critical_threshold`
- 内存使用率 > `memory_critical_threshold`
- Flash 使用率 > `disk_critical_threshold` (无法写入)
- Power supply 故障 (fail/no input/temp fail)
- Fan 故障或停止转动
- 温度超出最大限制
- 最近有多个致命错误
- Uptime < 1 小时 (正在反复重启)

## 故障排查

### 问题: CPU 使用率过高 (>90%)

**可能原因**:
1. 路由计算CPU 密集 - BGP 收敛, 重新计算
2. 数据包处理激增 - DDoS 攻击或网络风暴
3. 日志和调试过多 - 禁用不必要的日志
4. 进程泄漏或无限循环 - 检查特定进程

**排查命令**:
```
show processes cpu | head
show memory processor
debug [feature] [detail]
show process name [process_name]
show process memory | head
```

**缓解步骤**:
1. 禁用高成本功能 (netflow, syslog, debug)
2. 重启特定进程或设备
3. 优化配置 (ACL, policy)

### 问题: 内存使用率过高 (>95%)

**可能原因**:
1. 路由表庞大 - BGP 前缀过多
2. 会话数超限 - TCP/UDP 连接过多
3. 缓冲池耗尽 - 高速率网络流量
4. 内存泄漏 - IOS 或应用程序 bug

**排查命令**:
```
show memory processor detail
show processes memory | head
show ip bgp summary  # 检查前缀数
show tcp brief
show ip route summary
```

**缓解步骤**:
1. 清除不必要的连接 (clear sessions)
2. 增加内存 (硬件升级)
3. 分割路由表 (VLAN, 多进程)

### 问题: Flash 空间不足 (<5%)

**可能原因**:
1. 日志文件过大 - 未定期清理
2. 诊断/coredump 文件 - 自动保存的故障转储
3. 备份配置太多 - 多个config历史版本
4. Core dump - 进程崩溃转储

**排查命令**:
```
dir flash: all
show file systems
show log
show diagnostic capture list
show core
```

**清理步骤**:
```
delete flash:*.log
delete flash:*.core
delete flash:old-config-*
erase nvram:
```

### 问题: Power Supply 故障

**可能原因**:
1. 电源线松动或损坏
2. 电源模块故障
3. 内部短路或故障

**排查命令**:
```
show env power
show env all
show int status | include Port-channel|Ethernet
```

**缓解步骤**:
1. 重新插拔电源连接器
2. 更换故障电源模块 (需硬件访问)
3. 如果有冗余电源, 监视故障电源

### 问题: Fan 故障

**可能原因**:
1. 冷却风扇旋转不足
2. 积尘导致阻力增大
3. 风扇电机故障

**排查命令**:
```
show env temperature
show env fan
show env detailed
```

**缓解步骤**:
1. 清洁设备进出风口
2. 检查空气循环 (不要堵塞通风)
3. 更换故障风扇 (需硬件访问)

### 问题: 温度告警

**可能原因**:
1. 环境温度过高 (机房空调故障)
2. 通风被堵塞
3. 故障的 fan 导致冷却不足
4. 负载突增

**排查命令**:
```
show env temperature
show env all
show power supply
show env transceiver all
```

**缓解步骤**:
1. 检查机房温度和通风
2. 重启冷却 fan
3. 降低设备负载 (分流流量)

## 检查结果示例

### Healthy Report
```
Device Health Check Report - 2026-01-10 11:00 UTC

Target: core-router-1
Device Model: Cisco ASR 1006
Software Version: 15.7(3)M0
Serial Number: FDO12345678
Uptime: 342 days, 5:30:15

CPU Status: ✅ HEALTHY
├── Current: 12%
├── 1-min Average: 15%
├── 5-min Average: 14%
└── Top Process: eigrp (2%)

Memory Status: ✅ HEALTHY
├── Total: 16 GB
├── Used: 9.2 GB (57.5%)
├── Available: 6.8 GB (42.5%)
└── Peak Usage: 11.5 GB (71.9%)

Storage Status: ✅ HEALTHY
├── Flash Total: 8 GB
├── Used: 3.2 GB (40%)
├── Available: 4.8 GB (60%)
└── Files: config, IOS image

Temperature: ✅ HEALTHY
├── Inlet: 28°C
├── Outlet: 35°C
├── CPU: 45°C
└── Modules: Normal

Power Supply: ✅ HEALTHY
├── PS1: Normal (1000W)
└── PS2: Normal (1000W) [Redundant]

Fan Status: ✅ HEALTHY
├── Fan1: Normal
├── Fan2: Normal
└── Fan3: Normal

System Status: ✅ HEALTHY
└── Recent Errors: None (Last 7 days)

Overall: ✅ HEALTHY
Next Baseline: 2026-01-17
```

### Problem Report
```
Device Health Check Report - 2026-01-10 11:01 UTC

Target: access-switch-12
Device Model: Cisco Catalyst 2960X
Software Version: 15.2(5)E1
Serial Number: FOC2034A5678
Uptime: 23 hours, 15 minutes

CPU Status: ⚠️ WARNING
├── Current: 78%
├── 1-min Average: 82%
├── 5-min Average: 76%
├── Threshold (Warning): 75%
└── Top Process: sw_tcam_mon (25%), arp (12%)

Memory Status: ⚠️ WARNING
├── Total: 512 MB
├── Used: 435 MB (85%)
├── Available: 77 MB (15%)
└── Peak Usage: 490 MB (95.7%)

Storage Status: ❌ CRITICAL
├── Flash Total: 64 MB
├── Used: 61 MB (95%)
├── Available: 3 MB (5%) [INSUFFICIENT]
└── Action: DELETE OLD LOGS

Temperature: ✅ NORMAL
├── Inlet: 32°C
├── Module1: 52°C (Warning limit: 60°C)
└── Status: Monitor closely

Power Supply: ✅ NORMAL
└── PS1: Normal (370W)

Fan Status: ⚠️ WARNING
├── Fan1: Normal
└── Fan2: Degraded (Low Speed) [MONITOR]

System Status: ❌ ACTION REQUIRED
├── Recent Errors (Last 24h):
│   ├── %SYS-3-CRP_FAILURE: Crypto processor failure
│   └── %LINK-3-UPDOWN: Port Gi0/1 down/down
└── Restarted: 5 times in 24 hours

Overall: ❌ ACTION REQUIRED
Issues: High CPU/Memory, Low Flash, Fan Degradation
Next Step: Clear logs, investigate processor failure, check physical links
```

## Integration Notes

- **Device Support**: Cisco IOS, IOS-XE, NX-OS, Arista EOS, Juniper JunOS
- **Parallelization**: Can run on 200+ devices concurrently
- **Report Destination**: `data/reports/inspection/device-health-*.md`
- **Auto-Learning**: Report auto-embedded after generation
- **Estimated Runtime**: 4-10 seconds per device (depends on log size)

## Related Skills

- `interface-check.md` - Interface and link status monitoring
- `bgp-check.md` - BGP process and neighbor health

---

**Last Updated**: 2026-01-10  
**Status**: Phase B-1 Template
