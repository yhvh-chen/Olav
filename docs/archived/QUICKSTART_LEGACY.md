# OLAV 快速启动指南 (简化版)

面向首次部署，按顺序执行，避免遗漏。保持 `.env` 只存敏感变量，其它应用配置在 `config/settings.py`。

---
## 环境变量与配置（强制原则）

- `.env`：仅放置敏感信息与环境特定变量（Secrets + Docker 必需变量）
  - 保留：`LLM_API_KEY`、`NETBOX_TOKEN`、`DEVICE_USERNAME`、`DEVICE_PASSWORD`
  - 需要时：`NETBOX_URL`（外部 NetBox 时）、`POSTGRES_URI`/`OPENSEARCH_URL`/`REDIS_URL`（自定义主机时）
  - 不必放：`LLM_PROVIDER`、`LLM_MODEL_NAME`、默认端口/主机等非敏感项（这些在 `config/settings.py`）
- `config/settings.py`：非敏感默认值与应用级开关（LLM/工具/索引/日志等）
- 参照：`.env.example` 为最小示例，优先使用 settings 默认，必要时再在 `.env` 覆盖。

快速开始：
```bash
cp .env.example .env
# 编辑 .env 仅填写密钥与必要端点
# 必填：LLM_API_KEY、（使用 NetBox 时）NETBOX_TOKEN
```

注意：`config/settings.py` 会自动判断本地/容器环境并生成默认端点，未设置的 URI 会自动推导，无需在 .env 冗余填写。

---
## 1. 安装与准备
```bash
# 安装 uv（Linux/Mac）
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows 已用 venv，可选: pip install uv

# 克隆仓库
git clone <repo-url>
cd Olav

# 安装依赖（含开发工具）
uv sync --dev

# 复制环境文件并编辑敏感变量
cp .env.example .env
# 必改：LLM_API_KEY / NETBOX_TOKEN（若使用 NetBox 集成）
```

---
## 2. 准备设备清单 (NetBox Bootstrap)
编辑 `config/inventory.csv`（示例字段）：
```csv
name,device_role,device_type,platform,site,status,mgmt_interface,mgmt_address
R1,core,cisco-catalyst-9300,cisco_ios,HQ,active,GigabitEthernet0/0,192.168.100.101/24
R2,core,cisco-catalyst-9300,cisco_ios,HQ,active,GigabitEthernet0/0,192.168.100.102/24
SW1,access,cisco-2960,cisco_ios,Branch,active,Vlan1,192.168.100.105/24
```

**重要说明**:
- **首次部署**: 如果 NetBox 为空，`scripts/netbox_ingest.py` 会自动导入此 CSV 作为初始设备清单（**Bootstrap Mode**）
- **已有 NetBox**: 如果 NetBox 已有设备，脚本会自动跳过导入（**Skip Mode**），避免重复
- **强制导入**: 设置环境变量 `NETBOX_INGEST_FORCE=true` 可强制导入（**Force Mode**）

保证列名一致，IP 可 ping。

---
## 3. 一次性整体启动（含 NetBox 闸门）

OLAV 强制要求 NetBox 集成（作为 Source of Truth），但你可以选择是部署内置 NetBox 容器还是连接外部 NetBox。

### 选项 A: 部署内置 NetBox (推荐)
使用 `netbox` profile 启动所有服务：
```bash
docker-compose --profile netbox up -d
```
- 自动部署 NetBox, Postgres, Redis
- 使用 CLI 初始化基础设施（见下方步骤 4）

### 选项 B: 连接外部 NetBox
不使用 profile 启动，并在 `.env` 中配置外部地址：
```bash
# 1. 编辑 .env
# NETBOX_URL=http://your-external-netbox:8000
# NETBOX_TOKEN=your-token

# 2. 启动 (不带 netbox profile)
docker-compose up -d
```

---
## 4. 初始化基础设施

**使用 CLI 进行初始化**（推荐，替代原 Docker init 容器）：

```bash
# 查看当前索引状态
uv run python cli.py --init --status

# 基础初始化（PostgreSQL + Schema 索引）
# 适用于：已有自己的 NetBox
uv run python cli.py --init

# 完整初始化（含 NetBox inventory 导入）
# 适用于：全新部署，NetBox 也是新的
uv run python cli.py --init --full

# 强制重建所有索引
uv run python cli.py --init --force
```

### 初始化模式对比

