# Phase B 实施计划：CLI降级 + 存档代码复用

**计划创建日期**: 2025-11-25  
**预计完成时间**: Week 2-3 (3-4 work days)  
**负责人**: AI Coding Agent  
**优先级**: P1 (Critical for Architecture Completeness)

---

## 零、前置条件检查

### 0.1 代码提交状态
- ✅ **最新提交**: `f019a3b` - "test: add comprehensive unit tests for refactored tools and workflows"
- ✅ **工作区状态**: Clean (所有变更已提交)
- ✅ **测试覆盖**: 8个新单元测试文件 (100+ test cases)

### 0.2 P0 Production Blockers 修复状态
在开始Phase B前，必须先完成以下3个P0修复（预计0.7天）：

| Issue | 优先级 | 预计时间 | 状态 |
|-------|--------|----------|------|
| Issue 1: invoke endpoint timeout | P0 | 0.5天 | ⚠️ **待修复** |
| Issue 2: WWW-Authenticate header | P0 | 0.1天 | ⚠️ **待修复** |
| Issue 3: CLI Client server_url | P0 | 0.1天 | ⚠️ **待修复** |

**修复顺序**: Issue 2 → Issue 3 → Issue 1 (由易到难)

### 0.3 轻量代码清理（预计0.3天）
- 清理15个warnings (parallel_tool_calls, config_schema deprecation)
- 移除archive/deprecated_agents/未使用导入
- **不进行大规模重构**（新功能完成后统一重构）

---

## 一、Phase B.1: CLI降级支持实现（2-3天）

### 1.1 任务概述
**目标**: 实现单一 `cli_tool`，支持NETCONF连接失败时的CLI SSH降级  
**架构原则**: **NOT dual-agent**（比原设计更简洁），单工具多参数  
**Schema-Aware**: 运行时ntc-template匹配，**不预建索引**（避免维护负担）

### 1.2 存档代码复用计划

#### 1.2.1 TemplateManager 核心逻辑（300+ lines from `baseline_collector.py`）

**源文件**: `archive/baseline_collector.py` (lines 150-400)

**可复用组件**:
```python
class TemplateManager:
    def __init__(self, template_dir: Path):
        """扫描.backup.textfsm文件"""
        self._templates = self._scan_templates()
    
    def _parse_command_from_filename(self, filename: str) -> str:
        """从文件名提取命令
        示例: cisco_ios_show_running.backup.textfsm → "show running-config"
        """
        # 复用此逻辑，用于运行时模板匹配
    
    def _is_template_empty(self, template_path: Path) -> bool:
        """检测空模板（仅注释）"""
        # 避免使用空模板导致解析失败
    
    def get_commands_for_platform(self, platform: str) -> List[str]:
        """平台命令映射
        支持: cisco_ios, cisco_nxos, arista_eos, juniper_junos, huawei_vrp
        """
        # 91个标准cisco_ios命令 + 平台fallback机制
```

**复用策略**:
1. **直接迁移**: `_parse_command_from_filename()` 逻辑不变
2. **适配修改**: `_scan_templates()` 改为动态调用ntc-templates库
3. **新增功能**: 运行时 `match_template(platform, command)` 函数

#### 1.2.2 Blacklist 机制（100+ lines from `baseline_collector.py`）

**源文件**: `archive/baseline_collector.py` (lines 200-250)

**可复用组件**:
```python
class TemplateManager:
    def _load_blacklist(self) -> Set[str]:
        """从config/cli_blacklist.yaml加载危险命令"""
        # traceroute, reload, delete, clear等命令
    
    def filter_safe_commands(self, commands: List[str]) -> List[str]:
        """过滤危险命令"""
        # 确保CLI工具不执行破坏性操作
```

**复用策略**:
1. **直接集成**: 将blacklist逻辑迁移到 `CLITool.execute()`
2. **HITL集成**: 危险命令触发HITL approval（而非直接拒绝）
3. **配置文件**: 复用 `config/cli_blacklist.yaml`

### 1.3 实现步骤（分3个子任务）

#### Step 1.3.1: 创建CLITool基础框架（0.5天）

**文件**: `src/olav/tools/cli_tool.py`（新建）

