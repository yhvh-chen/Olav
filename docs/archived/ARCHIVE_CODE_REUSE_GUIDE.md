# 存档代码复用指南

**文档目的**: 快速定位可复用的存档代码位置和复用策略  
**创建日期**: 2025-11-25  
**适用Phase**: Phase B.1 (CLI降级) + Phase B.2 (DeepAgents中间件)

---

## 一、存档代码总览

### 1.1 代码量统计

| 源文件 | 总行数 | 可复用行数 | 复用率 | 目标模块 |
|--------|--------|-----------|--------|----------|
| `baseline_collector.py` | 842 | 300+ | 36% | CLITool |
| `filesystem.py` (DeepAgents) | 907 | 400-500 | 55% | FilesystemMiddleware |
| `subagents.py` (DeepAgents) | 200+ | 100+ | 50% | Future (DeepPath) |
| `patch_tool_calls.py` | 150+ | 80+ | 53% | Tool Calling Parser |
| **总计** | **2099+** | **980+** | **47%** | - |

### 1.2 复用优先级

| 优先级 | 模块 | 复用行数 | 预计节省时间 | Phase |
|--------|------|----------|-------------|-------|
| P1 | TemplateManager | 300+ | 1.5天 | B.1 |
| P1 | FilesystemMiddleware | 400-500 | 1天 | B.2 |
| P2 | PatchToolCalls | 80+ | 0.5天 | B.2 |
| P3 | SubAgentMiddleware | 100+ | Future | C |

---

## 二、baseline_collector.py 复用详解

### 2.1 文件信息
- **路径**: `archive/baseline_collector.py`
- **总行数**: 842 lines
- **作者**: Original OLAV implementation
- **最后修改**: 项目早期（已归档）

### 2.2 TemplateManager 类（Lines 150-400）

#### 核心方法清单

| 方法名 | 行数 | 功能 | 复用策略 | 优先级 |
|--------|------|------|----------|--------|
| `__init__()` | 10-20 | 初始化模板目录扫描 | ✅ 直接迁移 | P1 |
| `_scan_templates()` | 30-50 | 扫描.backup.textfsm文件 | ⚠️ 改为ntc-templates库调用 | P1 |
| `_parse_command_from_filename()` | 20-30 | 从文件名提取命令 | ✅ 直接迁移（核心逻辑） | P1 |
| `_is_template_empty()` | 15-25 | 检测空模板 | ✅ 直接迁移 | P1 |
| `_load_blacklist()` | 20-30 | 加载危险命令列表 | ✅ 直接迁移 | P1 |
| `get_commands_for_platform()` | 40-60 | 平台命令映射 | ✅ 直接迁移 | P1 |
| `filter_safe_commands()` | 15-25 | 过滤危险命令 | ✅ 直接迁移 | P1 |

#### 代码示例（可直接复用）

```python
# Lines 200-230 (可直接复制)
class TemplateManager:
    def _parse_command_from_filename(self, filename: str) -> str:
        """从ntc-templates文件名提取标准命令.
        
        示例转换:
            cisco_ios_show_running.backup.textfsm → "show running-config"
            cisco_ios_show_ip_interface_brief.textfsm → "show ip interface brief"
            arista_eos_show_version.textfsm → "show version"
        
        Args:
            filename: Template文件名（带扩展名）
        
        Returns:
            标准化的CLI命令字符串
        """
        # 移除扩展名
        name = filename.replace('.backup.textfsm', '').replace('.textfsm', '')
        
        # 移除平台前缀 (cisco_ios_, arista_eos_, etc.)
        parts = name.split('_')
        if len(parts) >= 3:
            command_parts = parts[2:]  # Skip platform (cisco_ios)
        else:
            command_parts = parts
        
        # 转换下划线为空格
        command = ' '.join(command_parts)
        
        # 处理特殊缩写
        command = command.replace('ip int', 'ip interface')
        command = command.replace('sh', 'show')
        command = command.replace('conf', 'configuration')
        
        return command
    
    def _is_template_empty(self, template_path: Path) -> bool:
        """检测模板是否为空（仅包含注释/空行）.
        
        Returns:
            True: 模板无效（空或仅注释）
            False: 模板有效（包含Value定义）
        """
        with open(template_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                # 跳过空行和注释
                if stripped and not stripped.startswith('#'):
                    # 检查是否包含Value定义
                    if stripped.startswith('Value'):
                        return False
        return True
```

#### 平台命令映射（Lines 250-350）

