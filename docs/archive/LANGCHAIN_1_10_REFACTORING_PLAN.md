# LangChain 1.10 重构计划

> 基于 `archive/langchain` (LangChain 1.10) 和 `archive/deepagents` 源码分析，识别项目中可使用新特性简化的代码模式。

## ✅ 重构进度

| 项目 | 状态 | 说明 |
|------|------|------|
| `LLMFactory` → `init_chat_model()` | ✅ 完成 | 从 ~150 行减少到 ~100 行 |
| `deep_path.py` JSON 解析 | ✅ 完成 | 删除 ~80 行回退代码，使用 `with_structured_output()` |
| `fast_path.py` JSON 解析 | ✅ 完成 | 删除 ~80 行回退代码，使用 `with_structured_output()` |
| 测试脚本清理 | ✅ 完成 | 已删除过时的 scripts/test_*.py 文件 |
| 文档更新 | ✅ 完成 | 更新 QUICKSTART.md、修复 prompt 模板 |
| 单元测试修复 | ✅ 完成 | 631 passed, 12 skipped |
| HITL 中间件重构 | 🔲 待做 | 使用 `HumanInTheLoopMiddleware` |
| 工作流重构 | 🔲 待做 | 使用 `create_agent()` |

**测试结果 (2025-11-30)**:
- ✅ 631 tests passed
- ⏭️ 12 tests skipped (需要环境配置)
- 🔧 修复的测试文件: `test_strategies.py`, `test_memory_rag.py`, `test_syslog_tool.py`, `test_workflows.py`

---

## 🔄 Fallback/漏斗机制分析与 LangChain 1.10 替代方案

### 当前 Fallback 实现现状

OLAV 项目中存在多种 Fallback/漏斗机制：

| 位置 | 当前实现 | 问题 |
|------|---------|------|
| `fast_path.py` 意图分类 | LLM 失败 → 关键词匹配 | 手动 try/except |
| `fast_path.py` Schema 不匹配 | SuzieQ → CLI → NETCONF | 硬编码链 |
| `deep_path.py` 工具执行 | 主工具失败 → LLM Fallback | 分散的错误处理 |
| `classify_intent_async()` | LLM → keyword fallback | 无重试机制 |
| 模型调用 | 无统一重试 | 每处单独处理 |

### LangChain 1.10 提供的替代方案

#### 1. `ModelFallbackMiddleware` - 模型级 Fallback

```python
from langchain.agents.middleware import ModelFallbackMiddleware

# 替代: 手动 try/except + 降级逻辑
fallback = ModelFallbackMiddleware(
    "openai:gpt-4o-mini",      # 第一备选
    "ollama:llama3",           # 第二备选
)

agent = create_agent(
    model="openai:gpt-4o",     # 主模型
    middleware=[fallback],
)
# 如果 gpt-4o 失败 → 自动尝试 gpt-4o-mini → 再尝试 llama3
```

**适用于**: `classify_intent_async()` 和所有 LLM 调用的统一容错

#### 2. `ModelRetryMiddleware` - 模型调用重试

```python
from langchain.agents.middleware import ModelRetryMiddleware
from openai import APITimeoutError, RateLimitError

retry = ModelRetryMiddleware(
    max_retries=3,
    retry_on=(APITimeoutError, RateLimitError),  # 仅重试这些异常
    backoff_factor=2.0,        # 指数退避
    initial_delay=1.0,
    max_delay=60.0,
    jitter=True,               # 避免雷群效应
    on_failure="continue",     # 失败后继续 (返回 AIMessage 错误)
)
```

**适用于**: 所有 LLM 调用的瞬态错误处理

#### 3. `ToolRetryMiddleware` - 工具调用重试

```python
from langchain.agents.middleware import ToolRetryMiddleware

tool_retry = ToolRetryMiddleware(
    max_retries=2,
    tools=["suzieq_query", "cli_tool"],  # 仅对这些工具重试
    retry_on=(ConnectionError, TimeoutError),
    on_failure="continue",  # 失败后返回 ToolMessage 让 LLM 处理
)
```

**适用于**: SuzieQ、CLI、NETCONF 工具的网络错误重试

