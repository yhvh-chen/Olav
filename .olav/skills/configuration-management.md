---
id: configuration-management
intent: config
complexity: complex
description: "设备配置管理和变更执行，需要HITL审批"
examples:
  - "修改VLAN配置"
  - "更新BGP路由策略"
  - "应用安全策略"
enabled: true
---

# 配置管理技能

## 概述

配置管理技能用于设备配置变更和策略应用。

### 应用场景

- 应用接口配置
- 修改路由策略
- 更新 ACL
- 配置 BGP 参数

### 执行步骤

1. ✅ 验证变更的合理性
2. ⚠️ **请求人工审批** (HITL)
3. 应用配置到设备
4. 验证配置是否生效
5. 保存配置

### 风险等级

**高 - 所有配置变更需人工审批**

### 相关命令

```
configure terminal
interface <name>
ip address <ip> <mask>
exit
copy running-config startup-config
```
