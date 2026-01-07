---
id: quick-query
intent: query
complexity: simple
description: "简单状态查询，1-2条命令即可完成，无需分解任务"
examples:
  - "R1的接口状态"
  - "查看R2 BGP邻居"
  - "设备版本信息"
enabled: true
---

# Quick Query (快速查询)

## 适用场景
- 查询设备接口状态
- 查询路由表
- 查询 ARP/MAC 表
- 简单的状态检查

## 识别标志
用户问题包含: "查一下"、"看看"、"状态"、"是否正常"、"show"、"display"

## 执行策略
1. **不需要 write_todos**，直接执行
2. 从 knowledge/aliases.md 解析设备别名
3. 使用 search_capabilities 查找合适命令
4. 执行 1-2 条命令即可
5. 结果简洁，只返回关键信息

## 示例

### 接口状态查询
**触发**: "R1 的 Gi0/1 状态"、"show interface status"
**命令**: `show interfaces GigabitEthernet0/1` or `show interface brief`
**提取**: up/down、速率、错误计数

### IP/MAC 定位
**触发**: "10.1.1.100 在哪个端口"、"找一下这个MAC"
**流程**:
1. `show arp | include 10.1.1.100` → 获取 MAC
2. `show mac address-table address <mac>` → 获取端口

### 版本信息
**触发**: "设备版本"、"show version"
**命令**: `show version` or `display version`
**提取**: 设备型号、软件版本、运行时间

### CPU/内存查询
**触发**: "CPU使用率"、"内存情况"
**命令**: `show processes cpu history`, `show memory statistics`
**提取**: 当前使用率、趋势

## 工作流程
```
用户查询 → 解析别名 → search_capabilities → nornir_execute → 格式化输出
```

## 输出格式
保持简洁，突出关键信息：
```
R1 (10.1.1.1) - Interface Status
├─ Gi0/1: up, line protocol up
│  ├─ Input: 1000 Mbps, 0 errors
│  └─ Output: 1000 Mbps, 0 errors
├─ Gi0/2: administratively down
└─ Gi0/3: up, line protocol up
   └─ CRC errors: 0
```

## 注意事项
- 只执行只读命令
- 不要配置修改
- 输出要简洁清晰
- 如果设备不存在，先用 list_devices 确认
