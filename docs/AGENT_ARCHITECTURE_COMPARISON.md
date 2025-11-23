# Agent 架构对比：Workflows vs ReAct vs Structured

## 架构对比总览

| 维度 | Workflows (Modular) | ReAct (Prompt-Driven) | Structured (StateGraph) | Legacy (SubAgent) |
|------|---------------------|----------------------|------------------------|-------------------|
| **控制方式** | 意图分类 + 模块化工作流 | LLM 隐式推理 | 显式状态机 | SubAgent 委托 |
| **流程透明度** | ✅ **高**（模块可视化） | ⚠️ 中等（依赖 Prompt） | ✅ **高**（图可视化） | ⚠️ 低（多层嵌套） |
| **可靠性** | ✅ **确定性路由** | ⚠️ 依赖触发词识别 | ✅ **确定性路由** | ⚠️ 委托开销大 |
| **性能** | ⚠️ 中等（分类+执行） | ✅ **快**（16s） | ⚠️ 中等（预计 25s） | ❌ 慢（72s） |
| **灵活性** | ✅ **高**（可插拔工作流） | ✅ **高** | ⚠️ 中等（固定流程） | ✅ 高（动态委托） |
| **维护成本** | ✅ **低**（模块隔离） | ⚠️ Prompt 调优 | ✅ **低**（结构清晰） | ❌ 高（多文件） |
| **适用场景** | **生产推荐**（全场景） | 日常运维（85%） | 复杂诊断（15%） | 对比基准 |

## 核心差异

### 1. Workflows 模式（Modular Architecture）**【推荐生产环境使用】**

**原理**：通过 LLM 意图分类将查询路由到专用工作流，每个工作流独立实现特定场景的最佳实践流程。

**架构组件**：
```python
# src/olav/agents/root_agent_orchestrator.py
WorkflowOrchestrator
    ├── Intent Classification (LLM + keyword fallback)
    │   └── 输出: QUERY_DIAGNOSTIC | DEVICE_EXECUTION | NETBOX_MANAGEMENT
    ├── QueryDiagnosticWorkflow (网络查询与诊断)
    │   ├── Macro Analysis (SuzieQ 历史数据)
    │   ├── Micro Diagnostics (NETCONF/CLI 实时查询)
    │   └── Root Cause Analysis (根因定位)
    ├── DeviceExecutionWorkflow (配置变更)
    │   ├── Config Planning (变更计划生成)
    │   ├── HITL Approval (人工审批，interrupt point)
    │   ├── Config Execution (NETCONF/CLI 执行)
    │   └── Verification (变更验证)
    └── NetBoxManagementWorkflow (清单管理)
        ├── NetBox API Query
        ├── HITL Approval (写操作审批)
        └── NetBox API Write
```

**三大工作流特点**：

1. **QueryDiagnosticWorkflow**（查询/诊断）
   - 强制漏斗式排错：SuzieQ 宏观 → NETCONF 微观
   - 多轮对话支持：动态调整诊断策略
   - 适用场景：`"BGP为什么down?"`, `"查询接口状态"`, `"诊断路由问题"`

2. **DeviceExecutionWorkflow**（配置变更）
   - 自动生成回滚计划
   - HITL 强制审批（LangGraph interrupt）
   - 变更后自动验证配置生效
   - 适用场景：`"修改BGP配置"`, `"添加VLAN 100"`, `"shutdown接口"`

3. **NetBoxManagementWorkflow**（清单管理）
   - 读操作免审批，写操作强制 HITL
   - 与设备配置隔离（不触发 NETCONF）
   - 适用场景：`"添加设备到NetBox"`, `"设备清单"`, `"IP地址分配"`

**意图分类策略（双层）**：
```python
# 1. LLM-based classification (primary)
response = llm.invoke("分类用户查询 → query_diagnostic|device_execution|netbox_management")

# 2. Keyword fallback (secondary, 当LLM失败时)
if "设备清单" in query or "ip分配" in query:
    return WorkflowType.NETBOX_MANAGEMENT
elif "配置" in query or "修改" in query:
    return WorkflowType.DEVICE_EXECUTION
else:
    return WorkflowType.QUERY_DIAGNOSTIC  # 默认
```

**优势**：
- ✅ **模块化隔离**：每个工作流独立演进，互不干扰
- ✅ **确定性路由**：意图明确后按固定流程执行，无黑盒推理
- ✅ **可扩展性强**：新增场景只需添加新工作流，不修改现有代码
- ✅ **HITL 集成**：自然支持不同工作流的差异化审批策略
- ✅ **测试友好**：每个工作流可独立单元测试
- ✅ **Prompt 管理**：每个节点独立 prompt 文件（`config/prompts/workflows/`）

