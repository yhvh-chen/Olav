# OLAV (Omni-Layer Autonomous Verifier)

**Project Code:** OLAV  
**Version:** 2.0  
**Status:** Active Development

## 1. 项目概述 (Project Overview)

OLAV 是一个企业级网络运维 ChatOps 平台，旨在通过智能体协作解决复杂的网络排错与运维任务。它不仅仅是一个执行命令的机器人，而是一个具备架构感知 (Schema-Aware)、自我学习 (Self-Learning) 和多层级排错能力的智能体系统。

### 核心设计哲学

*   **漏斗式排错 (The Funnel)**: 从 SuzieQ 的宏观历史数据入手，收敛故障范围，再利用 NETCONF/OpenConfig 进行微观实时诊断。
*   **知识分层 (Tiered Knowledge)**: 将知识分为 **Schema (真理)**、**Memory (经验)** 和 **Docs (文档)** 三层，通过 RAG 2.0 架构进行检索。
*   **安全第一 (Safety First)**: 实施 **Human-in-the-Loop (HITL)** 机制，所有副作用操作（Write/Config）必须经过人工批准；采用沙盒隔离执行逻辑。
*   **高内聚低耦合**: 组件通过标准化接口交互，支持 LLM 模型（OpenAI/Ollama）和网络设备（Cisco/Huawei/Arista）的无缝切换。

---

## 2. 系统架构 (System Architecture)

OLAV 采用微服务化的容器架构，基于 LangGraph 进行智能体编排。

### 架构概览

```mermaid
graph TD
    subgraph "User Interface"
        CLI[Rich CLI / Terminal] <-->|Stream/Input| App_Container
    end

    subgraph "OLAV Application (Main Brain)"
        App_Container[olav-app]
        LLM_Factory[LLM Factory] -->|Invoke| App_Container
        Supervisor[Supervisor Agent] -->|Route| Workers
        
        subgraph "Workers (Agents)"
            SuzieQ_Agent[Macro Agent]
            Netconf_Agent[Micro Agent]
            NetBox_Agent[SSOT Agent]
            Doc_Agent[Doc Agent]
            Learner_Agent[Reflection Node]
        end
    end

    subgraph "Infrastructure Services"
        Redis[(Redis)] <-->|State Persistence| App_Container
        OpenSearch[(OpenSearch)] <-->|Vector Search| App_Container
        SuzieQ_Service[SuzieQ Poller] -->|Parquet| Shared_Vol[Shared Volume]
    end

    subgraph "Support Containers"
        Init_Container[olav-init] -->|ETL Schema| OpenSearch
        Embedder_Service[olav-embedder] -->|Ingest PDF/Docs| OpenSearch
        Embedder_Service <-->|API Trigger| App_Container
    end

    subgraph "External World"
        NetBox[(NetBox Source of Truth)]
        Network_Devices[Switches/Routers]
        LLM_Provider[OpenAI/Ollama/Azure]
    end

    App_Container -->|Inventory| NetBox
    App_Container -->|Nornir Execution| Network_Devices
    NetBox_Agent -->|Manage| NetBox
```

---

## 3. 目录架构 (Directory Structure)

项目基于 `src` 布局，严格分离核心业务、工具、执行层和辅助服务。

```text
olav/
├── .env.example                # 环境变量模板
├── .gitignore
├── docker-compose.yml          # 编排所有容器
├── Dockerfile                  # 主程序 olav-app 镜像
├── Dockerfile.embedder         # 向量化服务 olav-embedder 镜像
├── Makefile                    # 开发命令 (test, lint, up, ingest)
├── pyproject.toml              # 依赖管理 (Ruff, Pytest)
├── config/                     # 全局配置
│   ├── prompts/                # LangChain 提示词模板 (YAML)
│   │   ├── agents/             # Agent 系统提示词
│   │   └── tools/              # Tool 描述模板
│   ├── inventory_template.csv  # CSV 设备导入模板
│   └── app_settings.template.yaml # 应用配置模板示例
├── data/                       # 挂载数据目录
│   ├── documents/              # 待上传的 PDF/MD
│   ├── suzieq-parquet/         # SuzieQ 数据
│   └── generated_configs/      # 动态生成的配置文件 (suzieq_config.yml)
├── src/
│   ├── olav/                   # [主程序] OLAV Agent
│   │   ├── __init__.py
│   │   ├── main.py             # CLI 入口 (Typer + Rich)
│   │   ├── core/               # 核心框架
│   │   │   ├── __init__.py
│   │   │   ├── settings.py     # ✅ Pydantic Settings (Env Loading)
│   │   │   ├── state.py        # ✅ TypedDict 状态定义
│   │   │   ├── llm.py          # ✅ LLM Factory (多厂商支持)
│   │   │   ├── memory.py       # ✅ OpenSearch 读写封装
│   │   │   ├── prompt_manager.py # ✅ 提示词模板管理器
│   │   │   └── inventory_manager.py # ✅ NetBox CSV 导入管理器
│   │   ├── agents/             # 智能体 (业务逻辑)
│   │   │   ├── __init__.py
│   │   │   ├── root_agent.py   # ✅ Supervisor / 路由逻辑 (create_deep_agent)
│   │   │   ├── suzieq_agent.py # ✅ 宏观分析 (SubAgent Factory)
│   │   │   ├── netconf_agent.py# ✅ 微观诊断 (SubAgent Factory + HITL)
│   │   │   ├── rag_agent.py    # ✅ 知识检索代理 (SubAgent Factory)
│   │   │   ├── learner_agent.py# ✅ 自我学习/反思节点 (SubAgent Factory)
│   │   │   └── middleware/     # 自定义中间件
│   │   │       ├── __init__.py
│   │   │       └── network_context.py # ✅ 注入网络上下文
│   │   ├── tools/              # 工具层 (Interface Layer)
│   │   │   ├── __init__.py
│   │   │   ├── opensearch_tool.py # ✅ OpenSearch 统一检索接口
│   │   │   ├── suzieq_tool.py  # ✅ SuzieQ Query Interface (Schema-Aware)
│   │   │   ├── nornir_tool.py  # ✅ Nornir Execution Interface
│   │   │   ├── netbox_tool.py  # ✅ NetBox API 工具 (Schema-Aware)
│   │   │   └── datetime_tool.py# ✅ 时间解析工具 (自然语言 -> 时间戳)
│   │   ├── execution/          # 执行层 (Backend + Sandbox)
│   │   │   ├── __init__.py
│   │   │   └── backends/       # Backend 实现
│   │   │       ├── __init__.py
│   │   │       ├── protocol.py  # ✅ Backend 协议定义
│   │   │       ├── nornir_sandbox.py # ✅ Nornir 沙盒 (HITL + 动态配置)
│   │   │       ├── state.py     # ⏳ StateBackend (开发环境)
│   │   │       └── redis.py     # ⏳ RedisBackend (生产环境)
│   │   └── etl/                # 数据处理 (Schema + Config Generation)
│   │       ├── __init__.py
│   │       ├── init_postgres.py # ✅ PostgreSQL Checkpointer 初始化
│   │       ├── init_schema.py  # ✅ OpenConfig YANG Schema 索引
│   │       ├── suzieq_schema_etl.py # ✅ SuzieQ Avro Schema 索引
│   │       ├── netbox_schema_etl.py # ✅ NetBox OpenAPI Schema 索引
│   │       └── generate_configs.py # ✅ 动态生成 SuzieQ 配置
│   └── embedder/               # ⏳ [微服务] 文档向量化服务 (待实现)
│       ├── __init__.py
│       ├── main.py             # FastAPI 入口
│       ├── loader.py           # PDF/Text Loaders
│       └── vectorizer.py       # 切片与 Embedding 逻辑
└── tests/                      # 测试套件
    ├── __init__.py
    ├── conftest.py             # Pytest Fixtures
    ├── unit/
    │   ├── test_agents.py
    │   ├── test_sandbox.py
    │   └── test_llm_factory.py
    └── e2e/
        └── test_workflow.py
```

---

## 4. 核心组件详解

### 4.1 LLM Core (`src/olav/core/llm.py`)
**职责**: 统一的 LLM 工厂，屏蔽 OpenAI, Azure, Ollama 的差异。
*   `get_chat_model(json_mode=True)`: 获取主模型，支持 JSON Mode。
*   `get_vision_model()`: 获取视觉模型（用于未来拓扑图分析）。
*   `get_embedding_model()`: 获取向量模型（用于 RAG）。
*   **配置驱动**: 完全由 `.env` 中的 `LLM_PROVIDER` 控制。

**代码示例**:
```python
from config.settings import settings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.chat_models import ChatOllama

class LLMFactory:
    @staticmethod
    def get_chat_model(json_mode: bool = False):
        if settings.LLM_PROVIDER == "openai":
            return ChatOpenAI(
                model=settings.LLM_MODEL_NAME,
                api_key=settings.LLM_API_KEY,
                model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {}
            )
        elif settings.LLM_PROVIDER == "ollama":
            return ChatOllama(
                model=settings.LLM_MODEL_NAME,
                base_url=settings.LLM_BASE_URL,
                format="json" if json_mode else None
            )
    
    @staticmethod
    def get_embedding_model():
        if settings.LLM_PROVIDER == "openai":
            return OpenAIEmbeddings(api_key=settings.LLM_API_KEY)
        # ... ollama embeddings
```

### 4.2 RAG Agent (`src/olav/agents/rag_agent.py`)
**职责**: 知识检索的统一入口，实现智能检索策略。

**检索策略 (Tiered Retrieval)**:
1. **Memory First**: 优先查询 `olav-episodic-memory` 索引
   - 如果用户意图与历史成功案例相似度 > 0.85，直接返回经验路径
   - 优势：快速响应，避免重复推理
2. **Schema Fallback**: Memory 未命中时查询 `openconfig-schema` 索引
   - 基于用户意图提取关键词（如 "BGP neighbor"）
   - 返回精确的 YANG XPath 和数据类型
3. **Docs Support**: 需要协议原理或厂商特定信息时查询 `olav-docs` 索引
   - 返回相关文档片段供 LLM 理解上下文

**接口设计**:
```python
class RAGAgent:
    def search_knowledge(
        self,
        query: str,
        knowledge_type: Literal["memory", "schema", "docs", "auto"] = "auto",
        top_k: int = 3
    ) -> List[Dict]:
        """统一知识检索接口"""
        pass
```

### 4.3 知识库三层索引 (Knowledge Base)
系统维护三个 OpenSearch 索引，对应三层知识:
1.  **Schema Index (`openconfig-schema`)**:
    *   来源: `olav-init` 容器启动时从 GitHub 拉取 OpenConfig YANG 并解析。
    *   用途: 让 Agent 查找准确的 XPath，避免幻觉。
2.  **Docs Index (`olav-docs`)**:
    *   来源: `olav-embedder` 服务异步扫描 `data/documents/` 目录下的 PDF/MD。
    *   用途: 查询厂商手册、设计规范、协议原理。
3.  **Memory Index (`olav-episodic-memory`)**:
    *   来源: 运行时由 `learner_agent.py` 写入。
    *   用途: 存储成功的排错路径（User Intent -> Successful XPath）。实现“越用越快”。

### 4.4 Backend 架构 (基于 DeepAgents Backend Protocol)
受 DeepAgents 启发，OLAV 实现三层 Backend 协议栈：

**Backend 协议**:
```python
# src/olav/execution/backends/protocol.py
from typing import Protocol

class BackendProtocol(Protocol):
    """Backend 基础协议"""
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def ls(self, path: str) -> List[str]: ...

class SandboxBackendProtocol(BackendProtocol, Protocol):
    """支持命令执行的 Sandbox Backend"""
    async def execute(
        self,
        command: str,
        background: bool = False
    ) -> ExecutionResult: ...

class StoreBackendProtocol(BackendProtocol, Protocol):
    """支持持久化存储的 Backend（用于 Memory）"""
    async def put(self, namespace: str, key: str, value: dict) -> None: ...
    async def search(self, namespace: str, query: dict) -> List[dict]: ...
```

**Backend 实现**:
1.  **StateBackend**: 基于 LangGraph State（开发/测试环境）
2.  **RedisBackend**: 基于 Redis + OpenSearch（生产环境）
3.  **NornirSandbox**: 实现 `SandboxBackendProtocol`（网络设备执行）

