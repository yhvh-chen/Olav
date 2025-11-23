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
2. 扩展 Deep Dive Phase 2：递归/并行执行、真实设备状态比对（NETCONF/XPath）、Episodic Memory。
3. ~~标记并跳过所有依赖 legacy 架构的测试，逐步迁移到新 orchestrator。~~ ✅ 已完成
4. ~~优化测试环境路径与包结构，确保 pytest 可直接运行所有单元测试。~~ ✅ 已完成
5. ~~垃圾代码与 ghost 代码清理。~~ ✅ 已完成
6. ~~Legacy Tools 清理（suzieq_tool.py, netbox_inventory_tool.py, ntc_tool.py）。~~ ✅ 已完成
7. 文档同步：持续更新架构演进、Known Issues、测试覆盖率。
8. TODO 注释处理：init_schema.py (YANG 解析 - 低优先级占位符)。

## 下一项任务规划

**目标：扩展 Deep Dive Phase 2 - 递归/并行执行与设备状态比对。**

### 步骤：
1. 实现递归任务分解（最大深度 3 层），支持子任务动态生成。
2. 添加并行执行支持：批量审计场景（30+ 设备）使用 asyncio.gather()。
3. 集成真实设备状态比对（NETCONF XPath 查询实际值 vs 期望值）。
4. 添加进度跟踪与恢复能力（基于 PostgreSQL Checkpointer state）。
5. 编写 Deep Dive Phase 2 测试用例（递归、并行、状态比对）。
6. 更新文档：Deep Dive 架构图、递归逻辑流程、并行执行策略。

**后续任务：**
Episodic Memory 架构、Reflexion 模式完整实现、真实设备集成测试。
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
- ⚠️ 待完善递归深入和并行优化（Phase 2-3）

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

- [ ] **Phase 2: 递归深入** (预计 8 小时)
  ```
  Todo 1: 检查 BGP 状态 → 发现 NotEstd
    ↓ (自动触发)
  Todo 1.1: 检查接口状态 → 发现 down
    ↓
  Todo 1.1.1: 查询告警历史 → 定位根因
  ```
  - 限制: `max_depth=3` 防止无限递归

- [ ] **Phase 3: 批量并行执行** (预计 6 小时)
  ```python
  # 并发执行独立任务
  results = await asyncio.gather(*[
      execute_todo(todos[i]) for i in range(5)  # 前 5 个无依赖任务
  ])
  ```

- [ ] **Phase 3: 结果聚合与报告** (预计 4 小时)
  - 表格化输出（设备 × 检查项 矩阵）
  - 合规百分比统计
  - 异常列表高亮

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
- ✅ **External Evaluator 基础接入**: 已集成 `ConfigComplianceEvaluator`（支持 `mpls_audit` / `bgp_session_check` 规则，自动标记 evaluation_passed/evaluation_score）
- ❌ **缺失 Episodic Memory**: 无跨会话失败案例学习

**建议渐进式接入方案**:

| 阶段 | 实现内容 | 预期效果 | 开发量 | 优先级 |
|------|---------|---------|-------|-------|
| **✅ Phase 1** | 轻量 Reflection（已完成） | Schema 验证 + HITL | **已完成** | ⭐⭐⭐ |
| **🚧 Phase 2** | External Evaluator（配置审计 基础版已接入） | 消除假阳性（进行中） | 3-5 天 | ⭐⭐⭐ **高** |
| **Phase 3** | Episodic Memory（失败案例库） | 跨会话学习 | 5-7 天 | ⭐ 低 |

**Phase 2 优先实现: External Evaluator（客观验证器）** （当前状态：核心模块与 Deep Dive 集成完成，后续增加更多协议规则与设备真实对比）
```python
# 新文件: src/olav/evaluators/config_compliance.py
class ConfigComplianceEvaluator:
    async def evaluate(self, task: TodoItem, result: dict) -> EvaluationResult:
        """基于实际设备状态验证任务完成度"""
        if task["task_type"] == "mpls_audit":
            # 实际验证 MPLS 配置
            actual = await netconf_tool.get(xpath="/mpls/global/config")
            expected = result.get("expected_mpls_status")
            
            if actual != expected:
                return EvaluationResult(
                    passed=False,
                    feedback=f"预测 MPLS {expected}，实际为 {actual}",
                    score=0.0
                )
            return EvaluationResult(passed=True, score=1.0)
```

**立即可做的轻量优化**:
1. **在 `execute_todo_node` 中增加结果验证**:
   ```python
   # 当前：执行后直接标记 completed
   result = await suzieq_query.invoke(...)
   todo["status"] = "completed"
   
   # 改进：检查结果有效性
   if result.get("data") and len(result["data"]) > 0:
       todo["status"] = "completed"
   else:
       todo["status"] = "failed"
       todo["failure_reason"] = "查询无数据，可能表名错误"
   ```

2. **HITL 中注入"质量反问"**:
   ```python
   # main.py: 审批界面增加引导
   console.print("[bold]质量检查:[/bold]")
   console.print("  - 结果是否完整回答了原始问题？")
   console.print("  - 是否有明显遗漏的检查项？")
   console.print("  - 数据来源是否可靠？（优先 schema 确认的表）")
   ```

**优先级**: P0 (Phase 1 已完成, Phase 2 高优先级)  
**剩余工作量**: 
- Phase 2 (Evaluator + 递归): 11-13 小时
- Phase 3 (并行 + 报告 + Memory): 15-18 小时

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

**当前状态**: 11 passed / 9 skipped

**待补充测试**:
- [ ] SuzieQ 工具 Mock 测试
- [ ] OpenSearch RAG 工具测试
- [ ] Nornir Sandbox 执行测试
- [ ] Deep Dive Schema Investigation 测试
- [ ] 端到端 API 测试 (需 FastAPI 先完成)

**优先级**: P3  
**预计工作量**: 10-12 小时

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

### 本周内 (This Week)
4. **External Evaluator 扩展**: 已接入基础评估（继续增加协议/字段规则）
5. 验证 ntc-templates-schema 索引状态
6. SuzieQ 高级功能测试（path show, topology, assert）

### 本月内 (This Month)
7. Deep Dive Workflow Phase 2（递归深入 + 并行执行）
8. HITL Phase 2 增强（风险评分 + 审计日志 + 参数编辑）
9. FastAPI 服务实现
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
- ✅ 工具架构标准化: SuzieQ Parquet直读 + NetBox统一API + Nornir执行层
- ✅ 测试验证通过: 45 passed, 7 skipped
- 🔧 保留 inventory_manager.py (CSV导入功能，未来可能使用)
- 📋 TODO清理: init_schema.py YANG解析占位符保留 (低优先级)
