# Phase 5 Real Device Testing Guide

## 概述

Phase 5 现在支持**真实设备和真实 LLM 测试**。这个指南说明如何配置和运行这些测试。

---

## 前置条件

### 1. 真实设备连接（Nornir）

需要配置 Nornir 来连接真实网络设备：

```yaml
# .olav/config/nornir/config.yaml
---
inventory:
  plugin: SimpleInventory
  options:
    host_file: "inventory/hosts.yaml"
    group_file: "inventory/groups.yaml"
    defaults_file: "inventory/defaults.yaml"

runner:
  plugin: ThreadPoolExecutor
  options:
    num_workers: 10

logging:
  log_file: "nornir.log"
  level: DEBUG
```

### 2. 设备清单（Inventory）

创建设备清单文件：

```yaml
# inventory/hosts.yaml
---
R1:
  hostname: 10.1.1.1
  groups:
    - routers
    - core
  data:
    device_type: cisco_ios
    username: admin
    password: ${DEVICE_PASSWORD}

R2:
  hostname: 10.1.1.2
  groups:
    - routers
    - core

CS-DC1:
  hostname: 10.2.1.1
  groups:
    - switches
    - access
```

```yaml
# inventory/groups.yaml
---
routers:
  data:
    connection_options:
      ssh:
        port: 22

switches:
  data:
    device_type: cisco_ios
```

### 3. 真实 LLM API 密钥

设置环境变量以使用真实 LLM：

```bash
# .env
export OPENAI_API_KEY=sk-...
# 或
export ANTHROPIC_API_KEY=...

# 可选：指定 LLM 模型
export LLM_PROVIDER=openai
export LLM_MODEL_NAME=gpt-4-turbo
```

### 4. 网络连接

确保：
- ✅ 可以通过 SSH 连接到所有设备
- ✅ 设备凭证有效且有足够权限
- ✅ 防火墙允许 SSH 连接

---

## 运行真实设备测试

### 基础用法

```bash
# 运行所有真实设备测试
uv run pytest tests/e2e/test_phase5_real_devices.py -v

# 运行特定测试类
uv run pytest tests/e2e/test_phase5_real_devices.py::TestHealthCheckRealDevices -v

# 运行特定测试方法
uv run pytest tests/e2e/test_phase5_real_devices.py::TestHealthCheckRealDevices::test_health_check_single_device -v
```

### 带有详细输出

```bash
# 显示测试输出（设备命令执行结果）
uv run pytest tests/e2e/test_phase5_real_devices.py -v -s

# 显示完整的错误追踪
uv run pytest tests/e2e/test_phase5_real_devices.py -v --tb=long
```

### 仅运行特定标记

```bash
# 只运行健康检查测试
uv run pytest tests/e2e/test_phase5_real_devices.py -m "health" -v

# 只运行需要真实 LLM 的测试
uv run pytest tests/e2e/test_phase5_real_devices.py -m "real_llm" -v

# 只运行需要真实设备的测试
uv run pytest tests/e2e/test_phase5_real_devices.py -m "real_devices" -v
```

### 跳过某些测试

```bash
# 跳过需要多个设备的测试
uv run pytest tests/e2e/test_phase5_real_devices.py -v -k "not multi_device"

# 跳过 LLM 分析测试
uv run pytest tests/e2e/test_phase5_real_devices.py -v -k "not llm"
```

---

## 测试类别

### 1. 健康检查测试 (TestHealthCheckRealDevices)

**命令**:
```bash
uv run pytest tests/e2e/test_phase5_real_devices.py::TestHealthCheckRealDevices -v -s
```

**测试内容**:
- ✅ 单设备健康检查 (show version, CPU, 内存, 接口)
- ✅ 多设备健康检查 (并行检查多个设备)
- ✅ LLM 分析 (使用真实 LLM 分析设备数据)

**输出**: `.olav/reports/health-check-*.html`

---

### 2. BGP 审计测试 (TestBGPAuditRealDevices)

**命令**:
```bash
uv run pytest tests/e2e/test_phase5_real_devices.py::TestBGPAuditRealDevices -v -s
```

**测试内容**:
- ✅ 单路由器 BGP 审计
- ✅ LLM 异常检测 (检测异常 BGP 邻居、路由)
- ✅ 多设备 BGP 对比

**输出**: `.olav/reports/bgp-audit-*.html`

---

### 3. 接口错误测试 (TestInterfaceErrorsRealDevices)

**命令**:
```bash
uv run pytest tests/e2e/test_phase5_real_devices.py::TestInterfaceErrorsRealDevices -v -s
```

**测试内容**:
- ✅ 接口错误检测
- ✅ LLM 诊断 (根据错误统计进行诊断)
- ✅ 错误趋势分析

**输出**: `.olav/reports/interface-errors-*.html`

---

### 4. 安全基线测试 (TestSecurityBaselineRealDevices)

**命令**:
```bash
uv run pytest tests/e2e/test_phase5_real_devices.py::TestSecurityBaselineRealDevices -v -s
```

**测试内容**:
- ✅ 安全基线扫描 (SSH, ACL, 加密密钥)
- ✅ LLM 合规性检查 (识别安全差距)

**输出**: `.olav/reports/security-baseline-*.html`

---

### 5. 综合工作流测试 (TestComprehensiveWorkflowRealDevices)

**命令**:
```bash
uv run pytest tests/e2e/test_phase5_real_devices.py::TestComprehensiveWorkflowRealDevices -v -s
```

**测试内容**:
- ✅ 完整检查工作流 (范围解析 → 数据收集 → 报告生成 → LLM 分析)
- ✅ 多设备检查工作流
- ✅ LLM 路由和分析

---

## 故障排除

### 问题 1: "Nornir initialization failed"