```python
# src/olav/execution/backends/nornir_sandbox.py
from deepagents.backends.protocol import SandboxBackendProtocol

class NornirSandbox(SandboxBackendProtocol):
    """Nornir 执行沙盒，实现 HITL 和审计"""
    
    def __init__(self, nornir_config: str):
        from olav.execution.nornir_loader import get_nornir
        self.nr = get_nornir()
        self.audit_log = []
    
    async def execute(
        self,
        command: str,  # NETCONF XML Payload
        background: bool = False,
        requires_approval: bool = True
    ) -> ExecutionResult:
        """执行 NETCONF 命令（带 HITL）"""
        
        # 分析操作类型
        is_write = self._is_write_operation(command)
        
        if is_write and requires_approval:
            # 触发 HITL（通过 LangGraph interrupt）
            approval = await self._request_approval(command)
            if approval.decision == "reject":
                return ExecutionResult(success=False, output="User rejected")
            elif approval.decision == "edit":
                command = approval.edited_command
        
        # 记录审计日志
        self._log_execution(command, is_write)
        
        # 调用 Nornir 执行
        result = self.nr.run(
            task=netconf_task,
            payload=command
        )
        
        return ExecutionResult.from_nornir(result)
```

### 4.5 执行沙盒 (`src/olav/execution/sandbox.py`)
**职责**: Backend 层的安全执行器。
*   实现 `SandboxBackendProtocol` 协议
*   接收 `nornir_tool.py` 传递的指令（XML Payload）
*   分析指令类型（Read vs Write）
*   Write 操作通过 LangGraph `interrupt` 机制触发 HITL
*   记录审计日志到 OpenSearch `olav-audit` 索引
*   调用 Nornir 执行并返回结构化结果

### 4.6 Middleware 架构 (LangChain Middleware Pattern)
基于 **LangChain V1 Middleware** 设计模式，OLAV 采用中间件栈实现横切关注点：

**核心中间件**:
*   **TodoListMiddleware**: 自动任务分解与跟踪（来自 `langchain.agents.middleware.todo`）
*   **HumanInTheLoopMiddleware**: HITL 审批机制（配置 `interrupt_on` 参数）
*   **SummarizationMiddleware**: 长对话自动摘要（170K tokens 阈值）
*   **AnthropicPromptCachingMiddleware**: Prompt 缓存优化
*   **ModelRetryMiddleware**: LLM 调用重试策略
*   **ToolSelectionMiddleware**: 工具选择优化

**自定义中间件**:
```python
# src/olav/agents/middleware/network_context.py
from langchain.agents.middleware import AgentMiddleware

class NetworkContextMiddleware(AgentMiddleware):
    """注入网络上下文（拓扑、设备状态）到每个请求"""
    
    async def on_model_request(self, request: ModelRequest, state: AgentState):
        # 从 NetBox 获取拓扑信息
        topology = await self.get_topology_context(state.get('device'))
        request.messages.insert(0, SystemMessage(content=f"Network Context: {topology}"))
        return request
```

### 4.7 智能体编排 (LangGraph + Deep Agents)
采用 **LangChain Deep Agents** 框架，通过 `create_deep_agent` 创建：

**Memory 共享机制** 🔑:
```python
# 使用 LangGraph Checkpointer 实现跨 Agent 的 State 持久化
from langgraph.checkpoint.postgres import PostgresSaver
import os

# 创建共享 Checkpointer（开发和生产环境统一使用 PostgreSQL）
checkpointer = PostgresSaver.from_conn_string(
    os.getenv("POSTGRES_URI", "postgresql://olav:OlavPG123!@localhost:5432/olav")
)

# 初始化 Checkpointer 表结构（首次运行）
checkpointer.setup()

agent = create_deep_agent(
    model=model,
    checkpointer=checkpointer,  # 🔑 所有 SubAgent 共享此 Checkpointer
    subagents=[suzieq_subagent, nornir_subagent],
    ...
)
```

**State 传递规则**:
- **Parent → SubAgent**: 自动过滤 `messages` 和 `todos` 字段（避免污染子上下文）
  ```python
  # 源码: deepagents/middleware/subagents.py
  _EXCLUDED_STATE_KEYS = ("messages", "todos")
  subagent_state = {k: v for k, v in runtime.state.items() 
                    if k not in _EXCLUDED_STATE_KEYS}
  ```
- **SubAgent → Parent**: 只返回最后一条消息 + 自定义 State 字段
  ```python
  return Command(
      update={
          **custom_state_fields,  # 如: device_status, network_topology
          "messages": [ToolMessage(result["messages"][-1].text, ...)]
      }
  )
  ```
- **线程隔离**: 通过 `thread_id` 隔离不同用户会话
  ```python
  config = {"configurable": {"thread_id": "user-123"}}
  agent.invoke({"messages": [...]}, config=config)
  ```

**Agent 角色定义**:

*   **Root Agent (`root_agent.py`)**: 使用 `create_deep_agent()` 创建主编排器
    - **内置中间件**: TodoList → Filesystem → SubAgent → Summarization → HITL
    - 自动生成多步骤执行计划（TODO List）
    - 动态路由到专业 SubAgent（SuzieQ/RAG/Netconf）
    - 支持 `recursion_limit=1000` 深度任务
    
*   **SuzieQ SubAgent**: 配置为只读 SubAgent（**无需沙盒，直接查询 Parquet**）
    ```python
    suzieq_subagent = SubAgent(
        name="suzieq-analyzer",
        description="查询历史网络数据和趋势分析（只读，无副作用）",
        prompt="""你是网络可观测性专家，使用 SuzieQ 分析历史数据。
        
        SuzieQ 是只读工具，查询存储在 Parquet 文件中的历史数据。
        使用 suzieq_schema_search 查询可用的表和字段。
        使用 suzieq_query 执行实际查询。
        """,
        tools=[suzieq_schema_search, suzieq_query, datetime_tool]
        # 注意：不需要 interrupt_on，因为是只读操作
    )
    ```
    
*   **RAG SubAgent**: 知识检索专家（三层策略）
    ```python
    rag_subagent = SubAgent(
        name="knowledge-retriever",
        description="检索 OpenConfig Schema、文档和历史经验",
        prompt="执行智能知识检索：Memory优先 → Schema回退 → Docs补充",
        tools=[opensearch_tool]
    )
    ```
    
*   **Netconf SubAgent**: 实时诊断 Agent（带 HITL）
    ```python
    netconf_subagent = SubAgent(
        name="netconf-executor",
        description="执行 NETCONF/gNMI 实时设备操作",
        prompt="基于 OpenConfig Schema 构建 NETCONF Payload",
        tools=[nornir_tool],
        interrupt_on={
            "nornir_tool": {"allowed_decisions": ["approve", "edit", "reject"]}
        }
    )
    ```

#### 4.7.1 CLI/NETCONF 双模式策略（统一 HITL 执行）

**背景**: GNS3/EVE-NG 等模拟器的 Cisco IOS 镜像通常不支持 NETCONF，需要降级到传统 CLI 模式。

**设计原则** 🔑:
1. **只读场景**: NTC-Templates 自动解析 → 结构化 JSON（完全自动化）
2. **配置变更场景**: CLI/NETCONF 双模式 → **统一 HITL 审批流程** → OLAV 执行
3. **双路由架构**: 自动检测设备能力 → NETCONF 优先 / CLI 降级（都支持执行）

**分层策略**:
```
User Intent ("配置接口描述")
    ↓
Schema-Aware Discovery (从 ntc-schema 索引查询)
    ↓
┌──────────────┬──────────────┐
│ NETCONF 可用 │ NETCONF 不可用│
│  (生产设备)  │   (模拟器)   │
└──────┬───────┴──────┬───────┘
       │              │
  生成 NETCONF RPC  生成 CLI 命令
  (OpenConfig YANG) (平台特定语法)
       │              │
       └──────┬───────┘
              ↓
         HITL 审批
    (approve/edit/reject)
              ↓
    执行配置 (Nornir)
              ↓
    审计日志 + 自动验证
```

**NTC-Templates Schema 索引设计**:

ETL 脚本从 `archive/ntc-templates/ntc_templates/templates/` 提取元数据：

```python
# src/olav/etl/ntc_schema_etl.py
def index_ntc_templates():
    """
    遍历 ntc-templates/*.textfsm
    提取: platform, command, fields, semantic_tags
    写入 OpenSearch ntc-schema 索引
    """
    
# 索引文档结构
{
    "platform": "cisco_ios",
    "command": "show interfaces",
    "parser": "cisco_ios_show_interfaces.textfsm",
    "fields": ["interface", "link_status", "protocol", "mtu", "bandwidth"],
    "semantic_tags": ["接口状态", "interface status", "port info"],
    "template_path": "templates/cisco_ios_show_interfaces.textfsm",
    "is_read_only": true
}
```

**Schema-Aware 工具升级**:

```python
# src/olav/tools/nornir_tool.py（升级版）
@tool
def query_device_adaptive(
    device: str,
    intent: str,  # "获取接口状态" / "修改接口描述"
    method: Literal["netconf", "cli", "auto"] = "auto",
    config_commands: Optional[List[str]] = None,  # 🔑 配置命令列表（触发HITL）
    requires_approval: bool = True  # 🔑 配置变更必须审批
) -> Dict:
    """
    自适应查询/配置工具：
    
    只读模式 (config_commands=None):
    1. auto 模式: 自动检测设备能力（探测 TCP 830/22）
    2. NETCONF 可用: 执行 get-config RPC
    3. NETCONF 不可用: 
       - 查询 ntc-schema 获取匹配命令
       - 执行 Netmiko 命令（use_textfsm=True）
       - 返回结构化 JSON
    
    配置模式 (config_commands=[...]):
    1. 检测设备能力 → 生成 NETCONF RPC 或 CLI 命令
    2. 触发 LangGraph HITL interrupt（等待人工审批）
    3. 审批通过 → 执行配置 → 记录审计日志
    4. CLI 模式额外警告: 无 NETCONF 原子回滚
    """

@tool
def discover_commands(
    intent: str,
    platform: str = "cisco_ios"
) -> List[Dict]:
    """
    从 ntc-schema 索引发现可用命令（支持语义搜索）
    
    输入: intent="接口流量统计", platform="cisco_ios"
    输出: [
        {
            "command": "show interfaces",
            "parser": "cisco_ios_show_interfaces.textfsm",
            "fields": ["interface", "input_packets", "output_packets"],
            "is_read_only": true
        }
    ]
    """
```

**配置变更的统一执行模式**:

配置变更通过 `query_device_adaptive` 的 `config_commands` 参数触发：

```python
# Agent 调用示例
result = query_device_adaptive(
    device="R1",
    intent="修改接口描述为 CORE-UPLINK",
    config_commands=[
        "configure terminal",
        "interface GigabitEthernet0/1",
        "description CORE-UPLINK",
        "end",
        "write memory"
    ]
)

# 工具内部流程:
# 1. 检测到 config_commands 非空 → 进入配置模式
# 2. 检测设备 NETCONF 能力
# 3. 构建审批请求（包含命令、回滚方案、风险警告）
# 4. 触发 LangGraph interrupt
# 5. 等待用户决策: approve/edit/reject
# 6. 执行并记录审计日志
```

**Agent Prompt 更新（平台感知设计）**:

```python
# config/prompts/agents/netconf_agent.yaml
template: |
  你是网络设备配置专家，负责执行实时诊断和配置任务。
  
  当前设备信息:
  - 设备名: {device_name}
  - 平台: {device_platform}  # cisco_ios / cisco_nxos / arista_eos / juniper_junos
  - 管理IP: {device_ip}
  - NETCONF支持: {netconf_available}  # true/false
  
  平台命令语法映射:
  - cisco_ios/iosxr: "configure terminal" → "interface xxx" → "end" → "write memory"
  - cisco_nxos: "config t" → "interface xxx" → "copy running-config startup-config"
  - arista_eos: "configure" → "interface xxx" → "write memory"
  - juniper_junos: "edit" → "set interfaces xxx" → "commit"
  - huawei_vrp: "system-view" → "interface xxx" → "commit"
  
  工作流程:
  
  1. **只读诊断（自动执行）**:
     - 使用 query_device_adaptive(device="{device_name}", intent="...", method="auto")
     - NETCONF 可用: 执行 get-config RPC
     - NETCONF 不可用: 自动降级到 CLI + TextFSM 解析
     - 返回结构化 JSON
  
  2. **配置变更（HITL 审批执行）**:
     A. 生成平台特定命令:
        - 根据 {device_platform} 生成正确语法
        - 使用 discover_commands 查询模板
     
     B. 调用配置工具:
        ```python
        query_device_adaptive(
            device="{device_name}",
            intent="修改接口描述",
            config_commands=[...],  # 平台特定命令列表
            method="auto"  # 自动选择 NETCONF/CLI
        )
        ```
     
     C. 等待 HITL 审批:
        - 系统自动暂停，展示审批界面
        - CLI 模式显示警告: "⚠️ 无 NETCONF 原子回滚"
        - 用户选择: Approve / Edit / Reject
     
     D. 执行后验证:
        - 自动调用只读命令验证更改
        - 对比变更前后配置差异
```
       
       R1# configure terminal
       R1(config)# interface GigabitEthernet0/1
       R1(config-if)# description CORE-UPLINK
       R1(config-if)# end
       R1# write memory
       
       回滚命令（如需撤销）:
       R1(config-if)# no description
       ```
     - 不要调用 nornir_tool 执行配置变更（模拟器无 NETCONF 保护）
  
  3. **生产环境（NETCONF 可用）**:
     - 配置变更通过 nornir_tool 执行
     - 触发 HITL 审批
     - 支持 NETCONF 原子回滚
```