**劣势**：
- ⚠️ 分类开销：额外一次 LLM 调用用于意图分类（~2-3s）
- ⚠️ 复杂度增加：需维护 3+ 个独立工作流图
- ⚠️ 误分类风险：如果意图分类错误，需要依赖关键词 fallback

**使用示例**：
```bash
# 默认模式（现在 workflows 是 default）
uv run python -m olav.main chat "BGP为什么down?"

# 执行流程：
# [Orchestrator] Classify intent → QUERY_DIAGNOSTIC
# [QueryDiagnosticWorkflow] Macro Analysis (SuzieQ)
# [QueryDiagnosticWorkflow] Micro Diagnostics (NETCONF)
# [QueryDiagnosticWorkflow] Root Cause Analysis

# 配置变更（自动触发HITL审批）
uv run python -m olav.main chat "修改R1的BGP AS号为65001"

# 执行流程：
# [Orchestrator] Classify intent → DEVICE_EXECUTION
# [DeviceExecutionWorkflow] Config Planning
# [DeviceExecutionWorkflow] HITL Approval (暂停，等待人工)
#   ↓ 用户批准后
# [DeviceExecutionWorkflow] Config Execution (NETCONF)
# [DeviceExecutionWorkflow] Verification
```

### 2. ReAct 模式（Prompt-Driven）

**原理**：通过精心设计的 System Prompt 引导 LLM 自主决策工具调用顺序。

```python
# config/prompts/agents/root_agent_react.yaml
template: |
  ## 核心原则
  - ✅ 强制漏斗式排错: 用户询问"为什么"/"原因"/"诊断" 
      → SuzieQ宏观 → NETCONF微观 → 根因定位
  - ❌ 禁止仅基于 SuzieQ 历史数据推测根因
  
  ### 诊断任务触发词识别
  用户问题包含以下关键词时，必须执行完整漏斗流程:
  - "为什么" / "原因" / "诊断" / "排查"
  - "没有建立" / "down" / "失败"
```

**优势**：
- ✅ 简洁高效：单一 Agent + 工具列表，无额外编排开销
- ✅ 灵活适应：LLM 可根据上下文动态调整策略
- ✅ 性能最优：平均 16s（vs Legacy 72s）

**劣势**：
- ⚠️ 依赖触发词：如果 Prompt 没覆盖的表述，可能跳过漏斗流程
- ⚠️ 黑盒推理：难以预测 LLM 是否严格遵循 Prompt 指令
- ⚠️ Prompt 膨胀：复杂场景需要更长的系统指令

### 3. Structured 模式（Explicit StateGraph）

**原理**：使用 LangGraph StateGraph 定义显式工作流，通过条件边强制执行任务流程。

#### 工作流结构（双路径）

**路径 1：查询/诊断任务**
```python
User Query
    ↓
[Intent Analysis] ─→ 分类: Simple/Diagnostic/Config
    ↓
[Macro Analysis] ─→ SuzieQ 历史分析
    ↓
[Self Evaluation] ─→ 评估: 数据是否充足？
    ├─ Yes → [Final Answer]
    └─ No → [Micro Diagnosis] → NETCONF/CLI 实时诊断
                ↓
            [Final Answer]
```

**路径 2：配置变更任务**
```python
User Query
    ↓
[Intent Analysis] ─→ 分类: CONFIG_CHANGE
    ↓
[Config Planning] ─→ 生成变更计划 + 回滚策略
    ↓
[HITL Approval] ─→ 人工审批（interrupt point）
    ├─ Approved → [Config Execution] ─→ 执行变更
    │                    ↓
    │              [Validation] ─→ 验证变更结果
    │                    ↓
    │              [Final Answer]
    │
    └─ Rejected → [Final Answer] (abort)
```

**优势**：
- ✅ **确定性执行**：无论 LLM 如何理解，都强制执行预定义流程
- ✅ **可观测性强**：每个 Node 独立可追踪，易于调试
- ✅ **自我评估**：显式判断是否需要深入诊断（vs 隐式触发词匹配）
- ✅ **解耦逻辑**：意图分析、工具调用、评估逻辑分离
- ✅ **HITL 集成**：原生支持 interrupt_before，自动暂停等待审批
- ✅ **变更验证**：执行后自动验证配置生效和系统稳定性