| 模式 | 命令 | PostgreSQL | Schema 索引 | 文档 RAG | 配置生成 | NetBox 导入 |
|------|------|------------|-------------|----------|----------|-------------|
| 基础 | `--init` | ✅ | ✅ | ❌ | ❌ | ❌ |
| 完整 | `--init --full` | ✅ | ✅ | ✅ | ✅ | ✅ |

**选择建议**：
- 已有 NetBox 数据 → 使用 `--init`
- 全新部署 → 使用 `--init --full`

### 4.1 Schema 索引控制（Force Reset）
OLAV 通过环境变量或命令行控制索引初始化行为：

```bash
# 查看当前索引状态
uv run python cli.py --init --status

# 强制重置所有索引（删除并重建）
uv run python cli.py --init --force

# 只重置特定索引（使用 ETL 模块）
uv run python -m olav.etl.init_all --openconfig --force
uv run python -m olav.etl.init_all --suzieq --force
uv run python -m olav.etl.init_all --netbox --force
uv run python -m olav.etl.init_all --episodic --force
```

**环境变量说明**：

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `OLAV_ETL_FORCE_RESET` | 强制重置所有索引 | `false` |
| `OLAV_ETL_FORCE_SUZIEQ` | 强制重置 suzieq-schema 索引 | `false` |
| `OLAV_ETL_FORCE_OPENCONFIG` | 强制重置 openconfig-schema 索引 | `false` |
| `OLAV_ETL_FORCE_NETBOX` | 强制重置 netbox-schema 索引 | `false` |
| `OLAV_ETL_FORCE_EPISODIC` | 强制重置 olav-episodic-memory 索引 | `false` |

### 4.2 验证初始化完成
```bash
# 查看索引状态
uv run python cli.py --init --status

# 验证 PostgreSQL 表
docker-compose exec postgres psql -U olav -d olav -c "\dt"

# 验证 OpenSearch 索引
curl -s http://localhost:19200/_cat/indices?v | grep -E "schema|episodic|docs"
```

---
## 5. 应用与嵌入服务日志
服务已在整体启动中自动拉起。
```bash
docker logs -n 50 olav-app
docker logs -n 50 olav-embedder
```
快速运行时健康确认：
```bash
docker-compose exec olav-app uv run python -c "from config.settings import settings, get_path; print('env=', settings.environment, 'data_dir=', get_path('suzieq_data'))"
```

---
## 6. 使用 OLAV 交互式对话（Agent 模式选择）

OLAV 提供 4 种 Agent 架构模式，可根据场景灵活切换：

| 模式 | 特点 | 适用场景 | 命令 |
|------|------|---------|------|
| **Remote** (默认) | 连接 API Server，支持分布式 | 生产环境 | `chat` |
| **Local** | 本地直接执行，无需 Server | 开发调试 | `chat -L` |
| **Expert** | Deep Dive Workflow，递归诊断 | 复杂诊断 | `chat -e` |
| **Local+Expert** | 本地 Expert 模式 | 离线复杂诊断 | `chat -L -e` |

### 6.1 启动交互式对话（推荐）
```bash
# 方案 A: CLI v2 对话工具（默认 Workflows 模式）
uv run olav                                          # 交互式 REPL（显示欢迎横幅 + 雪人）
uv run olav query "查询接口状态"                     # 单次查询
uv run olav query -e "审计所有边界路由器"            # Expert 模式（Deep Dive Workflow）
uv run olav dashboard                                # 全屏 TUI 仪表盘
uv run olav banner                                   # 显示 OLAV 彩色 Logo + 雪人

# 传统 CLI 命令（兼容旧版）
uv run python -m olav.main chat                     # 交互式对话（Remote 模式，连接 API Server）
uv run python -m olav.main chat -L                  # 交互式对话（Local 模式，直接执行）
uv run python -m olav.main chat "查询接口状态"        # 单次查询（Remote 模式）
uv run python -m olav.main chat -L "查询接口状态"    # 单次查询（Local 模式）
uv run python -m olav.main chat -e                  # Expert 模式（Deep Dive Workflow）
uv run python -m olav.main chat -L -e               # Expert 模式（Local 执行）

# 连接 Docker 中的 API Server（端口 8001）
uv run python -m olav.main chat --server "http://localhost:8001" "查询 R1 状态"

# 方案 B: LangChain Studio（推荐用于开发调试）
# 1. 启动 LangGraph Agent Server
uv add langgraph-cli[inmem]
langgraph dev

# 2. 浏览器访问 Studio
# https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

# 显示工具调用与推理链（调试模式）
uv run python -m olav.main chat --verbose           # 详细日志输出
uv run python -m olav.main chat -L --verbose        # Local 模式详细日志
uv run python -m olav.main chat -e --verbose        # Expert 模式详细日志
```