```python
# 可直接复用的91个cisco_ios标准命令
CISCO_IOS_STANDARD_COMMANDS = [
    "show version",
    "show running-config",
    "show ip interface brief",
    "show ip route",
    "show ip bgp summary",
    "show interfaces status",
    "show vlan brief",
    "show spanning-tree",
    "show mac address-table",
    "show arp",
    # ... (完整列表91个命令)
]

PLATFORM_FALLBACK = {
    "cisco_nxos": "cisco_ios",      # NXOS可用IOS模板
    "arista_eos": "cisco_ios",      # EOS语法类似IOS
    "juniper_junos": "juniper_junos",  # 独立
    "huawei_vrp": "cisco_ios",      # VRP语法兼容IOS
}
```

### 2.3 Blacklist 机制（Lines 200-250）

#### 配置文件格式

**源文件**: `config/cli_blacklist.yaml`

```yaml
# 危险命令黑名单（会触发HITL approval）
blacklist:
  - pattern: "reload"
    reason: "设备重启（需审批）"
    hitl_required: true
  
  - pattern: "delete.*"
    reason: "文件删除（不可逆）"
    hitl_required: true
  
  - pattern: "erase.*"
    reason: "配置擦除（极度危险）"
    hitl_required: true
  
  - pattern: "format.*"
    reason: "格式化操作（不可逆）"
    hitl_required: true
  
  - pattern: "traceroute"
    reason: "网络性能影响"
    hitl_required: false  # 仅警告
  
  - pattern: "clear.*"
    reason: "清空统计/日志"
    hitl_required: true

# 安全命令白名单（无需审批）
whitelist:
  - pattern: "show.*"
  - pattern: "display.*"  # Huawei
  - pattern: "get.*"      # Juniper
```

#### 代码示例（可直接复用）

```python
# Lines 200-230
class TemplateManager:
    def _load_blacklist(self) -> Dict[str, str]:
        """从YAML加载黑名单.
        
        Returns:
            Dict[command_pattern, reason]
        """
        blacklist_file = Path("config/cli_blacklist.yaml")
        if not blacklist_file.exists():
            logger.warning("Blacklist file not found, using default")
            return DEFAULT_BLACKLIST
        
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        blacklist = {}
        for item in config.get('blacklist', []):
            pattern = item['pattern']
            reason = item.get('reason', 'Potentially dangerous command')
            blacklist[pattern] = reason
        
        return blacklist
    
    def filter_safe_commands(self, commands: List[str]) -> List[str]:
        """过滤危险命令（触发HITL）.
        
        Args:
            commands: 待执行的命令列表
        
        Returns:
            过滤后的安全命令列表
        
        Raises:
            HITLRequiredException: 如果包含需审批的命令
        """
        safe_commands = []
        dangerous_commands = []
        
        for cmd in commands:
            is_dangerous = False
            for pattern, reason in self.blacklist.items():
                if re.match(pattern, cmd, re.IGNORECASE):
                    dangerous_commands.append({
                        'command': cmd,
                        'reason': reason,
                        'pattern': pattern
                    })
                    is_dangerous = True
                    break
            
            if not is_dangerous:
                safe_commands.append(cmd)
        
        if dangerous_commands:
            # 触发HITL审批
            raise HITLRequiredException(
                commands=dangerous_commands,
                approval_required=True,
                message=f"Found {len(dangerous_commands)} dangerous commands requiring approval"
            )
        
        return safe_commands
```

---

## 三、DeepAgents Middleware 复用详解

### 3.1 filesystem.py（907 lines）

#### 文件信息
- **路径**: `archive/deepagents/libs/deepagents/deepagents/middleware/filesystem.py`
- **总行数**: 907 lines
- **复用行数**: 400-500 lines (移除DeepAgents特定逻辑)
- **核心价值**: 文件操作抽象 + 审计日志

#### 核心类结构

