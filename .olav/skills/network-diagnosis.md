---
id: network-diagnosis
intent: diagnose
complexity: complex
description: "结构化网络故障诊断,按TCP/IP分层逐级排查"
examples:
  - "为什么网络不通"
  - "网络慢,帮我排查"
  - "某站点无法访问"
enabled: true
---

# Network Diagnosis (结构化网络诊断)

## 适用场景
- 网络连通性故障
- 性能问题诊断
- 间歇性故障排查
- 端到端路径分析

## 识别标志
用户问题包含: "不通"、"无法访问"、"慢"、"丢包"、"超时"、"时断时续"

## 执行策略

### 阶段1: 问题定义 (5分钟)
**目标**: 明确问题现象和范围

1. **收集基本信息**
   ```bash
   - 源地址/设备: ?
   - 目标地址/设备: ?
   - 问题现象: (不通/慢/间歇性)
   - 持续时间: ?
   - 影响范围: (单用户/全站点/特定业务)
   - 最近变更: (配置/设备/链路)
   ```

2. **快速验证**
   ```bash
   # 从不同测试点验证
   ping <目标> -c 10

   # 记录结果
   - 丢包率: ?
   - 延迟: ?
   - 抖动: ?
   ```

### 阶段2: 宏观分析 (10分钟)
**目标**: 定位故障域和影响范围

1. **路径追踪**
   ```bash
   # Traceroute定位问题节点
   traceroute <目标>

   # 分析:
   # - 哪一跳开始丢包/超时
   # - 路径是否符合预期
   # - 是否有异常路由
   ```

2. **拓扑检查**
   ```bash
   # 检查关键节点状态
   show ip ospf neighbor     # OSPF邻居
   show ip bgp summary       # BGP邻居
   show lldp neighbors       # 二层拓扑

   # 分析:
   # - 邻居关系是否正常
   # - 是否有邻居down
   # - 拓扑是否有变化
   ```

3. **影响范围评估**
   ```bash
   # 批量ping测试
   # - 同一网段其他主机
   # - 不同网段主机
   # - 外部网络

   # 确定影响范围:
   # - 单主机 (本地问题)
   # - 单子网 (网关/二层问题)
   # - 多子网 (路由/三层问题)
   # - 全网络 (核心/出口问题)
   ```

**输出**: 宏观分析报告
```
## 宏观分析结果
- 故障域: [具体位置]
- 影响范围: [影响描述]
- 可疑节点: [设备/接口列表]
- 初步判断: [物理层/二层/三层问题]
```

### 阶段3: 微观分析 (15-30分钟)
**目标**: 在故障域内逐层排查,定位根因

#### TCP/IP 分层排查框架

**Layer 1: 物理层 (5分钟)**
```bash
# 检查项:
show interfaces status
show interfaces counters errors
show interfaces transceiver detail

# 关注指标:
✓ 接口状态: up/up
✓ 错误计数: CRC, input errors, output errors
✓ 光功率: RX/TX 在正常范围
✓ 流量: 输入/输出速率正常

# 常见问题:
✗ 接口 down/down
✗ CRC错误增长
✗ 光功率异常
✗ 大量 runts/giants
```

**Layer 2: 数据链路层 (5分钟)**
```bash
# 检查项:
show vlan brief
show mac address-table
show spanning-tree summary
show lldp neighbors detail

# 关注指标:
✓ VLAN状态: active
✓ MAC表: 已学习相关MAC
✓ STP状态: forwarding,无环路
✓ LLDP: 邻居发现正常

# 常见问题:
✗ VLAN不匹配
✗ MAC表未学习
✗ STP阻塞
✗ 二层环路
```

**Layer 3: 网络层 (10分钟)**
```bash
# 检查项:
show ip interface brief
show ip route <目标>
show arp
show ip ospf neighbor
show ip bgp summary

# 关注指标:
✓ 接口IP: 配置正确,状态up
✓ 路由表: 存在到达目标的路径
✓ ARP: 已解析目标MAC
✓ 路由协议: 邻居正常,路由收敛

# 常见问题:
✗ IP地址配置错误
✗ 路由缺失
✗ ARP无法解析
✗ 路由协议邻居down
✗ 路由震荡
```

**Layer 4: 传输层 (5分钟)**
```bash
# 检查项:
show access-lists
show ip nat translations
show control-plane
show running-config | include service

# 关注指标:
✓ ACL: 无阻断规则
✓ NAT: 转换正常
✓ 端口: 服务端口可达

# 常见问题:
✗ ACL阻断
✗ NAT配置错误
✗ 端口过滤
```

**Layer 5: 应用层 (可选,根据业务)**
```bash
# 检查项:
show ip dns server
show running-config | include service
# 应用特定检查

# 常见问题:
✗ DNS解析失败
✗ 服务未启动
```

### 阶段4: 根因定位 (5分钟)
**综合分析,确定根本原因**

1. **排除法**
   ```
   ✓ 物理层正常
   ✓ 二层正常
   ✗ 三层路由缺失
   → 根因: 路由配置错误/未发布
   ```