**劣势**：
- ⚠️ 性能开销：多次 Node 转换 + LLM 调用（预计 +50% 延迟）
- ⚠️ 灵活性降低：固定流程难以适应边缘场景
- ⚠️ 代码复杂度：需维护 StateGraph 定义 + 多个 Node 函数

## 实现细节

### Structured Agent 核心组件

#### State 定义
```python
class StructuredState(TypedDict):
    messages: list[BaseMessage]
    task_type: TaskType | None  # SIMPLE_QUERY | DIAGNOSTIC | CONFIG_CHANGE
    stage: WorkflowStage  # 当前阶段
    macro_data: dict | None  # SuzieQ 结果
    micro_data: dict | None  # NETCONF 结果
    evaluation_result: dict | None  # 自我评估结果
    needs_micro: bool  # 是否需要微观诊断
    # 配置变更专用字段
    config_plan: dict | None  # 变更计划（XPath/设备/参数）
    approval_status: str | None  # 审批状态（pending/approved/rejected）
    execution_result: dict | None  # 执行结果
    validation_result: dict | None  # 验证结果
    iteration_count: int  # 迭代计数
```

#### Node 函数示例

**Config Planning Node**（配置变更专用）：
```python
async def config_planning_node(state: StructuredState) -> StructuredState:
    """生成详细变更计划，包含回滚策略"""
    llm = LLMFactory.get_chat_model()
    llm_with_tools = llm.bind_tools([
        search_episodic_memory,  # 查询类似成功案例
        search_openconfig_schema,  # 确认 XPath
        netconf_tool,  # 获取当前配置
    ])
    
    planning_prompt = f"""为配置变更任务生成详细执行计划。
    
    用户请求: {state['messages'][0].content}
    
    生成变更计划，包含：
    - 目标设备列表
    - 配置 XPath 和新值
    - 预期影响范围
    - 回滚策略（NETCONF commit confirmed 或 CLI 手动回滚命令）
    - 风险评估（LOW/MEDIUM/HIGH）
    """
    
    response = await llm_with_tools.ainvoke([SystemMessage(content=planning_prompt)])
    
    return {
        **state,
        "config_plan": {"plan": response.content},
        "stage": WorkflowStage.CONFIG_PLANNING,
    }
```

**HITL Approval Node**（中断点）：
```python
async def hitl_approval_node(state: StructuredState) -> StructuredState:
    """人工审批节点 - LangGraph interrupt 在此暂停"""
    # 当执行恢复时，approval_status 由用户更新
    approval_status = state.get("approval_status", "pending")
    
    return {
        **state,
        "stage": WorkflowStage.HITL_APPROVAL,
        "approval_status": approval_status,
    }
```

**Validation Node**（变更后验证）：
```python
async def validation_node(state: StructuredState) -> StructuredState:
    """验证配置变更是否成功生效"""
    llm_with_tools = llm.bind_tools([suzieq_query, netconf_tool, cli_tool])
    
    validation_prompt = f"""验证配置变更是否成功生效。
    
    步骤：
    1. 使用 netconf_tool(get-config) 确认新配置已应用
    2. 使用 suzieq_query 检查相关状态（如 BGP 邻居是否重新建立）
    3. 检查是否有异常告警
    
    返回验证结果：config_applied, state_healthy, recommendation
    """
    
    response = await llm_with_tools.ainvoke([SystemMessage(content=validation_prompt)])
    
    return {**state, "validation_result": {"result": response.content}}
```
```python
async def intent_analysis_node(state: StructuredState) -> StructuredState:
    """分析用户意图，分类任务类型"""
    llm = LLMFactory.get_chat_model()
    
    classification_prompt = f"""分析用户请求，分类任务类型：
    
    用户请求: {state['messages'][-1].content}
    
    任务分类标准：
    1. SIMPLE_QUERY: 仅查询状态/概览，无需深入分析
    2. DIAGNOSTIC: 需要分析根因、排查问题
    3. CONFIG_CHANGE: 需要修改配置
    
    仅返回: SIMPLE_QUERY 或 DIAGNOSTIC 或 CONFIG_CHANGE
    """
    
    response = await llm.ainvoke([SystemMessage(content=classification_prompt)])
    task_type = TaskType(response.content.strip().lower())
    
    return {**state, "task_type": task_type, "stage": WorkflowStage.INTENT_ANALYSIS}
```