```python
# Lines 1-50: 类定义
class FilesystemMiddleware:
    """File operation abstraction with Backend Protocol.
    
    Supports:
        - StateBackend (LangGraph state)
        - RedisBackend (Redis + OpenSearch)
        - LocalBackend (development only)
    """
    
    def __init__(self, backend: BackendProtocol):
        self.backend = backend
        self.audit_logger = AuditLogger()  # OpenSearch
    
    # Lines 100-200: 读操作（可直接复用）
    async def read_file(self, path: str) -> str:
        """从Backend读取文件（带缓存）"""
        # 1. 检查缓存
        cached = await self.backend.get(f"file_cache:{path}")
        if cached:
            return cached
        
        # 2. 读取原文件
        content = await self.backend.read(path)
        
        # 3. 写入缓存
        await self.backend.put(f"file_cache:{path}", content, ttl=3600)
        
        return content
    
    # Lines 250-350: 写操作（需适配HITL）
    async def write_file(self, path: str, content: str, requires_approval: bool = True):
        """写入文件（带HITL拦截）"""
        # 1. HITL检查
        if requires_approval:
            approval = await self._request_approval(
                operation="write_file",
                path=path,
                preview=content[:200]
            )
            if not approval.approved:
                raise HITLRejectedError(f"User rejected write to {path}")
        
        # 2. 执行写入
        await self.backend.write(path, content)
        
        # 3. 审计日志
        await self.audit_logger.log({
            "operation": "write_file",
            "path": path,
            "size": len(content),
            "timestamp": datetime.utcnow(),
            "approved": requires_approval,
        })
    
    # Lines 400-500: 列表操作（可直接复用）
    async def list_files(self, pattern: str = "*") -> List[str]:
        """列出文件（支持glob pattern）"""
        return await self.backend.list(pattern)
    
    # Lines 550-650: 删除操作（需适配HITL）
    async def delete_file(self, path: str, requires_approval: bool = True):
        """删除文件（带HITL拦截）"""
        # Similar to write_file logic
```

#### 复用策略详解

| 代码段 | 行数 | 复用策略 | 优先级 |
|--------|------|----------|--------|
| 类初始化 | 50-100 | ✅ 直接迁移 | P1 |
| read_file() | 100-200 | ✅ 直接迁移（缓存逻辑有价值） | P1 |
| write_file() | 250-350 | ⚠️ 适配HITL（LangGraph interrupt） | P1 |
| list_files() | 400-500 | ✅ 直接迁移 | P2 |
| delete_file() | 550-650 | ⚠️ 适配HITL | P2 |
| BackendProtocol | 700-800 | ⚠️ 替换为StateBackend | P1 |

#### Protocol适配示例

```python
# 原DeepAgents Protocol (需替换)
class BackendProtocol(Protocol):
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def list(self, pattern: str) -> List[str]: ...

# 新LangGraph StateBackend适配
from langgraph.checkpoint.base import BaseCheckpointSaver

class StateBackend:
    """Adapter for LangGraph Checkpointer to Backend Protocol."""
    
    def __init__(self, checkpointer: BaseCheckpointSaver):
        self.checkpointer = checkpointer
    
    async def read(self, path: str) -> str:
        """从Checkpointer state读取文件内容"""
        # 使用namespace作为文件路径
        state = await self.checkpointer.aget(namespace=path)
        if state and 'content' in state:
            return state['content']
        raise FileNotFoundError(f"Path {path} not found in state")
    
    async def write(self, path: str, content: str):
        """写入到Checkpointer state"""
        await self.checkpointer.aput(
            namespace=path,
            checkpoint={'content': content, 'timestamp': datetime.utcnow()}
        )
    
    async def list(self, pattern: str) -> List[str]:
        """列出匹配pattern的所有namespace"""
        # LangGraph Checkpointer不原生支持glob，需自定义实现
        all_namespaces = await self.checkpointer.alist_namespaces()
        import fnmatch
        return [ns for ns in all_namespaces if fnmatch.fnmatch(ns, pattern)]
```

### 3.2 subagents.py（200+ lines）

#### 文件信息
- **路径**: `archive/deepagents/libs/deepagents/deepagents/middleware/subagents.py`
- **复用场景**: Future Phase C (DeepPath多步骤递归)
- **核心价值**: Inter-workflow通信

#### 核心方法（Future Use）

```python
# Lines 50-150
class SubAgentMiddleware:
    async def delegate_to_subagent(self, agent_name: str, task: str):
        """将任务委托给子Workflow（LangGraph send）"""
        # 原DeepAgents实现
        result = await self.agent_pool.execute(agent_name, task)
        return result
    
    # LangGraph适配版本（Phase C实现）
    async def send_to_workflow(self, workflow_name: str, state: Dict):
        """通过LangGraph send机制调用子Workflow"""
        from olav.workflows.registry import WorkflowRegistry
        
        workflow = WorkflowRegistry.get_workflow(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow {workflow_name} not found")
        
        # 创建子Workflow实例
        sub_workflow = workflow.class_ref(checkpointer=self.checkpointer)
        
        # 执行并返回结果
        result = await sub_workflow.ainvoke(state)
        return result
```