#### 4. `LLMToolSelectorMiddleware` - 动态工具选择

```python
from langchain.agents.middleware import LLMToolSelectorMiddleware

# 替代: 硬编码的 FALLBACK_TOOL_CHAIN
selector = LLMToolSelectorMiddleware(
    model="openai:gpt-4o-mini",  # 使用小模型做选择
    max_tools=3,                  # 最多选 3 个工具
    always_include=["suzieq_schema_search"],  # 始终包含
)
```

**适用于**: 替代 `FALLBACK_TOOL_CHAIN` 硬编码映射

#### 5. 组合中间件 - 完整 Fallback 链

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ModelFallbackMiddleware,
    ToolRetryMiddleware,
    LLMToolSelectorMiddleware,
)

agent = create_agent(
    model="openai:gpt-4o",
    tools=[suzieq_query, cli_tool, netconf_tool, syslog_search],
    middleware=[
        # 1. 模型调用重试 (瞬态错误)
        ModelRetryMiddleware(max_retries=3),
        
        # 2. 模型 Fallback (主模型彻底失败)
        ModelFallbackMiddleware("openai:gpt-4o-mini", "ollama:llama3"),
        
        # 3. 工具调用重试 (网络错误)
        ToolRetryMiddleware(
            max_retries=2,
            tools=["suzieq_query", "cli_tool"],
        ),
        
        # 4. 动态工具选择 (替代硬编码 fallback chain)
        LLMToolSelectorMiddleware(max_tools=3),
    ],
)
```

### 迁移优先级

| 优先级 | 模块 | 当前代码 | 替代方案 | 工作量 |
|--------|------|---------|---------|--------|
| 🔴 P0 | 模型重试 | 无 | `ModelRetryMiddleware` | 1h |
| 🔴 P0 | 意图分类 Fallback | 手动 try/except | `ModelFallbackMiddleware` | 2h |
| 🟠 P1 | 工具重试 | 无 | `ToolRetryMiddleware` | 2h |
| 🟠 P1 | 工具链 Fallback | `FALLBACK_TOOL_CHAIN` | `LLMToolSelectorMiddleware` | 4h |
| 🟢 P2 | Deep Path LLM Fallback | 分散错误处理 | 统一中间件 | 3h |

### 重构示例

#### Before (当前代码):

```python
# fast_path.py - 意图分类
async def classify_intent_async(query: str) -> tuple[str, float]:
    try:
        result = await classify_intent_with_llm(query)
        return (result.category, result.confidence)
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}, using keyword fallback")
        return classify_intent(query)  # 关键词匹配 fallback

# fast_path.py - Schema 不匹配时的工具链
FALLBACK_TOOL_CHAIN = {
    "suzieq": ["cli_tool", "netconf_tool"],
    "netbox": ["suzieq_query", "cli_tool"],
    "openconfig": ["cli_tool", "netconf_tool"],
}
```

#### After (使用 LangChain 1.10 中间件):

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ModelFallbackMiddleware,
    ToolRetryMiddleware,
    LLMToolSelectorMiddleware,
)

# 创建 Agent 时配置所有 Fallback 策略
agent = create_agent(
    model="openai:gpt-4o",
    tools=[
        suzieq_query,
        suzieq_schema_search,
        cli_tool,
        netconf_tool,
    ],
    system_prompt=prompt_manager.load_agent_prompt("fast_path"),
    middleware=[
        # 意图分类失败 → 自动切换模型
        ModelFallbackMiddleware("openai:gpt-4o-mini"),
        
        # Rate Limit/Timeout → 指数退避重试
        ModelRetryMiddleware(
            max_retries=3,
            retry_on=(RateLimitError, APITimeoutError),
        ),
        
        # 工具执行失败 → 重试
        ToolRetryMiddleware(
            max_retries=2,
            tools=["suzieq_query", "cli_tool"],
        ),
        
        # 动态选择最相关的工具 (替代 FALLBACK_TOOL_CHAIN)
        LLMToolSelectorMiddleware(
            model="openai:gpt-4o-mini",
            max_tools=3,
            always_include=["suzieq_schema_search"],
        ),
    ],
)

# 删除: classify_intent_async 的手动 fallback
# 删除: FALLBACK_TOOL_CHAIN 硬编码
# 删除: 各处分散的 try/except 错误处理
```

