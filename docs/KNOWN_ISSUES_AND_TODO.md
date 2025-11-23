# OLAV 已知问题与待办事项

> **更新日期**: 2025-11-23  
> **版本**: v0.2.0-alpha  
> **架构**: **Workflows Orchestrator** (单一架构)  
> **状态**: 生产就绪，深度能力增强中

---

## 📐 当前架构设计 (Architecture Overview)

### 核心模式 (Production Only) ⭐

OLAV 采用**单一 Workflows Orchestrator 架构**，通过 Intent 分类自动路由到 4 个专用工作流。

#### **Workflows Orchestrator** (唯一生产架构)

**性能**: 
- 平均响应: **20-25s** (标准模式) / **30-45s** (专家模式)
- 工具调用: 4-8 次 (标准) / 10-20 次 (专家)
- 代码量: 280 lines (Orchestrator) + 4 个 Workflow (总计 ~1050 lines)

**当前 4 个 Workflows**:
- **QueryDiagnosticWorkflow** (285 lines): 
  - 强制漏斗流程: SuzieQ 宏观 → NETCONF 微观
  - 自动评估是否需要深入诊断
  - 适合: 查询、故障排查、根因分析
  
- **DeviceExecutionWorkflow** (270 lines):
  - Planning → HITL Approval → Execution → Validation
  - 支持 NETCONF (原子回滚) 和 CLI (降级)
  - 适合: 配置变更、设备管理
  
- **NetBoxManagementWorkflow** (220 lines):
  - 设备清单管理、IP 分配、站点配置
  - 集成 NetBox API
  - 适合: CMDB 操作

- **DeepDiveWorkflow** ⭐ **新增** (275 lines):
  - 任务自动分解 + Schema Investigation (反幻觉)
  - HITL 双重审批（计划 + 执行）
  - 进度持久化 + 中断恢复
  - 适合: 批量审计、复杂诊断、递归排错

**实现**: `src/olav/workflows/` + `src/olav/agents/root_agent_orchestrator.py`

## 当前进展

1. Deep Dive Phase 1 已完成：任务分解 + Schema 调查 + HITL + 反幻觉链路。
2. External Evaluator 已动态化，所有相关单元测试通过。
3. 兼容层修复（config/settings、root_agent stub）已落地，test_core.py 测试通过。
4. 遗留测试包结构问题已定位，采用 minimal shim 解决 legacy 路径。
5. pytest 环境已可运行核心单元测试，剩余 legacy 测试待适配。
6. **Shim 清理完成**：已删除所有 shadow 包（src/config、src/olav/config），统一使用真实 config/settings.py。
7. **测试路径统一完成**：tests/conftest.py 添加项目根到 sys.path，所有单元测试通过（46 passed, 7 skipped）。
8. **垃圾代码清理完成**：
   - 移动顶层测试文件到 tests/manual/
   - 移动调试脚本到 scripts/debug/
   - 删除 olav/ shim 包（已有 editable install）
   - 统一 CLI 入口为 olav.py（删除 olav_cli.py）
9. **旧 DeepAgents 架构清理完成**：
   - 删除所有基于 DeepAgents 的 agent 实现（simple_agent、suzieq_agent、cli_agent、netbox_agent）
   - 删除 DeepAgents middleware（network_context.py）
   - 删除 legacy root_agent stub
   - 移动旧 agent 测试脚本到 archive/legacy_agent_scripts/
   - 项目已完全迁移到基于 workflow 的 orchestrator 架构
10. **Legacy Tools 清理完成** (2025-11-23):
   - 删除 Legacy SuzieQ Tool: `src/olav/tools/suzieq_tool.py` (基于 SDK + Redis，已被 `suzieq_parquet_tool.py` 替代)
   - 删除冗余 NetBox Tool: `src/olav/tools/netbox_inventory_tool.py` (已被 `netbox_tool.py` 统一)
   - 删除未使用工具: `src/olav/tools/ntc_tool.py` (NTC Templates 未集成)
   - 测试全部通过: 45 passed, 7 skipped
   - 工具架构标准化完成：SuzieQ (Parquet直读) + NetBox (统一API) + Nornir (NETCONF/CLI)

## 待办事项

1. ~~清理 shim 兼容层（src/config/settings.py）与多余 shadow 包，统一配置入口。~~ ✅ 已完成
2. **Deep Dive Phase 3 实现**：递归深入 + 批量并行执行（当前仅占位符）。
3. ~~标记并跳过所有依赖 legacy 架构的测试，逐步迁移到新 orchestrator。~~ ✅ 已完成
4. ~~优化测试环境路径与包结构，确保 pytest 可直接运行所有单元测试。~~ ✅ 已完成
5. ~~垃圾代码与 ghost 代码清理。~~ ✅ 已完成
6. ~~Legacy Tools 清理（suzieq_tool.py, netbox_inventory_tool.py, ntc_tool.py）。~~ ✅ 已完成
7. **Deep Dive 单元测试补充**（当前完全缺失）。
8. 文档同步：持续更新架构演进、Known Issues、测试覆盖率。
9. TODO 注释处理：init_schema.py (YANG 解析 - 低优先级占位符)。