### 3.3 patch_tool_calls.py（150+ lines）

#### 文件信息
- **路径**: `archive/deepagents/libs/deepagents/deepagents/middleware/patch_tool_calls.py`
- **复用场景**: Phase B.2（Tool Calling规范化）
- **核心价值**: 兼容多LLM provider格式

#### 核心函数（可直接复用）

```python
# Lines 20-100
def normalize_tool_calls(raw_calls: List[Dict]) -> List[ToolCall]:
    """规范化不同LLM provider的tool call格式.
    
    Supports:
        - OpenAI function calling format
        - Anthropic tool use format
        - Ollama tool calls format
    
    Args:
        raw_calls: 原始LLM返回的tool call列表
    
    Returns:
        标准化的ToolCall对象列表
    """
    normalized = []
    
    for call in raw_calls:
        # OpenAI format
        if 'function' in call:
            normalized.append(ToolCall(
                name=call['function']['name'],
                arguments=json.loads(call['function']['arguments']),
                id=call.get('id'),
            ))
        
        # Anthropic format
        elif 'name' in call and 'input' in call:
            normalized.append(ToolCall(
                name=call['name'],
                arguments=call['input'],
                id=call.get('id'),
            ))
        
        # Ollama format (varies by model)
        elif 'tool' in call:
            normalized.append(ToolCall(
                name=call['tool'],
                arguments=call.get('parameters', {}),
                id=call.get('id'),
            ))
        
        else:
            logger.warning(f"Unknown tool call format: {call}")
    
    return normalized

# Lines 100-150: Error handling
def validate_tool_arguments(tool_name: str, arguments: Dict) -> bool:
    """验证工具参数完整性"""
    # 从ToolRegistry获取schema
    from olav.tools.base import ToolRegistry
    
    tool = ToolRegistry.get_tool(tool_name)
    if not tool:
        return False
    
    # 检查required参数
    schema = tool.get_input_schema()
    required_fields = schema.get('required', [])
    
    for field in required_fields:
        if field not in arguments:
            logger.error(f"Missing required field '{field}' for tool '{tool_name}'")
            return False
    
    return True
```

---

## 四、复用实施Checklist

### 4.1 Phase B.1: CLI降级（Week 2）

**TemplateManager 迁移**:
- [ ] 创建 `src/olav/tools/cli_template_manager.py`
- [ ] 复制 `_parse_command_from_filename()` (Lines 200-230)
- [ ] 复制 `_is_template_empty()` (Lines 230-250)
- [ ] 复制 `get_commands_for_platform()` (Lines 250-300)
- [ ] 复制 `CISCO_IOS_STANDARD_COMMANDS` 常量 (91个命令)
- [ ] 复制 `PLATFORM_FALLBACK` 映射

**Blacklist 机制**:
- [ ] 复用 `config/cli_blacklist.yaml` 配置文件
- [ ] 复制 `_load_blacklist()` (Lines 200-220)
- [ ] 复制 `filter_safe_commands()` (Lines 220-250)
- [ ] 集成到 `CLITool.execute()` 参数验证

**单元测试**:
- [ ] 测试命令解析正确性（91个标准命令）
- [ ] 测试Blacklist拦截（reload, delete, erase等）
- [ ] 测试平台fallback机制

### 4.2 Phase B.2: DeepAgents中间件（Week 3）

**FilesystemMiddleware**:
- [ ] 创建 `src/olav/core/middleware/filesystem.py`
- [ ] 复制 `read_file()` 方法（Lines 100-200）
- [ ] 复制 `write_file()` 方法（Lines 250-350）
- [ ] 复制 `list_files()` 方法（Lines 400-500）
- [ ] 创建 `StateBackend` adapter
- [ ] 替换 `BackendProtocol` 为 `StateBackend`

**HITL集成**:
- [ ] 修改 `write_file()` 使用LangGraph interrupt
- [ ] 修改 `delete_file()` 使用LangGraph interrupt
- [ ] 集成OpenSearch审计日志

**单元测试**:
- [ ] 测试文件读写操作
- [ ] 测试HITL拦截逻辑
- [ ] 测试StateBackend协议适配

### 4.3 Phase B.3: 工具调用规范化（Week 3）

**PatchToolCalls**:
- [ ] 创建 `src/olav/core/tool_parser.py`
- [ ] 复制 `normalize_tool_calls()` (Lines 20-100)
- [ ] 复制 `validate_tool_arguments()` (Lines 100-150)
- [ ] 集成到 `FastPathStrategy._extract_parameters()`