**执行模式详解**：

**Remote 模式（默认，推荐生产使用）**：
- ✅ 分布式架构：CLI Client → HTTP/WebSocket → API Server → Orchestrator
- ✅ 高可用：API Server 可独立部署、水平扩展
- ✅ 状态持久化：PostgreSQL Checkpointer 集成
- ✅ 适合团队协作：多用户共享同一 API Server
- 📝 本地 Server：`uv run python -m olav.main serve`（端口 8000）
- 📝 Docker Server：`docker-compose up -d olav-server`（端口 8001）

**Local 模式（开发调试）**：
- ✅ 单进程执行：CLI Client → 直接 Orchestrator（无需 Server）
- ✅ 快速启动：无需额外服务依赖
- ⚠️ 单用户：不支持分布式部署
- 📝 启动命令：`uv run python -m olav.main chat -L`

**Expert 模式（Deep Dive Workflow）**：
- ✅ 自动任务分解：复杂查询 → Todo List 生成
- ✅ 递归诊断：最多 3 层深入分析
- ✅ 批量审计：30+ 设备并行执行
- ✅ 进度恢复：Checkpointer 支持断点续传
- 📝 启动命令：`uv run python -m olav.main chat -e`

> **注意**：ReAct、Legacy、Structured、Simple agent 模式已弃用（2025-11-23）。  
> 详见 `archive/deprecated_agents/README.md`。

**方案对比**：

| 维度 | 自研 CLI | LangChain Studio |
|------|----------|------------------|
| **性能分析** | ❌ 无可视化工具 | ✅ **内置性能剖析**（节点耗时、LLM 延迟） |
| **调试能力** | ⚠️ 文本日志 + --verbose | ✅ **图可视化 + 断点调试** |
| **HITL 审批** | ⚠️ 需自己实现终端菜单 | ✅ **原生 UI 审批界面** |
| **用户体验** | ✅ 终端原生，快速启动 | ⚠️ 需浏览器，多一步跳转 |
| **生产部署** | ✅ 适合 SSH 远程运维 | ❌ 开发环境专用 |
| **离线使用** | ✅ 完全离线 | ⚠️ 需 LangSmith 连接（可设 `LANGSMITH_TRACING=false`） |
| **代码侵入性** | ⚠️ 需实现 CLI UI | ✅ **零代码改动** |

**推荐策略**：
- **开发调试阶段**：使用 **LangChain Studio**
  - ✅ 可视化性能瓶颈（LLM 调用、Checkpointer、SubAgent 委托）
  - ✅ 图形化调试工作流（查看 LangGraph 执行路径）
  - ✅ 内置 HITL 审批界面（无需自己实现终端菜单）
  - ✅ 实时监控 Thread 状态
- **生产运维阶段**：保留 **自研 CLI**
  - ✅ SSH 远程访问友好
  - ✅ 脚本自动化集成
  - ✅ 无需浏览器依赖

**性能分析优势**（Studio 特有）：
- **节点耗时追踪**：查看每个 SubAgent 的执行时间
- **LLM 调用统计**：Token 使用、API 延迟、并发情况
- **Checkpointer 写入监控**：识别频繁的 `aget_tuple()` / `aput()` 调用
- **内存使用分析**：State 大小、消息历史长度
- **瓶颈可视化**：红色高亮慢速节点

**实现建议**：
1. **立即启用 Studio**（用于性能排查）：
   ```bash
   # 安装 LangGraph CLI
   uv add langgraph-cli[inmem]
   
   # 启动开发服务器
   langgraph dev --debug-port 5678
   
   # 访问 Studio
   # https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
   ```

2. **保留自研 CLI**（用于生产运维）：
   - 添加简化的 Y/N 菜单（HITL）
   - 添加性能埋点（输出到日志）
   - 添加 `--profile` 参数（调用 cProfile）

3. **双轨并行**：
   - 开发环境：`langgraph dev` + Studio UI
   - 生产环境：`uv run python -m olav.main chat` + 审计日志

**Workflows 架构**

OLAV 采用模块化 Workflows 架构，包含 4 个核心工作流：