**Self Evaluation Node**：
```python
async def self_evaluation_node(state: StructuredState) -> StructuredState:
    """评估宏观数据是否足够，决定是否需要微观诊断"""
    if state["task_type"] == TaskType.SIMPLE_QUERY:
        return {**state, "needs_micro": False}
    
    llm = LLMFactory.get_chat_model()
    
    eval_prompt = f"""评估当前宏观分析数据是否足以回答用户问题。
    
    用户请求: {state['messages'][0].content}
    宏观分析: {state['macro_data']}
    
    评估标准：
    - 如果用户询问"为什么"/"原因"，仅历史数据不足，需要实时配置验证
    - 如果发现异常状态（NotEstd/down），需要获取实时配置确认根因
    
    返回 JSON: {{"sufficient": true/false, "reason": "..."}}
    """
    
    response = await llm.ainvoke([SystemMessage(content=eval_prompt)])
    
    # 解析评估结果（简化版：基于触发词）
    user_query = state['messages'][0].content.lower()
    needs_micro = any(word in user_query for word in ["为什么", "原因", "诊断", "排查"])
    
    return {**state, "needs_micro": needs_micro, "evaluation_result": {"response": response.content}}
```

#### 条件路由
```python
def route_after_evaluation(state: StructuredState) -> Literal["micro_diagnosis", "final_answer"]:
    """评估后路由：决定是否需要微观诊断"""
    if state.get("needs_micro", False):
        return "micro_diagnosis"
    return "final_answer"
```

## 使用场景建议

### 何时使用 ReAct
- ✅ **日常运维查询**（85% 场景）：快速响应，灵活适应
- ✅ **性能敏感场景**：CLI 实时交互，延迟要求 < 20s
- ✅ **探索性任务**：需要 LLM 自主判断策略
- ✅ **简单诊断**：触发词明确（"为什么 BGP down"）

### 何时使用 Structured
- ✅ **复杂多步诊断**：需要强制执行完整漏斗流程
- ✅ **合规/审计要求**：需要可追溯的确定性流程
- ✅ **批量任务**：预定义工作流（如巡检、健康检查）
- ✅ **调试/开发阶段**：需要可视化工作流，定位瓶颈

### 何时使用 Legacy
- ⚠️ **仅作对比基准**：验证新架构性能提升
- ⚠️ **特殊兼容需求**：依赖 SubAgent 特有功能

## 性能预测

基于现有基准测试：

| 查询类型 | ReAct | Structured (预测) | Legacy |
|---------|-------|------------------|--------|
| 简单查询（接口状态） | **16s** | 25s (+56%) | 72s |
| 中等诊断（BGP 原因） | **30s** | 40s (+33%) | 120s |
| 复杂任务（多设备聚合） | **50s** | 60s (+20%) | 200s |

**预测依据**：
- Structured 增加 3-5 次额外 LLM 调用（Intent/Evaluation/每个 Node 的 Prompt）
- 每次 LLM 调用平均 3-5s（gpt-4-turbo）
- StateGraph 转换开销 < 100ms（可忽略）

## 后续优化方向

### ReAct 模式
1. **Prompt 缓存**：固定系统指令部分复用编译后的 embedding
2. **提前终止**：首次工具计划生成即调用，减少思考轮数
3. **触发词扩展**：添加更多诊断任务识别模式

### Structured 模式
1. **并行 Node 执行**：Macro 和 Schema Search 同时进行
2. **条件跳过**：Simple Query 直接绕过 Evaluation Node
3. **缓存策略**：相似查询复用 Intent Analysis 结果

## 实际使用示例

### Workflows 模式（推荐）
```bash
# 默认模式（自动分类路由）
uv run python -m olav.main chat "查询 R1 的 BGP 为什么没建立"

# 执行流程：
# [Orchestrator] Intent Classification → QUERY_DIAGNOSTIC
# [QueryDiagnosticWorkflow] Macro Analysis → SuzieQ查询
# [QueryDiagnosticWorkflow] Micro Diagnostics → NETCONF实时查询
# [QueryDiagnosticWorkflow] Root Cause Analysis → 综合根因分析

# 配置变更（自动触发HITL）
uv run python -m olav.main chat "修改 R1 的 BGP AS 号为 65001"

# 执行流程：
# [Orchestrator] Intent Classification → DEVICE_EXECUTION
# [DeviceExecutionWorkflow] Config Planning → 生成变更计划+回滚策略
# [DeviceExecutionWorkflow] HITL Approval → 暂停等待人工审批
#   ↓ 用户批准后
# [DeviceExecutionWorkflow] Config Execution → NETCONF edit-config
# [DeviceExecutionWorkflow] Verification → 验证配置生效
```

