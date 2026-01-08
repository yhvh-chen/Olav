#!/usr/bin/env bash
# Comprehensive L1-L4 Lab Inspection Quick Reference

## 📋 运行comprehensive L1-L4检查

### 1️⃣ 所有测试
```bash
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py -v
```

### 2️⃣ 仅comprehensive全栈测试
```bash
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestComprehensiveL1L4LabInspection -v -s
```

### 3️⃣ 特定L层测试
```bash
# L1 Physical Layer
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestL1PhysicalLayer -v

# L2 Data Link Layer
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestL2DataLinkLayer -v

# L3 Network Layer
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestL3NetworkLayer -v

# L4 Transport Layer
uv run pytest tests/e2e/test_phase5_comprehensive_l1l4.py::TestL4TransportLayer -v
```

### 4️⃣ 使用标记过滤
```bash
# 所有comprehensive L1-L4测试
uv run pytest -m comprehensive_l1l4 -v

# 所有lab检查测试
uv run pytest -m lab_inspection -v

# 两者结合
uv run pytest -m "comprehensive_l1l4 and lab_inspection" -v
```

## 📊 在OLAV Agent中使用

### 触发comprehensive检查的用户请求
```
"Inspect all lab devices"
"Full L1-L4 health check lab"
"Complete network device inspection"
"Lab network comprehensive inspection"
```

### Agent自动执行
1. ✅ 匹配device-inspection skill
2. ✅ 列举lab组中的所有设备
3. ✅ 对每个设备执行comprehensive L1-L4模板
4. ✅ 生成统一的多设备报告
5. ✅ 标记异常和提供建议

## 📈 检查内容

### L1 - 物理层 (CPU/Memory/Temperature/Power)
- 设备型号、序列号、运行时间
- 硬件模块库存
- 温度、电源、风扇状态
- 物理接口状态

### L2 - 数据链路层 (VLAN/STP/LLDP/MAC)
- VLAN配置和状态
- STP拓扑和收敛
- LLDP邻居发现
- MAC地址表状态

### L3 - 网络层 (Routes/OSPF/BGP)
- 路由统计和汇总
- OSPF邻居和接口状态
- BGP邻居和前缀
- VPNv4状态（如适用）

### L4 - 传输层 (TCP/Processes/Errors)
- TCP会话计数
- 进程CPU分解
- 内存池统计
- 接口错误和丢包计数

## 📁 生成的报告

所有报告保存到: `.olav/reports/`

### 报告类型
```
lab-l1-physical-YYYYMMDD-HHMMSS.html
  └─ L1物理层详细数据

lab-comprehensive-l1l4-YYYYMMDD-HHMMSS.html
  └─ 完整L1-L4综合报告（所有8个设备）

lab-anomalies-YYYYMMDD-HHMMSS.html
  └─ 异常检测和建议
```

### 报告内容
```
Executive Summary
  • 设备总数
  • 整体健康状态
  • L1-L4状态矩阵

Device-by-Device Details
  • 每个设备的L1-L4数据
  • 性能指标
  • 错误计数

Anomaly Detection
  • Critical issues (红色 ❌)
  • Warnings (黄色 ⚠️)
  • Informational (蓝色 ℹ️)

Recommendations
  • 按优先级的行动项
  • 故障排除步骤
```

## ✅ 测试统计

```
Total Tests:    9
Passed:         8 (88.9%)
Skipped:        1 (11.1%)
Execution:      1.40s
Coverage:       L1-L4 (100%)
```

## 🔧 配置

### Nornir设备清单 (.olav/config/nornir/config.yaml)
```yaml
---
nornir:
  inventory:
    plugin: netmiko_inventory
    options:
      group_file: ".olav/config/nornir/groups.yaml"
      host_file: ".olav/config/nornir/hosts.yaml"
  runner:
    plugin: threaded
    options:
      num_workers: 4
```

### 设备定义 (.olav/config/nornir/hosts.yaml)
```yaml
lab:
  R1:
    hostname: 10.1.1.1
    groups: [lab, routers]
  R2:
    hostname: 10.1.1.2
    groups: [lab, routers]
  # ... more devices
```

## 🐛 故障排查

### 问题：No lab devices available
```
Solution:
1. 验证.olav/config/nornir/hosts.yaml中有设备
2. 确保设备在'lab'组中
3. 验证网络连接到所有设备
4. 检查SSH凭证
```

### 问题：Cannot query device
```
Solution:
1. 检查SSH连接: ssh user@device_ip
2. 验证Nornir配置
3. 检查防火墙规则
4. 验证设备SSH端口是否打开
```

### 问题：Report generation failed
```
Solution:
1. 检查.olav/reports目录权限
2. 验证Jinja2模板存在
3. 检查磁盘空间
4. 查看pytest输出获取详细错误
```

## 📚 相关文档

- [COMPREHENSIVE_L1L4_SIMPLIFICATION.md](COMPREHENSIVE_L1L4_SIMPLIFICATION.md) - 详细总结
- [.olav/skills/device-inspection.md](.olav/skills/device-inspection.md) - Skill定义
- [PHASE_5_REAL_DEVICES_GUIDE.md](PHASE_5_REAL_DEVICES_GUIDE.md) - Real设备配置指南
- [DESIGN_V0.8.md](DESIGN_V0.8.md) - 架构设计文档

## 🎯 最佳实践

### ✅ 推荐做法
- 使用标记过滤运行特定类别的测试
- 定期检查报告中的anomalies
- 建立baseline进行历史比较
- 自动化定期的comprehensive检查

### ❌ 避免做法
- 不要修改核心检查模板
- 不要跳过L4错误检查
- 不要忽视CRITICAL异常
- 不要禁用anomaly检测

---

**版本**: 0.8.0  
**上次更新**: 2026-01-08  
**维护**: GitHub Copilot + Claude Haiku 4.5