| 工作流 | 用途 | 触发关键词 |
|--------|------|-----------|
| **QueryDiagnosticWorkflow** | 网络查询诊断 (SuzieQ → NETCONF) | 查询、状态、BGP、OSPF |
| **DeviceExecutionWorkflow** | 设备配置变更 (HITL 审批) | 配置、修改、执行 |
| **NetBoxManagementWorkflow** | NetBox 清单管理 | 添加设备、NetBox |
| **InspectionWorkflow** ✨ | 巡检与 NetBox 同步 | 巡检、检查、对比、sync |

**交互模式功能**：
- 持续对话：无需每次重新启动，支持上下文记忆
- 内置命令：
  - `help` - 显示可用命令
  - `status` - 查看系统状态
  - `clear` - 清屏
  - `exit` / `quit` / `q` - 退出对话
- **会话持久化**：所有对话通过 PostgreSQL Checkpointer 保存，可随时恢复

**示例对话（Workflows 模式）**：
```
OLAV v1.0.0 - Network Operations ChatOps
LLM: openai (gpt-4-turbo)
Agent: WORKFLOWS (Default)
HITL: Enabled

Type 'exit' or 'quit' to end session
Type 'help' for available commands

Session ID: cli-interactive-1732215600

You: 查询设备 R1 的 BGP 为什么 down

[Orchestrator] Classify intent → QUERY_DIAGNOSTIC
[QueryDiagnosticWorkflow] Macro Analysis (SuzieQ)
  └─ suzieq_query(table='bgp', hostname='R1')
[QueryDiagnosticWorkflow] Micro Diagnostics (NETCONF)
  └─ netconf_tool(xpath='/bgp/neighbors')

╭─ OLAV ────────────────────────────────────────╮
│ 诊断结果：                                      │
│                                                │
│ R1 的 BGP 邻居 10.1.1.2 未建立的原因：          │
│ 1. 本地 AS 号配置错误（65100 vs 65001）        │
│ 2. 邻居地址不可达（路由缺失）                    │
│                                                │
│ 建议操作：                                      │
│ - 修正 AS 号：bgp 65001                         │
│ - 检查路由表：show ip route 10.1.1.2           │
╰────────────────────────────────────────────────╯

You: 修改 R1 的 BGP AS 号为 65001

[Orchestrator] Classify intent → DEVICE_EXECUTION
[DeviceExecutionWorkflow] Config Planning

╭─ OLAV ────────────────────────────────────────╮
│ ⚠️ 需要人工审批                                 │
│                                                │
│ 操作: 修改 BGP AS 号                            │
│ 设备: R1                                       │
│ 变更: router bgp 65001                         │
│ 回滚: router bgp 65100                         │
│                                                │
│ 请选择: [approve / edit / reject]              │
╰────────────────────────────────────────────────╯

You: exit
Goodbye!
```

### 6.2 单次查询模式（快速查询）
```bash
# Remote 模式（需先启动 API Server）
uv run python -m olav.main chat "查询设备 R1 的接口状态"

# 连接 Docker 中的 API Server（端口 8001）
uv run python -m olav.main chat --server "http://localhost:8001" "查询设备 R1 的接口状态"

# Local 模式（无需 Server）
uv run python -m olav.main chat -L "查询设备 R1 的接口状态"

# Expert 模式（复杂诊断）
uv run python -m olav.main chat -e "审计所有边界路由器的 BGP 安全配置"

# 恢复之前的会话继续对话
uv run python -m olav.main chat --thread-id "session-123"··

# 巡检 NetBox 同步状态 ✨ NEW
uv run python -m olav.main chat -L "巡检所有核心路由器"
```

### 6.3 启动 API Server（Remote 模式必需）

**方式 A: Docker 部署（推荐生产环境）**
```bash
# 启动所有服务（包括 olav-server）
docker-compose up -d

# 验证服务状态
curl http://localhost:8001/health
# 返回: {"status":"healthy","version":"0.4.0-beta","environment":"docker",...}

# 本地客户端连接 Docker Server
uv run python -m olav.main chat --server "http://localhost:8001" "查询 R1 状态"
```

**方式 B: 本地启动（开发调试）**
```bash
# 启动 LangServe API Server（默认端口 8000）
uv run python -m olav.main serve

# 自定义端口
uv run python -m olav.main serve --port 8080

# 开发模式（自动重载）
uv run python -m olav.main serve --reload
```

