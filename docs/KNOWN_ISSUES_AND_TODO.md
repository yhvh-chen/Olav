# OLAV 已知问题与待办事项

> **更新日期**: 2025-11-22  
> **版本**: v0.1.0-alpha  
> **状态**: 核心功能可用，仅保留待解决问题

---

## 🔴 严重问题 (Critical Issues)

### 1. 架构优化：迁移到 ReAct 模式 ✅ **RESOLVED** (2025-11-22)

**问题诊断**:
- **旧架构 (DeepAgents + SubAgent)**: 
  - 响应时间: 60-120 秒（简单查询）
  - 根本原因: 多层 LLM 调用链（Root → SubAgent → Root = 4-14 次调用）
  - 缺乏透明度: 无法追溯为什么选择某个 SubAgent
  - 幻觉风险: LLM 可能选择错误的 SubAgent

**解决方案: 纯 ReAct 架构** ⭐

**架构实现**:
```python
# 单一 ReAct Root Agent（工具直调，无 SubAgent）
root_agent_react = create_deep_agent(
    llm=model,
    tools=[
        suzieq_query,              # SuzieQ 查询
        suzieq_schema_search,      # SuzieQ Schema 检索
        search_episodic_memory,    # RAG 历史路径
          netbox_schema_search,      # NetBox API 检索
        search_openconfig_schema,  # RAG OpenConfig Schema
       system_prompt=react_prompt,    # DeepAgents 自动管理工具调用
       checkpointer=checkpointer,
       subagents=[],                  # 空列表 = 扁平架构（关键）
       interrupt_on={"netconf_tool": True, "cli_tool": True},  # HITL
        netbox_api_call,           # NetBox 管理
    ],
    prompt=react_prompt_template,  # Thought → Action → Observation 循环
    **实际性能表现** 🎯:
    - **简单查询** ("查询接口状态"): 
      - ReAct: **16.3 秒** ✅
      - Legacy: 72.5 秒
      - **提升 77.5%** (超过预期 64%)
1. **性能提升**:
    - **工具调用**: 
      - 单步完成（无冗余思考）
      - 正确选择 `suzieq_query(table='interfaces', method='summarize')`
      - 输出专业简洁（222 接口统计，91% Up）
2. **透明度提升**:
    **实施结果**:
3. **降低幻觉**:
    **Phase 1: 创建 ReAct Root Agent** ✅
    - ✅ 创建 `src/olav/agents/root_agent_react.py`
    - ✅ 编写 `config/prompts/agents/root_agent_react.yaml`（DeepAgents 格式）
    - ✅ 保留现有 `root_agent.py` 作为 `root_agent_legacy.py`
    - ✅ 添加 `--agent-mode` 参数（`react` / `legacy`）
    - ✅ 修复 SuzieQ 工具读取 `coalesced/` 目录
4. **架构简化**:
    **Phase 2: 性能验证** ✅
    - ✅ 初步测试: "查询接口状态" 性能提升 77.5%
    - ✅ Prompt 效果验证: 单步完成，无冗余思考
    - ✅ 创建 `scripts/benchmark_agents.py` 基准测试脚本
   - 单一 Prompt 维护（vs 6+ 个 SubAgent Prompt）
    **Phase 3: 优化与部署** 🔄 (进行中)
    - [ ] 完整基准测试（100 个查询）
    - [ ] 复杂查询测试（多步骤、降级策略）
    - [ ] 文档更新（README.md、QUICKSTART.md）
    - [ ] 设置 ReAct 为默认模式
  Observation: 工具结果
    **关键技术要点**:
    1. **DeepAgents 原生格式**: 不使用 LangChain ReAct 专用变量（`tools`, `tool_names`, `agent_scratchpad`, `input`），让 DeepAgents 自动管理
    2. **Coalesced 数据**: SuzieQ 工具优先读取 `coalesced/` 目录（优化后的 Parquet 数据）
    3. **扁平架构**: `subagents=[]` 实现零 SubAgent 层级，直接工具调用
  Thought: 我现在知道最终答案了
    **结论**: ✅ ReAct 架构成功实现，性能显著提升，建议作为默认模式。
  Final Answer: 最终答案

  策略:
  1. 简单查询 → 2-3 轮完成（直接 suzieq_query）
  2. 复杂任务 → 先 Thought 分解步骤
  3. 降级策略 → NETCONF 失败时用 CLI
  4. 写操作 → 触发 HITL 审批
```