## 下一项任务规划

**目标：补充 Deep Dive 缺失功能与测试。**

### 当前问题识别：
1. ❌ **递归深入未实现**：`recursive_check_node` 仅有占位符逻辑，返回 "Recursive analysis skipped in Phase 1"
2. ❌ **并行执行未实现**：`execute_todo_node` 串行执行，无 `asyncio.gather()` 批量优化
3. ❌ **Deep Dive 单元测试完全缺失**：`tests/unit/test_workflows.py` 仅测试 Orchestrator，无 Deep Dive 测试
4. ⚠️ **README 宣称功能未兑现**：声称支持 "递归深入（最大 3 层）" 和 "批量并行执行"，但代码未实现
5. ⚠️ **进度恢复未验证**：Checkpointer 集成存在但未测试中断恢复场景

### 修复步骤：
1. **实现递归任务分解**（预计 6-8 小时）：
   - `recursive_check_node` 中检测失败任务并生成子任务
   - 子任务继承父任务上下文（设备、协议等）
   - 限制递归深度为 3 层（已有 `max_depth` 检查）

2. **实现批量并行执行**（预计 4-6 小时）：
   ```python
   # execute_todo_node 优化
   independent_todos = [t for t in todos if not t['deps']]
   results = await asyncio.gather(*[
       self._execute_single_todo(todo) for todo in independent_todos[:5]
   ])
   ```

3. **补充 Deep Dive 单元测试**（预计 6-8 小时）：
   - `test_task_planning_node`: 验证 LLM 生成 Todo List
   - `test_schema_investigation_node`: 验证 feasibility 分类
   - `test_execute_todo_node`: 验证 External Evaluator 集成
   - `test_recursive_check_node`: 验证递归触发逻辑（待实现后）
   - `test_hitl_approval_flow`: 验证中断/恢复机制

4. **修正 README 宣传**（预计 30 分钟）：
   - 标注递归/并行为 "Phase 3 规划中" 或删除未实现功能描述

**后续任务（Phase 4）：**
Episodic Memory 架构、真实设备状态对比（NETCONF XPath）、完整端到端测试。
- ❌ **ReAct**: 缺少显式流程控制，依赖 Prompt 引导 (16s)

**废弃原因**: 
- Legacy/Structured/Simple: 性能差或未完成
- **ReAct**: 虽然速度快，但**无法保证强制漏斗流程**（企业网络运维核心需求）

**性能对比**:
| 模式 | 响应时间 | 工具调用 | 流程控制 | 状态 |
|------|---------|---------|---------|------|
| Legacy SubAgent | 72.5s | 4-14 次 | ❌ 黑盒 | ❌ 已废弃 |
| ReAct | 16.3s | 1-6 次 | ⚠️ Prompt 引导 | ❌ 已废弃 |
| **Workflows** ⭐ | **20-25s** | 4-8 次 | ✅ 强制状态机 | ✅ 唯一生产 |
| **Deep Dive** ⭐ | **30-45s** | 10-20 次 | ✅ Schema 验证 | ✅ 专家模式 |

详见: `archive/deprecated_agents/README.md`

---

## 🔴 高优先级任务 (Critical Issues)

### 1. ✅ Deep Dive Workflow Phase 1 完成 + Reflection/Reflexion 架构评估 - P0

**实现状态**: ✅ **Phase 1 已完成** (2025-11-23)
- ✅ 基础框架完成 (`src/olav/workflows/deep_dive.py`, 275 lines)
- ✅ Schema Investigation 节点（反幻觉机制）
- ✅ HITL 双重审批流程
- ✅ 任务分解与执行
- ✅ 修改计划重新审批显示修复
- ❌ **Phase 3 未实现**：递归深入和并行执行仅占位符，功能未兑现
- ❌ **单元测试缺失**：无 Deep Dive Workflow 测试用例

**Phase 1 核心创新** - Schema Investigation（反幻觉机制）:
```python
# src/olav/workflows/deep_dive.py: schema_investigation_node
# 执行前调查 schema 可用性，分类任务可行性
execution_plan = {
    "feasible_tasks": [1, 3, 4],      # Schema 确认可执行
    "uncertain_tasks": [2, 5],         # Schema 存在但字段不确定
    "infeasible_tasks": [6],           # Schema 无对应表
    "recommendations": {
        2: "建议使用 'lldp' 表或由用户指定",
        6: "无 YANG 模型支持，建议使用 NETCONF 实时验证"
    },
    "user_approval_required": True
}
```

**优势**:
- 🎯 **消除假阳性**: MPLS 审计场景（设备未启用但 LLM 假装成功）
- 🔍 **动态验证**: 实际查询 SuzieQ/OpenConfig schema 确认表/字段存在
- 📊 **透明度**: 向用户展示哪些任务可靠、哪些需确认
- 🔄 **轻量 Reflection**: 自我识别不确定性，请求人工介入