**端口说明**：
| 部署方式 | 端口 | 连接命令 |
|----------|------|----------|
| Docker (`olav-server`) | 8001 | `chat --server "http://localhost:8001"` |
| 本地 (`serve`) | 8000 | `chat`（默认）|

**连接到 Remote Server**：
```bash
# 默认连接 localhost:8000（本地 Server）
uv run python -m olav.main chat "查询 R1 状态"

# 连接 Docker Server（端口 8001）
uv run python -m olav.main chat --server "http://localhost:8001" "查询 R1 状态"

# 指定远程服务器地址
uv run python -m olav.main chat -s http://192.168.1.100:8001 "查询 R1 状态"

# 使用认证（可选）
uv run python -m olav.main login                    # 登录获取 JWT Token
uv run python -m olav.main chat "查询 R1 状态"      # 后续请求自动使用 Token
```

**内置测试用户**（开发环境）：
| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | admin |
| operator | operator123 | operator |
| viewer | viewer123 | viewer |

### 6.4 CLI v2 命令（推荐）
```bash
# ===== 交互式 REPL =====
uv run olav                                    # 启动 REPL（显示彩色 OLAV Logo + 雪人横幅）
uv run olav query "查询 R1 BGP 状态"           # 单次查询
uv run olav query -e "审计边界路由器"          # Expert 模式查询

# ===== TUI 仪表盘 =====
uv run olav dashboard                          # 全屏仪表盘（实时状态、设备统计、活动日志）
uv run olav banner                             # 显示 OLAV 彩色横幅 + 雪人 ASCII Art

# ===== 巡检命令 =====
uv run olav inspect list                       # 列出巡检配置文件
uv run olav inspect run <profile>              # 执行巡检

# ===== 文档管理 =====
uv run olav doc list                           # 列出已索引文档
uv run olav doc upload <file>                  # 上传文档（带进度条）
uv run olav doc search "BGP 配置"              # 搜索文档

# ===== 初始化 =====
uv run olav --init-status                      # 查看索引状态
uv run olav --init                             # 基础初始化（强制刷新索引）
uv run olav --init --full                      # 完整初始化（含 NetBox）

# ===== 版本信息 =====
uv run olav version                            # 查看版本
```

**CLI v2 特性**:
- ✅ 彩色 OLAV Logo（蓝/青/绿/品红渐变）
- ✅ 可爱雪人 ASCII Art（冬季主题 ❄ ⛄ ❆）
- ✅ 设备名自动补全（DynamicDeviceCompleter，5分钟缓存）
- ✅ 文件上传进度条（TransferSpeedColumn）
- ✅ 全屏 TUI 仪表盘（Rich Live 布局）
- ✅ 欢迎横幅（REPL 启动时显示）

### 6.5 传统 CLI 命令
```bash
# 查看版本信息
uv run python -m olav.main version

# 直接 SuzieQ Parquet 查询（非交互式）
uv run python -m olav.main suzieq "interface" --hostname R1

# 登录 API Server（获取 JWT Token）
uv run python -m olav.main login

# 查看当前认证状态
uv run python -m olav.main whoami

# 登出
uv run python -m olav.main logout
```

**Windows 用户注意**：
- OLAV 已自动配置 `SelectorEventLoop` 以兼容 psycopg 异步操作
- 如遇到 `ProactorEventLoop` 错误，请参考 `docs/CHECKPOINTER_SETUP.md`

---
## 7. 开发工作流
```bash
# 代码格式化
uv run ruff format src/ tests/

# 代码检查与自动修复
uv run ruff check src/ tests/ --fix

# 类型检查
uv run mypy src/ --strict

# 运行测试
uv run pytest -v

# 测试覆盖率
uv run pytest --cov=src/olav --cov-report=html
```
添加依赖：
```bash
uv add langchain-openai
uv add --dev pytest-asyncio
```

---
## 8. 下一步建设建议
1. NetBox 自动基线对齐脚本（inventory.csv ↔ NetBox 差异报告）
2. SuzieQ 采集与查询验证（填充 parquet 真实数据）
3. 嵌入流水线：文档分块 + 向量索引（`olav-docs` / `olav-episodic-memory`）
4. 初始化重试与指数回退（NetBox 短暂不可用场景）
5. 状态查询命令：`uv run python -m olav.main status`（显示各哨兵与索引）

