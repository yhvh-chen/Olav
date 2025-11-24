# PostgreSQL Checkpointer 设置指南

## 问题描述

在 OLAV 项目中使用 LangGraph 的 PostgreSQL checkpointer 时，常遇到以下错误：

```python
AttributeError: '_GeneratorContextManager' object has no attribute 'setup'
```

## 根本原因

`PostgresSaver.from_conn_string()` 返回的是一个**上下文管理器**（context manager），而不是直接可用的 checkpointer 对象。

## 解决方案

### 🪟 Windows 平台特殊注意事项

在 Windows 上，psycopg 异步需要 `SelectorEventLoop`，默认的 `ProactorEventLoop` 不兼容：

```python
import sys
import asyncio

# Windows: 必须在导入 AsyncPostgresSaver 之前设置
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
```

**错误信息**：
```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
Please use a compatible event loop, for instance by running
'asyncio.run(..., loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

**解决方法**：在脚本开头（所有异步导入之前）添加：
```python
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

### ✅ 方案 1：使用异步上下文管理器（推荐）

使用 `AsyncPostgresSaver` + `async with` 模式：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def my_agent_function():
    # ✅ 正确：使用 async with 自动管理生命周期
    async with AsyncPostgresSaver.from_conn_string(settings.postgres_uri) as checkpointer:
        # checkpointer 在这个块内有效
        agent = create_deep_agent(
            model=model,
            checkpointer=checkpointer,
            subagents=[...],
        )
        
        # 执行操作
        result = await agent.ainvoke(...)
        return result
    # checkpointer 自动清理
```

**优点**：
- ✅ 自动管理 checkpointer 生命周期
- ✅ 异常安全（自动清理资源）
- ✅ 符合 Python 最佳实践
- ✅ 代码简洁

**缺点**：
- ⚠️ 所有代码必须在 `async with` 块内
- ⚠️ 必须使用 async/await 语法

### ✅ 方案 2：手动管理生命周期

如果需要在多个作用域使用 checkpointer：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def setup_checkpointer():
    # 创建上下文管理器
    manager = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
    
    # 手动进入上下文
    checkpointer = await manager.__aenter__()
    
    return checkpointer, manager

async def cleanup_checkpointer(manager):
    # 手动退出上下文
    await manager.__aexit__(None, None, None)

# 使用示例
async def main():
    checkpointer, manager = await setup_checkpointer()
    
    try:
        agent = create_deep_agent(checkpointer=checkpointer, ...)
        result = await agent.ainvoke(...)
    finally:
        await cleanup_checkpointer(manager)
```

**优点**：
- ✅ 灵活控制生命周期
- ✅ 可以在多个函数间传递

**缺点**：
- ⚠️ 需要手动管理清理
- ⚠️ 代码复杂度更高
- ⚠️ 容易忘记清理导致资源泄露

### ❌ 错误方案：直接调用 setup()

```python
from langgraph.checkpoint.postgres import PostgresSaver

# ❌ 错误：from_conn_string() 返回上下文管理器，不是 checkpointer
checkpointer = PostgresSaver.from_conn_string(settings.postgres_uri)
checkpointer.setup()  # AttributeError!
```

**为什么错误**：
- `from_conn_string()` 返回 `_GeneratorContextManager`
- 上下文管理器没有 `.setup()` 方法
- 必须先进入上下文才能获得真正的 checkpointer

## 项目中的实际应用

### 测试脚本模板

