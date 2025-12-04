# 工具层重构计划 (Tool Layer Refactoring Plan)

## 背景

当前 `src/olav/tools/` 目录存在新旧两套工具实现：

| 类型 | 命名模式 | API 风格 | 状态 |
|------|----------|----------|------|
| 旧版 | `*_tool.py` | LangChain StructuredTool | 仍在 workflow 中使用 |
| 新版 | `*_tool_refactored.py` | BaseTool Protocol | 部分使用 |

## 目标

统一到 `BaseTool` Protocol 模式，删除冗余代码。

---

## Phase 1: 分析当前依赖

### 旧版工具使用情况

#### `netbox_tool.py`
```python
# 导出: netbox_api_call, netbox_schema_search
# 类型: StructuredTool (LangChain @tool decorator)

# 被引用:
# - src/olav/workflows/netbox_management.py:46
# - src/olav/tools/cli_tool.py:64
# - src/olav/core/inventory_manager.py:18
```

#### `nornir_tool.py`
```python
# 导出: cli_tool, netconf_tool
# 类型: StructuredTool

# 被引用:
# - src/olav/workflows/query_diagnostic.py:41
# - src/olav/workflows/device_execution.py:44
```

#### `opensearch_tool.py`
```python
# 导出: search_openconfig_schema, search_episodic_memory
# 类型: StructuredTool

# 被引用:
# - src/olav/workflows/query_diagnostic.py:42
# - src/olav/workflows/netbox_management.py:47
# - src/olav/workflows/device_execution.py:45
# - src/olav/strategies/fast_path.py:45 (使用 refactored 版本)
```

#### `datetime_tool.py`
```python
# 导出: parse_time_range
# 类型: StructuredTool

# 被引用: 无
# 状态: 可立即删除
```

---

## Phase 2: 迁移策略

### 方案 A: 适配器模式 (推荐)

在新版工具中创建兼容旧版 API 的适配器：

```python
# src/olav/tools/netbox_tool_refactored.py

# 新版类
class NetBoxAPITool(BaseTool):
    async def execute(self, endpoint: str, method: str, ...) -> ToolOutput:
        ...

# 兼容适配器 (保持旧版函数签名)
_netbox_api_tool = NetBoxAPITool()

@tool
def netbox_api_call(endpoint: str, method: str = "GET", ...) -> str:
    """StructuredTool 兼容适配器"""
    import asyncio
    result = asyncio.run(_netbox_api_tool.execute(endpoint, method, ...))
    return result.output
```

**优点**: 渐进式迁移，不破坏现有 workflow
**缺点**: 临时增加代码复杂度

### 方案 B: 直接替换

1. 将所有 workflow 中的导入改为新版工具
2. 更新调用方式从函数调用改为 `await tool.execute(...)`
3. 删除旧版文件

**优点**: 一步到位
**缺点**: 风险较高，需要大量测试

---

## Phase 3: 迁移顺序

### 第一批: datetime_tool (无风险)

```bash
# 1. 删除旧版
rm src/olav/tools/datetime_tool.py

# 2. 重命名新版
mv src/olav/tools/datetime_tool_refactored.py src/olav/tools/datetime_tool.py

# 3. 更新测试
# tests/unit/test_datetime_tool_refactored.py 导入路径
```

### 第二批: opensearch_tool (低风险)

`fast_path.py` 已经使用 refactored 版本，迁移较容易：

```python
# 当前 (src/olav/strategies/fast_path.py:45)
from olav.tools.opensearch_tool_refactored import EpisodicMemoryTool

# 迁移后
from olav.tools.opensearch_tool import EpisodicMemoryTool
```

需更新:
- `query_diagnostic.py`
- `netbox_management.py`
- `device_execution.py`

### 第三批: nornir_tool (中风险)

涉及 HITL 和设备交互，需要充分测试。

### 第四批: netbox_tool (中风险)

被多处引用，包括 `cli_tool.py` 和 `inventory_manager.py`。

---

## Phase 4: 文件变更清单

### 删除文件
```
src/olav/tools/datetime_tool.py          # Phase 3.1
src/olav/tools/opensearch_tool.py        # Phase 3.2
src/olav/tools/nornir_tool.py            # Phase 3.3
src/olav/tools/netbox_tool.py            # Phase 3.4
```

### 重命名文件
```
datetime_tool_refactored.py  → datetime_tool.py
opensearch_tool_refactored.py → opensearch_tool.py
nornir_tool_refactored.py     → nornir_tool.py
netbox_tool_refactored.py     → netbox_tool.py
```

### 更新导入的文件
```
src/olav/workflows/query_diagnostic.py
src/olav/workflows/device_execution.py
src/olav/workflows/netbox_management.py
src/olav/core/inventory_manager.py
src/olav/tools/cli_tool.py
src/olav/strategies/fast_path.py
tests/unit/test_datetime_tool_refactored.py
tests/unit/test_netbox_tool_refactored.py
tests/unit/test_nornir_tool_refactored.py
tests/unit/test_opensearch_tool_refactored.py
```

---

## Phase 5: 测试计划

### 每批迁移后运行

```bash
# 单元测试
uv run pytest tests/unit/ -v -k "tool"

# 集成测试
uv run pytest tests/integration/ -v

# E2E 测试
uv run pytest tests/e2e/ -v

# 冒烟测试
uv run python -c "
from olav.main import app
from olav.workflows.query_diagnostic import QueryDiagnosticWorkflow
from olav.workflows.device_execution import DeviceExecutionWorkflow
print('All imports successful')
"
```

---

## 时间线估算

| Phase | 任务 | 预计时间 |
|-------|------|----------|
| 3.1 | datetime_tool 迁移 | 0.5 天 |
| 3.2 | opensearch_tool 迁移 | 1 天 |
| 3.3 | nornir_tool 迁移 | 2 天 |
| 3.4 | netbox_tool 迁移 | 2 天 |
| 测试 | 全面回归测试 | 1 天 |
| **总计** | | **~6.5 天** |

---

## 回滚计划

每批迁移前创建 Git tag:

```bash
git tag pre-tool-migration-datetime
git tag pre-tool-migration-opensearch
git tag pre-tool-migration-nornir
git tag pre-tool-migration-netbox
```

如迁移失败:

```bash
git revert --no-commit HEAD~<n>..HEAD
git commit -m "Revert tool migration phase X"
```

---

*文档创建: 2025-11-26*
