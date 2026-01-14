---
name: Inspect Analyzer
description: Per-command inspection analysis (Map phase) with L1-L4 framework
version: 1.0.0
intent: analyze
mode: map  # 每设备×每命令 独立调用
---

## Inspect Analyzer - Map 阶段分析

### 输入

单个设备的单个命令输出:
- device: "R1"
- layer: L1 | L2 | L3 | L4
- check_type: 见下方检查框架
- raw_output: 命令原始输出
- parsed_data: TextFSM 解析后的 JSON (如有)

### L1-L4 检查框架

#### L1 - Physical Layer (物理层)

| 检查项 | Intent 查询 | WARNING | CRITICAL |
|--------|-------------|---------|----------|
| temperature | "environment status" | >60°C | >70°C |
| power | "power status" | 任一 inactive | 单 PSU 模式 |
| fans | "environment status" | 任一 failed | - |
| uptime | "device version" | <24h (重启?) | - |

#### L2 - Data Link Layer (数据链路层)

| 检查项 | Intent 查询 | WARNING | CRITICAL |
|--------|-------------|---------|----------|
| stp_role | "spanning-tree" | 非 root 但应为 root | - |
| mac_table | "mac address-table" | >80% 容量 | >95% 容量 |
| port_status | "interface status" | 关键端口 down | - |

#### L3 - Network Layer (网络层)

| 检查项 | Intent 查询 | WARNING | CRITICAL |
|--------|-------------|---------|----------|
| ospf | "ospf neighbors" | 邻居非 FULL | 全部邻居丢失 |
| bgp | "bgp summary" | 会话非 ESTABLISHED | 全部会话 down |
| routes | "routing table" | 路由数异常波动 | 无路由 |

#### L4 - Transport/Services (传输/服务层)

| 检查项 | Intent 查询 | WARNING | CRITICAL |
|--------|-------------|---------|----------|
| cpu | "cpu usage" | >50% | >80% |
| memory | "memory usage" | >75% | >90% |
| interface_errors | "interface counters" | CRC/错误 >0 | 错误率 >0.1% |
| interface_drops | "interface counters" | drops >0 | 持续增长 |

### 阈值判断汇总表

| 检查类型 | WARNING | CRITICAL |
|----------|---------|----------|
| cpu | >50% | >80% |
| memory | >75% | >90% |
| temperature | >60°C | >70°C |
| interface_errors | >0 | >0.1% 错误率 |
| interface_drops | >0 | 持续增长 |
| ospf | state != FULL | 全部邻居丢失 |
| bgp | state != ESTABLISHED | 全部会话 down |
| power | 任一 inactive | 单 PSU 模式 |
| fans | 任一 failed | - |
| stp | 非 root 但应为 | - |
| mac_table | >80% 容量 | >95% 容量 |

## 输出格式 (必须严格遵循)

### 正常
```json
{
  "device": "R1",
  "layer": "L4",
  "check": "cpu",
  "status": "ok",
  "value": "23%"
}
```

### 异常
```json
{
  "device": "R1",
  "layer": "L4",
  "check": "cpu",
  "status": "warning",
  "value": "62%",
  "threshold": "50%",
  "detail": "CPU利用率超过警告阈值"
}
```

### 接口异常 (需指明具体接口)
```json
{
  "device": "R1",
  "layer": "L4",
  "check": "interface_errors",
  "status": "warning",
  "interface": "Gi0/1",
  "value": "CRC 127",
  "detail": "CRC错误持续增长"
}
```

### OSPF 异常
```json
{
  "device": "R1",
  "layer": "L3",
  "check": "ospf",
  "status": "warning",
  "value": "2/3 FULL",
  "detail": "邻居 10.1.1.3 状态为 INIT"
}
```

## 注意事项

1. **每个命令独立判断**，不跨命令关联
2. **正常也要输出**，用于统计 "18/20 检查项正常"
3. **结构化输出**，便于 Reduce 阶段汇总
4. **不做建议**，建议在 Reduce 阶段生成
5. **标注 Layer**，便于报告按层分类