### 收益

1. **代码简化**: 删除 ~200 行手动 fallback/重试代码
2. **统一策略**: 所有容错逻辑集中在中间件配置
3. **可观测性**: 中间件自动记录重试/fallback 日志
4. **可测试性**: 中间件可独立单元测试
5. **灵活配置**: 不同 Agent/Workflow 可使用不同中间件组合

---

## 📋 TODO 实施计划

### 🔴 P0: LLM 层中间件 (llm.py)

**目标**: 为所有 LLM 调用添加统一的重试和降级机制

**任务**:
- [ ] 添加 `ModelRetryMiddleware` 配置 (Rate Limit, Timeout 自动重试)
- [ ] 添加 `ModelFallbackMiddleware` 配置 (主模型失败 → 降级模型)
- [ ] 新增 `get_resilient_chat_model()` 方法返回带中间件的模型
- [ ] 更新 `config/settings.py` 添加 fallback 模型配置

**实现位置**: `src/olav/core/llm.py`

**API 签名**:
```python
ModelRetryMiddleware(
    max_retries=3,
    retry_on=(RateLimitError, APITimeoutError),
    backoff_factor=2.0,
    initial_delay=1.0,
    max_delay=60.0,
    jitter=True,
    on_failure="continue",  # 返回错误消息而不是抛异常
)

ModelFallbackMiddleware(
    "openai:gpt-4o-mini",  # 第一降级
    "ollama:llama3",       # 第二降级
)
```

### 🟠 P1: 工具层中间件 (fast_path.py)

**目标**: 为 SuzieQ/CLI/NETCONF 工具调用添加重试机制

**任务**:
- [ ] 集成 `ToolRetryMiddleware` 到 FastPathStrategy
- [ ] 配置网络工具的重试策略 (ConnectionError, TimeoutError)
- [ ] 保留现有 `FALLBACK_TOOL_CHAIN` 作为语义级 fallback

**实现位置**: `src/olav/strategies/fast_path.py`

**API 签名**:
```python
ToolRetryMiddleware(
    max_retries=2,
    tools=["suzieq_query", "cli_tool", "netconf_tool"],
    retry_on=(ConnectionError, TimeoutError),
    on_failure="continue",
)
```

### 🟢 P2: 高级优化

#### P2.1: LLMToolSelectorMiddleware 评估

**目标**: 评估是否用 LLM 动态工具选择替代 `FALLBACK_TOOL_CHAIN`

**评估点**:
- [ ] 性能影响 (额外 LLM 调用 vs 硬编码 fallback)
- [ ] 准确性提升 (LLM 选择 vs 关键词匹配)
- [ ] 成本分析 (小模型 gpt-4o-mini 成本)

**结论**: 暂时保留 `FALLBACK_TOOL_CHAIN`，因为:
1. 网络诊断 fallback 是领域知识 (SuzieQ→CLI)
2. 额外 LLM 调用增加延迟
3. 现有 fallback 已稳定

#### P2.2: DeepDive RAG 读取功能

**目标**: 在 DeepDive 规划阶段查询历史诊断模式

**任务**:
- [ ] 在 `topology_analysis_node` 添加 `search_episodic_memory` 调用
- [ ] 用历史成功模式指导诊断计划生成
- [ ] 添加配置开关 `enable_deep_dive_rag_read`

**实现位置**: `src/olav/workflows/deep_dive.py`

---

## ✅ 实施进度

| 优先级 | 任务 | 状态 | 备注 |
|--------|------|------|------|
| P0 | ModelRetryMiddleware | ✅ 完成 | `LLMFactory.get_retry_middleware()` |
| P0 | ModelFallbackMiddleware | ✅ 完成 | `LLMFactory.get_fallback_middleware()` |
| P1 | ToolRetryMiddleware | ✅ 完成 | `FastPathStrategy._execute_with_retry()` |
| P2.1 | LLMToolSelectorMiddleware | ❌ 暂不实施 | 保留现有 `FALLBACK_TOOL_CHAIN` |
| P2.2 | DeepDive RAG Read | ✅ 完成 | `_search_historical_diagnostics()` |

