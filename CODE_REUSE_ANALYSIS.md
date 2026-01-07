# OLAV v0.8 代码复用分析

> **版本**: 1.0  
> **日期**: 2025-01-XX  
> **目的**: 指导开发者在 v0.8 重构中识别可复用代码，避免"垃圾代码"

---

## 概述

本文档分析 `src/olav/` 下现有代码与 DESIGN_V0.8.md 新架构的匹配度，帮助开发者：

1. **识别高价值代码** - 直接复用或少量修改
2. **避免垃圾代码** - 旧架构遗留、已废弃、复杂度高的代码
3. **明确迁移路径** - 每个模块的处理方式

---

## 评估标准

| 等级 | 含义 | 处理方式 |
|------|------|---------|
| ✅ **直接复用** | 代码质量高，与新架构兼容 | 复制到新目录 |
| ⚠️ **需要重构** | 核心逻辑有价值，需适配新架构 | 提取核心逻辑 |
| 🔄 **参考设计** | 设计模式可参考，但需重写 | 仅参考思路 |
| ❌ **不复用** | 旧架构遗留或质量差 | 不迁移 |

---

## 模块分析总表

| 目录 | 复用价值 | 主要原因 |
|------|---------|---------|
| `core/llm.py` | ✅ 直接复用 | 干净的 LLM 工厂模式 |
| `core/prompt_manager.py` | ✅ 直接复用 | 两层 prompt 解析 |
| `core/settings.py` → `config/settings.py` | ✅ 直接复用 | Pydantic Settings |
| `core/memory.py` | ⚠️ 需要重构 | OpenSearch → DuckDB |
| `core/inventory_manager.py` | 🔄 参考设计 | NetBox 集成思路 |
| `agents/network_relevance_guard.py` | ✅ 直接复用 | 对应新架构 Guard 设计 |
| `agents/dynamic_orchestrator.py` | ❌ 不复用 | 被 DeepAgents 替代 |
| `agents/root_agent_orchestrator.py` | ❌ 不复用 | 被 DeepAgents 替代 |
| `tools/base.py` | ⚠️ 需要重构 | ToolOutput 有价值 |
| `tools/adapters.py` | ⚠️ 需要重构 | Adapter 模式有价值 |
| `tools/nornir_tool.py` | ⚠️ 需要重构 | NETCONF/CLI 核心逻辑 |
| `tools/netbox_tool.py` | ⚠️ 需要重构 | REST API 封装 |
| `tools/suzieq_*.py` | ❌ 不复用 | SuzieQ 已从架构移除 |
| `execution/backends/protocol.py` | 🔄 参考设计 | DeepAgents 有自己的 Protocol |
| `execution/backends/nornir_sandbox.py` | ⚠️ 需要重构 | HITL + 黑名单核心价值 |
| `workflows/*.py` | ❌ 不复用 | LangGraph 被 DeepAgents 替代 |
| `etl/*.py` | ⚠️ 需要重构 | ETL 思路可参考 |

---

## 详细分析

### 1. 核心层 (`src/olav/core/`)

#### ✅ `llm.py` - 直接复用

**价值**: 干净的 LLM 工厂模式，支持 OpenAI/Ollama/Azure，含中间件。

**质量评估**:
- ✅ 使用 `init_chat_model()` 标准方式
- ✅ 支持 retry/fallback 中间件
- ✅ 类型注解完整
- ✅ 与 LLM 提供商解耦

**迁移方式**: 直接复制到 `src/olav_v08/core/llm.py`

**代码亮点** (可直接复用):
```python
# 来源: src/olav/core/llm.py L108-156
class LLMFactory:
    @staticmethod
    def get_chat_model(
        json_mode: bool = False,
        temperature: float | None = None,
        reasoning: bool = False,
        **kwargs: Any,
    ) -> BaseChatModel:
        # 使用 LangChain init_chat_model - 正确做法
        return init_chat_model(model_name, model_provider=provider, **config, **kwargs)
    
    @staticmethod
    def get_embedding_model() -> OpenAIEmbeddings:
        # 支持 OpenAI/Ollama embedding
        ...
```

---

#### ✅ `prompt_manager.py` - 直接复用

**价值**: 两层 prompt 解析，缓存机制，YAML 模板加载。

**质量评估**:
- ✅ 支持 `_defaults/` + 覆盖层设计
- ✅ 模板缓存，避免重复 IO
- ✅ 变量验证机制
- ✅ 支持 `thinking` 前缀 (Ollama 兼容)

**迁移方式**: 直接复制，修改 prompt 目录为 `.olav/prompts/`