**参考 baseline_collector.py 的关键功能**:

从 `archive/baseline_collector.py` 借鉴以下设计：

1. **TemplateManager** 类（简化版）:
   - 扫描 ntc-templates 目录
   - 解析 `cisco_ios_show_*.textfsm` → 提取 command 和 fields
   - 缓存 `platform → [(command, template_path, fields)]` 映射

2. **TextFSM 自动解析**:
   ```python
   # baseline_collector 中的核心逻辑
   result = nr.run(
       task=netmiko_send_command,
       command_string=command,
       use_textfsm=True  # 🔑 自动调用 NTC-Templates
   )
   ```

3. **黑名单机制**:
   - 过滤危险命令（traceroute, reload）
   - 支持从 `command_blacklist.txt` 加载自定义规则

**不采用的功能**:
- ❌ 配置备份自动化（OLAV 不做定时任务）
- ❌ 多命令批量执行（降低复杂度）
- ❌ Gitea 集成（OLAV 使用 OpenSearch Memory）

**ETL 实现优先级**:

1. **高优先级**: `src/olav/etl/ntc_schema_etl.py`
   - 解析 ntc-templates 目录
   - 索引到 OpenSearch `ntc-schema`
   - 支持语义搜索（"接口状态" → "show interfaces"）

2. **中优先级**: `src/olav/tools/config_advisor.py`
   - 生成配置命令建议
   - 返回 rollback 命令
   - 仅返回文本，不执行

3. **低优先级**: 设备能力探测（NETCONF vs CLI）
   - 可在 `nornir_sandbox.py` 中实现
   - 缓存结果到 Redis（避免重复探测）

**典型用户交互流程**:

```
用户: "检查 R1 的接口状态"
OLAV: [调用 query_device_adaptive(device="R1", intent="接口状态", method="auto")]
      检测到 R1 不支持 NETCONF，降级到 CLI 模式
      执行命令: show interfaces
      [解析 TextFSM 模板]
      
      结果:
      {
        "GigabitEthernet0/0": {"status": "up", "protocol": "up", "mtu": 1500},
        "GigabitEthernet0/1": {"status": "down", "protocol": "down", "mtu": 1500}
      }

用户: "修改 R1 的 GigabitEthernet0/1 描述为 CORE-UPLINK"
OLAV: [查询设备平台: cisco_ios]
      [生成 CLI 命令序列]
      [调用 query_device_adaptive(
          device="R1",
          config_commands=["configure terminal", "interface GigabitEthernet0/1", ...]
      )]
      
      ╔════════════════════════════════════════════════╗
      ║  配置变更审批                                   ║
      ╠════════════════════════════════════════════════╣
      ║  设备: R1 (cisco_ios)                          ║
      ║  模式: CLI (⚠️ 无NETCONF原子回滚)              ║
      ╠════════════════════════════════════════════════╣
      ║  待执行命令:                                    ║
      ║  1. configure terminal                         ║
      ║  2. interface GigabitEthernet0/1               ║
      ║  3. description CORE-UPLINK                    ║
      ║  4. end                                        ║
      ║  5. write memory                               ║
      ╠════════════════════════════════════════════════╣
      ║  [A] Approve  [E] Edit  [R] Reject            ║
      ╚════════════════════════════════════════════════╝

用户: [选择 A - Approve]
OLAV: 正在执行配置变更...
      ✅ 配置已应用
      
      验证结果:
      GigabitEthernet0/1:
        Description: CORE-UPLINK ✓
        Status: down → up (已激活)
      
      审计日志已记录到 OpenSearch (olav-audit 索引)
```

**安全考量**:
- ✅ 只读命令（show/display）: 完全自动化执行
- ⚠️ 配置变更（config/configure）: **强制 HITL 审批 + 审计日志**
- ❌ 危险命令（reload/erase）: 黑名单拦截
- 🔒 CLI 模式额外警告: 无原子回滚，建议执行前备份配置

#### 4.7.2 双 Agent 架构（避免幻觉 + Token 优化 + 自动降级）

**设计目标**: 
1. **避免幻觉**: 通过职责隔离，防止 LLM 混淆 NETCONF XML 和 CLI 命令语法
2. **Token 优化**: 分离 Prompt，节省 **~400-500 tokens/次调用**
3. **自动降级**: Root Agent 先尝试 NETCONF，失败后自动切换到 CLI

**架构设计（LangGraph 路由模式）**:

```
Root Agent (Orchestrator)
    ↓
    调用 netconf_subagent
    ↓
┌───────────────────────────┐
│ NETCONF SubAgent 执行     │
│ - 尝试连接 TCP:830        │
│ - 执行 NETCONF RPC        │
└───────────┬───────────────┘
            ↓
    ┌───────┴────────┐
    │ 成功           │ 失败 (ConnectionError)
    ↓                ↓
返回结果          netconf_subagent 返回错误
                     ↓
              Root Agent 检测到 NETCONF 失败
                     ↓
              更新计划: "NETCONF 不可用，降级到 CLI"
                     ↓
              调用 cli_subagent
                     ↓
              ┌──────────────────────┐
              │ CLI SubAgent 执行    │
              │ - 连接 SSH (TCP:22) │
              │ - 执行 CLI 命令      │
              └──────────────────────┘
```

**实现方式（基于 LangGraph State + 条件路由）**:

```python
# src/olav/agents/root_agent.py
from deepagents import create_deep_agent, SubAgent
from olav.core.prompt_manager import prompt_manager
from olav.agents.netconf_agent import netconf_subagent
from olav.agents.cli_agent import cli_subagent

# Root Agent Prompt
root_prompt = prompt_manager.load_agent_prompt(
    "root_agent",
    network_context="Enterprise Network Operations"
)

# 创建 Root Agent (包含两个 SubAgent)
root_agent = create_deep_agent(
    model=LLMFactory.get_chat_model(),
    system_prompt=root_prompt + """
    
## 设备操作策略（漏斗式降级）

当用户请求操作设备时，遵循以下策略:

1. **优先尝试 NETCONF** (生产环境标准)
   - 调用 netconf-executor SubAgent
   - 如果收到 "NETCONF connection failed" 或 "Port 830 unreachable"
   - 则执行步骤 2

2. **自动降级到 CLI** (兼容传统设备)
   - 更新你的计划: "NETCONF 不可用，使用 CLI 模式"
   - 调用 cli-executor SubAgent
   - ⚠️ 提醒用户: CLI 模式无原子回滚能力

3. **错误处理**
   - 如果 CLI 也失败 → 检查设备可达性
   - 引导用户验证: IP、凭据、防火墙规则

示例对话:
用户: "检查 R1 的接口状态"
你的思考:
1. 调用 netconf-executor(device="R1", operation="get-config", xpath="/interfaces")
2. [如果失败] 更新计划 → 调用 cli-executor(device="R1", command="show ip interface brief")
""",
    subagents=[netconf_subagent, cli_subagent],  # 🔑 两个 Agent 都注册
    checkpointer=checkpointer,
)
```

**NETCONF SubAgent (先锋尝试)**:

```python
# src/olav/agents/netconf_agent.py
from deepagents import SubAgent
from olav.tools.nornir_tool import netconf_tool

netconf_subagent = SubAgent(
    name="netconf-executor",
    description="通过 NETCONF/YANG 执行设备操作（优先使用）",
    prompt=prompt_manager.load_agent_prompt("netconf_agent"),
    tools=[netconf_tool],
    interrupt_on={
        "netconf_tool": {
            "condition": lambda args: args.get("operation") == "edit-config",
            "allowed_decisions": ["approve", "edit", "reject"]
        }
    }
)
```

**CLI SubAgent (降级备份)**:

```python
# src/olav/agents/cli_agent.py
from deepagents import SubAgent
from olav.tools.nornir_tool import cli_tool
from olav.tools.ntc_tool import discover_commands

cli_subagent = SubAgent(
    name="cli-executor",
    description="通过 CLI 命令执行设备操作（NETCONF 失败时使用）",
    prompt=prompt_manager.load_agent_prompt("cli_agent"),
    tools=[cli_tool, discover_commands],
    interrupt_on={
        "cli_tool": {
            "condition": lambda args: args.get("config_commands") is not None,
            "allowed_decisions": ["approve", "edit", "reject"]
        }
    }
)
```

**关键改进点**:

1. **Root Agent 控制流程** (而非预先探测)
   - ❌ 旧方案: `if probe_netconf_port(): use_netconf else: use_cli`
   - ✅ 新方案: `try netconf → catch error → fallback to cli`
   
2. **错误驱动的降级** (更符合实际网络场景)
   - NETCONF 失败不一定是端口问题（可能是认证、协议版本）
   - 真实尝试连接 → 根据实际错误决定是否降级

3. **Root Agent 的 Prompt 包含降级逻辑**
   - LLM 看到 "NETCONF connection failed" 错误
   - 自动更新计划调用 cli-executor
   - 无需硬编码 if-else 逻辑

4. **两个 SubAgent 平等注册**
   - `subagents=[netconf_subagent, cli_subagent]`
   - Root Agent 可以根据上下文自由选择
   - 符合 DeepAgents 的设计哲学

**Prompt 文件结构**:

```yaml
# config/prompts/agents/netconf_agent.yaml（NETCONF Agent 专用）
_type: prompt
input_variables: []
template: |
  你是 OLAV 的 **NETCONF 执行代理** (专注于 NETCONF 协议操作)。
  
  ## 你的职责
  1. **查询操作** (`<get-config>`)
     - 构造 NETCONF RPC 请求
     - 使用 XPath 过滤器精准查询
     - 优先查询 openconfig-schema 索引获取正确的 YANG 路径
  
  2. **配置操作** (`<edit-config>`)
     - 构造符合 OpenConfig 规范的 XML Payload
     - **必须人工审批** (触发 HITL 中断)
     - 利用 NETCONF 原子回滚能力
  
  3. **错误处理 (关键)**
     - 如果收到 **"Connection refused"** 或 **"Port 830 unreachable"**
     - 返回明确错误: "NETCONF connection failed: {原因}"
     - **让 Root Agent 决定是否降级到 CLI**
  
  ## 工具使用
  - `netconf_tool(device, operation, xpath, payload)`
    - device: 设备名称 (从 Root Agent 传递)
    - operation: "get-config" | "edit-config"
    - xpath: XPath 过滤器 (查询时使用)
    - payload: XML 字符串 (配置时使用)
  
  ## 示例对话
  用户: "检查设备的接口状态"
  你的执行:
  1. 查询 openconfig-schema: "interface state"
  2. 获取 XPath: `/interfaces/interface/state`
  3. 调用: netconf_tool(device="...", operation="get-config", xpath="/interfaces/interface/state")
  
  如果连接失败:
  返回: "NETCONF connection failed: Connection refused on port 830. 设备可能不支持 NETCONF。"
  (Root Agent 会自动切换到 CLI 模式)
  
  ## 注意事项
  - **绝不使用 CLI 命令语法** (如 `show ip bgp`)
  - **绝不尝试生成 CLI 命令** (这是 cli-executor 的职责)
  - 所有配置遵循 YANG Schema 约束
  - 连接失败时返回清晰的错误信息 (不要自己尝试降级)
```

