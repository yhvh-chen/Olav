---
id: device-inspection
intent: inspect
complexity: medium
description: "Device system health check, generate structured reports according to template"
examples:
  - "Inspect R1 system status"
  - "Device health check report"
  - "Pre-deployment device check"
enabled: true
---

# Device Inspection

## Applicable Scenarios
- Regular health checks
- Pre-deployment checks
- Post-fault verification
- Change before/after comparison

## Identification Signals
User questions contain: "inspect", "check", "health check", "baseline"

## Execution Strategy
1. **Use write_todos to list check items**
2. Execute step by step according to template
3. Generate structured report
4. Mark anomalies

## Inspection Template

### Basic Information
- [ ] `show version` (uptime, version, model)
- [ ] `show inventory` (hardware info, modules)
- [ ] `show license` (license status)

### System Health
- [ ] `show processes cpu history` (CPU trend)
- [ ] `show memory statistics` (memory usage)
- [ ] `show environment all` (temperature, power, fans)

### Interface Status
- [ ] `show interfaces summary` (port status summary)
- [ ] `show interfaces counters errors` (error counts)
- [ ] `show interfaces status` (detailed status)

### 路由状态
- [ ] `show ip route summary` (路由汇总)
- [ ] `show ip ospf neighbor` (OSPF 邻居)
- [ ] `show ip bgp summary` (BGP 邻居)

### 二层状态
- [ ] `show vlan brief` (VLAN 状态)
- [ ] `show spanning-tree summary` (STP 状态)
- [ ] `show lldp neighbors` (LLDP 邻居)

### 安全检查
- [ ] `show access-lists summary` (ACL 配置)
- [ ] `show login` (登录配置)
- [ ] `show users` (当前会话)

## 报告格式

### 执行摘要
```
设备巡检报告 - R1 (10.1.1.1)
检查时间: 2026-01-07 14:30:00
运行时间: 45 days, 6 hours

总体状态: ⚠️  2项异常
```

### 详细结果
| 检查项 | 状态 | 详情 | 建议 |
|--------|------|------|------|
| CPU | ✅ 正常 | 平均 15%, 峰值 25% | - |
| 内存 | ⚠️ 警告 | 使用 85% | 考虑升级内存 |
| Gi0/1 | ❌ 异常 | CRC错误: 1234 | 检查光模块 |
| OSPF | ✅ 正常 | 3个邻居全UP | - |
| BGP | ✅ 正常 | 2个邻居全UP | - |

### 异常详情
```
❌ 内存使用率过高
当前: 85%
阈值: >80%
建议: 监控趋势，考虑升级内存

❌ 接口 Gi0/1 CRC错误
错误计数: 1234
增长率: +10/分钟
建议: 检查光模块和线缆
```

## 快速巡检 vs 深度巡检

### 快速巡检 (Quick Check)
只检查关键指标:
- CPU/内存
- 接口状态
- 路由汇总
- 关键日志

**时间**: 2-3分钟
**适用**: 日常监控

### 深度巡检 (Full Inspection)
完整模板检查
**时间**: 10-15分钟
**适用**: 月度/季度检查

## 对比分析

### 变更前后对比
```
变更: 升级IOS版本
变更前: v17.3.1a
变更后: v17.3.2

指标对比:
- CPU: 20% → 18% ✅
- 内存: 75% → 78% ⚠️
- 错误率: 0.01% → 0% ✅

结论: 升级成功，性能略有改善
```

### 历史趋势
```
内存使用趋势 (最近7天):
Mon: 75% | Tue: 76% | Wed: 77% | Thu: 78%
Fri: 79% | Sat: 80% | Sun: 85% ⚠️

趋势: 上升
预测: 3天内可能达到90%
```

## 巡检自动化

### 批量巡检
对多台设备执行相同检查:
```
1. list_devices(role="core")
2. 对每台设备执行巡检模板
3. 生成汇总报告
4. 标记异常设备
```

### 定期巡检
建议:
- 核心设备: 每天快速巡检
- 汇聚设备: 每周快速巡检
- 接入设备: 每月深度巡检

## 输出示例
```
==========================================
设备巡检报告
==========================================
设备: R1 (10.1.1.1)
平台: cisco_ios
时间: 2026-01-07 14:30:00
运行时间: 45 days

检查结果: 12项 ✅, 2项 ⚠️, 1项 ❌

异常项:
1. ❌ Gi0/1 CRC错误 (1234个)
2. ⚠️ 内存使用率 85%

详细报告已保存到: knowledge/inspections/R1_20260107.md
==========================================
```