**需要调整**:
```python
# 旧: config/prompts/
# 新: .olav/prompts/ (符合 Claude Code 结构)
```

---

#### ⚠️ `memory.py` - 需要重构

**价值**: OpenSearch 封装，审计日志设计。

**问题**: 新架构用 DuckDB 替代 OpenSearch。

**可复用部分**:
- 审计日志的数据模型设计
- 搜索接口抽象 (`search_schema()` 方法签名)

**重写方向**:
```python
# 新: 使用 DuckDB
import duckdb

class CapabilityStore:
    def __init__(self, db_path: str = ".olav/capabilities.db"):
        self.conn = duckdb.connect(db_path)
    
    async def search_capabilities(self, query: str) -> list[dict]:
        # FTS5 全文搜索
        return self.conn.execute(
            "SELECT * FROM capabilities WHERE text MATCH ?", [query]
        ).fetchall()
```

---

### 2. Agent 层 (`src/olav/agents/`)

#### ✅ `network_relevance_guard.py` - 直接复用

**价值**: 这正是 DESIGN_V0.8.md Section 4.6 "Guard 意图过滤器" 的实现！

**质量评估**:
- ✅ LLM 结构化输出 (`RelevanceResult`)
- ✅ Fail-open 策略 (默认允许)
- ✅ 单例模式 (`get_network_guard()`)
- ✅ 预定义拒绝消息

**迁移方式**: 直接复制到 `src/olav_v08/guard/relevance_guard.py`

**代码亮点** (完全对应新设计):
```python
# 来源: src/olav/agents/network_relevance_guard.py
class RelevanceResult(BaseModel):
    is_relevant: bool
    confidence: float
    reason: str
    method: str

class NetworkRelevanceGuard:
    async def check(self, query: str) -> RelevanceResult:
        # LLM 分类，失败时 fail-open
        ...
```

**与新设计对应关系**:

| 旧代码 | 新设计 (DESIGN_V0.8 §4.6) |
|-------|-------------------------|
| `NetworkRelevanceGuard` | Guard 意图过滤器 |
| `RelevanceResult.is_relevant` | 网络相关性判断 |
| Fail-open 策略 | "出错时默认允许" |

---

#### ❌ `dynamic_orchestrator.py` - 不复用

**原因**: 这是 LangGraph 的 workflow 路由器，被 DeepAgents 的 Skill 选择机制替代。

**设计参考价值**:
- 两阶段路由 (语义预过滤 + LLM 分类) 思路可参考
- 但实现需要完全重写为 DeepAgents 的 `skill_selector` 中间件

---

#### ❌ `root_agent_orchestrator.py` - 不复用

**原因**: 
1. 1248 行代码，过于庞大
2. 深度耦合 LangGraph StateGraph
3. 被 `create_deep_agent()` 替代

---

### 3. 工具层 (`src/olav/tools/`)

#### ⚠️ `base.py` - 需要重构

**价值**: `ToolOutput` 模型是核心抽象，消除 LLM 幻觉问题。

**可复用部分**:
```python
# 来源: src/olav/tools/base.py L66-96
class ToolOutput(BaseModel):
    source: str      # 工具标识
    device: str      # 设备名
    timestamp: datetime
    data: list[dict[str, Any]]  # 关键：永远是 list[dict]
    metadata: dict[str, Any]
    error: str | None
```

**不复用部分**:
- `ToolRegistry` - 被 DeepAgents 的 tool 注册替代
- `HITLChecker` - 被 DeepAgents 的 `interrupt_on` 替代

---

#### ⚠️ `adapters.py` - 需要重构

**价值**: Adapter 模式优雅，将各种格式统一为 `ToolOutput`。

**可复用部分**:
```python
class CLIAdapter:
    @staticmethod
    def adapt(cli_output: Any, device: str, command: str, ...) -> ToolOutput:
        # TextFSM 解析结果 → ToolOutput

class NetconfAdapter:
    @staticmethod  
    def adapt(xml_response: str, device: str, xpath: str, ...) -> ToolOutput:
        # XML → ToolOutput
```

**需要移除**:
- `SuzieqAdapter` - SuzieQ 已从架构移除

---

#### ⚠️ `nornir_tool.py` - 需要重构

**价值**: NETCONF/CLI 执行核心逻辑。

**可复用部分** (约 300 行):
```python
# NETCONF 执行逻辑
class NetconfTool:
    async def execute_netconf(
        self,
        device: str,
        operation: Literal["get", "get-config", "edit-config"],
        xpath: str | None = None,
        config: str | None = None,
    ) -> ToolOutput:
        ...

# CLI 执行逻辑  
class CLITool:
    async def execute_cli(
        self,
        device: str,
        command: str,
        parse: bool = True,
    ) -> ToolOutput:
        ...
```