**HITL 双重审批流程**:
```python
# Phase 1: 执行计划审批（新增）
# 用户输入: Y (批准) | N (中止) | 任意文本 (修改计划)

# Phase 2: 写操作审批（现有 HITL）
# 仅对 feasible_tasks 执行，已通过 schema 验证
```

**交互示例**:
```
============================================================
📋 执行计划（Schema 调研结果）
============================================================
✅ 可执行任务 (3 个):
  - 任务 1: 查询所有设备 device 表
    建议: 使用 'device' 表，字段完整
  - 任务 3: 检查 MPLS 接口配置（interfaces 表）
    建议: 'mplsIp' 字段已确认存在

⚠️ 不确定任务 (2 个):
  - 任务 2: 查询 LDP 配置
    建议: Schema 中无 'ldp' 表，可能需要 'lldp' 或用户指定
  - 任务 5: 检查 labeled-unicast 配置
    建议: 'bgp' 表存在但字段未完全确认

❌ 无法执行任务 (1 个):
  - 任务 6: 查询 YANG 模型标准路径
    建议: SuzieQ 无对应表，建议使用 NETCONF 实时获取

============================================================
请选择操作:
  Y - 批准执行可行任务
  N - 中止执行
  其他 - 输入修改请求（例如：'跳过任务2，使用bgp表执行任务5'）
============================================================
您的决定: 跳过任务2，使用bgp表执行任务5

⏸️  计划已修改，需要重新审批
[显示更新后的执行计划...]
```

**CLI 使用**:
```bash
# 普通模式（默认）- 3 个标准 Workflows
uv run olav.py                          # 交互式
uv run olav.py "查询 R1 接口状态"        # 单次查询

# 专家模式 - 启用 DeepDiveWorkflow
uv run olav.py -e "审计所有边界路由器 BGP 配置"     # -e 短参数
uv run olav.py --expert "跨域故障深度分析"          # --expert 长参数
```

**触发机制**:
- **Manual Trigger**: `-e/--expert` 参数显式启用
- **Auto Detection**: Orchestrator 检测复杂任务关键词自动切换
  - "所有设备"、"批量"、"审计"、"全部"、"所有.*路由器"
  - "递归"、"深入"、"详细分析"、"彻底排查"、"为什么"
  - "从...到..."、"跨..."、"MPLS.*配置"、"BGP.*安全"

**Graph 结构（已实现）**:
```
entry → task_planning_node (LLM 分解任务)
          ↓
schema_investigation_node (调研 schema 可行性) ← 🆕 核心节点
          ↓
      [HITL 中断] → 用户审批/修改计划 ← 🆕 双重审批
          ↓
execute_todo_node (仅执行 feasible_tasks)
          ↓
all done? → final_summary → END
  No ↓
execute_todo_node (next todo)
```

**已解决问题** ✅:
- ✅ MPLS 审计假阳性（Schema Investigation 动态验证）
- ✅ 用户不知道要执行什么（HITL 展示任务描述和建议）
- ✅ 修改计划后未重新显示（已修复 resume 返回 todos + execution_plan）

**待完成功能（Phase 2-3）**:

- [ ] **Phase 3.1: 递归深入实现** ⚠️ **当前占位符** (预计 6-8 小时)
  ```python
  # src/olav/workflows/deep_dive.py: recursive_check_node
  # 当前状态: 返回 "Recursive analysis skipped in Phase 1"
  # 需要实现:
  async def recursive_check_node(self, state):
      failures = [t for t in state['todos'] if t['status'] == 'failed']
      if failures and state['recursion_depth'] < state['max_depth']:
          # 为每个失败任务生成子任务
          sub_query = f"深入分析 {failures[0]['task']} 失败原因"
          # 触发 task_planning 生成子任务
          return {'messages': [HumanMessage(content=sub_query)]}
  ```

- [ ] **Phase 3.2: 批量并行执行** ⚠️ **当前串行** (预计 4-6 小时)
  ```python
  # src/olav/workflows/deep_dive.py: execute_todo_node
  # 当前状态: 单线程执行 next_todo
  # 需要优化:
  async def execute_todo_node(self, state):
      pending = [t for t in state['todos'] if t['status'] == 'pending']
      independent = [t for t in pending if not t['deps']]
      
      # 并行执行前 5 个独立任务
      results = await asyncio.gather(*[
          self._execute_single_todo(todo) for todo in independent[:5]
      ], return_exceptions=True)
  ```

- [ ] **Phase 3.3: 单元测试补充** ⚠️ **当前完全缺失** (预计 6-8 小时)
  - `tests/unit/test_deep_dive_workflow.py` (新文件)
  - 测试任务分解、Schema Investigation、External Evaluator 集成
  - Mock SuzieQ/NETCONF 工具，验证 HITL 中断/恢复

**Reflection/Reflexion 架构评估** (2025-11-23) 🆕:

**对比分析**:
| 维度 | **Reflection（反思）** | **Reflexion（自反射）** | **OLAV 当前** |
|------|----------------------|------------------------|--------------|
| **定义** | 单轮自我评估 + 改进 | 多轮迭代 + 记忆增强 | 轻量 Reflection |
| **组件** | Generator → Critic → Revise | Actor → Evaluator → Memory → Retry | Schema Investigation + HITL |
| **循环次数** | 固定（3 次） | 动态（外部验证） | 1 次（HITL 可触发修改） |
| **记忆机制** | ❌ 无 | ✅ Episodic Memory | ⚠️ 已设计未实现 |
| **外部反馈** | 可选（LLM 自评） | 必需（工具执行结果） | ✅ Schema 验证 + HITL |
| **适用场景** | 写作、报告生成 | 代码生成、故障诊断 | 网络配置审计 |

**OLAV 当前实现**（类 Reflection → Phase 2 进行中）:
- ✅ **Self-Evaluation**: `schema_investigation_node` 自评任务可行性
- ✅ **Human-in-the-Loop Reflection**: HITL 作为外部评估器
- ✅ **Uncertainty Identification**: `uncertain_tasks` + 建议
- ✅ **External Evaluator 基础接入**: 已集成 `ConfigComplianceEvaluator`（**Schema-Aware 动态识别**，无需硬编码协议规则）
- ❌ **缺失 Episodic Memory**: 无跨会话失败案例学习

**建议渐进式接入方案**:

| 阶段 | 实现内容 | 预期效果 | 开发量 | 优先级 |
|------|---------|---------|-------|-------|
| **✅ Phase 1** | 轻量 Reflection（已完成） | Schema 验证 + HITL | **已完成** | ⭐⭐⭐ |
| **✅ Phase 2** | External Evaluator（**动态验证已完成**） | 消除假阳性 | **已完成** | ⭐⭐⭐ **高** |
| **Phase 3** | Episodic Memory（失败案例库） | 跨会话学习 | 5-7 天 | ⭐ 低 |

**Phase 2 已实现: External Evaluator（Schema-Aware 动态验证器）**
```python
# src/olav/evaluators/config_compliance.py
class ConfigComplianceEvaluator:
    async def evaluate(self, task: Dict, execution_output: Dict) -> EvaluationResult:
        """动态验证 - 无需硬编码协议规则
        
        验证策略:
          1. 检查执行状态 (SCHEMA_NOT_FOUND/NO_DATA_FOUND/TOOL_ERROR)
          2. 验证数据存在性 (非空结果)
          3. 字段语义相关性检查 (任务关键词 vs 返回字段)
          4. 保守评分: 数据存在 + 语义相关 = 通过
        
        适用于任意协议/特性，无需添加新规则。
        """
        # 1. 状态检查
        if execution_output.get("status") in {"SCHEMA_NOT_FOUND", "TOOL_ERROR"}:
            return EvaluationResult(passed=False, score=0.0, ...)
        
        # 2. 数据存在性
        if not execution_output.get("data"):
            return EvaluationResult(passed=False, score=0.0, 
                feedback="执行输出无数据")
        
        # 3. 语义相关性 (复用 Deep Dive 的 _validate_field_relevance)
        if not self._validate_field_relevance(
            task["task"], 
            execution_output.get("columns", []),
            execution_output.get("table")
        ):
            return EvaluationResult(passed=False, score=0.3,
                feedback="返回字段与任务语义不匹配")
        
        # 4. 验证通过
        return EvaluationResult(passed=True, score=1.0)
```

**关键优势** - 无需为每个协议添加规则:
- ✅ MPLS/BGP/OSPF/ISIS/QoS/ACL **统一处理**
- ✅ 自动检测字段相关性（`mpls` 任务 → `device` 表 = 不通过）
- ✅ 复用现有 Schema Investigation 反幻觉机制
- ✅ 审计任务空数据 = 失败，查询任务空数据 = 部分通过
**下一步增强方向** (可选，非必需):
1. **真实设备状态对比** (NETCONF/XPath 实时验证):
   ```python
   # 当前: 仅验证工具输出结构
   # 可选增强: 对比真实设备当前状态 vs 历史数据
   if task.get("requires_device_verification"):
       actual = await netconf_tool.get(xpath=task["xpath"])
       if actual != execution_output.get("data"):
           return EvaluationResult(passed=False, 
               feedback="设备实际状态与历史数据不符")
   ```

2. **HITL 质量引导提示**:
   ```python
   # main.py: 审批界面增加引导
   console.print("[bold]质量检查:[/bold]")
   console.print("  - 结果是否完整回答了原始问题？")
   console.print("  - 是否有明显遗漏的检查项？")
   console.print("  - 数据来源是否可靠？（优先 schema 确认的表）")
   ```

**优先级**: P0 (✅ **Phase 1-2 已完成**, ⚠️ **Phase 3 未实现**)  
**剩余工作量**: 
- ✅ Phase 1 (任务分解 + Schema Investigation): **已完成**
- ✅ Phase 2 (Schema-Aware Evaluator): **已完成**
- ❌ Phase 3.1 (递归深入): 6-8 小时 (当前仅占位符)
- ❌ Phase 3.2 (并行执行): 4-6 小时 (当前串行)
- ❌ Phase 3.3 (单元测试): 6-8 小时 (完全缺失)
- Phase 4 (Episodic Memory): 5-7 小时