### 实施详情

#### P0: LLM 层中间件 (2025-11-30)

**文件**: `src/olav/core/llm.py`

新增方法:
- `LLMFactory.get_retry_middleware()`: 返回 `ModelRetryMiddleware` 实例
  - `max_retries=3`, `backoff_factor=2.0`, `jitter=True`
  - 重试异常: `RateLimitError`, `APITimeoutError`, `ConnectionError`, `TimeoutError`
- `LLMFactory.get_fallback_middleware()`: 返回 `ModelFallbackMiddleware` 实例
  - 自动降级到 `gpt-4o-mini` 或 `llama3.2`
- `LLMFactory.get_middleware_stack()`: 返回完整中间件栈
- `LLMFactory.reset_middleware()`: 重置缓存（测试用）

#### P1: 工具层重试 (2025-11-30)

**文件**: `src/olav/strategies/fast_path.py`

新增方法:
- `FastPathStrategy._execute_with_retry()`: 实现工具重试逻辑
  - `max_retries=3`, `backoff_factor=2.0`, `jitter=True`
  - 重试异常: `ConnectionError`, `TimeoutError`, `OSError`
  - 实现与 LangChain 1.10 `ToolRetryMiddleware` 相同的模式

#### P2.2: DeepDive RAG 读取 (2025-11-30)

**文件**: `src/olav/workflows/deep_dive.py`

新增方法:
- `DeepDiveWorkflow._search_historical_diagnostics()`: 查询历史诊断模式
  - 仅匹配 `deep_dive_workflow` 或 `deep_dive_funnel` 的历史记录
  - 相似度阈值: 0.6 (Jaccard similarity)
  - 返回: 历史问题、诊断阶段数、发现数量、受影响设备

修改方法:
- `topology_analysis_node()`: 在步骤 0 调用历史搜索
  - 历史上下文增强 LLM prompt
  - 用户消息中显示历史参考信息

### 测试结果 (2025-11-30)

```
631 passed, 12 skipped in 135.78s
```

---

## 📋 概述

LangChain 1.10 引入了多项重大改进，可大幅降低 OLAV 项目的代码复杂度：

- **`create_agent()` 工厂函数**: 一行代码创建完整 Agent，内置 tool loop
- **Middleware 系统**: 可组合的中间件（HITL、重试、摘要等）
- **`init_chat_model()`**: 统一的模型初始化接口
- **DeepAgents**: 子代理、文件系统、TODO 管理等高级功能

---

## 🔑 核心新特性

### 1. `create_agent()` 工厂函数 + 中间件系统

来源: `archive/langchain/libs/langchain_v1/langchain/agents/factory.py`

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    SummarizationMiddleware,
)

agent = create_agent(
    model="openai:gpt-4",
    tools=[suzieq_query_tool, netconf_tool],
    system_prompt="你是 OLAV 网络运维专家",
    middleware=[
        HumanInTheLoopMiddleware(interrupt_on={"cli_tool": True}),
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=2),
        SummarizationMiddleware(model=model, trigger=("tokens", 8000)),
    ],
    checkpointer=checkpointer,
)
```

**优势**:
- 自动构建 model → tools → model 循环
- 中间件可组合，无需手动编写 StateGraph
- 内置 HITL、重试、摘要等常用功能

### 2. `init_chat_model()` 统一模型初始化

来源: `archive/langchain/libs/langchain_v1/langchain/chat_models/base.py`

```python
from langchain.chat_models import init_chat_model

