# OLAV 已知问题与待办事项

> **更新日期**: 2025-11-24
> **版本**: v0.3.0-beta
> **架构**: **Dynamic Intent Router + Workflows + Unified Tools**
> **状态**: 生产就绪，正在进行平台化与插件化改造

---

## 📐 架构演进概览 (Architecture Overview)

本项目已完成从 "DeepAgents" 到 "Workflow Orchestrator" 的核心重构，目前正处于向 **"Dynamic Intent Router"** 三层架构演进的阶段：

1.  **顶层：Dynamic Intent Router** (待实现)
    -   基于 `WorkflowRegistry` 的插件化注册机制。
    -   语义预筛 (Semantic Pre-filtering) + LLM 精确分类。
2.  **中层：Execution Strategies** (已实现基础)
    -   Fast Path (Function Calling)
    -   Deep Path (DeepDiveWorkflow with Recursion)
    -   Batch Path (Parallel Execution)
3.  **底层：Unified Tool Layer** (已完成)
    -   Schema-Aware Tools (SuzieQ Parquet, NetBox, Nornir)
    -   HITL 中间件

---

## 🚀 近期已完成 (Recently Completed)

-   **核心重构**: 移除所有 Legacy Agents，统一使用 LangGraph Workflow 架构。
-   **Deep Dive Workflow**: 完成 Phase 1-3，包含 Schema Investigation (反幻觉)、递归深入 (Recursion)、批量并行执行 (Batch Execution)。
-   **工具层标准化**: 清理旧版 SuzieQ/NetBox 工具，确立 Parquet 直读与 NetBox 统一 API 标准。
-   **测试体系**: 修复 pytest 路径与 shim 问题，核心单元测试全通 (46 passed)。
-   **文档对齐**: 更新 `AGENT_ARCHITECTURE_REFACTOR.md`，定义了 Reconciliation 与 LangServe 新方向。

---

## 📅 路线图与下一步 (Roadmap & Next Steps)

### Phase 1: 动态意图路由 (Dynamic Intent Router) - P1
> 目标：解耦意图与执行，支持工作流插件化扩展。

- [ ] **WorkflowRegistry 实现**:
    -   创建 `src/olav/workflows/registry.py`。
    -   实现装饰器 `@WorkflowRegistry.register`，支持元数据（描述、示例、触发词）注入。
    -   改造现有 4 个 Workflow (Query/Device/NetBox/DeepDive) 使用注册机制。
- [ ] **DynamicIntentRouter 实现**:
    -   实现两阶段路由逻辑：Embedding 语义检索 (Top-K) -> LLM 最终分类。
    -   替换 `root_agent_orchestrator.py` 中的硬编码路由逻辑。
- [ ] **单元测试**: 验证路由准确性与插件注册机制。

### Phase 2: 状态协调工作流 (Controlled State Reconciliation) - P1
> 目标：实现 NetBox (SoT) 与现网状态 (Operational) 的闭环管理。

- [ ] **工作流编排**:
    -   实现 `ReconciliationWorkflow` 类。
    -   定义节点：`drift_detection` (漂移检测) -> `risk_assessment` (风险评分) -> `proposal_synthesis` (方案生成)。
- [ ] **核心算法**:
    -   实现基于 Hash 的配置/状态比对算法。
    -   实现风险评分模型 (High/Medium/Low)。
- [ ] **HITL 集成**:
    -   集成 LangGraph `interrupt` 机制，支持 "Approve / Reject / Modify" 操作。

### Phase 3: 平台化改造 (LangServe + New CLI) - P2
> 目标：从本地脚本工具转型为 C/S 架构的运维平台。

- [ ] **服务端 (Server)**:
    -   创建 `src/olav/server/app.py` (FastAPI + LangServe)。
    -   暴露标准端点：`/v1/chat/invoke`, `/v1/chat/stream`, `/v1/threads/{id}/state`。
    -   集成 JWT 认证与 RBAC 基础。
- [ ] **客户端 (Client)**:
    -   创建 `src/olav/client/cli.py` (Rich + HTTP Client)。
    -   实现瘦客户端逻辑：仅负责 UI 渲染与 WebSocket 通信。
    -   支持 HITL 交互界面 (Approval Gate)。

### Phase 4: 执行策略抽象与巡检模式 (Strategies & Inspection) - P3
> 目标：实现 Fast/Deep/Batch 策略的显式抽象，并支持 YAML 驱动的巡检。