```yaml
# config/prompts/agents/cli_agent.yaml（CLI Agent 专用）
_type: prompt
input_variables: []
template: |
  你是 OLAV 的 **CLI 执行代理** (专注于传统 CLI 命令操作)。
  
  ## 平台命令映射 (根据设备平台推断语法)
  | 平台 | 查看接口 | 查看 BGP | 配置接口 MTU |
  |------|---------|---------|--------------|
  | cisco_ios | `show ip interface brief` | `show ip bgp summary` | `interface Gi0/0` + `mtu 9000` |
  | cisco_nxos | `show interface brief` | `show bgp ipv4 unicast summary` | `interface Eth1/1` + `mtu 9000` |
  | cisco_iosxr | `show ipv4 interface brief` | `show bgp summary` | `interface Gi0/0/0/0` + `mtu 9000` |
  | arista_eos | `show ip interface brief` | `show ip bgp summary` | `interface Ethernet1` + `mtu 9000` |
  | juniper_junos | `show interfaces terse` | `show bgp summary` | `set interfaces ge-0/0/0 mtu 9000` |
  | huawei_vrp | `display ip interface brief` | `display bgp peer` | `interface Gi0/0/0` + `mtu 9000` |
  
  ## 你的职责
  1. **查询操作** (只读命令)
     - 使用 discover_commands 查询可用命令
     - 根据设备平台推断正确语法
     - 输出自动通过 TextFSM 解析为结构化数据
  
  2. **配置操作** (写命令)
     - 生成配置命令序列 (基于平台语法)
     - **必须人工审批** (触发 HITL 中断)
     - ⚠️ 警告: CLI 模式无原子回滚
  
  3. **故障排查**
     - 解析命令输出中的错误信息
     - 引导用户检查权限、语法、设备状态
  
  ## 工具使用
  - `cli_tool(device, command, config_commands)`
    - device: 设备名称 (从 Root Agent 传递)
    - command: 查询命令 (只读)
    - config_commands: 配置命令列表 (写操作)
  
  - `discover_commands(platform, intent)` (可选)
    - platform: 设备平台 (cisco_ios, arista_eos, etc.)
    - intent: 查询意图 ("查看接口状态", "配置 BGP")
  
  ## 示例对话
  用户: "检查设备的接口状态"
  你的执行:
  1. [可选] discover_commands(platform="cisco_ios", intent="查看接口")
  2. 调用: cli_tool(device="...", command="show ip interface brief")
  3. 返回 TextFSM 解析后的结构化数据
  
  用户: "修改设备的 GigabitEthernet0/0 MTU 为 9000"
  你的执行:
  1. 根据平台生成命令: ["interface GigabitEthernet0/0", "mtu 9000"]
  2. 调用: cli_tool(device="...", config_commands=["interface GigabitEthernet0/0", "mtu 9000"])
  3. ⚠️ 触发 HITL - 等待用户批准
  4. 提醒用户保存配置
  
  ## 注意事项
  - **绝不使用 NETCONF/YANG 术语** (如 XPath、RPC、Payload)
  - **绝不尝试构造 XML** (这是 netconf-executor 的职责)
  - 严格遵守平台命令语法 (参考上表)
  - ⚠️ 提醒用户: CLI 模式无自动回滚 - 建议先在测试设备验证
```

**双 Agent 架构优势 (错误驱动降级)**:

| 维度 | 预先探测模式 | 错误驱动降级 | 改进 |
|------|------------|------------|------|
| **幻觉风险** | Agent 需要同时理解两种语法 | 每个 Agent 只专注一种语法 | **职责隔离** |
| **路由准确性** | 端口探测可能误判 (防火墙/超时) | 真实连接尝试，基于实际错误 | **更可靠** |
| **Token 消耗** | 单 Prompt ~800 tokens | 分离 Prompt ~300-400 | **50-62% 节省** |
| **降级灵活性** | 硬编码 if-else | LLM 根据错误信息自主决定 | **智能降级** |
| **错误诊断** | 无法区分不同失败原因 | 清晰错误信息 (认证 vs 协议 vs 端口) | **更好排障** |
| **Root Agent 负担** | 需要设备探测逻辑 | 只需调用 SubAgent + 错误处理 | **简化编排** |

**避免幻觉的关键设计**:

1. **工具隔离**:
   - NETCONF Agent: 仅能访问 `netconf_tool` (发送 RPC)
   - CLI Agent: 仅能访问 `cli_tool` + `discover_commands`
   - **物理隔离** → LLM 无法调用错误工具

2. **Prompt 专注**:
   - NETCONF Prompt: 强调 "绝不使用 CLI 命令"
   - CLI Prompt: 强调 "绝不使用 NETCONF/YANG 术语"
   - **明确禁止** → 减少跨界幻觉

3. **示例对话**:
   - 每个 Prompt 包含 2 个典型场景（查询 + 配置）
   - 使用实际设备平台的真实命令
   - **Few-Shot Learning** → 引导正确模式

**成本优化（Prompt Caching）**:

```python
# 使用 Anthropic Prompt Caching
from langchain.agents.middleware import AnthropicPromptCachingMiddleware

agent = create_deep_agent(
    model=LLMFactory.get_chat_model(),
    middleware=[
        AnthropicPromptCachingMiddleware(
            cache_system_prompts=True,  # 缓存 System Prompt
            cache_tools=True             # 缓存 Tool Descriptions
        )
    ],
    ...
)
```

**缓存效果**:
- 第 1 次调用: 400 tokens (写入缓存)
- 第 2-N 次调用: 40 tokens (读取缓存，90% 折扣)
- 5 分钟缓存窗口内重复调用接近免费

    
*   **NetBox SubAgent (SSOT Manager)**: 设备和站点的单一真理源管理
    ```python
    netbox_subagent = SubAgent(
        name="netbox-manager",
        description="管理 NetBox 中的设备和站点信息",
        prompt="""
        你是网络资产管理专家，负责维护 NetBox 中的设备和站点信息。
        
        所有操作必须确保依赖关系完整，如：
        - Site 必须存在
        - Manufacturer 必须存在
        """,
        tools=[
            netbox_schema_search,  # 搜索 API 端点
            netbox_api_call,       # 执行 API 调用
            inventory_import,      # CSV 导入
            sync_configs            # 同步配置
        ]
    )
    ```
    
*   **Learner Agent (`learner_agent.py`)**: 后处理节点
    - LangGraph 图的最终节点（对话结束时触发）
    - 分析成功路径并向量化存入 `olav-episodic-memory`
    - 使用 `LLMFactory.get_embedding_model()`

**深度代理创建示例**:
```python
# root_agent.py
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

agent = create_deep_agent(
    model=LLMFactory.get_chat_model(),
    system_prompt="""你是企业网络运维专家 OLAV。
    
工作流程:
1. 使用 rag_agent 检索 Schema/Docs/Memory
2. 使用 suzieq_agent 进行宏观历史分析
3. 使用 netconf_agent 进行实时微观诊断
4. 所有 Write 操作必须等待人工批准
""",
    subagents=[suzieq_subagent, rag_subagent, netconf_subagent],
    middleware=[
        NetworkContextMiddleware(),  # 自定义中间件
    ],
    checkpointer=RedisCheckpointer(settings.REDIS_URL),
    interrupt_on={
        "nornir_tool": {"allowed_decisions": ["approve", "edit", "reject"]}
    }
).with_config({"recursion_limit": 1000})
```

**典型工作流**:
```mermaid
graph LR
    User -->|"查询 BGP 状态"| Supervisor
    Supervisor -->|"需要实时数据"| Netconf
    Netconf -->|"请求 Schema"| RAG[RAG Agent]
    RAG -->|"1. 查 Memory"| Memory[(Memory Index)]
    RAG -->|"2. 查 Schema"| Schema[(Schema Index)]
    RAG -->|"返回 XPath"| Netconf
    Netconf -->|"构建 Payload"| Sandbox
    Sandbox -->|"NETCONF RPC"| Device[Network Device]
```

---

## 5. 基础设施配置 (Docker Compose)

### 服务概览

*   **opensearch**: 向量数据库,存储 Schema、文档和记忆。
*   **redis**: 状态存储,用于 LangGraph 的 Checkpoint。
*   **olav-init**: Schema 初始化器 (一次性任务),解析 YANG 模型。
*   **olav-embedder**: 文档向量化服务 (常驻/按需),处理 PDF/MD。
*   **suzieq**: 可观测性平台,提供宏观网络数据。
*   **olav-app**: 主程序 (Agent CLI),挂载源码进行热重载开发。

### docker-compose.yml 配置

```yaml
version: '3.8'

services:
  # 1. 向量数据库 (OpenSearch)
  opensearch:
    image: opensearchproject/opensearch:latest
    environment:
      - discovery.type=single-node
      - "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m"
    ports: ["9200:9200"]
    volumes: ["opensearch-data:/usr/share/opensearch/data"]

  # 2. 关系数据库 (PostgreSQL - LangGraph Checkpointer)
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: olav
      POSTGRES_USER: olav
      POSTGRES_PASSWORD: OlavPG123!
    ports: ["5432:5432"]
    volumes: ["postgres-data:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U olav"]
      interval: 5s
      timeout: 5s
      retries: 5

  # 3. 状态存储 (Redis)
  redis:
    image: redis:alpine
    ports: ["6379:6379"]

  # 4. 初始化容器 (Run-once)
  # 负责初始化所有 Schema: OpenConfig YANG + SuzieQ Avro Schema + PostgreSQL Tables
  olav-init:
    build:
      context: .
      dockerfile: Dockerfile
    command: |
      bash -c '
        echo "=== Starting Initialization Pipeline ==="
        python -m olav.etl.init_postgres &&
        python -m olav.etl.init_schema && 
        python -m olav.etl.suzieq_schema_etl &&
        echo "✅ All schemas and tables initialized successfully"
      '
    env_file: .env
    depends_on:
      opensearch:
        condition: service_started
      postgres:
        condition: service_healthy
    profiles: ["init"] # 仅在显式调用时运行: docker-compose --profile init up

  # 5. 文档向量化服务 (Service)
  # 常驻后台,提供 API 触发文档重索引
  olav-embedder:
    build:
      context: .
      dockerfile: Dockerfile.embedder
    env_file: .env
    ports: ["8001:8000"]
    volumes:
      - ./data/documents:/app/data/documents
      - ./src:/app/src
    depends_on:
      opensearch:
        condition: service_started
      postgres:
        condition: service_healthy

  # 6. 可观测性 (SuzieQ)
  suzieq:
    image: netenglabs/suzieq:latest
    volumes:
      - ./data/suzieq-parquet:/suzieq/parquet
    command: sq-rest-server

  # 7. OLAV 主程序 (CLI/Agent)
  olav-app:
    build: .
    image: olav:latest
    env_file: .env
    volumes:
      - ./src:/app/src      # 源码热重载
      - ./config:/app/config
    depends_on:
      opensearch:
        condition: service_started
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      suzieq:
        condition: service_started
    # 保持运行,通过 docker exec 进入 CLI
    command: tail -f /dev/null

volumes:
  opensearch-data:
  postgres-data:
```

### 环境变量配置 (.env.example)

```bash
# LLM Configuration
LLM_PROVIDER=openai              # openai, ollama, azure
LLM_API_KEY=sk-...
LLM_MODEL_NAME=gpt-4-turbo
LLM_BASE_URL=                    # Optional for Azure/Ollama

# Infrastructure
OPENSEARCH_URL=http://opensearch:9200
POSTGRES_URI=postgresql://olav:OlavPG123!@postgres:5432/olav
REDIS_URL=redis://redis:6379
SUZIEQ_URL=http://suzieq:8000

# NetBox (Single Source of Truth)
NETBOX_URL=https://netbox.example.com
NETBOX_TOKEN=your-token-here

# Device Credentials (for Nornir/SuzieQ)
DEVICE_USERNAME=admin
DEVICE_PASSWORD=your-secure-password  # 生产环境建议使用 Vault

# OpenConfig Schema Repository
OPENCONFIG_REPO_URL=https://github.com/openconfig/public.git
OPENCONFIG_REPO_BRANCH=master
```

---

## 6. 快速开始 (Quick Start)

### 前置要求

*   Docker & Docker Compose
*   Python 3.11+ (本地开发)
*   uv (推荐的包管理器)

### 步骤 1: 初始化项目

```bash
# 克隆仓库
git clone <repository-url> olav
cd olav

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 填入你的 API Keys
```

### 步骤 2: 启动基础设施

```bash
# 启动所有服务
docker-compose up -d

# 初始化所有 Schema (一次性任务)
# 这会执行三个初始化流程：
#   1. PostgreSQL Checkpointer 表 → checkpoints, checkpoint_writes
#   2. OpenConfig YANG Schema → openconfig-schema 索引
#   3. SuzieQ Avro Schema → suzieq-schema 索引
docker-compose --profile init up olav-init

# 检查服务状态
docker-compose ps

# 验证 OpenSearch 索引
curl http://localhost:9200/_cat/indices?v | grep schema
# 应该看到: openconfig-schema, suzieq-schema

# 验证 PostgreSQL Checkpointer 表
docker-compose exec postgres psql -U olav -d olav -c "\dt"
# 应该看到: checkpoints, checkpoint_writes, checkpoint_migrations

# 验证 OpenSearch 索引
curl http://localhost:9200/_cat/indices?v | grep schema
# 应该看到: openconfig-schema, suzieq-schema

# 验证 PostgreSQL Checkpointer 表
docker-compose exec postgres psql -U olav -d olav -c "\dt"
# 应该看到: checkpoints, checkpoint_writes, checkpoint_migrations
```

### 步骤 3: 配置 NetBox 连接

OLAV 使用 **NetBox 作为唯一的 Inventory 来源**（SSOT），无需维护静态配置文件。

