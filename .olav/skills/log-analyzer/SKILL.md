---
name: Log Analyzer
description: Per-device log event analysis (Map phase) with keyword triggers
version: 1.0.0
intent: analyze
mode: map  # 每设备独立调用
---

## Log Analyzer - Map 阶段日志分析

### 输入

单个设备的日志原文或解析后的 NetworkEvent 列表:
- device: "R1"
- raw_log: show logging 输出 (如未解析)
- parsed_events: NetworkEvent JSON 列表 (如已解析)

### 关键词触发规则

#### 第一阶段: 关键词匹配 (快速过滤)

| 类别 | 触发关键词 | Severity |
|------|-----------|----------|
| **错误** | `%ERROR`, `%CRITICAL`, `%ALERT` | 0-3 |
| **接口** | `UPDOWN`, `LINK-3-UPDOWN`, `changed state to down` | 3 |
| **路由** | `OSPF-5-ADJCHG`, `ADJCHG`, `neighbor down`, `went down` | 5 |
| **BGP** | `BGP-5-ADJCHANGE`, `session reset`, `connection closed` | 5 |
| **STP** | `SPANTREE-2-`, `topology change`, `root change` | 2-5 |
| **硬件** | `FAN`, `POWER`, `TEMP`, `%ENVMON` | 2-4 |
| **安全** | `SEC_LOGIN`, `AUTHEN`, `failed`, `denied` | 4-5 |
| **重启** | `RESTART`, `RELOAD`, `BOOT`, `Initializing` | 5 |

#### 第二阶段: 上报判断 (LLM 分析)

匹配关键词后，LLM 判断是否需要上报:

| 情况 | 判断 | 上报? |
|------|------|-------|
| 接口 DOWN 后立即 UP (抖动) | flap_count > 3 | ⚠️ WARNING |
| 接口 DOWN 后未恢复 | 持续 DOWN | 🔴 CRITICAL |
| 接口 DOWN 后正常恢复 | 维护窗口内 | ❌ 不上报 |
| OSPF 邻居 DOWN 后恢复 | <5min 恢复 | ❌ 不上报 |
| OSPF 邻居持续 DOWN | >5min 未恢复 | ⚠️ WARNING |
| 多个 OSPF 邻居同时 DOWN | 本设备可能故障 | 🔴 CRITICAL |
| 单次登录失败 | 正常现象 | ❌ 不上报 |
| 多次连续登录失败 | >3 次失败 | ⚠️ WARNING |
| 设备重启 | 计划外 | 🔴 CRITICAL |

### 异常模式识别

| 模式 | 定义 | 状态 |
|------|------|------|
| **Flapping** | 同一接口 >3 次 UP/DOWN (1h内) | WARNING |
| **邻居丢失** | OSPF/BGP neighbor DOWN 未恢复 | WARNING |
| **批量事件** | >10 条相同类型事件 (1h内) | WARNING |
| **严重事件** | severity <= 3 | CRITICAL |
| **重启事件** | 非计划重启 | CRITICAL |

## 输出格式 (必须严格遵循)

### 有异常需上报
```json
{
  "device": "R1",
  "status": "warning",
  "event_count": 5,
  "events": [
    {
      "type": "ospf_neighbor_down",
      "severity": "warning",
      "count": 3,
      "neighbors": ["10.1.1.2", "10.1.1.3"],
      "first_seen": "2026-01-13T02:15:00Z",
      "last_seen": "2026-01-13T05:30:00Z",
      "recovered": false,
      "detail": "3个OSPF邻居DOWN超过5分钟未恢复"
    },
    {
      "type": "link_flapping",
      "severity": "warning",
      "interface": "Gi0/2",
      "flap_count": 5,
      "detail": "接口在1小时内UP/DOWN 5次"
    }
  ]
}
```

### 无异常或已恢复
```json
{
  "device": "R2",
  "status": "ok",
  "event_count": 0,
  "events": [],
  "note": "检测到2条OSPF事件，但均已恢复，不上报"
}
```

### 有关键词匹配但判定为正常
```json
{
  "device": "R3",
  "status": "ok",
  "event_count": 0,
  "events": [],
  "filtered": [
    {"type": "interface_down", "interface": "Gi0/3", "reason": "维护窗口内正常操作"},
    {"type": "ospf_adjchg", "reason": "邻居在2分钟内恢复"}
  ]
}
```

## 注意事项

1. **先匹配关键词**，再判断是否上报
2. **考虑时间上下文**：事件是否已恢复
3. **考虑数量**：单次事件 vs 重复事件
4. **不上报也要记录**：在 `filtered` 字段说明原因
5. **结构化输出**，便于 Reduce 阶段汇总