**风险评估**:
- ⚠️ ReAct Prompt 复杂度高（需精心设计格式）
- ⚠️ LLM 可能不遵循 Thought → Action 格式（需 `handle_parsing_errors=True`）
- ✅ 可通过 A/B 测试验证效果（保留旧架构对照）

**废弃方案**:
- ❌ Simple/PM 双架构: ReAct 自带复杂度自适应，无需预先分流
- ❌ ReAct + SubAgent 混合: 性能最差（结合两者缺点）

**优先级**: P0 (核心架构重构)  
**预计工作量**: 
- Phase 1 实现: 8-12 小时
- Phase 2 测试: 8 小时
- Phase 3 优化: 8 小时
- **总计: 24-28 小时**

---

### 2. 性能瓶颈分析（已诊断，待 ReAct 方案解决）

**根本原因** (已确认):
- DeepAgents 多层委托: Root → RAG → SuzieQ → Root（4-14 次 LLM 调用）
- PostgreSQL Checkpointer 写开销: 每次状态变更 0.5-2s
- 缺少缓存: OpenSearch 查询、LLM 响应未缓存

**解决方案**: 采用 ReAct 单 Agent 架构（见问题 1）

**暂时缓解措施** (如需保留旧架构):
1. **LangChain Studio 剖析**: 
   ```bash
   uv add langgraph-cli[inmem]
   langgraph dev --debug-port 5678
   ```
2. **Redis 缓存**: 缓存 LLM 响应和 SuzieQ 查询结果
3. **更快 LLM**: 切换到 gpt-4o-mini（50% 速度提升）

**优先级**: P0 (通过问题 1 的 ReAct 方案解决)  
**预计工作量**: 已包含在问题 1 中

---

### 3. Windows 平台 ProactorEventLoop 兼容性

**问题描述**:
- `psycopg` 异步模式在 Windows 默认事件循环下报错
- 错误: `NotImplementedError: Interrupting wait_for() is not supported on Windows with ProactorEventLoop`