```bash
# 1. 配置环境变量（.env 文件）
cat > .env <<EOF
# NetBox SSOT Configuration
NETBOX_URL=https://netbox.example.com
NETBOX_TOKEN=your_netbox_api_token_here

# Device Credentials (可选，如果 NetBox 未存储)
DEVICE_USERNAME=admin
DEVICE_PASSWORD=secure_password
EOF

# 2. 启动 olav-init 容器（自动生成 SuzieQ 配置）
docker-compose --profile init up olav-init

# 3. 验证配置生成
cat data/generated_configs/suzieq_config.yml
# 应该看到从 .env 读取的 NETBOX_URL 和 NETBOX_TOKEN

# 4. 重启 SuzieQ 以加载生成的配置
docker-compose restart suzieq

# 5. 验证设备同步
docker exec -it suzieq sq device show
```

**说明**: 
- **Nornir**: 使用代码中的 `InitNornir()` 动态配置，无需 YAML 文件
- **SuzieQ**: 配置由 `generate_configs.py` 在初始化时生成到 `data/generated_configs/`
- **凭据管理**: 所有敏感信息从环境变量读取，符合 12-Factor App 原则

### 步骤 4: 进入 OLAV CLI

```bash
# 进入主容器
docker exec -it olav-app bash

# 启动交互式 CLI
python -m olav.main chat
```

### 步骤 5: 上传文档 (可选)

```bash
# 将 PDF 文档放入 data/documents/
cp your-manual.pdf data/documents/

# 触发向量化服务
curl -X POST http://localhost:8001/ingest
```

### 开发模式

```bash
# 本地运行 (不使用 Docker)
uv sync
uv run python -m olav.main chat

# 运行测试
uv run pytest

# 代码检查
uv run ruff check .
```

---

## 7. 项目脚手架生成 (Scaffolding)

使用以下脚本快速生成完整的目录结构:

```bash
#!/bin/bash
# init_olav.sh

PROJECT="olav"
echo "🏗️  Scaffolding Project OLAV..."

# 1. 创建根目录文件
mkdir -p $PROJECT
cd $PROJECT
touch .env.example .gitignore uv.lock pyproject.toml docker-compose.yml Dockerfile Dockerfile.embedder Makefile README.md

# 2. 创建 Archive 和 Data
mkdir -p archive
touch archive/.gitkeep
mkdir -p data/{documents,suzieq-parquet}

# 3. 创建 Config
mkdir -p config/prompts/{agents,tools}
touch config/inventory_template.csv
touch config/app_settings.template.yaml

# 4. 创建 SRC 核心结构
SRC="src/olav"
mkdir -p $SRC/{core,agents,tools,execution,etl}
touch $SRC/__init__.py
touch $SRC/main.py

# Core
touch $SRC/core/{__init__.py,settings.py,state.py,llm.py,memory.py,prompt_manager.py,inventory_manager.py}

# Agents
mkdir -p $SRC/agents/middleware
touch $SRC/agents/{__init__.py,root_agent.py,suzieq_agent.py,netconf_agent.py,rag_agent.py,learner_agent.py}
touch $SRC/agents/middleware/{__init__.py,network_context.py}

# Tools
touch $SRC/tools/{__init__.py,opensearch_tool.py,suzieq_tool.py,nornir_tool.py,netbox_tool.py,datetime_tool.py}

# Execution
mkdir -p $SRC/execution/backends
touch $SRC/execution/__init__.py
touch $SRC/execution/backends/{__init__.py,protocol.py,nornir_sandbox.py,state.py,redis.py}

# ETL
touch $SRC/etl/{__init__.py,init_postgres.py,init_schema.py,suzieq_schema_etl.py,netbox_schema_etl.py,generate_configs.py}

# 5. 创建 Embedder 服务
SVC="src/embedder"
mkdir -p $SVC
touch $SVC/{__init__.py,main.py,loader.py,vectorizer.py}

# 6. 创建 Tests
mkdir -p tests/{unit,e2e}
touch tests/{__init__.py,conftest.py}
touch tests/unit/{test_agents.py,test_sandbox.py,test_llm_factory.py}
touch tests/e2e/test_workflow.py

echo "✅ OLAV structure created successfully in ./$PROJECT"
```

运行脚本:

```bash
chmod +x init_olav.sh
./init_olav.sh
```

---



### 当前进度（2025-11-23）
- Deep Dive Workflow 递归与并行批量执行已实现并通过全部测试
- 相关文档与 TODO 已同步更新
- 下一步：多失败递归增强、Checkpointer 恢复测试、性能调优

### 当前进度（2025-11-23）
- Deep Dive Workflow 递归与并行批量执行已实现并通过全部测试
- 相关文档与 TODO 已同步更新
- 下一步：多失败递归增强、Checkpointer 恢复测试、性能调优

### Phase 1: 基础建设 (Day 1-3)
*   **目标**: 跑通 `docker-compose`，所有服务显示 Healthy。
*   **任务**:
    *   编写 Dockerfile 和 `docker-compose.yml`。
    *   实现 `src/config/settings.py`。
    *   实现 `olav-init`，拉取 OpenConfig 并存入 OpenSearch。

### Phase 2: 核心 Agent 与工具 (Day 4-7)
*   **目标**: Agent 可以调用工具查询数据。
*   **任务**:
    *   实现 `src/olav/core/llm.py` (LLM Factory)。
    *   封装 `opensearch_tool.py` 和 `netbox_tool.py`。
    *   实现 `src/olav/agents/rag_agent.py` - 统一知识检索入口。
    *   编写 `src/olav/agents/root_agent.py` 实现基础路由。

### Phase 3: 执行层与安全性 (Day 8-10)
*   **目标**: 实现 Nornir 调用和 HITL。
*   **任务**:
    *   实现 `src/olav/execution/sandbox.py`。
    *   集成 Rich CLI，实现漂亮的 Spinner 和 Confirm Prompt。
    *   Test: 编写 `tests/unit/test_sandbox.py` 确保审批逻辑生效。

### Phase 4: 进阶能力 (Day 11-14)
*   **目标**: 自我学习与文档检索。
*   **任务**:
    *   实现 `olav-embedder` 服务，支持 PDF 上传。
    *   实现 LangGraph 中的 `learner_agent.py` 节点。
    *   完善 `rag_agent.py` 的三层检索逻辑（Memory -> Schema -> Docs）。
    *   实现 RAG Agent 的缓存机制，提升检索性能。
    *   Deep Dive Workflow 递归与并行批量执行（已实现，详见相关测试与代码注释）

### Phase 5: 测试与发布
*   **任务**:
    *   运行 E2E 测试。
    *   编写使用手册。
    *   Deep Dive Workflow 并行/递归测试已全部通过（详见 tests/unit/test_deep_dive_workflow.py）

---

## 9. 配置管理 (Configuration)

### settings.py (config/settings.py)

使用 Pydantic Settings 加载 `.env`:

```python
from pydantic_settings import BaseSettings
from typing import Literal, Optional

class Settings(BaseSettings):
    # LLM 配置
    LLM_PROVIDER: Literal["openai", "ollama", "azure"] = "openai"
    LLM_API_KEY: str
    LLM_MODEL_NAME: str = "gpt-4-turbo"
    LLM_BASE_URL: Optional[str] = None

    # 基础设施
    OPENSEARCH_URL: str = "http://opensearch:9200"
    REDIS_URL: str = "redis://redis:6379"
    SUZIEQ_URL: str = "http://suzieq:8000"
    
    # NetBox (Single Source of Truth)
    NETBOX_URL: str
    NETBOX_TOKEN: str
    
    # 设备认证
    DEVICE_USERNAME: str = "admin"
    DEVICE_PASSWORD: str
    
    # OpenConfig Schema 仓库
    OPENCONFIG_REPO_URL: str = "https://github.com/openconfig/public.git"
    OPENCONFIG_REPO_BRANCH: str = "master"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**注意**: Nornir 和 SuzieQ 的配置现在通过**代码动态生成**或**内嵌配置字典**实现，不再依赖静态 YAML 文件。详见下文。

---

## 11. Inventory 管理 (NetBox Integration)

### NetBox 作为单一信任源

OLAV 使用 NetBox 作为唯一的设备清单来源，避免配置漂移。SuzieQ 和 Nornir 都通过各自的配置文件直接从 NetBox 同步设备。

### Nornir NetBox 配置

### Nornir 动态配置 (无静态文件)

**当前实现**: Nornir 通过代码直接初始化，无需 `nornir_config.yml`：

```python
# src/olav/execution/backends/nornir_sandbox.py
from nornir import InitNornir
from olav.core.settings import settings

nr = InitNornir(
    runner={
        "plugin": "threaded",
        "options": {"num_workers": 100},
    },
    inventory={
        "plugin": "NetBoxInventory2",
        "options": {
            "url": settings.netbox_url,
            "token": settings.netbox_token,
            "ssl_verify": False,
        },
    },
)

if __name__ == "__main__":
    print(f"✅ Loaded {len(nr.inventory.hosts)} hosts from NetBox")
    for hostname, host in nr.inventory.hosts.items():
        print(f"  - {hostname}: {host.platform}")
```

**优势**: 配置集中在 `settings.py`，无静态文件维护负担，符合 12-Factor App 原则。

### SuzieQ 动态配置

**当前实现**: `olav-init` 容器启动时动态生成配置到 `data/generated_configs/suzieq_config.yml`：

```python
# src/olav/etl/generate_configs.py
import os
import yaml
from olav.core.settings import settings

config_dir = "data/generated_configs"
os.makedirs(config_dir, exist_ok=True)

suzieq_config = {
    "sources": [{
        "name": "netbox",
        "type": "netbox",
        "url": settings.netbox_url,
        "token": settings.netbox_token,
        "tag": "suzieq"
    }]
}

with open(f"{config_dir}/suzieq_config.yml", "w") as f:
    yaml.dump(suzieq_config, f)
```

在 `docker-compose.yml` 中挂载生成的配置：

```yaml
suzieq:
  image: netenglabs/suzieq:latest
  volumes:
    - ./data/suzieq-parquet:/suzieq/parquet
    - ./data/generated_configs:/suzieq/config:ro
  depends_on:
    olav-init:
      condition: service_completed_successfully
```

**优势**: 配置由 ETL 管道自动生成，消除手工维护和环境变量替换的复杂性。

### CSV 批量导入设备

使用 `InventoryManager` 将 CSV 设备清单导入 NetBox：

```python
# 示例使用
from olav.core.inventory_manager import InventoryManager

manager = InventoryManager()
with open("config/inventory_template.csv") as f:
    csv_content = f.read()

results = manager.import_from_csv(csv_content)
print(f"✅ 成功: {results['success']}, ❌ 失败: {results['failed']}")
```

导入后，Nornir 和 SuzieQ 自动从 NetBox 同步新设备，无需手动更新配置文件。

---

## 12. 核心工具实现

### datetime_tool.py - 时间解析工具
    period: 60
    
    # 传输协议
    transport: ssh
    
    # 设备认证（从 NetBox Custom Fields 读取，或使用默认值）
    username: "${DEVICE_USERNAME}"
    password: "${DEVICE_PASSWORD}"
```

#### SuzieQ 启动配置

在 `docker-compose.yml` 中挂载生成的配置：

```yaml
suzieq:
  image: netenglabs/suzieq:latest
  volumes:
    - ./data/suzieq-parquet:/suzieq/parquet
    - ./data/generated_configs:/suzieq/config:ro
  depends_on:
    olav-init:
      condition: service_completed_successfully
```

**优势**: 配置由 ETL 管道自动生成，消除手工维护和环境变量替换的复杂性。

### CSV 批量导入设备

使用 `InventoryManager` 将 CSV 设备清单导入 NetBox：

```python
# 示例使用
from olav.core.inventory_manager import InventoryManager

manager = InventoryManager()
with open("config/inventory_template.csv") as f:
    csv_content = f.read()

results = manager.import_from_csv(csv_content)
print(f"✅ 成功: {results['success']}, ❌ 失败: {results['failed']}")
```

导入后，Nornir 和 SuzieQ 自动从 NetBox 同步新设备，无需手动更新配置文件。

---

## 12. 核心工具实现

### datetime_tool.py - 时间解析工具

```python
# src/olav/tools/datetime_tool.py
from datetime import datetime, timedelta
from typing import Tuple
from langchain.tools import tool

@tool
def parse_time_range(natural_text: str, timezone: str = "UTC") -> Tuple[str, str]:
    """
    将自然语言时间描述转换为时间戳范围
    
    Args:
        natural_text: 自然语言时间描述，如 "昨晚", "过去2小时", "上周五"
        timezone: 时区，默认 UTC
    
    Returns:
        (start_time, end_time) ISO 8601 格式字符串
    
    Examples:
        >>> parse_time_range("昨晚")
        ('2025-11-20T18:00:00Z', '2025-11-21T06:00:00Z')
    """
    now = datetime.now()
    
    if "昨晚" in natural_text or "last night" in natural_text.lower():
        start = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0)
        end = now.replace(hour=6, minute=0, second=0)
    elif "过去" in natural_text and "小时" in natural_text:
        hours = int(''.join(filter(str.isdigit, natural_text)))
        start = now - timedelta(hours=hours)
        end = now
    elif "上周" in natural_text:
        start = now - timedelta(days=7)
        end = now - timedelta(days=1)
    else:
        # 默认过去24小时
        start = now - timedelta(days=1)
        end = now
    
    return start.isoformat() + 'Z', end.isoformat() + 'Z'
```