```python
from typing import Literal, Optional, List
from olav.tools.base import BaseTool, ToolOutput
from olav.tools.adapters import CLIAdapter
from olav.execution.backends.nornir_sandbox import NornirSandbox

class CLITool(BaseTool):
    """Schema-Aware CLI Tool with TextFSM runtime matching.
    
    Parameters:
        - device: str (required) - NetBox设备名
        - command: str (optional) - show命令
        - config_commands: List[str] (optional) - 配置命令列表
        - platform: str (optional) - 从NetBox inventory注入
        - use_textfsm: bool (default True) - 是否尝试TextFSM解析
    
    HITL Trigger: config_commands 非空时
    """
    
    name = "cli_execute"
    description = "Execute CLI commands via SSH (fallback when NETCONF unavailable)"
    
    def __init__(self, sandbox: Optional[NornirSandbox] = None):
        self._sandbox = sandbox
        self._adapter = CLIAdapter()
        self._template_manager = TemplateManager()  # 从存档复用
    
    async def execute(
        self,
        device: str,
        command: Optional[str] = None,
        config_commands: Optional[List[str]] = None,
        platform: Optional[str] = None,
        use_textfsm: bool = True,
        **kwargs
    ) -> ToolOutput:
        # 参数验证
        if not command and not config_commands:
            return ToolOutput(
                source="cli",
                device=device,
                data=[{"status": "PARAM_ERROR", "message": "Must provide command or config_commands"}],
                error="Missing required parameter",
            )
        
        # Blacklist检查（从存档复用）
        if config_commands:
            config_commands = self._template_manager.filter_safe_commands(config_commands)
        
        # 运行时模板匹配（从存档复用逻辑）
        if use_textfsm and command:
            template_name = self._template_manager.match_template(platform, command)
        
        # 执行命令（通过NornirSandbox）
        result = await self.sandbox.execute_cli_command(
            device=device,
            command=command,
            platform=platform,
            template=template_name if use_textfsm else None,
        )
        
        # 适配器规范化输出
        return self._adapter.to_tool_output(result, device=device)
```

**测试文件**: `tests/unit/test_cli_tool.py`（新建）

#### Step 1.3.2: 集成TemplateManager（1.5天）

**文件**: `src/olav/tools/cli_template_manager.py`（新建）

**迁移任务**:
1. ✅ 从 `archive/baseline_collector.py` 提取 `TemplateManager` 类（300+ lines）
2. ✅ 适配ntc-templates库动态调用（替代静态.backup.textfsm扫描）
3. ✅ 实现 `match_template(platform: str, command: str) -> Optional[str]` 方法
4. ✅ 集成Blacklist机制

**核心方法**:
```python
class TemplateManager:
    def match_template(self, platform: str, command: str) -> Optional[str]:
        """运行时匹配ntc-templates
        
        Returns:
            - template_name (str): e.g., "cisco_ios_show_version"
            - None: 无匹配，返回raw text
        """
        # 1. 标准化命令（去多余空格、统一缩写）
        normalized_cmd = self._normalize_command(command)
        
        # 2. 查询ntc-templates index（通过ntc_templates库）
        from ntc_templates.parse import parse_output
        template = self._find_template(platform, normalized_cmd)
        
        # 3. 验证模板非空（复用 _is_template_empty 逻辑）
        if template and not self._is_template_empty(template):
            return template
        
        return None
```

#### Step 1.3.3: NetBox Platform注入（0.5天）

**修改文件**: `src/olav/strategies/fast_path.py`, `src/olav/agents/dynamic_orchestrator.py`

**集成点**: Agent Prompt Context注入

```python
# src/olav/strategies/fast_path.py
async def _extract_parameters(self, query: str, context: Dict = None):
    # 从NetBox查询设备平台信息
    if "device" in context:
        device_info = await self._netbox_client.get_device(context["device"])
        context["platform"] = device_info.platform.slug  # e.g., "cisco-ios"
    
    # 注入到LLM Prompt
    prompt = self._build_extraction_prompt(query, context)
    ...
```

**Prompt示例**:
```yaml
# config/prompts/agents/fast_path.yaml
template: |
  设备: {device_name}
  平台: {platform}  # <-- 新增
  可用工具: netconf_execute, cli_execute
  
  如果平台支持NETCONF（juniper-junos, arista-eos），优先选择 netconf_execute。
  否则使用 cli_execute (cisco-ios, cisco-nxos)。
```

