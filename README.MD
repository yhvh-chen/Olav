# OLAV (Omni-Layer Autonomous Verifier)

Enterprise Network Operations ChatOps Platform using LangGraph Workflows.

## Quick Start

OLAV 使用**单一 Workflows Orchestrator 架构**，提供两种运行模式：

### Normal Mode（普通模式，默认）

标准网络运维场景，3 个专用工作流：

```powershell
# Interactive mode
uv run olav.py

# Single query
uv run olav.py "查询 R1 接口状态"
uv run olav.py "为什么 BGP 没有建立邻居？"
uv run olav.py "修改 R1 MTU 为 9000"
```

**可用工作流**:
- **QueryDiagnosticWorkflow**: 强制漏斗式排错（SuzieQ 宏观 → NETCONF 微观）
- **DeviceExecutionWorkflow**: 配置变更（Planning → HITL 审批 → Execution → Validation）
- **NetBoxManagementWorkflow**: 设备清单管理

### Expert Mode（专家模式）

复杂多步任务，启用 Deep Dive Workflow：

```powershell
# Batch audits (30+ devices)
uv run olav.py -e "审计所有边界路由器的 BGP 安全配置"

# Cross-domain troubleshooting
uv run olav.py --expert "为什么数据中心 A 无法访问数据中心 B？"

# Recursive diagnostics
uv run olav.py -e "深入分析 OSPF 邻居关系异常"
```

**Deep Dive 能力**:
- 自动任务分解（LLM 生成 Todo List）
- 递归深入诊断（最大 3 层，已实现）
- 批量并行执行（asyncio.gather，已实现并通过全部测试）
- 进度追踪与恢复（PostgreSQL Checkpointer，支持断点续传）

---

## Architecture Overview（架构概览）

OLAV 采用 **Workflows Orchestrator** 单一架构（2025-11-23 简化）：

```
用户请求 → Orchestrator (Intent 分类)
  ↓
Workflow Selection (LLM 自动路由)
  ↓
├─ QueryDiagnosticWorkflow   (查询/诊断)
├─ DeviceExecutionWorkflow    (配置变更)
├─ NetBoxManagementWorkflow   (设备管理)
└─ DeepDiveWorkflow           (复杂任务，需 -e 启用)
```

**已废弃架构**（2025-11-23 归档至 `archive/deprecated_agents/`）:
- ❌ ReAct: 虽快（16s）但缺少显式流程控制
- ❌ Legacy (SubAgent): 多层委托，性能差（72s）
- ❌ Structured: 未完成
- ❌ Simple: 功能重叠

当前主线架构已实现：
- Deep Dive Workflow 递归与并行批量执行（详见 DESIGN.md）
- 所有相关测试已通过（21/21）
- 文档与 TODO 已同步更新

详见: `archive/deprecated_agents/README.md` 与 `docs/DESIGN.md`

---

## Workflows Details（工作流详解）
RAG   : search_episodic_memory, search_openconfig_schema
NetCONF/CLI: netconf_tool, cli_tool (HITL 对写操作自动中断)
NetBox: netbox_api_call, netbox_schema_search
```
关键策略：
- 漏斗式排错：先宏观 `suzieq_query` → 再微观 `netconf_tool`
- Schema-Aware：不确定表/字段/XPath 先调用 `*_schema_search`
- 降级链：NETCONF → CLI（提示无原子回滚能力）
- HITL：`netconf_tool` / `cli_tool` 写操作触发人工审批

单步简单查询示例：
```
输入: 查询接口状态
调用: suzieq_query(table="interfaces", method="summarize")
输出: 总 222 接口，91% up，类型分布...
耗时: ~16s (对比 legacy ~72s)
```

## 性能对比 (示例基准)

| Query | ReAct (s) | Legacy (s) | Speedup |
|-------|-----------|------------|---------|
| 查询接口状态 | 16.3 | 72.5 | 77.5% |

运行完整基准：
```powershell
uv run python scripts/benchmark_agents.py --mode both -n 8
Get-Content benchmark_results.md | Select-Object -First 20
```

## Quick Start

## Quick Start

```bash
# Install dependencies
uv sync --dev

# Start Docker infrastructure
docker-compose up -d opensearch postgres redis

# Initialize databases
docker-compose --profile init up olav-init

# Run CLI (ReAct 默认)
uv run python -m olav.main chat

# Use legacy mode (对照测试)
uv run python -m olav.main chat --agent-mode legacy

# Run tests
uv run pytest
```

## Architecture

| Layer | Purpose | Implementation |
|-------|---------|---------------|
| Prompt | 统一策略/安全规范 | `config/prompts/agents/root_agent_react.yaml` |
| Agent  | 推理 + 工具调用 | `create_deep_agent(subagents=[])` |
| Tools  | Schema-Aware 网络数据 & 控制 | `src/olav/tools/*.py` |
| Safety | 写操作 HITL 审批 & 审计 | Interrupt + OpenSearch Logs |
| State  | 会话与多轮推理持久化 | PostgreSQL Async Checkpointer |

核心原则：
- **Schema-Aware**：减少工具数量（SuzieQ/NetBox/YANG 动态发现）
- **漏斗式排错**：宏观 → 微观，避免盲目深入
- **最小信任**：写操作必须人工审批 (HITL)
- **可追溯性**：工具调用路径 + 结果审计

更多细节见 `DESIGN.md` 与 `docs/` 内部文档。

## 常用命令 (PowerShell)
```powershell
# 初始化（首次）
docker-compose --profile netbox up -d

# 查看健康状态
docker ps --format "table {{.Names}}\t{{.Status}}" | findstr olav

# 运行单次查询 (ReAct)
uv run python -m olav.main chat "查询接口状态"

# 基准测试
uv run python scripts/benchmark_agents.py --mode both

# 查看最近提交
git log --oneline -n 5
```

## 安全与合规
- 所有写操作工具自动进入审批等待（HITL）
- NETCONF 优先，失败后才降级 CLI 并提示风险
- 审计日志包含：时间戳、设备、操作类型、结果
- 推荐在生产启用 OpenSearch 索引生命周期管理（ILM）


## 后续路线
- 多失败递归增强（Deep Dive 多点失败处理）
- Checkpointer 恢复与断点续传测试
- 性能基准与批量任务调优
- 完整 100 查询基准测试覆盖
- 引入 Prompt 结果缓存减少 token
- 复杂任务早停 (early stopping) 策略
- WebUI 展示工具调用链路

---
如需更多帮助：运行 `uv run python -m olav.main chat --verbose` 查看推理与工具调用细节。
