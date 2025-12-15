# 清理建议执行脚本 (Cleanup Recommendations)

本文档提供了 CODE_AUDIT_REPORT.md 中推荐操作的可执行命令。

## ⚠️ 警告

在执行任何删除操作之前，请确保：
1. 已提交所有当前更改到 Git
2. 已创建备份分支
3. 已审查要删除的内容

```bash
# 创建备份分支
git checkout -b backup/pre-cleanup-2025-11-26
git checkout main
```

---

## P0 - 立即执行命令

### 1. 删除第三方项目副本

```powershell
# PowerShell 命令
Remove-Item -Recurse -Force archive/suzieq
Remove-Item -Recurse -Force archive/netbox
Remove-Item -Recurse -Force archive/deepagents
Remove-Item -Recurse -Force archive/ntc-templates
Remove-Item -Recurse -Force archive/langchain
Remove-Item -Recurse -Force archive/langgraph
```

### 2. 删除调试脚本目录

```powershell
Remove-Item -Recurse -Force scripts/debug
```

### 3. 删除未使用的工具

```powershell
# 保留 datetime 工具：用于 CLI 时间范围解析（今天/过去一周故障查询）
# 暂不删除，后续集成到 CLI 与工作流
# No action needed here
```

### 4. 删除根目录重复文件

```powershell
# 保留 docs/DESIGN.md，删除根目录版本
Remove-Item DESIGN.md
```

---

## P1 - 迁移测试文件

### 从 scripts/ 迁移到 tests/

```powershell
# 迁移到 tests/e2e/
Move-Item scripts/test_api_server.py tests/e2e/
Move-Item scripts/test_auth_cli.py tests/e2e/

# 迁移到 tests/unit/
Move-Item scripts/test_auth.py tests/unit/
Move-Item scripts/test_cli_basic.py tests/unit/

# 迁移到 tests/integration/
Move-Item scripts/test_cli_client.py tests/integration/
Move-Item scripts/test_cli_tool_direct.py tests/integration/
Move-Item scripts/test_llm_connection.py tests/integration/
Move-Item scripts/test_nornir_netbox.py tests/integration/
Move-Item scripts/test_openapi_docs.py tests/integration/
Move-Item scripts/test_openconfig_support.py tests/integration/
Move-Item scripts/test_suzieq_parquet_direct.py tests/integration/
```

### 删除过时脚本

```powershell
Remove-Item scripts/check_and_tag_devices.py
Remove-Item scripts/test_netbox_from_suzieq.py
Remove-Item scripts/test_scrapli_ssh.py
Remove-Item scripts/test_suzieq_in_container.py
Remove-Item scripts/debug_env.py
Remove-Item scripts/debug_llm_response.py
```

---

## P1 - 删除/更新测试文件

### 删除 Ghost 测试

```powershell
Remove-Item tests/unit/test_tools.py
Remove-Item tests/manual/test_suzieq_tool.py
```

### 需要更新的测试文件（手动更新）

以下文件需要手动更新导入和 API 调用：

1. `tests/unit/test_cli_tool.py` - 更新导入路径
2. `tests/unit/test_suzieq_tools_parquet.py` - 更新到类 API
3. `tests/unit/test_suzieq_tools_extended.py` - 更新到类 API
4. `tests/manual/test_parquet_tool.py` - 更新 API
5. `tests/manual/test_time_filter.py` - 更新 API

---

## P2 - 工具重构 (中期)

这些更改需要更谨慎的迁移计划：

### 步骤 1: 更新 workflow 导入

需要更新以下文件中的工具导入：

- `src/olav/workflows/query_diagnostic.py`
- `src/olav/workflows/device_execution.py`
- `src/olav/workflows/netbox_management.py`
- `src/olav/core/inventory_manager.py`
- `src/olav/tools/cli_tool.py`
- `src/olav/strategies/fast_path.py`

### 步骤 2: 删除旧版工具

完成迁移后：

```powershell
Remove-Item src/olav/tools/netbox_tool.py
Remove-Item src/olav/tools/nornir_tool.py
Remove-Item src/olav/tools/opensearch_tool.py
```

### 步骤 3: 重命名新版工具

```powershell
Rename-Item src/olav/tools/netbox_tool_refactored.py netbox_tool.py
Rename-Item src/olav/tools/nornir_tool_refactored.py nornir_tool.py
Rename-Item src/olav/tools/opensearch_tool_refactored.py opensearch_tool.py
Rename-Item src/olav/tools/datetime_tool_refactored.py datetime_tool.py
```

---

## 验证清理结果

执行清理后，运行以下命令验证：

```powershell
# 检查导入错误
uv run python -c "from olav.main import app; print('Main imports OK')"

# 运行测试
uv run pytest tests/unit/ -v --tb=short

# 检查代码质量
uv run ruff check src/ --fix
```

---

## 回滚计划

如果清理导致问题：

```bash
# 恢复到备份分支
git checkout backup/pre-cleanup-2025-11-26

# 或者恢复特定文件
git checkout backup/pre-cleanup-2025-11-26 -- <file_path>
```

---

*生成时间: 2025-11-26*