### 1.4 验收标准（CLI降级 Phase B.1）

- [ ] CLITool支持show命令 + config_commands双模式
- [ ] 运行时ntc-template匹配成功率 > 80%（91个cisco_ios标准命令）
- [ ] Blacklist机制生效（危险命令触发HITL）
- [ ] NetBox platform注入到Agent Prompt
- [ ] 单元测试覆盖率 > 85%（含TextFSM解析测试）
- [ ] E2E测试: NETCONF失败 → 自动降级到CLI → 返回解析后JSON

### 1.5 预期收益

- ✅ **架构完整性**: 填补原设计中的CLI降级缺失（架构符合度 85% → 90%）
- ✅ **代码复用**: 减少300+行重复代码（复用TemplateManager）
- ✅ **运维可靠性**: NETCONF不可用时自动降级（零中断）
- ✅ **解析质量**: TextFSM结构化输出（vs 原始文本）

---

## 二、Phase B.2: DeepAgents中间件复用（1-2天）

### 2.1 任务概述
**目标**: 从DeepAgents framework提取中间件代码，适配到LangGraph StateBackend  
**核心价值**: 减少500+行自维护代码（文件操作、工具调用归一化）

### 2.2 存档代码复用计划

#### 2.2.1 FilesystemMiddleware（907 lines from `archive/deepagents/`）

**源文件**: `archive/deepagents/libs/deepagents/deepagents/middleware/filesystem.py`

**可复用组件**:
```python
class FilesystemMiddleware:
    """File operation abstraction with Backend Protocol."""
    
    async def read_file(self, path: str) -> str:
        """从StateBackend/Redis读取文件"""
    
    async def write_file(self, path: str, content: str):
        """写入文件到StateBackend（审计日志）"""
    
    async def list_files(self, pattern: str) -> List[str]:
        """列出文件（支持glob pattern）"""
    
    async def delete_file(self, path: str):
        """删除文件（HITL拦截）"""
```

**复用策略**:
1. **协议适配**: 将 `BackendProtocol` 替换为 `StateBackend`（LangGraph）
2. **保留审计**: 所有文件操作写入OpenSearch审计日志
3. **HITL集成**: 写/删操作触发HITL approval

#### 2.2.2 SubAgentMiddleware（200+ lines from `archive/deepagents/`）

**源文件**: `archive/deepagents/libs/deepagents/deepagents/middleware/subagents.py`

**可复用组件**:
```python
class SubAgentMiddleware:
    """Inter-agent communication router."""
    
    async def delegate_to_subagent(self, agent_name: str, task: str):
        """将任务委托给子Agent"""
    
    async def collect_results(self, subagent_ids: List[str]) -> List[Dict]:
        """收集子Agent执行结果"""
```

**复用策略**:
1. **LangGraph集成**: 适配为Workflow间通信（`send_to_workflow()`）
2. **Future Use**: Phase C DeepPath多步骤递归可复用此逻辑

#### 2.2.3 PatchToolCalls（150+ lines from `archive/deepagents/`）

**源文件**: `archive/deepagents/libs/deepagents/deepagents/middleware/patch_tool_calls.py`

**可复用组件**:
```python
def normalize_tool_calls(raw_calls: List[Dict]) -> List[ToolCall]:
    """规范化LLM返回的工具调用格式"""
    # 处理LLM返回的各种格式差异（OpenAI vs Anthropic vs Ollama）
```

**复用策略**:
1. **LangChain集成**: 替代现有tool_calling解析逻辑
2. **多LLM兼容**: 统一处理不同provider格式

### 2.3 实现步骤（分2个子任务）

#### Step 2.3.1: 提取FilesystemMiddleware（0.5天）

**文件**: `src/olav/core/middleware/filesystem.py`（新建目录结构）

**迁移任务**:
1. ✅ 从 `archive/deepagents/middleware/filesystem.py` 复制核心类
2. ✅ 替换 `BackendProtocol` 为 `StateBackend`
3. ✅ 集成 `OpenSearchMemory` 审计日志
4. ✅ 添加HITL拦截点

