---
name: daily-run
version: 1.0.0
description: Complete daily network operations pipeline
schedule: "0 6 * * *"
timeout: 30m
---

# Daily Run Workflow

## Usage

```bash
/daily-run                    # Complete execution
/daily-run --group core       # Specify device group
/daily-run --fast             # Skip LLM stage
/daily-run --stage sync       # Execute specific stage only
/daily-run --continue         # Continue from failure point
```

## Stage Definition (Map-Reduce Pattern)

### Stage 1: sync (Tool)
- Tool: `sync_all()`
- Output: raw/, configs/, parsed/
- Description: Pure data collection

### Stage 2: topology (Tool)
- Tool: `generate_topology_from_sync()`
- Output: reports/topology.html
- Description: Pure topology generation

### Stage 3: inspect (Tool + LLM Map)
- Tool: `collect_inspection_data()` → Collect raw data
- LLM: Independent judgment for each device metric
- Output: map/inspect/*.json + reports/inspect_summary.json
- Description: Map phase - independent judgment per command, summarized then simplified

### Stage 4: logs (Tool + LLM Map)
- Tool: `parse_device_logs()` → Parse structured events
- LLM: Independent analysis per device log
- Output: map/logs/*.json + reports/log_summary.json
- Description: Map phase - keyword triggered, determine if needs escalation

### Stage 5: report (LLM Reduce)
- Skill: `@skills/daily-report/SKILL.md`
- Input: Anomaly summary (not raw data)
- Output: reports/daily_<date>.md
- Description: Reduce phase - global correlation analysis

## 阶段依赖

```
sync ──┬──► topology ──┐
       │               │
       ├──► inspect ───┼──► report
       │   (Map)       │   (Reduce)
       └──► logs ──────┘
           (Map)
```

## 阶段职责

| 阶段 | 执行者 | 模式 | 输入 | 输出 |
|------|--------|------|------|------|
| sync | 工具 | - | 设备列表 | 原始数据 |
| topology | 工具 | - | CDP/LLDP 数据 | HTML |
| **inspect** | **工具+LLM** | **Map** | **每设备每命令** | **检查结果** |
| **logs** | **工具+LLM** | **Map** | **每设备日志** | **事件摘要** |
| **report** | **LLM** | **Reduce** | 检查结果汇总 | **最终报告** |

## Map 阶段详解 (每命令独立判断)

### Inspect Map 阶段 (每设备 × 每命令 独立判断)

```
粒度: 设备 + 命令 + 检查项

R1 show cpu      ──► LLM ──► "R1 | cpu      | ⚠️ 62% 超50%阈值"
R1 show memory   ──► LLM ──► "R1 | memory   | ✅ 45% 正常"
R1 show int      ──► LLM ──► "R1 | int Gi0/1| ⚠️ CRC 127 errors"
R2 show cpu      ──► LLM ──► "R2 | cpu      | ✅ 23% 正常"
R2 show memory   ──► LLM ──► "R2 | memory   | ✅ 38% 正常"
R3 show env      ──► LLM ──► "R3 | temp     | ⚠️ 68°C 超60°C阈值"
...

输出: inspect_results.json (包含所有检查项，正常和异常都记录)
[
  {"device": "R1", "check": "cpu",    "status": "warning", "value": "62%", "detail": "超50%阈值"},
  {"device": "R1", "check": "memory", "status": "ok",      "value": "45%"},
  {"device": "R1", "check": "interface", "status": "warning", "interface": "Gi0/1", "detail": "CRC 127"},
  {"device": "R2", "check": "cpu",    "status": "ok",      "value": "23%"},
  {"device": "R2", "check": "memory", "status": "ok",      "value": "38%"},
  {"device": "R3", "check": "temp",   "status": "warning", "value": "68°C", "detail": "超60°C阈值"}
]

Report 阶段输入 (只含异常摘要):
- 异常项: R1 cpu ⚠️, R1 Gi0/1 CRC ⚠️, R3 temp ⚠️
- 正常项: 统计数字 "15/18 检查项正常"
```

### Logs Map 阶段 (每设备日志独立分析)

```
R1 日志 ──► LLM ──► "R1 | ⚠️ 3个OSPF邻居DOWN, 2个LINK flapping"
R2 日志 ──► LLM ──► "R2 | ✅ 无异常事件"
R3 日志 ──► LLM ──► "R3 | ⚠️ 1个BGP session reset"
...

输出: log_results.json
[
  {"device": "R1", "status": "warning", "events": [
    {"type": "ospf_down", "count": 3, "neighbors": ["10.1.1.2"]},
    {"type": "flapping", "interface": "Gi0/2", "count": 5}
  ]},
  {"device": "R2", "status": "ok", "events": []},
  {"device": "R3", "status": "warning", "events": [
    {"type": "bgp_reset", "neighbor": "10.2.2.2"}
  ]}
]
```

## Reduce 阶段详解

```
输入 (精简摘要):
- inspect_results.json → 过滤后: 3 个异常项 + "15/18 正常"
- log_results.json → 过滤后: 2 个设备有告警事件
- topology.html: 链接引用

Report 输入示例 (~500 tokens):
{
  "summary": {"total_checks": 18, "ok": 15, "warning": 3},
  "anomalies": [
    {"device": "R1", "check": "cpu", "value": "62%", "detail": "超阈值"},
    {"device": "R1", "check": "interface", "interface": "Gi0/1", "detail": "CRC 127"},
    {"device": "R3", "check": "temp", "value": "68°C"}
  ],
  "events": [
    {"device": "R1", "type": "ospf_down", "count": 3},
    {"device": "R1", "type": "flapping", "interface": "Gi0/2"}
  ]
}

LLM 关联分析:
- R1 CPU 高 + OSPF DOWN + Gi0/2 flapping → 链路抖动导致路由重算
- R3 温度高 → 需检查风扇/机房空调

输出: daily_2026-01-13.md
- 执行摘要表 (含正常/异常统计)
- 问题列表 (关联分析 + 建议)
- [查看拓扑](./topology.html)
```

## Token 对比

| 模式 | Map 粒度 | Report 输入 | 风险 |
|------|----------|-------------|------|
| ❌ 无 Map | - | 6 设备 × 20 命令 ≈ **50K tokens** | 爆炸 + 幻觉 |
| ⚠️ 每设备 Map | 设备 | 异常设备摘要 ≈ **1-2K tokens** | 可接受 |
| ✅ **每命令 Map** | **设备×命令** | 异常项 + 统计 ≈ **500 tokens** | **最优** |

## 错误处理

| 阶段 | 错误类型 | 处理方式 |
|------|----------|----------|
| sync | 设备不可达 | 记录失败，继续其他设备 |
| sync | 命令超时 | 重试 3 次，仍失败则跳过该命令 |
| inspect Map | LLM 调用失败 | 重试 3 次，仍失败则标记该检查项为 `error` |
| logs Map | LLM 调用失败 | 重试 3 次，仍失败则跳过该设备日志分析 |
| report Reduce | LLM 调用失败 | 重试 3 次，生成降级报告 (仅统计，无分析) |

### 降级报告示例

```markdown
# 网络日报 - 2026-01-13 (降级模式)

> ⚠️ LLM 分析不可用，仅显示统计数据

## 统计摘要
- 设备总数: 6
- 异常检查项: 4
- 异常事件: 3

## 异常列表
| 设备 | 检查项 | 状态 | 值 |
|------|--------|------|-----|
| R1 | cpu | warning | 62% |
...

[查看拓扑](./topology.html)
```