# 一行代码支持所有 Provider
model = init_chat_model("openai:gpt-4")
model = init_chat_model("anthropic:claude-sonnet-4-5-20250929")
model = init_chat_model("ollama:llama2")
model = init_chat_model("azure_openai:gpt-4")
```

**支持的 Provider**:
- `openai`, `anthropic`, `azure_openai`, `azure_ai`
- `google_vertexai`, `google_genai`, `bedrock`, `bedrock_converse`
- `cohere`, `fireworks`, `together`, `mistralai`
- `huggingface`, `groq`, `ollama`, `deepseek`, `xai`, `perplexity`

### 3. 内置中间件

来源: `archive/langchain/libs/langchain_v1/langchain/agents/middleware/`

| 中间件 | 功能 | 文件 |
|--------|------|------|
| `HumanInTheLoopMiddleware` | 工具执行审批 (approve/edit/reject) | `human_in_the_loop.py` |
| `ModelRetryMiddleware` | 模型调用自动重试 (指数退避) | `model_retry.py` |
| `ToolRetryMiddleware` | 工具调用自动重试 | `tool_retry.py` |
| `SummarizationMiddleware` | 长对话自动摘要 | `summarization.py` |
| `ModelFallbackMiddleware` | 模型故障切换 | `model_fallback.py` |
| `ToolCallLimitMiddleware` | 工具调用次数限制 | `tool_call_limit.py` |
| `ModelCallLimitMiddleware` | 模型调用次数限制 | `model_call_limit.py` |
| `PIIMiddleware` | PII 检测与脱敏 | `pii.py` |
| `TodoListMiddleware` | TODO 列表管理 | `todo.py` |

### 4. DeepAgents 模式

来源: `archive/deepagents/libs/deepagents/deepagents/graph.py`

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model=model,
    tools=network_tools,
    system_prompt="你是 OLAV 网络诊断专家",
    subagents=[
        {"name": "bgp_specialist", "prompt": "BGP 专家", "tools": [bgp_tool]},
        {"name": "ospf_specialist", "prompt": "OSPF 专家", "tools": [ospf_tool]},
    ],
    backend=StateBackend,  # 或 RedisBackend
    interrupt_on={"cli_tool": True, "netconf_tool": True},
)
```

**功能**:
- SubAgent 委托 (复杂任务分解)
- FilesystemMiddleware (文件读写)
- TodoListMiddleware (任务跟踪)
- SummarizationMiddleware (上下文压缩)

---

## 📊 重构项目清单

### 1. `src/olav/core/llm.py` → 使用 `init_chat_model()`

**当前代码** (~150 行):
```python
class LLMFactory:
    @staticmethod
    def get_chat_model(json_mode: bool = False, ...):
        if env_settings.llm_provider == "openai":
            return FixedChatOpenAI(...)
        elif env_settings.llm_provider == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(...)
        elif env_settings.llm_provider == "azure":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(...)
        # ... 更多分支
```

**重构后** (~30 行):
```python
from langchain.chat_models import init_chat_model

class LLMFactory:
    @staticmethod
    def get_chat_model(json_mode: bool = False, **kwargs):
        model_string = f"{env_settings.llm_provider}:{env_settings.llm_model_name}"
        model_kwargs = {}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}
        
        return init_chat_model(
            model_string,
            temperature=LLMConfig.TEMPERATURE,
            max_tokens=LLMConfig.MAX_TOKENS,
            api_key=env_settings.llm_api_key,
            base_url=LLMConfig.BASE_URL,
            **model_kwargs,
            **kwargs,
        )
```

**收益**: 删除 ~120 行 Provider 分支代码，统一初始化接口

---

### 2. HITL 实现 → 使用 `HumanInTheLoopMiddleware`

**当前代码** (分散在多个 workflow 文件):
```python
# src/olav/workflows/device_execution.py
from langgraph.types import interrupt

async def plan_approval_node(state):
    approval = interrupt({"plan": state["execution_plan"]})
    if approval == "reject":
        return {"aborted": True}
    # ... 手动处理 approve/edit/reject
```

**重构后**:
```python
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig

hitl_middleware = HumanInTheLoopMiddleware(
    interrupt_on={
        "cli_tool": InterruptOnConfig(
            allowed_decisions=["approve", "edit", "reject"],
            description="CLI 命令执行需要审批",
        ),
        "netconf_tool": InterruptOnConfig(
            allowed_decisions=["approve", "reject"],
            description="NETCONF 配置变更需要审批",
        ),
    }
)

agent = create_agent(
    model=model,
    tools=[cli_tool, netconf_tool],
    middleware=[hitl_middleware],
)
```