- [ ] **策略抽象 (Strategy Abstraction)**:
    -   定义 `BaseStrategy` 接口。
    -   实现 `FastPathStrategy` (纯 Function Calling，无循环)。
    -   实现 `BatchPathStrategy` (Map-Reduce 编译器)。
    -   改造 Workflow 以支持声明 `preferred_strategies`。
- [ ] **巡检模式 (Inspection Mode)**:
    -   定义 `InspectionConfig` Pydantic Schema。
    -   实现 `ThresholdValidator` (纯 Python 逻辑验证器)。
    -   支持从 `config/inspections/*.yaml` 加载巡检任务。

---

## 🔴 待解决问题 (Active Issues)

### Critical Cleanup (P0)

#### 0. Legacy Code Removal
-   **现状**: 存在已废弃的脚本和模块，可能导致混淆或测试失败。
-   **待办**:
    -   [ ] **Scripts**: 移除/归档 `scripts/benchmark_agents.py` (依赖旧 API), `scripts/test_ntc_schema.py` (依赖已删除的 ntc_tool)。
    -   **ETL**: 移除/归档 `src/olav/etl/ntc_schema_etl.py` (NTC 支持已移除)。
    -   **Core**: 审查 `src/olav/core/inventory_manager.py` (CSV 导入逻辑，确认是否保留)。
    -   **UI**: 标记 `src/olav/ui/chat_ui.py` 为 Legacy，计划在 Phase 3 替换。

### High Priority (P1)

#### 1. HITL 审批机制完善
-   **现状**: 基础 CLI HITL 存在，但未与 LangGraph `interrupt` 深度集成，且缺乏风险分级。
-   **待办**:
    -   [ ] 在所有写操作工作流中统一使用 `interrupt`。
    -   [ ] 实现风险评分系统 (Risk Scoring)，对高危操作强制拦截。
    -   [ ] 提供参数编辑功能 (JSON Editor) 供用户在审批时修改 Payload。
    -   [ ] 记录审计日志到 `olav-audit` 索引。

### Medium Priority (P2)

#### 2. NetBox 集成验证
-   **现状**: 代码已就绪，但缺乏端到端的数据一致性验证。
-   **待办**:
    -   [ ] 验证 `NBInventory` 动态拉取与标签过滤 (`olav-managed`)。
    -   [ ] 测试 NetBox 作为 Source of Truth 的数据准确性。

#### 3. SuzieQ 高级功能测试
-   **现状**: 基础查询正常，高级分析功能未覆盖。
-   **待办**:
    -   [ ] 测试 `path show` (路由追踪)。
    -   [ ] 测试 `topology` (拓扑发现)。
    -   [ ] 测试 `assert` (健康检查)。

#### 4. RAG 第三层 (Documents)
-   **现状**: 仅实现了 Memory 和 Schema 层，缺少文档知识库。
-   **待办**:
    -   [ ] 创建 `olav-docs` 索引。
    -   [ ] 编写 ETL 脚本加载 `data/documents/`。
    -   [ ] 实现 `search_documents` 工具。

#### 5. CLI 工具平台感知 (Platform Awareness)
-   **现状**: `cli_tool` 未暴露设备平台信息，Agent 需自行查询或猜测以生成厂商特定命令。
-   **待办**:
    -   [ ] 利用 NetBox Inventory 中的 `platform` 字段。
    -   [ ] 在 `cli_tool` 执行上下文或返回元数据中传递平台信息，辅助 Agent 生成正确语法。

### Low Priority (P3)

#### 6. 工程化完善
-   **日志**: 实现 JSON 结构化日志与文件轮转。
-   **测试**: 补充 Dynamic Router 与 Reconciliation 的单元测试。
-   **审计**: 确保所有 NETCONF/CLI 操作均写入审计索引。
-   **初始化**: 优化 `olav-init` 的幂等性检查。

---

## 💡 新功能提案 (Future Proposals)

### 1. 轻量级反思 (Lightweight Reflection)
-   **概念**: 在普通模式下增加一轮 Schema-Aware 的结果自检。
-   **计划**: 评估在 Fast Path 中集成的性能损耗，作为可选配置项提供。

---

**备注**: 本文档仅包含当前架构下的有效任务。已废弃的 DeepAgents 相关问题请查阅 `archive/deprecated_agents/README.md`。