**测试覆盖**:
- [ ] 测试OpenAI格式解析
- [ ] 测试Anthropic格式解析
- [ ] 测试Ollama格式解析
- [ ] 测试参数验证逻辑

---

## 五、复用收益评估

### 5.1 代码量减少

| 场景 | 如果重写 | 复用存档 | 减少量 | 减少比例 |
|------|----------|----------|--------|----------|
| CLI Template匹配 | 400行 | 300行迁移 | 100行 | 25% |
| Blacklist机制 | 150行 | 50行迁移 | 100行 | 67% |
| FilesystemMiddleware | 600行 | 400行迁移 | 200行 | 33% |
| Tool Call Parser | 200行 | 80行迁移 | 120行 | 60% |
| **总计** | **1350行** | **830行** | **520行** | **39%** |

### 5.2 时间节省

| 场景 | 如果重写 | 复用存档 | 节省时间 |
|------|----------|----------|----------|
| CLI Template匹配 | 2天 | 0.5天 | **1.5天** |
| Blacklist机制 | 0.5天 | 0.1天 | **0.4天** |
| FilesystemMiddleware | 2天 | 1天 | **1天** |
| Tool Call Parser | 1天 | 0.5天 | **0.5天** |
| **总计** | **5.5天** | **2.1天** | **3.4天** |

### 5.3 质量提升

| 维度 | 重写代码 | 复用存档 | 优势 |
|------|----------|----------|------|
| 测试覆盖 | 需从零编写 | 已有参考 | ✅ 加速测试编写 |
| Bug风险 | 新代码未验证 | 生产验证过 | ✅ 降低Bug率 |
| 文档完整 | 需重新编写 | 已有注释 | ✅ 文档质量高 |
| 维护成本 | 长期维护 | 成熟代码 | ✅ 减少维护工作 |

---

## 六、注意事项

### 6.1 不可直接复用的部分

| 代码段 | 原因 | 解决方案 |
|--------|------|----------|
| DeepAgents SubAgent调用 | Framework已淘汰 | 适配为LangGraph Workflow通信 |
| BackendProtocol | 与LangGraph不兼容 | 创建StateBackend适配层 |
| .backup.textfsm扫描 | 静态文件依赖 | 改为ntc-templates库动态调用 |

### 6.2 需要适配的部分

| 代码段 | 适配内容 | 工作量 |
|--------|----------|--------|
| HITL approval | 从DeepAgents改为LangGraph interrupt | 0.5天 |
| 审计日志 | 从自定义logger改为OpenSearch | 0.2天 |
| 缓存机制 | 从内存缓存改为Redis | 0.3天 |

### 6.3 测试要求

1. **单元测试覆盖率**: > 85%
2. **集成测试**: 必须覆盖NETCONF → CLI降级场景
3. **性能测试**: TextFSM解析延迟 < 100ms
4. **回归测试**: 确保现有功能不受影响

---

## 七、快速参考

### 7.1 关键文件路径

```
archive/
├── baseline_collector.py                # CLI Template + Blacklist
└── deepagents/libs/deepagents/deepagents/middleware/
    ├── filesystem.py                    # 文件操作中间件
    ├── subagents.py                     # Workflow通信（Future）
    └── patch_tool_calls.py              # Tool Call解析
```

### 7.2 复用代码行数对照表

| 源文件 | 开始行 | 结束行 | 复用内容 | 目标位置 |
|--------|--------|--------|----------|----------|
| baseline_collector.py | 200 | 230 | _parse_command_from_filename | cli_template_manager.py |
| baseline_collector.py | 230 | 250 | _is_template_empty | cli_template_manager.py |
| baseline_collector.py | 250 | 300 | get_commands_for_platform | cli_template_manager.py |
| baseline_collector.py | 200 | 220 | _load_blacklist | cli_tool.py |
| filesystem.py | 100 | 200 | read_file | middleware/filesystem.py |
| filesystem.py | 250 | 350 | write_file | middleware/filesystem.py |
| patch_tool_calls.py | 20 | 100 | normalize_tool_calls | core/tool_parser.py |

### 7.3 配置文件依赖

- `config/cli_blacklist.yaml`: CLI危险命令黑名单
- `config/prompts/tools/cli_tool.yaml`: CLI工具Prompt模板
- NetBox API: `/api/dcim/devices/?id={device_id}` (获取platform字段)

---

**文档维护**: 每次复用存档代码后更新此文档  
**下次更新**: Phase B.2完成后（预计Week 3结束）