**需要移除** (约 600 行):
- LangChain `@tool` 装饰器包装
- 旧的 HITL 检查逻辑
- 与 `ToolRegistry` 的集成代码

**重构方向**:
```python
# 新架构: 作为 DeepAgents tool 注册
from deepagents import create_deep_agent

netconf_tool = create_netconf_tool()  # 返回 Callable
cli_tool = create_cli_tool()          # 返回 Callable

agent = create_deep_agent(
    model=llm,
    tools=[netconf_tool, cli_tool],
    interrupt_on=["edit-config", "configure"],  # DeepAgents HITL
)
```

---

#### ❌ `suzieq_*.py` - 不复用

**原因**: SuzieQ 已从 v0.8 架构移除，其功能被 Nornir + DuckDB 替代。

涉及文件:
- `suzieq_tool.py`
- `suzieq_schema_tool.py`

---

### 4. 执行层 (`src/olav/execution/backends/`)

#### 🔄 `protocol.py` - 参考设计

**价值**: Protocol 抽象设计思路。

**问题**: DeepAgents 有自己的 `BackendProtocol`。

**可参考**:
```python
# 来源: src/olav/execution/backends/protocol.py
class BackendProtocol(Protocol):
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...

@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: str | None
    exit_code: int
```

**DeepAgents 对应**:
```python
# archive/deepagents/libs/deepagents/deepagents/backends/protocol.py
class BackendProtocol(Protocol):
    async def read_file(self, path: str) -> str: ...
    async def write_file(self, path: str, content: str) -> None: ...
    async def run_command(self, command: str) -> BackendResult: ...
```

---

#### ⚠️ `nornir_sandbox.py` - 需要重构

**核心价值**: 这是项目最关键的代码之一！包含：

1. **命令黑名单机制** (安全)
2. **权限级别检测** (安全)
3. **NetBox 动态 Inventory** (核心)
4. **Nornir 初始化逻辑** (基础设施)

**可复用部分** (约 400 行):
```python
# 黑名单加载 (安全关键)
def _load_blacklist(self) -> set[str]:
    # 从 config/command_blacklist.txt 加载
    ...

def _is_blacklisted(self, command: str) -> str | None:
    # 检查命令是否被禁止
    ...

# NetBox Inventory (核心)
def _init_nornir(self) -> Nornir:
    """从 NetBox 动态加载设备清单"""
    from nornir_netbox.plugins.inventory import NBInventory
    ...

# 权限检测 (安全)
def _get_privilege_level(self, device: str) -> int | None:
    """检测当前权限级别"""
    ...
```

**需要移除** (约 300 行):
- 旧的 HITL 中断逻辑 (被 DeepAgents `interrupt_on` 替代)
- OpenSearch 审计日志 (改用 DuckDB)

**重构方向**:
```python
# 新架构: 作为 DeepAgents backend
from deepagents import BackendProtocol

class NornirBackend(BackendProtocol):
    def __init__(self):
        self.nr = self._init_nornir()
        self.blacklist = self._load_blacklist()
    
    async def run_command(self, command: str) -> BackendResult:
        if self._is_blacklisted(command):
            return BackendResult(success=False, error="Command blacklisted")
        ...
```

---

### 5. 工作流层 (`src/olav/workflows/`)

#### ❌ 全部不复用

**原因**: LangGraph StateGraph 被 DeepAgents 替代。

涉及文件:
- `base.py` - LangGraph 基类
- `query_diagnostic.py`
- `device_execution.py`
- `netbox_management.py`
- `deep_dive.py`
- `inspection.py`
- `registry.py`

**设计参考价值**:
- `WorkflowRegistry` 的装饰器注册模式可参考
- 工作流分类思路可映射为 Skills

**新架构对应**:

| 旧 Workflow | 新 Skill |
|-------------|---------|
| `query_diagnostic.py` | `.olav/skills/diagnosis/interface-troubleshooting.md` |
| `device_execution.py` | `.olav/skills/execution/config-change.md` |
| `deep_dive.py` | `.olav/skills/analysis/deep-dive.md` |

---

### 6. ETL 层 (`src/olav/etl/`)

#### ⚠️ 需要重构

**问题**: 现有 ETL 面向 OpenSearch，需改为 DuckDB。