**解决方案** (已应用):
```python
# 所有异步脚本开头添加
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

**影响文件**:
- ✅ `scripts/test_netbox_hitl.py` - 已修复
- ✅ `src/olav/main.py` - 已修复
- ⚠️ 需检查其他异步脚本

**优先级**: P1 (已修复，需验证覆盖率)  
**预计工作量**: 1 小时

---

### 4. ntc-templates-schema 索引缺失

**问题描述**:
- 运行 chat 模式时报错: `NotFoundError(404, 'index_not_found_exception', 'no such index', ntc-templates-schema)`
- 影响 Nornir CLI Agent 功能

**待解决**:
- [ ] 创建 `ntc-templates-schema` OpenSearch 索引
- [ ] 编写 ETL 脚本加载 NTC templates 数据
- [ ] 或禁用 CLI Agent 对该索引的依赖

**优先级**: P1  
**预计工作量**: 2-4 小时

---

## 🟡 中等问题 (Medium Priority Issues)

### 5. Agent 提示词与工具描述优化

**问题描述**:
- **SuzieQ 高级功能未被利用**: 
  - SuzieQ 内置路由追踪功能（`path show`）可以一次性查询完整路径
  - 当前 Agent 采用"一跳跳查询"方式，多次调用 `routes` 表效率低下
  - 示例: 查询 "192.168.20.101 能否访问 192.168.10.101" 应直接调用 `path show`，而非 4 次独立查询
- **SubAgent 描述仍需优化**:
  - 虽然已将 suzieq_agent 描述从"分析历史数据"改为"查询设备状态、接口、BGP..."，但仍不够具体
  - 缺少对 SuzieQ 高级功能的提示（如 path show、topology、assert）
- **Nornir CLI Agent 功能受限**:
  - 当前未实现 Schema-Aware 查询（只能执行预定义命令）
  - 缺少黑名单机制（高危命令保护）
  - 不支持批量命令执行（需多次调用）

**待优化内容**:

1. **SuzieQ Agent 提示词增强** (`config/prompts/agents/suzieq_agent.yaml`):
   ```yaml
   ## 高级分析功能
   
   - **路径追踪** (path show): 
     - 一次性查询完整路由路径，比手动查询每跳更高效
     - 示例: `suzieq_query(table='path', method='show', src='192.168.20.101', dest='192.168.10.101')`
   
   - **拓扑发现** (topology):
     - 自动构建 LLDP/CDP 拓扑图
     - 示例: `suzieq_query(table='topology', method='get')`
   
   - **健康检查** (assert):
     - 批量验证网络状态（BGP 邻居、接口状态、路由数量）
     - 示例: `suzieq_query(table='bgp', method='assert', status='Established')`
   ```

2. **Nornir CLI Agent 功能扩展** (`src/olav/tools/nornir_tool.py` + `config/prompts/agents/cli_agent.yaml`):
   - **Schema-Aware 支持**: 
     - 集成设备平台的命令映射表（类似 SuzieQ Schema）
     - 允许 LLM 查询 "查看接口状态的命令是什么？" → `show interfaces status`
   - **黑名单机制**:
     ```python
     BLACKLIST_COMMANDS = [
         r"^reload",           # 设备重启
         r"^write\s+erase",    # 擦除配置
         r"^format\s+flash",   # 格式化存储
         r"^delete\s+/force",  # 强制删除
     ]
     ```
   - **批量命令执行**:
     ```python
     @tool
     def nornir_cli_batch(
         commands: list[str],  # 支持多条命令
         devices: list[str],
         stop_on_error: bool = False
     ):
         """Execute multiple CLI commands in sequence"""
     ```

3. **Root Agent 提示词补充** (`config/prompts/agents/root_agent.yaml`):
   - 在场景示例中添加 SuzieQ 高级功能的使用案例
   - 明确说明何时使用 CLI Agent（NETCONF 不可用或需执行特殊命令）

**优先级**: P1 (影响 Agent 智能化水平)  
**预计工作量**: 
- SuzieQ 提示词优化: 2 小时
- Nornir CLI 功能扩展: 6-8 小时（Schema-Aware + 黑名单 + 批量执行）

---

### 6. HITL 审批机制需完善

**当前状态**:
- ✅ **配置已完成**: `interrupt_on` 已简化为 `{"netbox_api_call": True, "import_devices_from_csv": True}`
- ❌ **测试失败**: `scripts/test_netbox_hitl.py` 运行失败，Agent 未尝试执行写操作
- ⚠️ **CLI 模式不支持交互**: `main.py` 的 chat 命令无 HITL 处理逻辑，写操作会挂起

**最新进展 (2025-11-22 更新)**:
- ✅ 基础 CLI HITL 审批环节已实现 (`main.py`): 在 AIMessage 发出敏感工具调用 (`nornir_tool`, `netconf_tool`, `netbox_api_call`) 前进行交互式审批 (Y/n/i)。
- ✅ 拒绝时立即终止当前查询并返回安全中止提示。
- ⚠️ 现阶段为“前置启发式”审批：基于工具名称判断风险，尚未结合真实写操作解析和风险分级。
- ⚠️ 暂不支持参数编辑/继续流控制（计划在二阶段实现）。
- ⚠️ 未与 LangGraph 原生 interrupt/resume 状态融合，仅在流式解析层拦截。

**CLI HITL 基础实现特点**:
| 能力 | 状态 | 说明 |
|------|------|------|
| 敏感工具名称匹配 | ✅ | `nornir_tool`, `netconf_tool`, `netbox_api_call` |
| 同步终端审批 | ✅ | 阻塞等待用户输入 Y/n/i |
| 拒绝立即中止 | ✅ | 返回提示，不执行后续工具流 |
| 查看详情 (i) | ✅ | JSON 格式展示工具参数 |
| 参数编辑 | ❌ | 预留占位，后续添加 |
| 风险分级 (低/中/高) | ❌ | 后续基于命令/操作类型判定 |
| 多工具批量审批 | ❌ | 逐条审批，后续支持汇总视图 |
| 与 interrupt_on 集成 | ❌ | 目前未调用 LangGraph resume 机制 |

**下一阶段增强 (Phase 2)**:
1. 写操作检测：解析工具参数自动识别“配置/提交/删除”类操作。
2. 风险评分：根据操作类型 + 影响范围生成 risk_level (Low/Medium/High)。
3. 参数编辑：允许用户以 JSON 输入修改字段后继续执行。
4. 多工具合并审批：同一批次多个写操作一次性展示与批准。
5. 内置日志与审计：审批决策写入 `olav-audit` 索引 (operation, decision, actor, timestamp)。
6. LangGraph 原生中断融合：利用中断状态 `resume=approved/rejected/edited` 反馈给 Agent。

**Phase 2 实施任务清单**:
- [ ] 工具参数分类：区分 read/write；在工具包装层标记 `operation_type`。
- [ ] 风险引擎：简单规则集（如包含 `delete`, `commit`, `reload` → High）。
- [ ] 审批数据结构：`{tool, args, risk, impact, proposed_changes}`。
- [ ] 参数编辑 UI：支持 JSON 验证与回填。
- [ ] 审计写入：新增 `audit_logger` 在批准/拒绝时记录。
- [ ] LangGraph resume 集成：在拒绝/编辑时调用底层中断恢复 API。
- [ ] 批量审批缓冲：缓存一批工具调用后统一呈现 (可配置批大小 N)。

**短期验证步骤**:
```bash
uv run python -m olav.main chat "创建一个测试设备"  # 触发 netbox_api_call
uv run python -m olav.main chat "下发接口配置到 R1"  # 触发 nornir_tool
```
期望：出现 HITL 审批提示，输入 `n` 能安全拒绝，`i` 显示参数详情。

**当前限制说明**:
> 该版本 HITL 仅在流式输出层拦截工具调用，无法阻止已经进入执行阶段的异步操作。后续通过 LangGraph 原生中断实现更精细的暂停与恢复。

**问题分析**:
1. **测试脚本失败原因**:
   - LLM 可能未理解应该调用 NetBox 写操作工具
   - NetBox 工具描述不够清晰（需优化 `netbox_api_call` 的 description）
   - 测试 prompt "创建一个测试设备" 可能不够明确
2. **CLI 无 HITL 支持**:
   - 当前 `main.py` 使用 `agent.ainvoke()`，遇到中断会挂起
   - 需要改为 `agent.astream()` + 检查 `state.next` + 用户确认
3. **ChatUI 未实现**:
   - `src/olav/ui/chat_ui.py` 可能没有 HITL 交互界面
   - 需要 Web UI 展示审批界面（操作详情、决策按钮）

**待完成任务**:

1. **修复 CLI 的 HITL 处理** (`src/olav/main.py`):
   
   **方案 A: 终端 Y/N 菜单（推荐）**:
   ```python
   # 简化版 - 终端交互式审批
   async for event in agent.astream(...):
       state = agent.get_state(config)
       if state.next:  # 检测到中断
           # 展示操作摘要
           print("\n" + "="*60)
           print("🔔 需要审批的操作")
           print("="*60)
           print(f"工具: {state.next}")
           print(f"操作类型: {state.values.get('pending_tool')}")
           print(f"影响范围: {state.values.get('impact_summary')}")
           print(f"风险评估: {state.values.get('risk_level', 'Medium')}")
           print("="*60)
           
           # Y/N 菜单
           while True:
               decision = input("\n是否批准此操作？[Y/n/e(编辑)/i(详情)]: ").strip().lower()
               
               if decision in ['y', 'yes', '']:
                   print("✅ 已批准，继续执行...")
                   agent.update_state(config, Command(resume="approved"))
                   break
               elif decision in ['n', 'no']:
                   print("❌ 已拒绝，操作取消")
                   agent.update_state(config, Command(resume="rejected"))
                   return
               elif decision == 'e':
                   # 编辑参数（高级功能）
                   print("\n编辑模式（输入 JSON 格式修改参数，或直接回车保持原样）:")
                   new_params = input("> ")
                   if new_params.strip():
                       # TODO: 解析并更新参数
                       print("⚠️  编辑功能待实现")
                   continue
               elif decision == 'i':
                   # 显示详细信息
                   print("\n详细操作信息:")
                   print(json.dumps(state.values, indent=2, ensure_ascii=False))
                   continue
               else:
                   print("⚠️  无效选择，请输入 Y/n/e/i")
   ```
   
   **方案 B: 三选项模式（完整版）**:
   ```python
   # 完整版 - 支持 Approve/Edit/Reject
   decision = input("决策 [approve/edit/reject]: ").strip().lower()
   
   if decision == "approve":
       agent.update_state(config, Command(resume="approved"))
   elif decision == "reject":
       agent.update_state(config, Command(resume="rejected"))
   elif decision == "edit":
       # 交互式编辑参数
       edited_params = interactive_edit(state.values.get('tool_params'))
       agent.update_state(config, Command(resume={"action": "edit", "params": edited_params}))
   ```
   
   **实现建议**:
   - 优先使用方案 A（Y/N 菜单）- 用户体验更好，符合终端交互习惯
   - 默认选项为 Y（直接回车=批准）- 适合信任场景
   - 提供 'i' 选项查看详情 - 满足审慎用户需求
   - 'e' 编辑功能可选实现 - 降低初期开发复杂度

2. **优化 NetBox 工具描述** (`src/olav/tools/netbox_tool.py`):
   - 明确说明 `netbox_api_call` 可以执行写操作
   - 添加示例: "创建设备: netbox_api_call(endpoint='dcim/devices', method='POST', data={...})"

3. **实现 ChatUI 的 HITL 界面** (`src/olav/ui/chat_ui.py`):
   - 检测 LangGraph 中断
   - 展示审批卡片（操作摘要、影响范围、风险评估）
   - 提供 Approve/Edit/Reject 按钮

4. **编写可复现的 HITL 测试**:
   - 创建 `scripts/test_hitl_simple.py`
   - 直接调用 NetBox 写操作工具（绕过 LLM 理解问题）
   - 验证 `interrupt_on` 配置生效

**优先级**: P1 (安全合规核心功能)  
**预计工作量**: 
- CLI HITL 支持: 4 小时
- ChatUI HITL 界面: 8-12 小时（需前端交互）
- 简化测试脚本: 2 小时

---

### 7. NetBox 集成未完全验证

**问题描述**:
- NetBox 作为 Single Source of Truth，但未完整测试
- 缺少设备清单同步验证
- 标签过滤逻辑 (`olav-managed`, `suzieq-monitor`) 未测试

**待验证功能**:
- [ ] 动态拉取设备清单 (`NBInventory`)
- [ ] 设备角色和站点过滤
- [ ] 标签过滤逻辑
- [ ] inventory.csv ↔ NetBox 双向对齐

**优先级**: P1 (影响数据准确性)  
**预计工作量**: 4-6 小时

---

### 8. SuzieQ 数据采集 (高级功能待测试)

**当前状态**:
- ✅ Poller 正常运行
- ✅ 数据采集正常（6个设备，interfaces/routes/bgp/ospf/arpnd等表）
- ✅ 基础查询成功（get/summarize方法已测试）
- ⚠️ 高级功能待测试（path show, topology, assert）

**待测试**:
- [ ] `path show` - 路由追踪
- [ ] `topology` - 拓扑发现
- [ ] `assert` - 健康检查

**优先级**: P2  
**预计工作量**: 2-4 小时

---

### 9. OpenSearch RAG 索引未完全验证

**当前状态**:
- ✅ **第 1 层 RAG (Episodic Memory)**: 已修复并验证
  - 索引: `olav-episodic-memory`
  - 工具: `search_episodic_memory`
- ⚠️ **第 2 层 RAG (Schema Index)**: 待测试
  - 索引: `openconfig-schema`, `suzieq-schema`
  - 工具: `search_openconfig_schema`, `suzieq_schema_search`
- ⚠️ **第 3 层 RAG (Documents)**: 待实现
  - 索引: `olav-docs`
  - 工具: `search_documents`

**待完成**:
- 第 3 层实现: 8-12 小时

---

### 10. FastAPI/LangServe 未实现

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

## 🟢 低优先级问题 (Low Priority Issues)

### 11. 日志系统不完善

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

### 12. 单元测试覆盖率不足

**当前状态**: 11 passed / 9 skipped

**待补充测试**:
- [ ] SuzieQ 工具 Mock 测试
- [ ] OpenSearch RAG 工具测试
- [ ] Nornir Sandbox 执行测试
- [ ] 端到端 API 测试 (需 FastAPI 先完成)

**优先级**: P3  
**预计工作量**: 8-10 小时

---

### 13. 审计日志未持久化

**问题**:
- NETCONF/CLI 执行结果未记录到 OpenSearch
- 缺少操作审计索引
- 无法追溯历史操作

**待实现**:
- [ ] 创建 `olav-audit` 索引
- [ ] 在 `NornirSandbox.execute()` 中写入审计
- [ ] 实现审计查询接口

**优先级**: P3 (安全合规需求)  
**预计工作量**: 4-6 小时

---

### 14. 初始化 ETL 无幂等性

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

---

**最后更新**: 2025-11-22  
**本次更新**: 清理已完成项目，仅保留待解决问题