```python
"""测试脚本模板 - 使用 AsyncPostgresSaver"""
import asyncio
import sys
from pathlib import Path

# Windows: 修复事件循环
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from deepagents import create_deep_agent

from olav.core.llm import LLMFactory
from olav.core.settings import settings
from olav.agents.netbox_agent import create_netbox_subagent


async def test_my_agent():
    """测试函数"""
    # ✅ 正确模式
    async with AsyncPostgresSaver.from_conn_string(settings.postgres_uri) as checkpointer:
        # 1. 创建 LLM
        model = LLMFactory.get_chat_model()
        
        # 2. 创建 SubAgent
        netbox_subagent = create_netbox_subagent()
        
        # 3. 创建 Agent
        agent = create_deep_agent(
            model=model,
            system_prompt="你是 NetBox 管理专家。",
            checkpointer=checkpointer,
            subagents=[netbox_subagent],
        )
        
        # 4. 执行查询
        config = {"configurable": {"thread_id": "test-123"}}
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="查询设备清单")]},
            config=config
        )
        
        print(f"结果: {result}")
        return result


if __name__ == "__main__":
    asyncio.run(test_my_agent())
```

### CLI 应用模板

对于 CLI 应用（如 `olav.main`），应该在应用启动时创建 checkpointer，在关闭时清理：

```python
"""CLI 应用模板"""
import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from olav.core.settings import settings


class OLAVChatApp:
    def __init__(self):
        self.checkpointer_manager = None
        self.checkpointer = None
        self.agent = None
    
    async def startup(self):
        """启动时初始化"""
        # 创建并进入上下文
        self.checkpointer_manager = AsyncPostgresSaver.from_conn_string(
            settings.postgres_uri
        )
        self.checkpointer = await self.checkpointer_manager.__aenter__()
        
        # 创建 Agent
        self.agent = create_deep_agent(
            checkpointer=self.checkpointer,
            ...
        )
    
    async def shutdown(self):
        """关闭时清理"""
        if self.checkpointer_manager:
            await self.checkpointer_manager.__aexit__(None, None, None)
    
    async def chat(self, query: str):
        """执行查询"""
        result = await self.agent.ainvoke({"messages": [HumanMessage(content=query)]})
        return result


async def main():
    app = OLAVChatApp()
    
    try:
        await app.startup()
        
        # 交互式聊天循环
        while True:
            query = input("OLAV> ")
            if query.lower() in ["exit", "quit"]:
                break
            
            result = await app.chat(query)
            print(result)
    
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

## 同步 vs 异步版本对比

| 特性 | PostgresSaver (同步) | AsyncPostgresSaver (异步) |
|------|---------------------|--------------------------|
| 导入路径 | `langgraph.checkpoint.postgres` | `langgraph.checkpoint.postgres.aio` |
| 使用场景 | 同步代码（不推荐） | 异步代码（推荐） ✅ |
| 上下文管理器 | `with` | `async with` |
| Agent 调用 | `.invoke()` | `.ainvoke()` |
| 性能 | 阻塞 I/O | 非阻塞 I/O ⚡ |
| 适用于 OLAV | ❌ 不适用（全异步架构） | ✅ 适用 |

## 常见错误及解决

### 错误 1：AttributeError: 'setup'

```python
# ❌ 错误代码
checkpointer = PostgresSaver.from_conn_string(uri)
checkpointer.setup()  # AttributeError!

# ✅ 正确代码
async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
    # 使用 checkpointer
    pass
```

### 错误 2：在 async with 外使用 checkpointer

```python
# ❌ 错误：checkpointer 在块外失效
async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
    agent = create_deep_agent(checkpointer=checkpointer, ...)

result = await agent.ainvoke(...)  # RuntimeError: checkpointer 已关闭

# ✅ 正确：所有操作在块内
async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
    agent = create_deep_agent(checkpointer=checkpointer, ...)
    result = await agent.ainvoke(...)
```

### 错误 3：混用同步和异步版本

```python
# ❌ 错误：在异步函数中使用同步版本
from langgraph.checkpoint.postgres import PostgresSaver

async def my_async_function():
    with PostgresSaver.from_conn_string(uri) as checkpointer:  # 不匹配
        await agent.ainvoke(...)  # 潜在的阻塞