### ReAct 模式
```bash
# 默认模式
uv run python -m olav.main chat "查询 R1 的 BGP 为什么没建立"

# 预期行为：
# 1. LLM 识别"为什么" → 触发漏斗流程
# 2. suzieq_query(table='bgp') → 发现 NotEstd
# 3. search_openconfig_schema → 获取 XPath
# 4. netconf_tool(get-config) → 实时配置
# 5. 对比分析 → 给出根因
```

### Structured 模式
```bash
# 诊断任务（显式工作流）
uv run python -m olav.main chat -m structured "查询 R1 的 BGP 为什么没建立"

# 预期行为：
# [Intent Analysis] → DIAGNOSTIC
# [Macro Analysis] → SuzieQ 查询
# [Self Evaluation] → needs_micro=True
# [Micro Diagnosis] → NETCONF 获取配置
# [Final Answer] → 综合分析

# 配置变更任务（包含 HITL 审批）
uv run python -m olav.main chat -m structured "修改 R1 的 BGP AS 号为 65001"

# 预期行为：
# [Intent Analysis] → CONFIG_CHANGE
# [Config Planning] → 生成变更计划
# [HITL Approval] → 暂停，等待人工审批
#   用户审批后（通过 LangGraph API 或 CLI）
# [Config Execution] → 执行 NETCONF edit-config
# [Validation] → 验证配置生效
# [Final Answer] → 返回执行结果
```

## 总结与选择指南

### 模式选择决策树

```
用户查询 → 
  ├─ 生产环境 → **Workflows**（推荐）
  │   ├─ 优点：模块化、确定性路由、易维护
  │   ├─ 适用：全场景覆盖（查询+配置+清单）
  │   └─ 性能：中等（意图分类+工作流执行）
  │
  ├─ 性能敏感场景 → **ReAct**
  │   ├─ 优点：最快（16s）、单次LLM调用
  │   ├─ 适用：日常运维查询（85%）
  │   └─ 缺点：依赖Prompt调优、黑盒推理
  │
  ├─ 复杂诊断/合规场景 → **Structured**
  │   ├─ 优点：确定性最强、自我评估
  │   ├─ 适用：多步骤复杂诊断（15%）
  │   └─ 缺点：性能开销、灵活性低
  │
  └─ 对比基准/研究 → **Legacy**
      └─ 仅用于性能对比，不推荐生产使用
```

### 关键差异对比

| 特性 | Workflows | ReAct | Structured | Legacy |
|------|-----------|-------|------------|--------|
| **意图分类** | ✅ 显式分类 | ❌ 无分类 | ⚠️ 内置判断 | ❌ SubAgent委托 |
| **工作流隔离** | ✅ 3个独立工作流 | ❌ 单一Agent | ⚠️ 2条路径 | ⚠️ 多层SubAgent |
| **HITL集成** | ✅ 按工作流定制 | ⚠️ 全局配置 | ✅ 原生interrupt | ⚠️ 复杂实现 |
| **可扩展性** | ✅ **最强** | ⚠️ Prompt膨胀 | ⚠️ 需修改图 | ❌ 多文件修改 |
| **性能** | ⚠️ 中等 | ✅ **最快** | ⚠️ 中等 | ❌ 最慢 |
| **代码维护** | ✅ **最易** | ⚠️ Prompt调优 | ✅ 结构清晰 | ❌ 最难 |

### 当前建议

- **默认使用 Workflows 模式**（已设为 CLI 默认值）
  - 适合生产环境全场景部署
  - 模块化架构易于团队协作
  - 确定性路由减少意外行为

- **性能敏感场景临时切换 ReAct**
  ```bash
  olav chat -m react "快速查询接口状态"
  ```

- **复杂诊断场景切换 Structured**（未来可按需激活）
  ```bash
  olav chat -m structured "深度诊断BGP+OSPF交互问题"
  ```

- **Legacy 模式仅用于对比测试**
  ```bash
  olav chat -m legacy "对比测试性能基准"
  ```

### 未来演进方向（Hybrid Mode）

计划实现**智能路由**：
```python
async def auto_select_mode(query: str) -> AgentMode:
    """根据查询复杂度自动选择最佳模式"""
    complexity = analyze_query_complexity(query)
    
    if complexity == "simple":
        return AgentMode.REACT  # 性能优先
    elif complexity == "diagnostic":
        return AgentMode.WORKFLOWS  # 模块化流程
    elif complexity == "critical_config":
        return AgentMode.STRUCTURED  # 确定性最高
```