**下一步**: Deep Dive Phase 3 实现 或 补充单元测试

---

### 2. ntc-templates-schema 索引缺失 - P1

**问题描述**:
- 运行 chat 模式时可能报错: `NotFoundError(404, 'index_not_found_exception', 'no such index', ntc-templates-schema)`
- 影响 CLI Agent 的 Schema-Aware 功能

**待解决**:
- [ ] 验证 `src/olav/etl/ntc_schema_etl.py` 是否已正确运行
- [ ] 如未创建索引，执行 ETL 脚本
- [ ] 或禁用 CLI Agent 对该索引的依赖（降级方案）

**优先级**: P1  
**预计工作量**: 2-4 小时

---

### 3. HITL 审批机制需完善 - P1

**当前状态** (2025-11-23 更新):
- ✅ **基础 CLI HITL 已实现**: `main.py` 在敏感工具调用前进行交互式审批
  - 支持工具: `nornir_tool`, `netconf_tool`, `netbox_api_call`
  - 审批选项: Y (批准) / n (拒绝) / i (查看详情)
- ✅ **Deep Dive HITL**: 执行计划审批 + 修改计划重新审批
- ⚠️ **标准 Workflows 限制**: 
  - 仅在流式输出层拦截，未与 LangGraph 原生 interrupt 集成
  - 不支持参数编辑
  - 无风险分级（所有写操作统一处理）

**Phase 2 增强计划**:
1. **写操作自动检测**: 解析工具参数识别配置/提交/删除类操作
2. **风险评分系统**: Low/Medium/High 三级
   ```python
   risk_rules = {
       "reload|reboot|shutdown": "High",
       "delete|remove|erase": "High", 
       "edit-config|commit": "Medium",
       "get-config|show": "Low"
   }
   ```
3. **参数编辑功能**: JSON 格式编辑后继续执行
4. **批量审批**: 多个工具调用一次性展示
5. **审计日志**: 写入 `olav-audit` 索引
6. **LangGraph 中断集成**: 统一使用 LangGraph `interrupt` 机制

**测试验证**:
```bash
uv run python -m olav.main chat "创建一个测试设备"  # 触发 netbox_api_call
# 期望: 出现审批提示，输入 'n' 能拒绝，'i' 显示参数
```

**优先级**: P1 (安全合规核心)  
**预计工作量**: 
- Phase 2 增强: 8-12 小时
- 审计日志: 4 小时

---

## 🟡 中等优先级任务 (Medium Priority Issues)

### 4. Agent 提示词与工具描述优化 - P2

**问题描述**:
- **SuzieQ 高级功能未被充分利用**: 
  - 内置路由追踪 (`path show`) 未在提示词中说明
  - 拓扑发现 (`topology`) 和健康检查 (`assert`) 缺少示例
- **Nornir CLI Agent 功能受限**:
  - 未实现 Schema-Aware 查询
  - 缺少黑名单机制（高危命令保护）

**待优化**:
1. **SuzieQ 提示词增强** (`config/prompts/agents/root_agent_react.yaml`):
   - 添加 `path show` 路由追踪使用说明
   - 添加 `topology` 拓扑发现示例
   - 添加 `assert` 健康检查案例

2. **CLI Agent 扩展** (`src/olav/tools/nornir_tool.py`):
   - Schema-Aware 命令映射表
   - 黑名单机制（`reload`, `write erase`, `format` 等）
   - 批量命令执行支持

**优先级**: P2  
**预计工作量**: 
- SuzieQ 提示词: 2 小时
- CLI Agent 扩展: 6-8 小时

---

### 5. NetBox 集成未完全验证 - P2

**问题描述**:
- NetBox 作为 Single Source of Truth，但未完整测试
- 缺少设备清单同步验证
- 标签过滤逻辑 (`olav-managed`, `suzieq-monitor`) 未测试

**待验证功能**:
- [ ] 动态拉取设备清单 (`NBInventory`)
- [ ] 设备角色和站点过滤
- [ ] 标签过滤逻辑
- [ ] inventory.csv ↔ NetBox 双向对齐

**优先级**: P2 (影响数据准确性)  
**预计工作量**: 4-6 小时

---

### 6. SuzieQ 高级功能测试 - P2

**当前状态**:
- ✅ Poller 正常运行
- ✅ 数据采集正常（6个设备）
- ✅ 基础查询成功（get/summarize）
- ⚠️ 高级功能待测试

**待测试**:
- [ ] `path show` - 路由追踪
- [ ] `topology` - 拓扑发现
- [ ] `assert` - 健康检查

**优先级**: P2  
**预计工作量**: 2-4 小时

---

### 7. OpenSearch RAG 第三层未实现 - P2

**当前状态**:
- ✅ **第 1 层 (Episodic Memory)**: 已验证
  - 索引: `olav-episodic-memory`
  - 工具: `search_episodic_memory`
- ✅ **第 2 层 (Schema Index)**: 已实现
  - 索引: `openconfig-schema`, `suzieq-schema`, `netbox-schema`, `ntc-templates-schema`
  - 工具: `search_openconfig_schema`, `suzieq_schema_search`