2. **关联分析**
   ```
   - 接口CRC错误 + 光功率低
   → 根因: 光模块老化

   - OSPF邻居down + 认证配置错误
   → 根因: OSPF认证密码不匹配

   - ACL阻断 + 特定流量不通
   → 根因: ACL规则配置错误
   ```

3. **时间线分析**
   ```
   - 故障开始时间
   - 最近配置变更
   - 设备重启/替换
   → 找到触发事件
   ```

### 阶段5: 解决方案与验证 (10分钟)

**制定解决方案**
1. **临时缓解** (如需要)
   ```
   - 切换到备用链路
   - 调整路由策略
   - 临时旁路故障点
   ```

2. **永久修复**
   ```
   - 修正配置错误
   - 更换故障硬件
   - 优化网络设计
   - 添加监控告警
   ```

**验证步骤**
```bash
# 1. 验证配置变更
show running-config | section <相关配置>

# 2. 验证状态恢复
show <相关状态命令>

# 3. 业务测试
ping <目标> -c 100
traceroute <目标>

# 4. 持续监控
# 观察10-30分钟确认稳定
```

## 常见故障场景与排查路径

### 场景1: 单用户无法访问网络
```
排查路径:
1. ping 本地网关 → 检查本地连接
2. ping 公网IP → 检查路由
3. 检查VLAN/MAC → 检查二层
4. 检查ACL/NAT → 检查策略
```

### 场景2: 全子网无法访问
```
排查路径:
1. 检查网关设备 → 接入层/汇聚层
2. 检查VLAN配置 → SVI状态
3. 检查上行链路 → 核心层
4. 检查路由发布 → 路由协议
```

### 场景3: 网络慢
```
排查路径:
1. traceroute定位慢的节点
2. 检查该节点接口错误/利用率
3. 检查QoS配置
4. 检查路径选择
```

### 场景4: 间歇性故障
```
排查路径:
1. 检查接口错误计数增长趋势
2. 检查路由协议稳定性
3. 检查STP状态变化
4. 检查链路质量
```

### 场景5: 特定应用不通
```
排查路径:
1. 测试基本连通性 (ping)
2. 测试端口可达性 (telnet <ip> <port>)
3. 检查ACL策略
4. 检查应用层配置
```

## 输出格式

### 诊断报告模板
```markdown
## 网络故障诊断报告

### 问题描述
[用户描述的问题]

### 宏观分析
**路径追踪**: [traceroute结果]
**故障域**: [确定的故障位置]
**影响范围**: [影响描述]

### 微观分析
**物理层**: ✅/❌ [发现]
**二层**: ✅/❌ [发现]
**三层**: ✅/❌ [发现]
**四层**: ✅/❌ [发现]

### 根因
[确定的根本原因]

### 解决方案
1. 临时措施: [如有]
2. 永久修复: [具体步骤]

### 验证结果
✅/❌ [验证结果]
```

## 最佳实践

### 1. 系统化排查
- 严格按照分层顺序
- 每层检查完整后再进入下一层
- 记录所有检查结果

### 2. 并行检查
- 多个设备可并行检查
- 使用batch_query提高效率
- 不相关检查项可并行

### 3. 对比分析
- 与正常设备/链路对比
- 与历史数据对比
- 与配置基线对比

### 4. 变更控制
- 诊断时避免做配置变更
- 确认根因后再修复
- 修复后要有验证
- 记录所有变更

### 5. 文档记录
- 诊断过程要记录
- 根因要记录
- 解决方案要记录
- 保存到knowledge/solutions/

## 工具使用优先级

### 优先使用
1. `smart_query(device, intent)` - 快速获取信息
2. `batch_query(devices, intent)` - 批量检查
3. `list_devices()` - 了解环境

### 按需使用
4. `search_capabilities(query, platform)` - 查找特定命令
5. `nornir_execute(device, command)` - 执行特定命令

### 辅助工具
- `ping`, `traceroute` - 连通性测试
- `show` 命令 - 状态检查
- `debug` 命令 - 深度调试 (谨慎使用)

## 注意事项

### 安全第一
- 只执行只读命令诊断
- 不做配置变更 (除非用户明确要求)
- 不执行危险命令 (reload等)

### 效率优先
- 优先使用批量工具
- 避免重复检查
- 快速定位故障域

### 用户沟通
- 及时报告进展
- 解释技术术语
- 给出明确建议
- 提供验证方法

## 学习行为

成功诊断后:
1. **保存案例**: `write_file .olav/knowledge/solutions/<问题>.md`
2. **更新技能**: 如发现新的排查模式,更新 `skills/network-diagnosis.md`
3. **更新别名**: 如使用了新设备别名,更新 `knowledge/aliases.md`
4. **记录标签**: 便于后续检索

## 相关技能
- `quick-query.md` - 简单查询
- `deep-analysis.md` - 深度分析(使用macro/micro子代理)
- `device-inspection.md` - 设备巡检