**目标代码量**: 400-500行（vs 原907行，移除DeepAgents特定逻辑）

#### Step 2.3.2: 集成到FastPathStrategy（1天）

**修改文件**: `src/olav/strategies/fast_path.py`, `src/olav/strategies/deep_path.py`

**集成点**: Tool执行结果缓存

```python
from olav.core.middleware.filesystem import FilesystemMiddleware

class FastPathStrategy:
    def __init__(self, ..., filesystem: Optional[FilesystemMiddleware] = None):
        self.filesystem = filesystem or FilesystemMiddleware()
    
    async def execute(self, query: str):
        # 检查是否有缓存结果
        cache_key = f"tool_results/{hash(query)}.json"
        cached = await self.filesystem.read_file(cache_key)
        if cached:
            return json.loads(cached)
        
        # 执行工具 + 写缓存
        result = await self._execute_tool(...)
        await self.filesystem.write_file(cache_key, json.dumps(result))
        return result
```

### 2.4 验收标准（DeepAgents中间件 Phase B.2）

- [ ] FilesystemMiddleware迁移完成（400-500行）
- [ ] StateBackend协议适配（兼容LangGraph）
- [ ] OpenSearch审计日志集成（所有文件操作可追溯）
- [ ] HITL拦截点生效（写/删操作需approval）
- [ ] 工具执行缓存实现（减少重复LLM调用）
- [ ] 单元测试覆盖率 > 80%

### 2.5 预期收益

- ✅ **代码减少**: 移除500行自维护文件操作逻辑
- ✅ **性能提升**: 工具结果缓存（减少10-20% LLM调用）
- ✅ **审计完整**: 所有文件操作可追溯（合规要求）
- ✅ **复用质量**: DeepAgents经过生产验证的中间件（vs 重写）

---

## 三、Phase B.3: 轻量重构（0.5天）

**时机**: Phase B.1 + B.2 完成后  
**目标**: 统一代码风格，移除临时hack

### 3.1 重构清单

1. **移除warnings** (0.2天)
   - [ ] 添加 `model_kwargs={'parallel_tool_calls': False}` 到所有LLM初始化
   - [ ] 替换 `config_schema` 为 `get_context_jsonschema`
   - [ ] 修复event loop warnings

2. **清理注释** (0.1天)
   - [ ] 移除 `# TODO: ` 标记（已完成的任务）
   - [ ] 移除 `# FIXME: ` 标记（已修复的问题）

3. **统一命名** (0.2天)
   - [ ] 工具名称统一后缀: `_tool` vs `_execute`
   - [ ] Adapter类统一继承 `BaseAdapter`

### 3.2 验收标准

- [ ] pytest运行0 warnings
- [ ] ruff check无报错
- [ ] mypy strict mode通过（如有时间）

---

## 四、时间线与里程碑

### Week 1: P0修复 + 清理（1天）
**时间**: Day 1-2  
**负责人**: AI Coding Agent

| 任务 | 预计时间 | 状态 |
|------|----------|------|
| Issue 2: WWW-Authenticate header | 0.1天 | ⚠️ **待开始** |
| Issue 3: CLI Client server_url | 0.1天 | ⚠️ **待开始** |
| Issue 1: invoke endpoint timeout + retry | 0.5天 | ⚠️ **待开始** |
| 轻量清理（warnings压制） | 0.3天 | ⚠️ **待开始** |

**里程碑**: v0.4.1-beta (100% E2E passing)

### Week 2: Phase B.1 CLI降级（2-3天）
**时间**: Day 3-5  
**负责人**: AI Coding Agent

| 任务 | 预计时间 | 复用存档 | 状态 |
|------|----------|----------|------|
| Step 1.3.1: CLITool框架 | 0.5天 | - | ⚠️ **待开始** |
| Step 1.3.2: TemplateManager集成 | 1.5天 | ✅ **300+ lines** | ⚠️ **待开始** |
| Step 1.3.3: NetBox Platform注入 | 0.5天 | - | ⚠️ **待开始** |

**里程碑**: v0.5.0-beta (CLI fallback capability)

### Week 3: Phase B.2 DeepAgents中间件（1-2天）
**时间**: Day 6-7  
**负责人**: AI Coding Agent