- ❌ **第 3 层 (Documents)**: 待实现
  - 索引: `olav-docs`
  - 工具: `search_documents`
  - 内容: Vendor 手册、RFC、最佳实践文档

**待完成**:
- [ ] 创建 `olav-docs` 索引
- [ ] ETL 脚本加载 `data/documents/` 目录
- [ ] 实现 `search_documents` 工具
- [ ] **Reflexion Memory**: 扩展为失败案例存储（可选）

**优先级**: P2  
**预计工作量**: 8-12 小时（文档检索）+ 5-7 小时（Reflexion Memory，可选）

---

### 8. FastAPI/LangServe 未实现 - P2

**问题描述**:
- `serve()` 命令仅为占位循环
- 缺少 HTTP API 端点
- 无法通过 Web 调用 Agent

**待实现端点**:
- [ ] `GET /health` - 健康检查
- [ ] `POST /chat` - 对话接口
- [ ] `GET /devices` - 设备列表
- [ ] `GET /schema/search` - Schema 查询
- [ ] `POST /agent/invoke` - Agent 调用
- [ ] WebSocket 流式响应

**优先级**: P2 (影响生产部署)  
**预计工作量**: 8-12 小时

---

## 🟢 低优先级任务 (Low Priority Issues)

### 9. 日志系统不完善 - P3

**问题**:
- 只有 stdout 日志，无文件持久化
- 缺少日志轮转 (rotation)
- 缺少结构化日志 (JSON)

**待改进**:
- [ ] 接入 `LoggingConfig.LOG_FILE`
- [ ] 添加 `RotatingFileHandler`
- [ ] 实现 JSON 格式日志
- [ ] 集成 ELK/Loki (可选)

**优先级**: P3  
**预计工作量**: 4 小时

---

### 10. 单元测试覆盖率不足 - P3

**当前状态**: 45 passed / 7 skipped

**重点缺失**:
- ❌ **Deep Dive Workflow 测试完全缺失** (P1 优先级)
  - 无 `tests/unit/test_deep_dive_workflow.py`
  - 需测试: 任务分解、Schema Investigation、External Evaluator、HITL 中断/恢复

**待补充测试**:
- [ ] **Deep Dive Workflow 单元测试** (高优先级)
  - task_planning_node: Mock LLM 生成 Todo List
  - schema_investigation_node: 验证 feasibility 分类
  - execute_todo_node: 验证 External Evaluator 集成
  - recursive_check_node: 验证递归触发逻辑（待 Phase 3.1 实现后）
  - HITL approval flow: 验证中断/恢复机制
- [ ] SuzieQ 工具 Mock 测试
- [ ] OpenSearch RAG 工具测试
- [ ] Nornir Sandbox 执行测试
- [ ] 端到端 API 测试 (需 FastAPI 先完成)

**优先级**: P3 (Deep Dive 测试提升为 P1)  
**预计工作量**: 
- Deep Dive 测试: 6-8 小时 (高优先级)
- 其他测试: 10-12 小时

---

### 11. 审计日志未持久化 - P3

**问题**:
- NETCONF/CLI 执行结果未记录到 OpenSearch
- 缺少操作审计索引
- 无法追溯历史操作

**待实现**:
- [ ] 创建 `olav-audit` 索引
- [ ] 在 `NornirSandbox.execute()` 中写入审计
- [ ] 实现审计查询接口
- [ ] **Reflexion Memory**: 可扩展为失败案例存储

**优先级**: P3 (安全合规需求)  
**预计工作量**: 4-6 小时

---

### 12. 初始化 ETL 无幂等性 - P3

**问题**:
- `olav-init` 重复运行可能造成重复索引
- 缺少 `data/bootstrap/init.ok` 哨兵文件检查

**待改进**:
- [ ] 添加索引存在性检查
- [ ] 实现幂等写入逻辑
- [ ] 添加 `--force-reinit` 参数

**优先级**: P3  
**预计工作量**: 2-3 小时

---

## 📚 相关文档

- `docs/DESIGN.md` - 架构设计说明
- `docs/CHECKPOINTER_SETUP.md` - Checkpointer 配置指南
- `docs/NETBOX_AGENT_HITL.md` - HITL 审批流程
- `QUICKSTART.md` - 快速启动指南
- `README.MD` - 项目总览
- `archive/deprecated_agents/README.md` - 已废弃架构说明

---

## 🎯 下一步行动 (Next Actions)

### 立即执行 (Immediate)
1. ✅ **代码归档清理**: 移动废弃 Agent 到 `archive/deprecated_agents/` ← **已完成**
2. ✅ **Deep Dive Workflow Phase 1**: 基础任务分解 + Schema Investigation ← **已完成**
3. ✅ **修改计划重新审批**: 修复 resume 返回 payload ← **已完成**
4. ✅ **External Evaluator**: Schema-Aware 动态验证器 ← **已完成**
5. ✅ **Legacy Tools 清理**: 移除 suzieq_tool, netbox_inventory_tool, ntc_tool ← **已完成**