### suzieq_tool.py - Schema-Aware 设计（避免维护大量工具）

**设计原则**: 不为每个资源类型创建独立工具，而是让 LLM 通过 **SuzieQ Schema 索引** 动态查询可用的表和字段。

**架构**:
1. **Schema 索引化**: 将 SuzieQ 的所有 `.avsc` Schema 文件解析并存入 OpenSearch `suzieq-schema` 索引
2. **单一查询工具**: 提供一个通用的 `suzieq_query` 工具，接受 `table_name`, `method`, `filters` 参数
3. **Schema 检索工具**: 提供 `suzieq_schema_search` 工具，让 LLM 查询哪些表/字段可用

```python
# src/olav/tools/suzieq_tool.py
from suzieq.sqobjects import get_sqobject, get_tables
from suzieq.shared.context import SqContext
from suzieq.shared.schema import Schema
from suzieq.shared.utils import load_sq_config
from langchain.tools import tool
import pandas as pd
from typing import List, Dict, Literal

class SuzieQSchemaAwareTool:
    """Schema-Aware SuzieQ 工具，避免为每个资源创建独立工具"""
    
    def __init__(self, config_file: str = None):
        # 初始化 SuzieQ Context
        cfg = load_sq_config(validate=True, config_file=config_file)
        self.ctxt = SqContext(cfg=cfg, engine='pandas')
        
        # 加载 Schema（用于元数据查询）
        self.schema = Schema(cfg['schema-directory'])
    
    @tool
    def suzieq_query(
        self,
        table: str,
        method: Literal['get', 'summarize', 'unique', 'aver'] = 'get',
        **filters
    ) -> pd.DataFrame:
        """
        通用 SuzieQ 查询工具（Schema-Aware）
        
        使用前建议先调用 suzieq_schema_search 查询可用的表和字段。
        
        Args:
            table: 表名，如 'interfaces', 'bgp', 'routes' 等
                  可用表列表：通过 suzieq_schema_search(query='list all tables') 获取
            method: 查询方法
                - 'get': 获取原始数据（支持时间范围、过滤器）
                - 'summarize': 聚合统计
                - 'unique': 去重查询
                - 'aver': 平均值统计
            **filters: 过滤条件，常用参数：
                - hostname: 设备名（支持通配符）
                - namespace: 命名空间列表
                - start_time: 开始时间（ISO 8601）
                - end_time: 结束时间（ISO 8601）
                - columns: 返回字段列表（['default'] 或 ['all'] 或具体字段名）
                - view: 'latest'（最新）/ 'all'（时间序列）/ 'changes'（变化记录）
                - 其他表特定字段（如 state, vrf, peer 等）
        
        Returns:
            Pandas DataFrame
        
        Examples:
            # 查询接口状态
            >>> suzieq_query(
                    table='interfaces',
                    method='get',
                    hostname='R1',
                    state='down',
                    columns=['ifname', 'state', 'reason']
                )
            
            # 查询 BGP 会话摘要
            >>> suzieq_query(table='bgp', method='summarize', namespace=['prod'])
            
            # 查询唯一路由前缀
            >>> suzieq_query(table='routes', method='unique', columns=['prefix'])
        """
        # 动态获取 SqObject
        sq_obj = get_sqobject(table)(context=self.ctxt)
        
        # 调用对应方法
        if method == 'get':
            return sq_obj.get(**filters)
        elif method == 'summarize':
            return sq_obj.summarize(**filters)
        elif method == 'unique':
            return sq_obj.unique(**filters)
        elif method == 'aver':
            return sq_obj.aver(**filters)
        else:
            raise ValueError(f"Unsupported method: {method}")
    
    @tool
    def suzieq_schema_search(self, query: str) -> Dict:
        """
        查询 SuzieQ Schema 信息（检索可用的表和字段）
        
        这是一个 Schema-Aware 工具，用于查询：
        - 哪些表（table）可用？
        - 某个表有哪些字段（fields）？
        - 某个字段的类型和描述是什么？
        
        Args:
            query: 自然语言查询，例如：
                - "list all tables"
                - "show fields for interfaces table"
                - "what fields are available for bgp table"
                - "show key fields for routes table"
        
        Returns:
            Dict with schema information
        
        Examples:
            >>> suzieq_schema_search("list all tables")
            {
                "tables": ["interfaces", "bgp", "routes", "ospf", ...],
                "total": 30
            }
            
            >>> suzieq_schema_search("show fields for interfaces table")
            {
                "table": "interfaces",
                "fields": [
                    {"name": "ifname", "type": "string", "description": "...", "key": 3},
                    {"name": "state", "type": "string", "description": "..."},
                    ...
                ],
                "key_fields": ["namespace", "hostname", "ifname"],
                "display_fields": ["namespace", "hostname", "ifname", "state", "type"]
            }
        """
        # 解析 query 意图
        query_lower = query.lower()
        
        if 'list' in query_lower and 'table' in query_lower:
            # 返回所有表
            tables = self.schema.tables()
            return {
                "tables": sorted(tables),
                "total": len(tables),
                "note": "Use 'suzieq_query(table=TABLE_NAME, ...)' to query these tables"
            }
        
        # 提取表名
        for table in self.schema.tables():
            if table in query_lower:
                # 返回表的字段信息
                fields = self.schema.get_raw_schema(table)
                key_fields = self.schema.key_fields_for_table(table)
                display_fields = self.schema.sorted_display_fields_for_table(table)
                
                return {
                    "table": table,
                    "fields": [
                        {
                            "name": f['name'],
                            "type": self._simplify_type(f['type']),
                            "description": f.get('description', ''),
                            "key": f.get('key'),
                            "display": f.get('display')
                        }
                        for f in fields
                        if not f.get('suppress', False)
                    ],
                    "key_fields": key_fields,
                    "display_fields": display_fields,
                    "note": f"Key fields identify unique records. Display fields are shown by default."
                }
        
        # 默认返回表列表
        return {
            "error": "Could not parse query. Try 'list all tables' or 'show fields for TABLE_NAME table'",
            "available_tables": self.schema.tables()[:10]  # 前10个作为提示
        }
    
    def _simplify_type(self, type_def):
        """简化复杂类型定义为字符串"""
        if isinstance(type_def, str):
            return type_def
        elif isinstance(type_def, dict):
            if type_def.get('type') == 'array':
                item_type = type_def.get('items', {}).get('type', 'unknown')
                return f"array<{item_type}>"
            return type_def.get('type', 'complex')
        return 'unknown'
```

**核心优势**:
1. **零工具维护**: 不需要为每个资源（interface/bgp/route）创建工具
2. **自描述**: LLM 可以动态查询可用的表和字段
3. **灵活性**: 新增 SuzieQ 表时自动支持，无需修改代码
4. **只读安全**: SuzieQ 只查询 Parquet 历史数据，**无副作用，不需要沙盒隔离**

**与 Nornir 的对比**:
| 维度 | SuzieQ (Macro Agent) | Nornir (Micro Agent) |
|------|---------------------|---------------------|
| **操作类型** | 只读查询（Parquet 数据） | 读写操作（NETCONF/gNMI） |
| **是否需要沙盒** | ❌ 否（无副作用） | ✅ 是（NornirSandbox + HITL） |
| **Schema 来源** | Avro Schema (.avsc) | YANG Models |
| **查询方式** | `suzieq_query(table, method, filters)` | `nornir_tool(device, xpath, operation)` |
| **安全风险** | 无风险（只读） | 高风险（可修改设备配置） |

---

## 13. ETL 流程详解 (初始化流程)

**统一初始化容器**: `olav-init` 容器在启动时依次执行三个初始化流程：

1. **PostgreSQL 初始化** (`init_postgres.py`): 创建 Checkpointer 表结构
2. **OpenConfig Schema ETL** (`init_schema.py`): 解析 YANG 模型 → `openconfig-schema` 索引
3. **SuzieQ Schema ETL** (`suzieq_schema_etl.py`): 解析 Avro Schema → `suzieq-schema` 索引

### PostgreSQL Checkpointer 初始化 (init_postgres.py)

**功能**: 创建 LangGraph Checkpointer 所需的表结构。

```python
# src/olav/etl/init_postgres.py
from langgraph.checkpoint.postgres import PostgresSaver
import os
import logging

logger = logging.getLogger(__name__)

def init_postgres_checkpointer():
    """初始化 PostgreSQL Checkpointer 表结构"""
    postgres_uri = os.getenv(
        "POSTGRES_URI",
        "postgresql://olav:OlavPG123!@postgres:5432/olav"
    )
    
    logger.info(f"Initializing PostgreSQL Checkpointer: {postgres_uri}")
    
    with PostgresSaver.from_conn_string(postgres_uri) as checkpointer:
        checkpointer.setup()
        logger.info("✅ Checkpointer tables created successfully")
        logger.info("   - checkpoints")
        logger.info("   - checkpoint_writes")
        logger.info("   - checkpoint_migrations")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_postgres_checkpointer()
```

**创建的表**:
- `checkpoints`: 存储 Agent State 快照
- `checkpoint_writes`: 存储待写入的 State 更新
- `checkpoint_migrations`: 跟踪 Schema 版本

### SuzieQ Schema 索引化 (suzieq_schema_etl.py)

**职责**: 将 SuzieQ 的所有 Schema 定义解析并存入 OpenSearch，供 LLM 动态查询。

```python
# src/olav/etl/suzieq_schema_etl.py
import json
from pathlib import Path
from suzieq.shared.schema import Schema
from suzieq.shared.utils import load_sq_config
from olav.tools.opensearch_tool import OpenSearchTool

def index_suzieq_schemas():
    """
    将 SuzieQ Schema 索引化到 OpenSearch
    
    创建索引: suzieq-schema
    文档结构:
    {
        "table": "interfaces",
        "fields": [
            {
                "name": "ifname",
                "type": "string",
                "description": "Interface name",
                "key": 3,
                "display": 3
            },
            ...
        ],
        "key_fields": ["namespace", "hostname", "ifname"],
        "display_fields": ["namespace", "hostname", "ifname", "state", "type"],
        "table_type": "record"  # counter/record/derived
    }
    """
    print("=== Starting SuzieQ Schema ETL ===")
    
    # 1. 加载 SuzieQ Schema
    cfg = load_sq_config(validate=True)
    schema = Schema(cfg['schema-directory'])
    
    # 2. 解析所有表的 Schema
    documents = []
    for table in schema.tables():
        raw_schema = schema.get_raw_schema(table)
        
        # 提取字段信息
        fields = []
        for field in raw_schema:
            if field.get('suppress', False):
                continue  # 跳过内部字段
            
            fields.append({
                "name": field['name'],
                "type": _simplify_type(field['type']),
                "description": field.get('description', ''),
                "key": field.get('key'),
                "display": field.get('display'),
                "partition": field.get('partition')
            })
        
        # 构建文档
        doc = {
            "table": table,
            "fields": fields,
            "key_fields": schema.key_fields_for_table(table),
            "display_fields": schema.sorted_display_fields_for_table(table),
            "table_type": schema.type_for_table(table),
            "field_count": len(fields)
        }
        documents.append(doc)
    
    # 3. 写入 OpenSearch
    os_tool = OpenSearchTool()
    os_tool.create_index(
        index_name="suzieq-schema",
        mappings={
            "properties": {
                "table": {"type": "keyword"},
                "fields": {
                    "type": "nested",
                    "properties": {
                        "name": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "description": {"type": "text"},
                        "key": {"type": "integer"},
                        "display": {"type": "integer"}
                    }
                },
                "key_fields": {"type": "keyword"},
                "display_fields": {"type": "keyword"},
                "table_type": {"type": "keyword"}
            }
        }
    )
    
    os_tool.bulk_index(
        index_name="suzieq-schema",
        documents=documents
    )
    
    print(f"✅ Indexed {len(documents)} SuzieQ table schemas")
    print(f"Available tables: {', '.join([d['table'] for d in documents])}")

def _simplify_type(type_def):
    """简化类型定义"""
    if isinstance(type_def, str):
        return type_def
    elif isinstance(type_def, dict):
        if type_def.get('type') == 'array':
            item_type = type_def.get('items', {}).get('type', 'unknown')
            return f"array<{item_type}>"
        return type_def.get('type', 'complex')
    return 'unknown'

if __name__ == "__main__":
    index_suzieq_schemas()
```

