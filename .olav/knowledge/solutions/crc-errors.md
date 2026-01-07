# Case: CRC Errors Causing Network Jitter

> **Created**: 2026-01-07
> **Fault Type**: Physical Layer Fault
> **Impact Scope**: Single link performance degradation

## Problem Description

Users reported intermittent network issues on a dedicated line, serious packet loss in ping tests, unstable business access.
- **Symptoms**: Intermittent packet loss, large bandwidth latency jitter
- **Impact**: Critical business cannot function normally
- **Duration**: 2 days

## Troubleshooting Process

### 1. Initial Diagnosis (Macro Analysis)
```bash
# Check end-to-end path
ping 10.2.1.1 -c 100
# Result: 15% packet loss, large latency jitter

# Traceroute to locate problem node
traceroute 10.2.1.1
# Result: Packet loss begins after second hop (exit router)
```

**Conclusion**: Problem located between exit router and ISP

### 2. Interface Check (Micro Analysis - Physical Layer)
```bash
# Check interface status
show interfaces GigabitEthernet0/0/1

# Key Findings:
# - Interface is up, line protocol is up
# - CRC errors: 12,345 (continuously increasing)
# - Input errors: 12,350
# - Runts: 0, Giants: 0

# Check optical module information
show interfaces transceiver detail Gi0/0/1

# Key Findings:
# - RX power: -18.5 dBm (low, normal range -3 to -15 dBm)
# - TX power: -2.1 dBm (normal)
# - Temperature: 42°C (normal)
```

**Root Cause Located**: Receive optical power too low, causing CRC error increase

### 3. Further Verification
```bash
# Check error growth trend
show interfaces counters Gi0/0/1 | include CRC
# Check again 30 seconds later
show interfaces counters Gi0/0/1 | include CRC
# CRC increased +10 (continuous growth)

# Check optical module model
show inventory
# Finding: Optical module used 3 years, near end-of-life
```

## Root Cause

**Optical Module Aging, Receive Sensitivity Degradation, Causing CRC Error Increase**

- **Physical Reason**: Optical module laser aging, stable TX power but decreased RX sensitivity
- **Environmental Factor**: Possible fiber link contamination or connector oxidation
- **Affected Link**: GigabitEthernet0/0/1 (exit dedicated line)

## Solution

### Immediate Measures
```bash
# 1. Temporary: Reduce interface speed to 1G (if currently 10G)
interface GigabitEthernet0/0/1
 speed 1000
 negotiation auto

# 2. Or: Enable forward error correction (if optical module supports)
interface GigabitEthernet0/0/1
 fec mode rs
```

### Permanent Fix
1. **Replace Optical Module** (Priority: High)
   - Model: SFP-10G-LR (match link distance)
   - Brand: OEM or certified third-party
   - Expected: Restore normal RX power (-3 to -15 dBm)

2. **Check Fiber Link** (Simultaneously)
   - Clean fiber connectors
   - Check if optical loss is in normal range
   - Test fiber integrity

3. **Monitor Verification** (After replacement)
   ```bash
   # Continuous monitoring for 24 hours
   show interfaces counters Gi0/0/1 | include CRC
   # CRC错误应不再增长

   # 验证接收功率
   show interfaces transceiver detail Gi0/0/1
   # RX power应恢复至 -3 to -15 dBm

   # 业务测试
   ping 10.2.1.1 -c 1000
   # 丢包率应 < 0.1%
   ```

## 验证结果

✅ **更换光模块后24小时监控**:
- CRC错误: 0增长
- RX power: -7.2 dBm (正常)
- 丢包率: 0%
- 带宽利用率: 恢复正常

## 关键命令

| 命令 | 用途 |
|------|------|
| `show interfaces status` | 接口状态概览 |
| `show interfaces counters errors` | 错误计数详情 |
| `show interfaces transceiver detail` | 光模块详细信息 |
| `show inventory` | 硬件清单 |
| `ping -c 100` | 丢包率测试 |

## 经验总结

### CRC错误排查流程
1. **发现**: 接口错误计数异常 (CRC errors > 0且持续增长)
2. **定位**: `show interfaces counters errors` 确认具体接口
3. **检查**: `show interfaces transceiver detail` 查看光功率
4. **判断**:
   - RX power < -20 dBm: 光模块/光纤断裂
   - RX power -15 to -20 dBm: 光功率不足,可能老化
   - RX power -3 to -15 dBm: 正常
5. **修复**: 更换光模块,清洁光纤,检查链路

### 预防措施
- 定期检查接口错误计数 (每周)
- 监控光功率趋势 (每月)
- 光模块寿命管理 (3-5年更换计划)
- 配置CRC告警阈值
  ```
  # 监控脚本示例
  if (CRC > 100 或 RX < -18 dBm):
      触发告警
  ```

## 标签
#物理层 #CRC错误 #光模块 #接口故障 #专线故障 #丢包

## 相关案例
- [MAC地址漂移](./mac-flapping.md) - 二层环路问题
- [BGP邻居震荡](./bgp-flapping.md) - 路由协议故障