**可参考的设计模式**:
```python
# Schema ETL 思路可复用
# 来源: src/olav/etl/suzieq_schema_etl.py
class SchemaETL:
    def extract(self) -> list[dict]: ...
    def transform(self, raw: list[dict]) -> list[Document]: ...
    def load(self, docs: list[Document]) -> None: ...
```

**重写方向**:
```python
# 新: 面向 DuckDB
class CapabilityETL:
    def __init__(self, db_path: str = ".olav/capabilities.db"):
        self.conn = duckdb.connect(db_path)
    
    def load_cli_commands(self, txt_path: str):
        """从 .olav/imports/commands/*.txt 加载"""
        ...
    
    def load_openapi_specs(self, yaml_path: str):
        """从 .olav/imports/apis/*.yaml 加载"""
        ...
```

---

### 7. 配置层 (`config/`)

#### ✅ `settings.py` - 直接复用

**价值**: 干净的 Pydantic Settings，支持 `.env` 加载。

**迁移方式**: 直接复制，添加新配置项。

**需要添加**:
```python
# 新增配置 (对应 DESIGN_V0.8 §11.6)
class EnvSettings(BaseSettings):
    # 旧配置保留
    ...
    
    # 新增 v0.8 配置
    olav_dir: str = ".olav"  # OLAV 核心目录
    duckdb_path: str = ".olav/capabilities.db"
```

---

## 复用优先级排序

### 高优先级 (Sprint 1)

| 文件 | 复用类型 | 工作量 |
|------|---------|--------|
| `core/llm.py` | ✅ 直接复制 | 0.5h |
| `config/settings.py` | ✅ 直接复制 | 0.5h |
| `core/prompt_manager.py` | ✅ 直接复制 + 路径修改 | 1h |
| `agents/network_relevance_guard.py` | ✅ 直接复制 | 0.5h |

### 中优先级 (Sprint 2)

| 文件 | 复用类型 | 工作量 |
|------|---------|--------|
| `tools/base.py` (ToolOutput) | ⚠️ 提取模型 | 2h |
| `tools/adapters.py` | ⚠️ 移除 SuzieQ | 2h |
| `execution/backends/nornir_sandbox.py` | ⚠️ 重构为 Backend | 4h |

### 低优先级 (Sprint 3)

| 文件 | 复用类型 | 工作量 |
|------|---------|--------|
| `tools/nornir_tool.py` | ⚠️ 重构为 tool | 4h |
| `tools/netbox_tool.py` | ⚠️ 重构为 tool | 3h |
| `etl/*.py` | ⚠️ 改为 DuckDB | 6h |

---

## 明确不复用清单

以下代码**不应该**迁移到新架构：

| 文件/目录 | 原因 |
|----------|------|
| `agents/root_agent_orchestrator.py` | 1248 行，LangGraph 耦合 |
| `agents/dynamic_orchestrator.py` | 被 Skill 选择替代 |
| `workflows/*.py` (全部) | LangGraph 被 DeepAgents 替代 |
| `tools/suzieq_*.py` | SuzieQ 已移除 |
| `core/memory.py` | OpenSearch 改为 DuckDB |
| `cli/*.py` | CLI 层将基于 Typer 重写 |
| `admin/*.py` | 管理功能重新设计 |

---

## 迁移检查清单

在复用代码前，确保：

- [ ] 移除所有 `from olav.workflows.*` 导入
- [ ] 移除所有 `from langgraph.*` 导入
- [ ] 移除所有 SuzieQ 相关代码
- [ ] 移除 `ToolRegistry` 使用 (改用 DeepAgents tools)
- [ ] 更新 prompt 路径为 `.olav/prompts/`
- [ ] 更新配置导入为 `from config.settings import settings`
- [ ] 添加类型注解 (mypy strict 兼容)
- [ ] 确保 async/await 一致性

---

## 总结

**复用比例估算**:

| 类别 | 行数 | 可复用 | 复用率 |
|------|------|--------|--------|
| core/ | ~1200 | ~800 | 67% |
| agents/ | ~1600 | ~200 | 12% |
| tools/ | ~2500 | ~800 | 32% |
| execution/ | ~900 | ~400 | 44% |
| workflows/ | ~2000 | 0 | 0% |
| **总计** | ~8200 | ~2200 | **27%** |

**关键结论**:

1. **核心层质量高** - `llm.py`, `prompt_manager.py`, `settings.py` 可直接复用
2. **Guard 设计正确** - `network_relevance_guard.py` 正是新设计需要的
3. **工具层需重构** - 核心逻辑有价值，但需适配 DeepAgents
4. **工作流层全部废弃** - LangGraph 被 DeepAgents 完全替代
5. **避免复制粘贴** - 理解代码意图，按新架构重组