### NTC-Templates Schema 索引化 (ntc_schema_etl.py)

**职责**: 解析 NTC-Templates 的 TextFSM 模板，提取命令元数据并索引到 OpenSearch，支持 CLI 降级模式。

**设计要点**:
1. **轻量级解析**: 仅提取模板头部 `Value` 定义（字段名和类型），不使用完整 pyang 解析器
2. **语义映射**: 将命令映射到常见运维意图（"接口状态" → "show interfaces"）
3. **黑名单过滤**: 排除危险命令（reload, traceroute）

```python
# src/olav/etl/ntc_schema_etl.py
import re
from pathlib import Path
from typing import List, Dict, Optional
from opensearchpy import OpenSearch, helpers
import os

# 正则提取 TextFSM 模板中的字段定义
VALUE_RE = re.compile(r'^Value\s+(?P<name>\w+)\s+\((?P<regex>.+?)\)', re.MULTILINE)

# 语义映射表（命令 → 运维意图）
SEMANTIC_MAP = {
    "show interfaces": ["接口状态", "interface status", "port info", "link state"],
    "show ip route": ["路由表", "routing table", "ip routes"],
    "show ip bgp summary": ["BGP 邻居", "bgp neighbors", "bgp peers"],
    "show version": ["设备版本", "device version", "system info"],
    "show running-config": ["运行配置", "running config", "current config"],
    "show inventory": ["硬件清单", "hardware inventory", "chassis info"],
}

# 危险命令黑名单
BLACKLIST = {"reload", "traceroute", "write erase", "format", "delete"}

class NTCSchemaETL:
    def __init__(self, templates_dir: str = "archive/ntc-templates/ntc_templates/templates"):
        self.templates_dir = Path(templates_dir)
        self.client = OpenSearch(
            hosts=[os.getenv("OPENSEARCH_URL", "http://localhost:9200")],
            http_auth=None,
            use_ssl=False,
            verify_certs=False
        )
        self.index_name = "ntc-schema"
    
    def parse_template_metadata(self, template_path: Path) -> Optional[Dict]:
        """解析 TextFSM 模板头部，提取字段定义"""
        # ... (实现略，提取 Value 定义)
    
    def extract_command_from_filename(self, filename: str) -> Optional[str]:
        """从模板文件名提取命令"""
        # ... (实现略)
    
    def index_templates(self):
        """索引所有 NTC-Templates 到 OpenSearch ntc-schema 索引"""
        # ... (实现略)
```

**索引文档结构**:
```json
{
    "platform": "cisco_ios",
    "command": "show interfaces",
    "parser": "cisco_ios_show_interfaces.textfsm",
    "fields": ["interface", "link_status", "protocol", "mtu", "bandwidth"],
    "field_types": {"interface": "string", "link_status": "enum", "protocol": "enum"},
    "field_count": 5,
    "semantic_tags": ["接口状态", "interface status", "port info"],
    "template_path": "templates/cisco_ios_show_interfaces.textfsm",
    "is_read_only": true,
    "is_dangerous": false
}
```

**与 baseline_collector.py 的对比**:

| 功能 | baseline_collector | ntc_schema_etl (OLAV) |
|------|-------------------|----------------|
| 模板扫描 | ✅ .backup.textfsm | ✅ 所有 .textfsm |
| 字段提取 | ✅ TextFSM 解析 | ✅ 正则提取 Value |
| 命令黑名单 | ✅ command_blacklist.txt | ✅ 内置 BLACKLIST |
| 自动执行 | ✅ Nornir 批量执行 | ❌ 仅索引元数据 |
| 配置备份 | ✅ backups/ 目录 | ❌ 不执行备份 |
| Gitea 集成 | ✅ Git 版本控制 | ❌ OpenSearch |
| 语义搜索 | ❌ 无 | ✅ semantic_tags |
| Schema 索引 | ❌ 无 | ✅ ntc-schema |

**OLAV 采用的设计**:
- ✅ **只索引 Schema**: 不执行命令，仅提供元数据给 LLM
- ✅ **语义搜索**: 支持自然语言查询 ("接口状态" → "show interfaces")
- ✅ **安全标记**: `is_read_only`, `is_dangerous` 字段辅助决策
- ❌ **不做备份**: 备份任务由专用工具（baseline_collector）或定时任务处理

---

### YANG 模型转换 (init_schema.py)

```python
# src/olav/etl/init_schema.py
import git
import os
from pathlib import Path
from config.settings import settings
from olav.etl.yang_parser import YANGParser
from olav.tools.opensearch_tool import OpenSearchTool

def clone_openconfig_repo():
    """克隆 OpenConfig 仓库"""
    repo_dir = Path("/tmp/openconfig")
    
    if repo_dir.exists():
        print("OpenConfig repo already exists, pulling latest...")
        repo = git.Repo(repo_dir)
        repo.remotes.origin.pull()
    else:
        print(f"Cloning {settings.OPENCONFIG_REPO_URL}...")
        git.Repo.clone_from(
            settings.OPENCONFIG_REPO_URL,
            repo_dir,
            branch=settings.OPENCONFIG_REPO_BRANCH
        )
    
    return repo_dir

def main():
    """Schema ETL 主流程"""
    print("=== Starting OpenConfig Schema ETL ===")
    
    # 1. 克隆仓库
    repo_dir = clone_openconfig_repo()
    
    # 2. 解析 YANG 模型
    parser = YANGParser()
    yang_files = list(repo_dir.glob("release/models/**/*.yang"))
    
    print(f"Found {len(yang_files)} YANG files")
    
    schemas = []
    for yang_file in yang_files:
        try:
            schema_data = parser.parse(yang_file)
            schemas.extend(schema_data)
        except Exception as e:
            print(f"Error parsing {yang_file}: {e}")
    
    # 3. 写入 OpenSearch
    os_tool = OpenSearchTool()
    os_tool.bulk_index(
        index_name="openconfig-schema",
        documents=schemas
    )
    
    print(f"✅ Indexed {len(schemas)} schema entries")

if __name__ == "__main__":
    main()
```

### YANG 解析器 (yang_parser.py)

```python
# src/olav/etl/yang_parser.py
from pyang import repository, context
from pyang.statements import Statement
from typing import List, Dict

class YANGParser:
    def parse(self, yang_file: Path) -> List[Dict]:
        """
        解析 YANG 文件并提取可检索的 XPath
        
        Returns:
            [
                {
                    "xpath": "/interfaces/interface/state/counters/in-errors",
                    "module": "openconfig-interfaces",
                    "type": "uint64",
                    "description": "Number of input errors"
                },
                ...
            ]
        """
        repos = repository.FileRepository(str(yang_file.parent))
        ctx = context.Context(repos)
        
        with open(yang_file) as f:
            module = ctx.add_module(yang_file.name, f.read())
        
        if module is None:
            raise ValueError(f"Failed to parse {yang_file}")
        
        schemas = []
        self._extract_paths(module, "", schemas)
        return schemas
    
    def _extract_paths(self, stmt: Statement, path: str, schemas: List[Dict]):
        """递归提取 XPath"""
        if stmt.keyword in ['container', 'list', 'leaf', 'leaf-list']:
            current_path = f"{path}/{stmt.arg}"
            
            if stmt.keyword in ['leaf', 'leaf-list']:
                schemas.append({
                    "xpath": current_path,
                    "module": stmt.top.arg,
                    "type": stmt.search_one('type').arg if stmt.search_one('type') else None,
                    "description": stmt.search_one('description').arg if stmt.search_one('description') else ""
                })
            
            for child in stmt.substmts:
                self._extract_paths(child, current_path, schemas)
```

---

## 14. Learner Agent 向量化存储

```python
# src/olav/agents/learner_agent.py
from langchain.schema import Document
from olav.core.llm import LLMFactory
from olav.tools.opensearch_tool import OpenSearchTool

class LearnerAgent:
    def __init__(self):
        self.embedding_model = LLMFactory.get_embedding_model()
        self.os_tool = OpenSearchTool()
    
    def store_episode(
        self,
        user_intent: str,
        solution: str,
        device: str,
        success: bool = True
    ):
        """
        向量化存储成功的故障诊断经验
        
        Args:
            user_intent: 用户原始问题
            solution: 解决方案（包含 XPath、命令等）
            device: 设备名称
            success: 是否成功解决
        """
        if not success:
            return  # 只存储成功案例
        
        # 构建文档
        doc = Document(
            page_content=f"问题: {user_intent}\n解决方案: {solution}",
            metadata={
                "device": device,
                "intent": user_intent,
                "solution": solution,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # 生成向量
        embedding = self.embedding_model.embed_query(doc.page_content)
        
        # 存储到 OpenSearch
        self.os_tool.index_document(
            index_name="olav-episodic-memory",
            document={
                "content": doc.page_content,
                "embedding": embedding,
                **doc.metadata
            }
        )
        
        print(f"✅ Stored episode to memory: {user_intent[:50]}...")
```

---

## 15. Prompt 管理系统 (LangChain Prompt Templates)

**设计原则**: 所有 Prompt 使用 **配置文件** 管理，避免硬编码在 Python 代码中。

### Prompt 目录结构

```
config/prompts/
├── agents/              # Agent System Prompts
│   ├── root_agent.yaml
│   ├── rag_agent.yaml
│   ├── suzieq_agent.yaml
│   └── netconf_agent.yaml
├── tools/               # Tool Descriptions  
│   ├── nornir_tool.yaml
│   ├── suzieq_query.yaml
│   └── opensearch_tool.yaml
└── rag/                 # RAG Query Templates
    ├── schema_search.yaml
    ├── memory_search.yaml
    └── docs_search.yaml
```

### Prompt 模板示例

**Agent System Prompt** (`config/prompts/agents/root_agent.yaml`):
```yaml
_type: prompt
input_variables:
  - user_name
  - network_context
template: |
  你是企业网络运维专家 OLAV (OpenConfig LLM-Assisted Validator)。
  
  当前操作员: {user_name}
  网络上下文: {network_context}
  
  工作流程:
  1. 使用 rag_agent 检索 Schema/Docs/Memory
  2. 使用 suzieq_agent 进行宏观历史分析
  3. 使用 netconf_agent 执行实时诊断和配置变更
  
  核心原则:
  - 配置变更必须经过 HITL 审批
  - 优先使用 OpenConfig 标准化路径
  - 所有操作记录审计日志
  - 不确定时主动询问用户
```

**Tool Description** (`config/prompts/tools/suzieq_query.yaml`):
```yaml
_type: prompt
input_variables:
  - available_tables
  - example_usage
template: |
  Query SuzieQ historical network data using schema-aware approach.
  
  Available Tables: {available_tables}
  
  Parameters:
    - table: Table name (e.g., 'interfaces', 'bgp', 'routes')
    - method: Query method ('get', 'summarize', 'unique', 'aver')
    - filters: Dict of field filters (e.g., hostname='router1', state='up')
  
  Example Usage:
  {example_usage}
  
  Note: This is a READ-ONLY tool. All data is queried from Parquet files.
```

**自定义中间件**:
```python
# src/olav/agents/middleware/network_context.py
from langchain.agents.middleware import AgentMiddleware

class NetworkContextMiddleware(AgentMiddleware):
    """注入网络上下文（拓扑、设备状态）到每个请求"""
    
    async def on_model_request(self, request: ModelRequest, state: AgentState):
        # 从 NetBox 获取拓扑信息
        topology = await self.get_topology_context(state.get('device'))
        request.messages.insert(0, SystemMessage(content=f"Network Context: {topology}"))
        return request
```

### Prompt 加载器实现

**Prompt Manager** (`src/olav/core/prompt_manager.py`):
```python
from pathlib import Path
from langchain.prompts import load_prompt
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    """统一 Prompt 管理器，使用 LangChain PromptTemplate"""
    
    def __init__(self, prompts_dir: Path = None):
        self.prompts_dir = prompts_dir or Path("config/prompts")
        self._cache: Dict[str, Any] = {}
    
    def load_prompt(self, category: str, name: str, **kwargs) -> str:
        """
        加载并渲染 Prompt 模板
        
        Args:
            category: 'agents', 'tools', 'rag'
            name: prompt 文件名（无扩展名）
            **kwargs: 模板变量
        
        Returns:
            渲染后的 Prompt 字符串
        """
        cache_key = f"{category}/{name}"
        
        if cache_key not in self._cache:
            prompt_path = self.prompts_dir / category / f"{name}.yaml"
            
            if not prompt_path.exists():
                raise FileNotFoundError(f"Prompt not found: {prompt_path}")
            
            # 使用 LangChain 的 load_prompt
            self._cache[cache_key] = load_prompt(str(prompt_path))
            logger.info(f"Loaded prompt: {cache_key}")
        
        template = self._cache[cache_key]
        return template.format(**kwargs)
    
    def load_agent_prompt(self, agent_name: str, **context) -> str:
        """快捷方法：加载 Agent System Prompt"""
        return self.load_prompt("agents", agent_name, **context)
    
    def reload(self):
        """清空缓存，重新加载所有 Prompts（用于开发调试）"""
        self._cache.clear()

# 全局单例
prompt_manager = PromptManager()
```