# ✅ 正确：异步函数使用异步版本
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def my_async_function():
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        await agent.ainvoke(...)
```

### 错误 4：Windows ProactorEventLoop 不兼容（Windows 特有）

```python
# ❌ 错误：在 Windows 上直接使用 AsyncPostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def main():
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:  
        # psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'
        pass

# ✅ 正确：先设置 SelectorEventLoop
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def main():
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        pass  # 正常工作
```

**错误信息**：
```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in 
async mode. Please use a compatible event loop...
```

**原因**：Windows 的默认 `ProactorEventLoop` 不支持 psycopg 异步操作

**解决**：在脚本最开头设置 `WindowsSelectorEventLoopPolicy`

## 最佳实践

### 1. 优先使用 AsyncPostgresSaver

OLAV 是全异步架构，所有 Agent 调用都是 `ainvoke()`，应该使用异步版本的 checkpointer。

### 2. 使用 async with 管理生命周期

除非有特殊需求，始终使用 `async with` 自动管理 checkpointer 生命周期。

### 3. 在测试中隔离线程

每个测试使用不同的 `thread_id` 以避免状态污染：

```python
async def test_case_1():
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        config = {"configurable": {"thread_id": "test-case-1"}}  # 唯一 ID
        agent = create_deep_agent(checkpointer=checkpointer, ...)
        await agent.ainvoke(..., config=config)

async def test_case_2():
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        config = {"configurable": {"thread_id": "test-case-2"}}  # 不同 ID
        agent = create_deep_agent(checkpointer=checkpointer, ...)
        await agent.ainvoke(..., config=config)
```

### 4. 环境变量配置

在 `.env` 中配置 PostgreSQL 连接：

```bash
# PostgreSQL Checkpointer
POSTGRES_URI=postgresql://olav:OlavPG123!@localhost:5432/olav

# 或分别配置
POSTGRES_USER=olav
POSTGRES_PASSWORD=OlavPG123!
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=olav
```

在 `settings.py` 中读取：

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Option 1: 直接使用 URI
    postgres_uri: str
    
    # Option 2: 分开配置（在 __init__ 中组合）
    # postgres_user: str
    # postgres_password: str
    # postgres_host: str = "localhost"
    # postgres_port: int = 5432
    # postgres_db: str = "olav"

settings = Settings()
```

## 项目文件修复清单

以下文件已修复为使用 `AsyncPostgresSaver`：

- ✅ `scripts/test_netbox_hitl.py` - NetBox HITL 测试
- ✅ `scripts/test_agent_simple.py` - 简化 Agent 测试
- ✅ `scripts/test_cli_tool_direct.py` - CLI 工具直接测试

**待修复文件**（如果存在）：

检查以下文件是否需要修复：

```bash
# 搜索仍使用同步版本的文件
grep -r "from langgraph.checkpoint.postgres import PostgresSaver" src/ scripts/
grep -r "PostgresSaver.from_conn_string" src/ scripts/
```

如果发现使用同步版本，应按以下步骤修复：

1. 改 import：`PostgresSaver` → `AsyncPostgresSaver`
2. 改路径：`langgraph.checkpoint.postgres` → `langgraph.checkpoint.postgres.aio`
3. 改语法：`with` → `async with`
4. 删除：`.setup()` 调用（不需要）
5. 确保函数是 `async def`

## 参考资源

- LangGraph Checkpointer 文档: https://langchain-ai.github.io/langgraph/reference/checkpoints/
- Python 异步上下文管理器: https://docs.python.org/3/reference/datamodel.html#async-context-managers
- PostgreSQL 异步连接: https://www.psycopg.org/psycopg3/docs/advanced/async.html

## 总结

**核心规则**：

1. ✅ 使用 `AsyncPostgresSaver` （不是 `PostgresSaver`）
2. ✅ 使用 `async with` 管理生命周期（不要手动 `.setup()`）
3. ✅ 所有操作在 `async with` 块内完成
4. ✅ 每个测试/会话使用唯一的 `thread_id`

遵循这些规则，checkpointer 设置问题将不再出现。
