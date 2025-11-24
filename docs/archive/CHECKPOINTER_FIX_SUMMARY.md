# Checkpointer 设置问题解决方案总结

## 问题回顾

在 OLAV 项目中，`test_netbox_hitl.py` 和其他测试脚本遇到了 PostgreSQL checkpointer 设置问题。

## 两个主要错误

### 错误 1：AttributeError: '_GeneratorContextManager' object has no attribute 'setup'

**原因**：
```python
# ❌ 错误代码
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(settings.postgres_uri)
checkpointer.setup()  # AttributeError!
```

`PostgresSaver.from_conn_string()` 返回的是**上下文管理器**，不是直接可用的 checkpointer 对象。

**解决方案**：
```python
# ✅ 正确代码
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(settings.postgres_uri) as checkpointer:
    # checkpointer 在这里可用
    agent = create_deep_agent(checkpointer=checkpointer, ...)
    result = await agent.ainvoke(...)
```

### 错误 2：psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' (Windows 特有)

**原因**：
Windows 默认的 `ProactorEventLoop` 不支持 psycopg 异步操作。

**错误信息**：
```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
Please use a compatible event loop, for instance by running 
'asyncio.run(..., loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

**解决方案**：
```python
# 在脚本最开头（所有异步导入之前）添加
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

## 已修复的文件

### 1. `scripts/test_netbox_hitl.py`

**修复内容**：
- ✅ 改用 `AsyncPostgresSaver`（不是 `PostgresSaver`）
- ✅ 使用 `async with` 上下文管理器
- ✅ 删除 `.setup()` 调用
- ✅ 添加 Windows 事件循环修复
- ✅ 调整所有代码缩进到 `async with` 块内

**关键代码**：
```python
import sys
import asyncio

# Windows 修复
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def test_function():
    async with AsyncPostgresSaver.from_conn_string(settings.postgres_uri) as checkpointer:
        agent = create_deep_agent(checkpointer=checkpointer, ...)
        result = await agent.ainvoke(...)  # 必须在 async with 块内
        return result
```

### 2. `docs/CHECKPOINTER_SETUP.md`

**新建文档**包含：
- ✅ 问题原因详解
- ✅ Windows 平台特殊注意事项
- ✅ 同步 vs 异步版本对比
- ✅ 测试脚本模板（含 Windows 修复）
- ✅ CLI 应用模板
- ✅ 常见错误及解决方案
- ✅ 最佳实践

## 核心修复模式

### 旧代码（错误）

```python
"""错误的 checkpointer 使用模式"""
import asyncio
from langgraph.checkpoint.postgres import PostgresSaver

async def test_agent():
    # ❌ 错误 1：使用同步版本
    checkpointer = PostgresSaver.from_conn_string(uri)
    
    # ❌ 错误 2：尝试调用 setup()
    checkpointer.setup()  # AttributeError!
    
    # ❌ 错误 3：在 Windows 上运行异步 psycopg
    # psycopg.InterfaceError: ProactorEventLoop 不兼容
    
    agent = create_deep_agent(checkpointer=checkpointer, ...)
    result = await agent.ainvoke(...)
```

### 新代码（正确）

```python
"""正确的 checkpointer 使用模式"""
import sys
import asyncio

# ✅ 修复 1：Windows 事件循环
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ✅ 修复 2：使用异步版本
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def test_agent():
    # ✅ 修复 3：使用 async with 上下文管理器
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        # ✅ 修复 4：所有操作在 async with 块内
        agent = create_deep_agent(checkpointer=checkpointer, ...)
        result = await agent.ainvoke(...)
        return result  # ✅ 正常工作
```

## 快速检查清单

在任何使用 PostgreSQL checkpointer 的脚本中，确保：

- [ ] 导入：`from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`
- [ ] Windows 修复：`if sys.platform == 'win32': asyncio.set_event_loop_policy(...)`
- [ ] 使用 `async with AsyncPostgresSaver.from_conn_string(...) as checkpointer:`
- [ ] 不要调用 `.setup()`（上下文管理器自动处理）
- [ ] 所有 agent 操作在 `async with` 块内完成
- [ ] 使用唯一的 `thread_id` 隔离测试

## 测试验证

运行修复后的脚本：
```bash
$env:PYTHONPATH="c:\Users\yhvh\Documents\code\Olav"
uv run python scripts/test_netbox_hitl.py
```

**预期结果**：
- ✅ 不再出现 `AttributeError: 'setup'`
- ✅ 不再出现 `ProactorEventLoop` 错误
- ✅ 可以正常连接 PostgreSQL
- ✅ Agent 可以正常执行

## 后续步骤

1. **检查其他测试脚本**：
   ```bash
   # 搜索仍使用同步版本的文件
   grep -r "from langgraph.checkpoint.postgres import PostgresSaver" scripts/
   ```

2. **应用相同修复**：
   - 改用 `AsyncPostgresSaver`
   - 添加 Windows 事件循环修复
   - 使用 `async with` 管理生命周期

3. **更新 CLI 应用**（如果需要）：
   - `src/olav/main.py` 应该在启动时创建 checkpointer
   - 在关闭时清理 checkpointer
   - 参考 `docs/CHECKPOINTER_SETUP.md` 的 CLI 应用模板

## 参考文档

- **完整指南**：`docs/CHECKPOINTER_SETUP.md`
- **成功示例**：`scripts/test_agent_simple.py`
- **修复示例**：`scripts/test_netbox_hitl.py`

## 总结

**核心原则**：

1. ✅ 使用 `AsyncPostgresSaver`（异步版本）
2. ✅ Windows 上先设置 `SelectorEventLoop`
3. ✅ 使用 `async with` 管理生命周期
4. ✅ 所有操作在上下文管理器内完成

遵循这些原则，checkpointer 设置问题将彻底解决。