### 本周内 (This Week)
6. **Deep Dive Phase 3.1**: 递归深入实现（当前仅占位符）
7. **Deep Dive Phase 3.3**: 补充单元测试（当前完全缺失）
8. 验证 ntc-templates-schema 索引状态
9. SuzieQ 高级功能测试（path show, topology, assert）

### 本月内 (This Month)
10. **Deep Dive Phase 3.2**: 批量并行执行优化
11. HITL Phase 2 增强（风险评分 + 审计日志 + 参数编辑）
12. FastAPI 服务实现
10. OpenSearch 第三层 RAG（文档检索）
11. Reflexion Memory（失败案例学习，可选）

---

## 🔬 架构演进方向 (Architecture Roadmap)

### 当前: 轻量 Reflection ✅
- Schema Investigation（自我评估可行性）
- HITL 双重审批（人工反馈循环）
- 不确定性识别与建议

### 短期: External Evaluator（3-5 天）⭐ **高优先级**
- 已完成：基础评估规则（MPLS、BGP 会话存在性）
- 进行中：扩展更多协议（OSPF、ISIS、ACL、QoS）
- 待办：增加真实设备状态对比（NETCONF/XPath 验证）避免假阳性

### 中期: Episodic Memory（5-7 天）
- 失败案例向量化存储（`olav-episodic-memory`）
- 跨会话学习机制
- 相似任务历史检索

### 长期: 完整 Reflexion（未来规划）
- Actor-Evaluator-Memory 闭环
- 多轮迭代自动改进
- 质量评分与自动重试

**参考**: `archive/langgraph/examples/reflection` & `archive/langgraph/examples/reflexion`

---

**最后更新**: 2025-11-23  
**本次更新**: 
- ✅ Legacy Tools 清理完成 (suzieq_tool, netbox_inventory_tool, ntc_tool)
- ✅ External Evaluator 已完成 (Schema-Aware 动态验证，无需硬编码协议规则)
- ✅ 工具架构标准化: SuzieQ Parquet直读 + NetBox统一API + Nornir执行层
- ✅ 测试验证通过: 45 passed, 7 skipped
- 📋 文档更新: 识别 Deep Dive Phase 3 未实现问题
- ⚠️ **问题识别**:
  - Deep Dive 递归深入/并行执行仅占位符，功能未兑现
  - Deep Dive 单元测试完全缺失
  - README 宣称功能与实际代码不符
- 🎯 **下一优先级**: Deep Dive Phase 3.1 递归实现 或 补充单元测试

---

## 🆕 新功能提案与规划（文档阶段）

本节仅定义需求与验收标准，不包含代码实现。

### 1) 普通模式的「反思（Reflection）」能力评估 - 提升可靠性（草案）

**背景**
- 普通模式（非专家模式）当前依赖固定工作流与 Schema 调研提示，但缺少一次性结果自检。
- 在不引入复杂多轮 Reflexion 的前提下，增加“轻量反思”有助于减少假阳性与遗漏。

**目标**
- 为普通模式在生成最终答复前，增加一轮轻量自检：
  - 使用 Schema-Aware 规则快速核对“数据来源、字段相关性、空结果”的可靠性。
  - 对存在不确定性的回答，附带“置信度说明 + 建议下一步验证方法（可选 HITL）”。

**实施原则**
- 轻量、可选：默认开启，遇到超时或工具失败时自动降级为“提示性告警”。
- 无状态：不引入跨会话记忆，仅基于当次工具结果与 schema 索引。
- 与 HITL 互补：如触发高风险或不确定性，建议进入 HITL 或专家模式。

**验收标准**
- 输出中新增“质量自检”小节，包含：
  - 数据来源列表（SuzieQ/NetBox/设备即时查询等）
  - 字段相关性判断结果（相关/不相关/未知）
  - 置信度评分（Low/Medium/High）与下一步建议
- 普通查询类问题无显著延迟（+1~3s 内）。

**开放问题**
- 是否对“查询类空结果”判定为失败，还是提示为“可能正常（无匹配项）”？
- 是否允许用户通过 `.env` 或 CLI 参数关闭反思自检？

**后续动作（仅文档阶段）**
- 在 `README.MD` 与 `docs/DESIGN.md` 标注“普通模式轻量反思（计划中）”。

---

### 2) 巡检模式（Inspection Mode）- 基于 YAML 的自动巡检与日报（草案）

**目标**
- 用户仅需在 YAML 模板中声明要检查的项目（表/字段/条件/设备集合），Agent 自动：
  1) 解析 YAML → 生成待办（TODO）
  2) 逐项执行（SuzieQ/NETCONF/NetBox 等）
  3) 生成结构化 Markdown 巡检报告（支持按日归档）
  4) 用户可用 cron 或 Windows 计划任务定时执行，实现“每天巡检”

**启用方式（更新）**
- 通过设置变量 `INSPECTION_MODE_ENABLED=true` 激活（默认关闭）
- 配置目录：`INSPECTION_CONFIG_DIR=config/prompts/inspection`
- 报告目录：`INSPECTION_REPORT_DIR=reports/inspection`
- 默认计划文件：`INSPECTION_DEFAULT_PLAN=daily_core_checks.yaml`
- 并行上限：`INSPECTION_MAX_PARALLEL=5`

