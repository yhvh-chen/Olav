# 诊断技能

## 概述

网络诊断技能用于问题排查和根因分析。

### 应用场景

- BGP 邻居状态不正常
- 设备无法到达
- 路由不存在
- 性能下降

### 执行步骤

1. 收集设备基础信息 (show version, show interfaces)
2. 收集路由信息 (show ip route, show bgp summary)
3. 分析数据找出问题根因
4. 提供修复建议

### 相关命令

```
show version
show interfaces status
show ip route
show bgp summary
show bgp neighbors
show ospf neighbor
```