**已完成功能**：
- ✅ **CLI v2 全新界面**：彩色 OLAV Logo + 雪人 ASCII Art ✨ NEW
- ✅ **TUI 仪表盘**：全屏 Rich 布局，实时状态监控 ✨ NEW
- ✅ **设备名自动补全**：DynamicDeviceCompleter（5分钟缓存 TTL）✨ NEW
- ✅ **文件上传进度条**：TransferSpeedColumn 显示速度 ✨ NEW
- ✅ 交互式 CLI 对话界面（支持上下文记忆、会话恢复）
- ✅ **Workflows 模块化架构**：4 个核心工作流（查询/配置/清单/巡检）
- ✅ **Remote/Local 双模式**：分布式 API Server 或本地直接执行
- ✅ **Expert 模式**：Deep Dive Workflow 复杂诊断
- ✅ **InspectionWorkflow**：NetBox 双向同步巡检
- ✅ 优雅的 UI 界面（思考过程可视化、工具调用追踪）
- ✅ LLM 流式输出（实时显示推理过程）
- ✅ NetBox Agent HITL 审批机制（写操作需人工批准）
- ✅ NetBox 工具集成（设备查询、API 调用、批量导入）
- ✅ 自主执行能力（Agent 主动规划多步操作）
- ✅ PostgreSQL Checkpointer 状态持久化
- ✅ Windows 平台异步兼容性修复
- ✅ 日志分层管理（--verbose 调试模式）

> **注意**：ReAct、Legacy、Structured、Simple agent 模式已弃用（2025-11-23）。  
> 详见 `archive/deprecated_agents/README.md`。

更详细架构说明参见 `README.MD` 与 `docs/` 目录。

**重要文档**:
- `docs/AGENT_ARCHITECTURE_COMPARISON.md` - Agent 架构对比（workflows/react/structured）
- `docs/WORKFLOWS_INTEGRATION.md` - Workflows 模式集成详解
- `docs/CHECKPOINTER_SETUP.md` - PostgreSQL Checkpointer 配置指南
- `docs/NETBOX_AGENT_HITL.md` - NetBox Agent HITL 审批流程详解
- `docs/CHECKPOINTER_FIX_SUMMARY.md` - Checkpointer 问题解决方案总结

---
## 9. 已知问题与限制

### 9.1 OpenRouter/DeepSeek 与 TodoListMiddleware 不兼容

**问题描述**:  
使用 OpenRouter + DeepSeek模型 时,`TodoListMiddleware` 会导致工具调用验证错误:
```
ValidationError: 1 validation error for AIMessage
invalid_tool_calls.0.args
  Input should be a valid string [type=string_type, input_value={'todos': [...]}, input_type=dict]
```

**根本原因**:  
- OpenRouter/DeepSeek 返回的 `tool_calls[].function.arguments` 是 JSON **字符串** 而非字典
- LangChain 的 `TodoListMiddleware` 在解析这些工具调用时产生格式不正确的 `invalid_tool_calls`
- `InvalidToolCall.args` 字段必须是 `str`,但中间件生成的是 `dict`

**临时解决方案** (已应用):  
在 `src/olav/agents/simple_agent.py` 中禁用了 `TodoListMiddleware`:
```python
middleware=[], # TODO: Re-enable TodoListMiddleware after switching to native OpenAI
```

**长期解决方案** (推荐选其一):

1. **切换到原生 OpenAI API** (推荐)
   ```bash
   # .env 配置
   LLM_PROVIDER=openai
   LLM_API_KEY=sk-...
   LLM_MODEL_NAME=gpt-4-turbo
   ```
   原生 OpenAI API 返回的工具调用格式完全兼容 LangChain。

2. **使用本地 Ollama**
   ```bash
   # 启动 Ollama 服务
   ollama serve
   ollama pull qwen2.5:32b
   
   # .env 配置
   LLM_PROVIDER=ollama
   LLM_MODEL_NAME=qwen2.5:32b
   ```

3. **保持 OpenRouter**  
   LangChain 1.10 的 `init_chat_model()` 已统一处理各种模型提供商的差异，
   工具调用 JSON 解析问题已通过 `with_structured_output()` 解决。

**影响范围**:
- ✅ 其他工具调用 (NETCONF/CLI) 正常工作
- ✅ 基础对话和查询功能不受影响

---
### 9.2 Windows 平台 ProactorEventLoop 问题

**问题**: `psycopg` 异步模式在 Windows 默认事件循环下报错。

**解决方案** (已应用):  
在所有异步脚本开头添加:
```python
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

参考: `docs/CHECKPOINTER_SETUP.md` 第 2 节。