**YAML 模板目录**
- 所有计划：`config/prompts/inspection/*.yaml`

**示例模板（草案）**
```yaml
_type: inspection_plan
name: daily_core_checks
schedule_hint: daily 08:00
targets:
  namespace: production
  tags: ["core", "olav-managed"]

checks:
  - id: interfaces_down
    title: 接口异常（down/admin-down）
    type: suzieq_query
    table: interfaces
    method: summarize
    filters:
      state: ["down", "adminDown"]
    assert:
      mode: must_be_empty    # 为空则通过
    severity: high
    remediation: 请检查链路/光模块/邻接设备状态

  - id: bgp_session_health
    title: BGP 会话健康
    type: suzieq_query
    table: bgp
    method: summarize
    filters:
      state: ["Established"]
    assert:
      mode: ratio_over_total
      threshold: 0.98        # 通过阈值
    severity: high
    remediation: 低于阈值时检查告警与邻居状态

  - id: netconf_diff
    title: 关键设备配置漂移
    type: netconf_check      # 运行期可选择性支持（HITL）
    xpaths:
      - /interfaces/interface[name=xe-0/0/0]/config
    assert:
      mode: equals_snapshot
      snapshot_ref: baseline-2025-11-01
    severity: medium
```

**执行流程（设想）**
1) 载入 YAML → 校验 schema（缺失字段提前告警）
2) 分解为 TODO 列表（可并行的标记为 independent）
3) 逐项执行并评估（重用 External Evaluator 的“数据存在性 + 字段相关性”）
4) 汇总生成 Markdown 报告：
   - 概览：通过/失败/不确定 统计、合规分
   - 明细：每项检查的结论、证据链接、建议
   - 附录：部分原始数据（表格/JSON 摘要）

**输出位置（建议）**
- `reports/inspection/{plan_name}-{YYYY-MM-DD}.md`

**CLI（草案，仅文档）**
```bash
# 交互式
uv run olav.py --mode inspection --plan config/prompts/inspection/daily_core_checks.yaml

# 非交互，输出指定文件
uv run olav.py --mode inspection \
  --plan config/prompts/inspection/daily_core_checks.yaml \
  --output reports/inspection/daily_core_checks-$(date +%F).md
```

**容器化调度（新增）**
```yaml
services:
  olav-inspection:
    build: .
    environment:
      INSPECTION_MODE_ENABLED: "true"
      INSPECTION_CONFIG_DIR: "config/prompts/inspection"
      INSPECTION_REPORT_DIR: "reports/inspection"
      INSPECTION_DEFAULT_PLAN: "daily_core_checks.yaml"
      INSPECTION_MAX_PARALLEL: 5
    volumes:
      - ./reports/inspection:/app/reports/inspection
      - ./config/prompts/inspection:/app/config/prompts/inspection:ro
    profiles: [inspection]
```
容器内置 cron 每日 08:00 运行默认计划，避免宿主机差异。

**Windows 计划任务（示例，仅文档）**
```powershell
$workDir = "C:\Users\<you>\Documents\code\Olav"
$plan    = "config\prompts\inspection\daily_core_checks.yaml"
$outDir  = "reports\inspection"
$cmd     = "powershell -NoProfile -ExecutionPolicy Bypass -Command \"cd $workDir; if(!(Test-Path $outDir)){New-Item -ItemType Directory -Path $outDir | Out-Null}; uv run olav.py --mode inspection --plan $plan --output $outDir\\daily_core_checks-$(Get-Date -Format yyyy-MM-dd).md\""
schtasks /Create /SC DAILY /ST 08:00 /TN "OLAV Daily Inspection" /TR "$cmd"
```

**Linux/macOS 定时（示例，仅文档）**
```cron
0 8 * * * cd /opt/olav && uv run olav.py --mode inspection --plan config/prompts/inspection/daily_core_checks.yaml --output reports/inspection/daily_core_checks-$(date +\%F).md >> logs/inspection.log 2>&1
```

**验收标准**
- 能从 YAML 成功解析出 N 项检查，逐项执行并生成统一格式的 Markdown 报告。
- 报告包含：统计总览、逐项结论、建议、关键证据（表格/字段列举）。
- 失败/不确定项高亮，附带下一步建议（可选进入 HITL）。

**开放问题（更新）**
- `netconf_check` 等需要 HITL 的写/读敏感操作如何在计划任务中安全运行？
- 巡检报告是否需要同时生成 JSON 以便机读？
- 是否需要“阈值基线快照”的管理命令（导入/导出）？
- 是否需要容器健康检查与报告生成失败重试策略？

**后续动作（仅文档阶段）**
- 新增 `docs/INSPECTION_MODE.md` 详细规格（本次已添加）。
- 在 `docs/DESIGN.md` 与 `docs/WORKFLOWS_INTEGRATION.md` 标注巡检模式对接点。