| 任务 | 预计时间 | 复用存档 | 状态 |
|------|----------|----------|------|
| Step 2.3.1: FilesystemMiddleware提取 | 0.5天 | ✅ **907 lines** | ⚠️ **待开始** |
| Step 2.3.2: 集成到Strategies | 1天 | - | ⚠️ **待开始** |
| 单元测试 | 0.5天 | - | ⚠️ **待开始** |

**里程碑**: v0.5.1-beta (Code reduction 30%+)

### Week 4: Phase B.3 轻量重构（0.5天）
**时间**: Day 8  
**负责人**: AI Coding Agent

| 任务 | 预计时间 | 状态 |
|------|----------|------|
| Warning清理 | 0.2天 | ⚠️ **待开始** |
| 注释清理 | 0.1天 | ⚠️ **待开始** |
| 命名统一 | 0.2天 | ⚠️ **待开始** |

**里程碑**: v0.5.2-beta (Clean codebase for Phase C)

---

## 五、风险管理

### 5.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| ntc-templates库API变更 | 中 | 固定版本号，测试覆盖 |
| TextFSM解析失败率高 | 低 | 降级到raw text输出 |
| DeepAgents中间件依赖冲突 | 低 | 仅复用核心逻辑，移除framework |
| StateBackend协议不兼容 | 中 | 创建适配层 |

### 5.2 时间风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| TemplateManager复杂度超预期 | 中 | 可先实现basic版本（仅cisco_ios） |
| FilesystemMiddleware重构工作量大 | 高 | 采用增量迁移策略 |
| 单元测试编写耗时 | 低 | 优先覆盖核心路径 |

---

## 六、成功指标（Phase B完成标准）

### 6.1 功能指标
- [ ] CLI降级成功率 > 95%（NETCONF失败场景）
- [ ] TextFSM解析成功率 > 80%（91个标准命令）
- [ ] 文件操作审计100%覆盖（OpenSearch日志）

### 6.2 代码质量指标
- [ ] 单元测试覆盖率 > 85%
- [ ] E2E测试通过率 100% (12/12)
- [ ] 代码行数减少 30%+（复用存档代码）

### 6.3 架构指标
- [ ] 架构符合度 90%+（vs 原设计85%）
- [ ] Schema-Aware工具比例 100%（CLI工具也采用运行时匹配）
- [ ] HITL拦截覆盖所有写操作

---

## 七、后续Phase预览

### Phase C: Batch YAML Executor（Week 5-6）
- 实现 `load_inspection_config()` YAML加载器
- NL Intent → SQL Compiler（LLM驱动）
- 示例: `config/inspections/daily_core_check.yaml`

### Phase D: SoT Reconciliation（Week 7-9）
- **调整为只读检测模式**（不自动修正）
- NetBox vs 设备实际状态对比
- 差异报告生成（Markdown格式）

### Phase E: WebUI + Auto-Correction（Future）
- HITL WebUI审批界面
- SoT自动修正（需人工确认）
- Multi-approval工作流

---

## 八、参考资源

### 8.1 存档代码位置
- **baseline_collector.py**: `archive/baseline_collector.py` (842 lines)
  - TemplateManager: lines 150-400 (300+ lines)
  - Blacklist: lines 200-250 (50+ lines)
  
- **DeepAgents Middleware**: `archive/deepagents/libs/deepagents/deepagents/middleware/`
  - filesystem.py: 907 lines
  - subagents.py: 200+ lines
  - patch_tool_calls.py: 150+ lines

### 8.2 相关文档
- 原始设计: `docs/DESIGN.md`
- 架构重构: `docs/AGENT_ARCHITECTURE_REFACTOR.md`
- Gap分析: `docs/ARCHITECTURE_GAP_ANALYSIS_UPDATE.md`
- 已知问题: `docs/KNOWN_ISSUES_AND_TODO.md`

### 8.3 关键配置文件
- CLI Blacklist: `config/cli_blacklist.yaml`
- Prompt Templates: `config/prompts/tools/cli_tool.yaml`
- NetBox Inventory: NetBox REST API (`/api/dcim/devices/`)

---

**文档状态**: ✅ 规划完成，等待执行  
**下一步行动**: 修复Issue 2 (WWW-Authenticate header) - 0.1天