### 使用示例

**在 Agent 中使用**:
```python
# src/olav/agents/root_agent.py
from olav.core.prompt_manager import prompt_manager
from deepagents import create_deep_agent

# 加载 System Prompt（支持动态变量注入）
system_prompt = prompt_manager.load_agent_prompt(
    "root_agent",
    user_name=current_user.name,
    network_context=get_network_context()
)

agent = create_deep_agent(
    model=model,
    system_prompt=system_prompt,  # 从配置文件加载
    subagents=[...],
)
```

**在 Tool 中使用**:
```python
# src/olav/tools/suzieq_tool.py
from olav.core.prompt_manager import prompt_manager

# 动态加载 Tool Description
available_tables = schema.tables()
tool_description = prompt_manager.load_tool_description(
    "suzieq_query",
    available_tables=", ".join(available_tables),
    example_usage="suzieq_query(table='bgp', method='summarize')"
)

suzieq_query_tool = StructuredTool.from_function(
    name="suzieq_query",
    func=suzieq_query,
    description=tool_description  # 从配置文件加载
)
```

### 优势总结

| 特性 | 传统硬编码 | LangChain Prompt 管理 |
|------|-----------|----------------------|
| **可维护性** | 代码中修改 Prompt | 配置文件中修改 |
| **版本控制** | 混杂在代码中 | 独立 YAML 文件 |
| **动态注入** | 手动字符串拼接 | PromptTemplate 自动渲染 |
| **多语言支持** | 需要重写代码 | 切换配置文件 |
| **A/B 测试** | 困难 | 轻松切换不同版本 |
| **热更新** | 需重启服务 | `prompt_manager.reload()` |

---

## 16. 架构优化建议（基于源码分析）

基于对 **DeepAgents**, **LangChain V1**, **LangGraph**, **SuzieQ** 源代码的分析，以下是关键架构改进建议：

### 15.1 直接使用 DeepAgents 框架

**发现**: DeepAgents 已经实现了 OLAV 需要的核心能力：
*   **TodoListMiddleware**: 自动任务分解与跟踪
*   **SubAgentMiddleware**: 子代理委托机制
*   **HumanInTheLoopMiddleware**: HITL 审批流程
*   **SummarizationMiddleware**: 长对话自动摘要
*   **FilesystemMiddleware**: 文件系统操作（可适配为配置文件读写）

**建议**:
```python
# 直接使用 create_deep_agent 而非自己实现
from deepagents import create_deep_agent, SubAgent

# 不需要自己写 root_agent.py 的 LangGraph 编排
# DeepAgents 已内置 TodoList, Subagent, HITL 机制
agent = create_deep_agent(
    model=LLMFactory.get_chat_model(),
    system_prompt="""你是企业网络运维专家 OLAV。
    
工作流程:
1. 使用 rag_agent 检索 Schema/Docs/Memory
2. 使用 suzieq_agent 进行宏观历史分析
3. 使用 netconf_agent 进行实时微观诊断
4. 所有 Write 操作必须等待人工批准
""",
    subagents=[suzieq_subagent, rag_subagent, netconf_subagent],
    middleware=[
        NetworkContextMiddleware(),  # 自定义中间件
    ],
    checkpointer=RedisCheckpointer(settings.REDIS_URL),
    interrupt_on={
        "nornir_tool": {"allowed_decisions": ["approve", "edit", "reject"]}
    }
).with_config({"recursion_limit": 1000})
```

**优势**:
- 减少 500+ 行自定义 LangGraph 编排代码
- 内置 `recursion_limit=1000` 支持深度任务
- 自动集成 Anthropic Prompt Caching
- 社区维护，持续更新

### 15.2 利用 SuzieQ 原生 SqObject API

**发现**: SuzieQ 使用插件模式，所有查询通过 `get_sqobject()` 工厂函数返回标准化对象：

```python
from suzieq.sqobjects import get_sqobject

# 支持 30+ 种网络资源类型
iface_obj = get_sqobject('interface')  # InterfaceObj
bgp_obj = get_sqobject('bgp')          # BgpObj
route_obj = get_sqobject('routes')     # RouteObj

# 所有对象统一 API

df = iface_obj.get(hostname='R1', start_time=t1, end_time=t2)
summary = bgp_obj.summarize(namespace='prod')
unique = route_obj.unique(columns=['prefix'])
```

**建议**:
*   **不需要** 封装 `suzieq_tool.py` 为单独的工具
*   直接使用 `SqObject` 的 `get()`, `summarize()`, `unique()` 方法
*   LLM 可以直接学会 SuzieQ 的 标准 API（简化 Prompt）

### 15.3 采用 LangGraph Checkpointer 模式

**发现**: LangGraph 有完善的 Checkpoint 体系：
*   `checkpoint-postgres`: PostgreSQL 持久化
*   `checkpoint-sqlite`: SQLite 本地存储
*   `langgraph.checkpoint.memory.MemorySaver`: 内存模式（测试）

**当前设计问题**: 直接使用 Redis 存储 State，未遵循 LangGraph 的 Checkpointer 协议。

**建议**:
```python
from langgraph.checkpoint.postgres import PostgresSaver

# 使用标准 Checkpointer
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@postgres:5432/olav"
)

agent = create_deep_agent(
    ...,
    checkpointer=checkpointer  # 自动持久化状态
)

# 支持断点续传
config = {"configurable": {"thread_id": "user-123"}}
result = agent.invoke({"messages": [...]}, config=config)
```

### 15.4 Backend 协议层（借鉴 DeepAgents）

**发现**: DeepAgents 定义了清晰的 Backend 协议栏：
*   `BackendProtocol`: 基础 CRUD
*   `SandboxBackendProtocol`: 支持命令执行
*   `StoreBackendProtocol`: 持久化存储

**OLAV 应用**:
```python
# src/olav/execution/backends/nornir_sandbox.py
from deepagents.backends.protocol import SandboxBackendProtocol

class NornirSandbox(SandboxBackendProtocol):
    async def execute(self, command: str, background: bool = False):
        # 实现 NETCONF 执行逻辑
        pass

# 使用
agent = create_deep_agent(
    backend=lambda rt: NornirSandbox(rt),
    ...
)
```

### 15.5 中间件扩展模式

**发现**: LangChain V1 中间件支持 30+ 种内置类型：
*   `tool_retry.py`: 工具调用重试
*   `model_fallback.py`: LLM 降级机制
*   `pii.py`: PII 数据编码
*   `summarization.py`: 对话摘要

**OLAV 自定义中间件**:
```python
# src/olav/agents/middleware/network_context.py
from langchain.agents.middleware import AgentMiddleware

class NetworkContextMiddleware(AgentMiddleware):
    """NetBox 上下文注入"""
    
    async def on_model_request(self, request, state):
        # 从 NetBox 获取拓扑信息
        device = state.get('device_name')
        if device:
            topology = await self.netbox.get_topology(device)
            request.messages.insert(0, 
                SystemMessage(content=f"Network Context: {topology}")
            )
        return request
```

### 15.6 依赖包调整

**当前 `pyproject.toml` 补充**:
```toml
[tool.uv.dependencies]
# 核心框架
deepagents = "^0.2.0"              # 替代自己实现的 LangGraph 编排
langchain = "^0.3.20"             # LangChain V1 中间件支持
langgraph = "^0.2.65"             # StateGraph 基础
langgraph-checkpoint-postgres = "^1.0.0"  # Checkpoint 持久化

# LLM Providers
langchain-openai = "^0.3.0"
langchain-anthropic = "^0.3.0"
langchain-ollama = "^0.2.0"

# 网络工具
suzieq = "^0.23.0"                # 使用原生 API
nornir = "^3.4.0"
nornir-netbox = "^1.1.0"         # NetBox 插件
nornir-scrapli = "^2024.1.30"    # NETCONF 连接

# 向量数据库
opensearch-py = "^2.7.1"

# Web 框架
fastapi = "^0.115.0"
uvicorn = "^0.32.0"

# CLI
typer = "^0.15.0"
rich = "^13.9.0"
```

### 15.7 架构调整清单

**需要删除/简化的模块**:
- ☐ `src/olav/core/graph.py` → 用 `create_deep_agent()` 替代
- ☐ `src/olav/agents/root_agent.py` → 简化为 SubAgent 配置文件
- ☐ 自己实现的 TodoList 逻辑 → 使用 `TodoListMiddleware`

**需要新增的模块**:
- ☑ `src/olav/agents/middleware/network_context.py`
- ☑ `src/olav/execution/backends/protocol.py`
- ☑ `src/olav/execution/backends/nornir_sandbox.py`

**配置文件调整**:
```yaml
# config/agents.yml - SubAgent 配置
subagents:
  - name: suzieq-analyzer
    description: 查询历史网络数据和趋势分析
    prompt: |
      你是网络可观测性专家，使用 SuzieQ API 分析历史数据。
      
      可用 API:
      - get_sqobject('interface').get(hostname, start_time, end_time)
      - get_sqobject('bgp').summarize(namespace)
      - get_sqobject('routes').unique(columns=['prefix'])
    tools:
      - suzieq_toolkit
      - datetime_tool
  
  - name: knowledge-retriever
    description: 检索 OpenConfig Schema、文档和历史经验
    prompt: |
      执行智能知识检索：
      1. Memory 优先：查找历史成功案例
      2. Schema 回退：查询 OpenConfig XPath
      3. Docs 补充：搜索相关文档
    tools:
      - opensearch_tool
  
  - name: netconf-executor
    description: 执行 NETCONF/gNMI 实时设备操作
    prompt: 基于 OpenConfig Schema 构建 NETCONF Payload
    tools:
      - nornir_tool
    interrupt_on:
      nornir_tool:
        allowed_decisions: [approve, edit, reject]
    
  - name: netbox-manager
    description: 管理 NetBox 中的设备和站点信息
    prompt: |
      你是网络资产管理专家，负责维护 NetBox 中的设备和站点信息。
      
      所有操作必须确保依赖关系完整，如：
      - Site 必须存在
      - Manufacturer 必须存在
    tools:
      - netbox_schema_search
      - netbox_api_call
      - inventory_import
      - sync_configs
```

### 15.8 最终架构示意图

```mermaid
graph TD
    subgraph "User Interface"
        CLI[Rich CLI / Terminal] <-->|Stream/Input| App_Container
    end

    subgraph "OLAV Application (Main Brain)"
        App_Container[olav-app]
        LLM_Factory[LLM Factory] -->|Invoke| App_Container
        Supervisor[Supervisor Agent] -->|Route| Workers
        
        subgraph "Workers (Agents)"
            SuzieQ_Agent[Macro Agent]
            Netconf_Agent[Micro Agent]
            NetBox_Agent[SSOT Agent]
            Doc_Agent[Doc Agent]
            Learner_Agent[Reflection Node]
        end
    end

    subgraph "Infrastructure Services"
        Redis[(Redis)] <-->|State Persistence| App_Container
        OpenSearch[(OpenSearch)] <-->|Vector Search| App_Container
        SuzieQ_Service[SuzieQ Poller] -->|Parquet| Shared_Vol[Shared Volume]
    end

    subgraph "Support Containers"
        Init_Container[olav-init] -->|ETL Schema| OpenSearch
        Embedder_Service[olav-embedder] -->|Ingest PDF/Docs| OpenSearch
        Embedder_Service <-->|API Trigger| App_Container
    end

    subgraph "External World"
        NetBox[(NetBox Source of Truth)]
        Network_Devices[Switches/Routers]
        LLM_Provider[OpenAI/Ollama/Azure]
    end

    App_Container -->|Inventory| NetBox
    App_Container -->|Nornir Execution| Network_Devices
    NetBox_Agent -->|Manage| NetBox
```

**核心优势**:
- **代码量减少 60%**：不需要自己实现 LangGraph 编排、TodoList、HITL
- **标准化**：遵循 LangChain/LangGraph/DeepAgents 官方模式
- **可维护性**：社区驱动，持续更新
- **学习成本低**：开发者可直接查阅 DeepAgents 官方文档

*   **单元测试 (Unit Tests)**: 针对 Agent 逻辑和工具类。使用 `unittest.mock` 模拟 LLM 返回和网络设备响应。
*   **集成测试 (Integration Tests)**: 测试 OpenSearch 连接、NetBox API 调用。
*   **E2E 测试**: 在 Docker 环境中模拟完整对话流程（使用模拟设备或 Lab 环境）。
*   **工具链**: `pytest` (测试框架), `ruff` (代码风格检查)。