**收益**:
- 删除 ~200 行手动 interrupt 处理代码
- 统一 HITL 交互格式 (`HITLRequest` / `HITLResponse`)
- 自动处理 AI/Tool message 对

---

### 3. `src/olav/strategies/deep_path.py` JSON 解析 → 移除回退逻辑

**当前代码** (~80 行):
```python
def _parse_json_response(self, content: str, model_class: type[BaseModel]) -> BaseModel | None:
    raw_content = content.strip()
    
    # Strategy 1: Clean markdown code blocks
    if "```" in raw_content:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_content, re.DOTALL)
        if match:
            raw_content = match.group(1).strip()
    
    # Strategy 2: Find JSON object boundaries
    # Strategy 3: Try direct Pydantic parsing
    # Strategy 4: Fix common JSON issues
    # Strategy 5: Regex extraction
    # ... 约 50 行回退逻辑
```

**重构后** (~10 行):
```python
# with_structured_output 内部已处理所有回退逻辑
async def _collect_initial_observations(self, state, context):
    structured_llm = self.llm.with_structured_output(ToolCallPlanList)
    result = await structured_llm.ainvoke([SystemMessage(content=prompt)])
    # 直接使用 result，无需手动解析
```

**收益**: 删除 ~70 行 JSON 解析回退代码

---

### 4. Workflow 图构建 → 使用 `create_agent()`

**当前代码** (每个 workflow ~100 行):
```python
# src/olav/workflows/query_diagnostic.py
class QueryDiagnosticWorkflow(BaseWorkflow):
    def build_graph(self, checkpointer):
        graph = StateGraph(QueryState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", ToolNode(self.tools))
        graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "end": END}
        )
        graph.add_edge("tools", "agent")
        graph.set_entry_point("agent")
        return graph.compile(checkpointer=checkpointer)
```

**重构后** (~30 行):
```python
from langchain.agents import create_agent

class QueryDiagnosticWorkflow(BaseWorkflow):
    def build_graph(self, checkpointer):
        return create_agent(
            model=LLMFactory.get_chat_model(),
            tools=[
                ToolRegistry.get_tool("suzieq_query"),
                ToolRegistry.get_tool("suzieq_schema_search"),
            ],
            system_prompt=prompt_manager.load_agent_prompt("query_diagnostic"),
            middleware=[
                ToolRetryMiddleware(max_retries=2),
            ],
            checkpointer=checkpointer,
        )
```

**收益**: 每个 workflow 删除 ~70 行图构建代码

---

### 5. 添加重试中间件 (新增功能)

**当前状态**: 无统一重试机制

**添加**:
```python
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware

# 模型调用重试 (处理 Rate Limit、Timeout 等)
model_retry = ModelRetryMiddleware(
    max_retries=3,
    retry_on=(RateLimitError, APITimeoutError),
    backoff_factor=2.0,
    initial_delay=1.0,
    max_delay=60.0,
    jitter=True,
)

# 工具调用重试 (处理网络错误、设备超时等)
tool_retry = ToolRetryMiddleware(
    max_retries=2,
    tools=["suzieq_query", "netbox_api_call", "cli_tool"],
    retry_on=(ConnectionError, TimeoutError),
)
```

**收益**: 提高系统健壮性，自动处理瞬态错误

---

### 6. 添加摘要中间件 (新增功能)

**当前状态**: 无长对话摘要机制

**添加**:
```python
from langchain.agents.middleware import SummarizationMiddleware