**原因**: Nornir 配置不正确或设备清单缺失

**解决方案**:
```bash
# 验证 Nornir 配置
uv run python -c "from nornir import InitNornir; nr = InitNornir(config_file='.olav/config/nornir/config.yaml'); print(list(nr.inventory.hosts.keys()))"

# 检查清单文件
cat .olav/config/nornir/config.yaml
ls inventory/
```

### 问题 2: "No devices in Nornir inventory"

**原因**: 清单文件为空或配置错误

**解决方案**:
```bash
# 检查并填充清单
cat inventory/hosts.yaml
# 确保至少有一个设备

# 验证设备可达性
ping 10.1.1.1  # 替换为实际设备 IP
```

### 问题 3: "SSH connection refused"

**原因**: 设备凭证错误或 SSH 端口关闭

**解决方案**:
```bash
# 手动测试连接
ssh admin@10.1.1.1

# 检查设备凭证
env | grep DEVICE
# 或在 .env 中设置
export DEVICE_USERNAME=admin
export DEVICE_PASSWORD=xxx
```

### 问题 4: "LLM API key not found"

**原因**: 环境变量未设置

**解决方案**:
```bash
# 设置 LLM API 密钥
export OPENAI_API_KEY=sk-...

# 验证
echo $OPENAI_API_KEY
```

### 问题 5: 测试被跳过 (skipped)

**原因**: 设备不可达或 API 调用失败

**解决方案**:
```bash
# 查看详细信息
uv run pytest tests/e2e/test_phase5_real_devices.py -v -s --tb=short

# 检查报告中的错误信息
```

---

## 测试报告

所有生成的报告保存在 `.olav/reports/` 目录：

```
.olav/reports/
├── health-check-20260108-*.html
├── bgp-audit-20260108-*.html
├── interface-errors-20260108-*.html
├── security-baseline-20260108-*.html
└── multi-device-inspection-20260108-*.html
```

### 查看报告

```bash
# 在浏览器中打开
open .olav/reports/health-check-*.html

# 或在 VS Code 中预览
code .olav/reports/
```

---

## 安全注意事项

### 凭证管理

```bash
# ✅ 正确做法：使用环境变量
export DEVICE_PASSWORD=$(pass network/admin_password)

# ❌ 错误做法：在清单中硬编码密码
# 永远不要在 inventory/hosts.yaml 中硬编码敏感信息
```

### 防火墙规则

```bash
# 仅从特定 IP 允许测试脚本连接
# firewall-cmd --add-rich-rule='rule family="ipv4" source address="10.0.0.5" port protocol="tcp" port="22" accept'
```

### 审计日志

所有设备命令执行记录在 `nornir.log`：

```bash
# 查看执行记录
tail -f nornir.log
```

---

## 最佳实践

### 1. 逐步增加测试范围

```bash
# 阶段 1: 单设备测试
uv run pytest tests/e2e/test_phase5_real_devices.py::TestHealthCheckRealDevices::test_health_check_single_device -v

# 阶段 2: 多设备测试
uv run pytest tests/e2e/test_phase5_real_devices.py::TestHealthCheckRealDevices::test_health_check_multiple_devices -v

# 阶段 3: 完整工作流测试
uv run pytest tests/e2e/test_phase5_real_devices.py::TestComprehensiveWorkflowRealDevices -v
```

### 2. 使用虚拟设备进行开发测试

在真实网络上运行前：

```bash
# 使用容器化 Cisco IOS 模拟器（如 GNS3、EVE-NG）
# 或使用 Nornir 模拟器
uv run pytest tests/e2e/test_phase5_production.py -v  # Mock 测试
```

### 3. 监控资源使用

```bash
# 运行测试时监控 CPU/内存
watch -n 1 'ps aux | grep pytest'
```

### 4. 使用日志进行调试

```bash
# 启用详细日志
export LOGLEVEL=DEBUG
uv run pytest tests/e2e/test_phase5_real_devices.py -v -s --log-cli-level=DEBUG
```

---

## 集成 CI/CD

### GitHub Actions 示例

```yaml
# .github/workflows/test-real-devices.yml
name: Real Device Tests

on:
  schedule:
    - cron: '0 2 * * *'  # 每天 2:00 运行
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      DEVICE_USERNAME: ${{ secrets.DEVICE_USERNAME }}
      DEVICE_PASSWORD: ${{ secrets.DEVICE_PASSWORD }}
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - name: Install uv
        run: |
          pip install uv
          uv sync --dev
      
      - name: Run real device tests
        run: |
          uv run pytest tests/e2e/test_phase5_real_devices.py -v --tb=short
      
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: inspection-reports
          path: .olav/reports/
```

---

## 总结

| 功能 | Mock 测试 | 真实设备测试 |
|------|----------|----------|
| **执行速度** | ⚡ 快 (<1s) | 🐢 慢 (10-60s) |
| **真实性** | ❌ 模拟数据 | ✅ 真实数据 |
| **LLM 分析** | ⚠️ Mock | ✅ 真实 LLM |
| **设备连接** | ❌ 无 | ✅ 真实 SSH/NETCONF |
| **适用场景** | 开发/测试 | 生产验证 |
| **成本** | 🟢 低 | 🟡 中等（API 调用） |

### 运行建议

```bash
# 开发阶段：使用 Mock 测试（快速反馈）
uv run pytest tests/e2e/test_phase5_production.py -v

# 集成阶段：添加真实设备测试
uv run pytest tests/e2e/test_phase5_real_devices.py -v -m "not real_llm"

# 发布前：完整真实设备 + LLM 验证
uv run pytest tests/e2e/test_phase5_real_devices.py -v
```

---

**更多信息**: 参考 [DESIGN_V0.8.md](../DESIGN_V0.8.md)
