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

## Subagent 选择

### macro-analyzer (宏观分析)
适用于:
- "哪个节点出了问题"
- "路径上哪里丢包"
- "影响范围有多大"
- 需要查看拓扑关系

**使用场景**:
- 端到端连通性问题
- 多设备故障
- 路由路径分析
- BGP/OSPF 邻居问题

### micro-analyzer (微观分析)
适用于:
- "为什么这个端口不通"
- "接口有错误"
- 需要逐层排查具体设备

**使用场景**:
- 单端口故障
- 接口错误计数高
- VLAN 问题
- ARP/MAC 问题

### 组合使用
1. 先用 **macro-analyzer** 确定故障域
2. 再用 **micro-analyzer** 定位具体原因

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