summarization = SummarizationMiddleware(
    model=LLMFactory.get_chat_model(),
    trigger=("tokens", 8000),  # Token 超过 8000 时触发摘要
    keep=("messages", 20),     # 保留最近 20 条消息
    trim_tokens_to_summarize=4000,  # 摘要输入限制
)
```

**收益**: 支持超长对话，避免 context window 溢出

---

## 📈 优先级与工作量评估

| 优先级 | 模块 | 当前行数 | 预估改进后 | 删除代码量 | 工作量 | 风险 |
|--------|------|---------|-----------|-----------|--------|------|
| 🔴 P0 | `LLMFactory` | ~150 行 | ~30 行 | -120 行 | 2h | 低 |
| 🔴 P0 | HITL 实现 | ~200 行 | ~30 行 | -170 行 | 4h | 中 |
| 🟠 P1 | `deep_path.py` JSON 解析 | ~80 行 | ~10 行 | -70 行 | 2h | 低 |
| 🟠 P1 | Workflow 图构建 (5个) | 5×100 行 | 5×30 行 | -350 行 | 8h | 中 |
| 🟢 P2 | 添加重试中间件 | 0 | +40 行 | N/A | 2h | 低 |
| 🟢 P2 | 添加摘要中间件 | 0 | +20 行 | N/A | 1h | 低 |

**总计**: 删除 ~710 行代码，新增 ~160 行，净减少 ~550 行

---

## 🚀 实施步骤

### Phase 1: 基础设施 (1 天)

1. **升级依赖**
   ```bash
   uv add langchain@latest langgraph@latest
   uv add langchain-anthropic langchain-ollama  # 如需要
   ```

2. **重构 `LLMFactory`**
   - 替换为 `init_chat_model()`
   - 保留 `FixedChatOpenAI` 作为 OpenRouter 兼容层（如需要）

3. **运行测试验证**
   ```bash
   uv run pytest tests/unit/test_llm.py -v
   ```

### Phase 2: 中间件集成 (2 天)

4. **创建中间件配置**
   ```python
   # src/olav/core/middleware.py
   from langchain.agents.middleware import (
       HumanInTheLoopMiddleware,
       ModelRetryMiddleware,
       ToolRetryMiddleware,
       SummarizationMiddleware,
   )
   
   def get_default_middleware(hitl_tools: dict = None):
       middleware = [
           ModelRetryMiddleware(max_retries=3),
           ToolRetryMiddleware(max_retries=2),
       ]
       if hitl_tools:
           middleware.append(HumanInTheLoopMiddleware(interrupt_on=hitl_tools))
       return middleware
   ```

5. **重构 HITL 实现**
   - 移除手动 `interrupt()` 调用
   - 使用 `HumanInTheLoopMiddleware`

### Phase 3: Workflow 重构 (3 天)

6. **重构 `QueryDiagnosticWorkflow`** (试点)
   - 使用 `create_agent()` 替换 `StateGraph`
   - 验证功能一致性

7. **批量重构其他 Workflow**
   - `DeviceExecutionWorkflow`
   - `NetBoxManagementWorkflow`
   - `DeepDiveWorkflow`
   - `InspectionWorkflow`

### Phase 4: 清理优化 (1 天)

8. **移除 `deep_path.py` JSON 解析回退**

9. **添加摘要中间件**

10. **更新文档和测试**

---

## ⚠️ 迁移注意事项

### 兼容性

1. **依赖版本**: 需要 LangChain >= 1.10
2. **State Schema**: `create_agent()` 使用 `AgentState`，与现有 `BaseWorkflowState` 可能不兼容
3. **Checkpointer**: 确保 PostgresSaver 版本兼容

### 风险缓解

1. **渐进式迁移**: 先从 `LLMFactory` 开始，逐步替换
2. **功能开关**: 添加环境变量控制新旧实现切换
   ```python
   USE_NEW_AGENT_FACTORY = os.getenv("OLAV_USE_NEW_AGENT", "false").lower() == "true"
   ```
3. **回归测试**: 每个 Phase 完成后运行完整测试套件

### 保留项

以下现有实现建议保留：

1. **`ToolRegistry`**: Schema-Aware 工具注册模式仍然有效
2. **`PromptManager`**: 提示词管理与新特性正交
3. **`DynamicIntentRouter`**: 意图路由逻辑独立于 Agent 实现

---

## 📚 参考资料

- LangChain 1.10 源码: `archive/langchain/libs/langchain_v1/`
- DeepAgents 源码: `archive/deepagents/libs/deepagents/`
- LangChain Agents 文档: https://docs.langchain.com/oss/python/langchain/agents
- LangChain Middleware 文档: https://docs.langchain.com/oss/python/langchain/middleware

---

## 📝 更新日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-11-30 | 1.0 | 初始版本，基于 LangChain 1.10 和 DeepAgents 分析 |
