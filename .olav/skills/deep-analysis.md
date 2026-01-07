---
id: deep-analysis
intent: diagnose
complexity: complex
description: "复杂故障分析，需要多步诊断和子任务分解"
examples:
  - "网络故障完整根因分析"
  - "跨域连通性问题排查"
  - "端到端路径分析"
enabled: true
---

# Deep Analysis (深度分析)

## 适用场景
- 网络故障排查
- 性能问题分析
- 路径追踪
- 根因定位

## 识别标志
用户问题包含: "为什么"、"排查"、"分析"、"故障"、"不通"、"无法访问"、"慢"

## 执行策略
1. **使用 write_todos 分解问题**
2. 判断问题类型，选择分析方向
3. 委派给合适的 Subagent
4. 综合分析，给出结论和建议

## Subagent 委派策略 (Phase 3)

### 如何使用 Subagent

OLAV 现在支持专业的 Subagent 来处理复杂分析任务。使用 `task` 工具委派任务:

```
task(subagent_type="macro-analyzer", task_description="...")
task(subagent_type="micro-analyzer", task_description="...")
```

### macro-analyzer (宏观分析子代理)

**何时使用**:
- "哪个节点出了问题"
- "路径上哪里丢包"
- "影响范围有多大"
- 需要查看拓扑关系
- 端到端连通性问题
- 多设备故障
- 路由路径分析
- BGP/OSPF 邻居问题

**委派方式**:
```
task(subagent_type="macro-analyzer",
     task_description="分析从R1到R3的路径,定位哪个节点导致丢包。请:
     1. 执行traceroute追踪路径
     2. 检查BGP/OSPF邻居状态
     3. 确定故障域和影响范围
     返回: 故障节点位置、影响范围描述")
```

**子代理能力**:
- 网络拓扑分析 (LLDP/CDP/BGP)
- 数据路径追踪 (traceroute, 路由表)
- 端到端连通性检查
- 故障域识别

### micro-analyzer (微观分析子代理)

**何时使用**:
- "为什么这个端口不通"
- "接口有错误"
- 需要逐层排查具体设备
- 单端口故障
- 接口错误计数高
- VLAN 问题
- ARP/MAC 问题

**委派方式**:
```
task(subagent_type="micro-analyzer",
     task_description="对R1的Gi0/1接口进行TCP/IP逐层排查:
     1. 物理层: 检查接口状态、CRC错误、光功率
     2. 数据链路层: 检查VLAN、MAC表、STP
     3. 网络层: 检查IP配置、路由、ARP
     逐层分析并返回每层的检查结果")
```

**子代理能力**:
- TCP/IP 分层排错 (从物理层到应用层)
- 具体设备深度诊断
- 接口级问题定位
- 配置检查和验证

### 组合使用策略 (推荐)

**两阶段分析法**:
1. **阶段1: 委派 macro-analyzer**
   - 目标: 确定故障域
   - 输出: 问题设备/接口列表

2. **阶段2: 委派 micro-analyzer**
   - 目标: 定位具体根因
   - 输出: 逐层检查结果

**示例**:
```
# 用户: "R1到R3的网络很慢"

# Agent 响应:
# 1. 先用宏观分析定位问题
task("macro-analyzer", "检查R1-R3路径,找出慢的节点")

# 2. 根据宏观分析结果,用微观分析深入
task("micro-analyzer", "对[R2]进行TCP/IP逐层排查,找出网络慢的原因")

# 3. 综合两个子代理的结果,生成报告
```

## TCP/IP 逐层排错框架 (微观)

### 1. 物理层
**症状**: 完全无法通信，链路down
**检查**:
```bash
show interfaces status          # 端口状态
show interfaces transceiver     # 光模块信息
show interfaces counters errors # 错误计数
```
**常见问题**: 光模块故障、光衰过大、线缆损坏、CRC错误

### 2. 数据链路层
**症状**: 链路up但无法ping通
**检查**:
```bash
show vlan brief                 # VLAN状态
show mac address-table          # MAC表
show spanning-tree              # STP状态
show lldp neighbors             # 邻居发现
```
**常见问题**: VLAN不匹配、STP阻塞、MAC表未学习

### 3. 网络层
**症状**: 无法跨网段通信
**检查**:
```bash
show ip interface brief         # IP状态
show ip route                   # 路由表
show arp                        # ARP表
show ip ospf neighbor           # OSPF邻居
show ip bgp summary             # BGP邻居
```
**常见问题**: 路由缺失、ARP未解析、路由协议未建立

### 4. 传输层
**症状**: 部分应用不通
**检查**:
```bash
show access-lists               # ACL规则
show ip nat translations        # NAT表
show control-plane              # CoPP配置
```
**常见问题**: ACL阻断、NAT配置错误、端口过滤

### 5. 应用层
**症状**: 特定应用故障
**检查**:
```bash
show ip dns server              # DNS配置
show running-config | include service # 应用服务
```
**常见问题**: DNS解析失败、服务未启用

## 典型故障场景

### 场景1: 网络慢
1. macro-analyzer: traceroute 定位慢的节点
2. micro-analyzer: 检查该节点接口错误、CPU、队列

### 场景2: 无法访问服务器
1. macro-analyzer: 检查端到端路径
2. micro-analyzer: 从服务器开始逐层向源排查

### 场景3: 路由震荡
1. macro-analyzer: 检查所有BGP/OSPF邻居
2. micro-analyzer: 检查问题邻居的接口、路由配置

### 场景4: 广播风暴
1. macro-analyzer: 确定风暴范围
2. micro-analyzer: 找到环路端口，检查STP

## 输出格式
使用结构化报告:
```
## 故障分析报告

### 问题概述
用户反映: 从上海到北京专线不稳定

### 宏观分析 (macro-analyzer)
1. 路径: 上海路由器 → 出口 → 运营商 → 北京入口
2. 故障点: 上海路由器 Gi0/1 接口错误率高
3. 影响范围: 所有经该接口的流量

### 微观分析 (micro-analyzer)
1. 物理层: 接口up，CRC错误增长中
2. 数据链路层: 正常
3. 网络层: 正常
4. **根因**: 光模块老化，接收功率偏低

### 建议
1. 更换上海路由器 Gi0/1 光模块
2. 临时方案: 降低接口速率至1G
```

## 学习行为
成功解决后，将案例保存到 knowledge/solutions/:
```markdown
# 案例: [问题标题]

## 问题描述
[用户描述]

## 排查过程
1. [第一步]
2. [第二步]
...

## 根因
[根本原因]

## 解决方案
[解决方法]

## 关键命令
- command1
- command2

## 标签
#标签1 #标签2
```
