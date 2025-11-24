# OLAV Agent 架构重构方案

## 一、设计理念：解耦意图与执行策略

### 核心问题
当前架构存在两大瓶颈：
1. **扩展困难**：每增加一个新能力（如安全审计、无线诊断），需要修改 Orchestrator 核心代码
2. **策略固化**：无法根据任务复杂度动态选择执行路径（快速查询 vs 深度推理）

### 重构目标
构建**"意图驱动 + 策略自适应"**架构，实现：
- **业务意图 (Intent)** 与 **执行模式 (Strategy)** 完全解耦
- 工作流（Workflow）作为插件动态注册，零侵入扩展
- 根据任务特征自动选择 Fast Path（查表）或 Deep Path（推理循环）

### 三层架构

```
┌─────────────────────────────────────────────────────┐
│  顶层：Dynamic Intent Router (动态意图路由)          │
│  - 工作流注册中心 (WorkflowRegistry)                 │
│  - 语义路由 (Semantic Matching + LLM Classification) │
│  - 零侵入扩展：新 Workflow 通过装饰器自注册          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  中层：Execution Strategies (执行策略)               │
│  - Fast Path: Semantic Router + Function Calling    │
│  - Deep Path: Hypothesis-Driven Loop                │
│  - Batch Path: Map-Reduce Compiler-Executor         │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  底层：Unified Tool Layer (统一工具层)               │
│  - Schema-Aware Tools (SuzieQ, OpenConfig)          │
│  - Pydantic 标准化输出                               │
│  - HITL 中间件（写操作安全拦截）                     │
└─────────────────────────────────────────────────────┘
```

## 二、动态意图路由 (Dynamic Intent Router)

### 2.1 工作流注册机制

**设计目标**：工作流作为插件，通过装饰器自注册，编排器无需感知具体实现。

**实现方式**：
```python
# src/olav/workflows/registry.py
class WorkflowRegistry:
    _workflows: Dict[str, WorkflowMetadata] = {}
    
    @classmethod
    def register(cls, name: str, description: str, examples: List[str], 
                 triggers: List[str] = None):
        """装饰器：自动注册工作流"""
        def decorator(workflow_class):
            cls._workflows[name] = WorkflowMetadata(
                name=name,
                description=description,
                examples=examples,  # 用于语义匹配的示例查询
                triggers=triggers,  # 正则触发关键词
                class_ref=workflow_class
            )
            return workflow_class
        return decorator

# 使用示例
@WorkflowRegistry.register(
    name="network_diagnosis",
    description="网络状态查询、BGP/OSPF 诊断、接口分析",
    examples=[
        "查询 R1 的 BGP 邻居状态",
        "为什么 Switch-A 和 Switch-B 之间丢包？",
        "检查所有核心路由器的 CPU 使用率"
    ],
    triggers=[r"BGP", r"OSPF", r"接口.*状态", r"路由.*表"]
)
class NetworkDiagnosisWorkflow(BaseWorkflow):
    ...
```

### 2.2 两阶段路由策略

**阶段一：语义初筛 (Semantic Pre-filtering)**
- 将用户 Query 转为向量 (Embeddings)
- 与注册的 `examples` 进行相似度匹配
- 返回 Top-3 最可能的工作流候选

**阶段二：LLM 精确分类**
- 仅对 Top-3 候选构建分类 Prompt（而非全部工作流）
- LLM 基于 `description` 做最终决策
- 降低上下文长度，提升准确率和速度

**优势对比**：
| 方案 | 可扩展性 | 响应速度 | 准确率 | 维护成本 |
|------|---------|---------|--------|---------|
| 当前方案 (硬编码) | ❌ 低 | ✅ 快 | ⚠️ 中 | ❌ 高 |
| 纯 LLM 分类 | ✅ 高 | ❌ 慢 | ✅ 高 | ✅ 低 |
| **动态路由 (本方案)** | ✅ **高** | ✅ **快** | ✅ **高** | ✅ **低** |

### 2.3 代码实现示例

```python
# src/olav/agents/dynamic_orchestrator.py
from langchain_openai import OpenAIEmbeddings
from sklearn.metrics.pairwise import cosine_similarity

class DynamicIntentRouter:
    def __init__(self):
        self.registry = WorkflowRegistry
        self.embeddings = OpenAIEmbeddings()
        self.llm = LLMFactory.get_chat_model(json_mode=True)
        
        # 预计算所有示例的向量（启动时执行一次）
        self._build_semantic_index()
    
    def _build_semantic_index(self):
        """为所有注册的工作流示例构建向量索引"""
        self.example_vectors = {}
        for name, metadata in self.registry._workflows.items():
            vectors = [self.embeddings.embed_query(ex) for ex in metadata.examples]
            self.example_vectors[name] = np.mean(vectors, axis=0)  # 取平均向量
    
    async def route(self, user_query: str) -> str:
        # 阶段 1: 语义初筛
        query_vector = self.embeddings.embed_query(user_query)
        similarities = {
            name: cosine_similarity([query_vector], [vec])[0][0]
            for name, vec in self.example_vectors.items()
        }
        top_3 = sorted(similarities.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # 阶段 2: LLM 精确分类（仅对 Top-3）
        candidates = [self.registry._workflows[name] for name, _ in top_3]
        prompt = self._build_classification_prompt(user_query, candidates)
        
        response = await self.llm.ainvoke(prompt)
        return response["workflow_name"]
    
    def _build_classification_prompt(self, query: str, candidates: List[WorkflowMetadata]):
        workflows_desc = "\n".join([
            f"- **{c.name}**: {c.description}" for c in candidates
        ])
        return f"""
        根据用户查询，选择最合适的工作流。
        
        用户查询: {query}
        
        候选工作流:
        {workflows_desc}
        
        返回 JSON: {{"workflow_name": "选中的工作流名称", "confidence": 0.95}}
        """
```

## 三、执行策略 (Execution Strategies)

### 关键概念：策略选择与意图解耦
- **Intent (意图)**：用户想做什么（如"BGP 故障排查"）
- **Strategy (策略)**：如何执行任务（快速查询 vs 深度推理）
- **原则**：同一意图可根据任务复杂度动态选择不同策略

### 3.1 Fast Path - 快速响应策略

**适用场景**：
- 简单查询："Switch-A 的管理 IP 是什么？"
- 状态检查："BGP 邻居起多少个？"
- 单设备单指标查询

**架构设计**：
```
User Query → Intent Extraction → Tool Selector → Direct Answer
              (LLM 提取参数)    (优先 SuzieQ/NetBox)  (结构化输出)
```

**关键特性**：
1. **无循环**：单次 Function Calling，拒绝 Agent 思考链
2. **优先级**：Suzieq (毫秒级) > NetBox (SSOT) > CLI (最后降级)
3. **防幻觉**：强制 LLM 仅基于工具返回的 JSON 回答

**实现要点**：
```python
class FastPathStrategy:
    async def execute(self, intent: Intent, context: Context):
        # 1. 参数提取 (LLM-based)
        params = await self.llm.extract_parameters(intent.query)
        
        # 2. 工具选择（优先级队列）
        tool = self.select_tool(params, priority=["suzieq", "netbox", "cli"])
        
        # 3. 单次调用
        result = await tool.invoke(**params)
        
        # 4. 格式化输出（禁止发散）
        return self.llm.format_answer(result, strict_mode=True)
```

### 3.2 Deep Path - 深度推理策略

**适用场景**：
- 复杂故障："为什么从 A 无法访问 B？"
- 多源验证："业务报障，Web 访问慢，请分析"
- 跨层诊断：L2 链路 + L3 路由 + L4 连通性

**架构设计**：Hypothesis-Driven Loop (假设-验证循环)

```
┌──────────────────────────────────────────────┐
│ 1. Macro Collection (宏观数据采集)            │
│    - SuzieQ: 拓扑、路由表、接口状态           │
│    - NetBox: 预期配置（SoT）                  │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 2. Hypothesis Generator (假设生成)           │
│    - LLM 对比实际 vs 预期                     │
│    - 输出可验证假设："Switch-B 接口 CRC 错误" │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 3. Micro Verification (微观验证)             │
│    - 针对性登录设备                           │
│    - OpenConfig/CLI 获取细节                  │
└──────────────┬───────────────────────────────┘
               ↓
┌──────────────────────────────────────────────┐
│ 4. Evaluator (评估器)                        │
│    - 假设成立 → 生成报告                     │
│    - 假设不成立 → 修正假设，重新循环 (Max 3)  │
└──────────────────────────────────────────────┘
```

**核心创新**：SoT Validation (真理源校验)
- 不问"现在是什么状态"
- 而问"实际状态与 NetBox 定义是否一致？"
- 差异分析 (Diffing) 是自动化排障的核心

**扩展性设计**：
```python
class DeepPathStrategy:
    def __init__(self):
        # 数据源插件化
        self.macro_sources = [SuzieqSource(), NetBoxSource()]
        self.micro_sources = [OpenConfigSource(), CLISource()]
    
    async def execute(self, intent: Intent, max_iterations: int = 3):
        # 1. 并行采集宏观数据
        macro_data = await asyncio.gather(
            *[source.collect(intent) for source in self.macro_sources]
        )
        
        # 2-4. 假设-验证循环
        for i in range(max_iterations):
            hypothesis = await self.generate_hypothesis(macro_data)
            micro_data = await self.verify_hypothesis(hypothesis)
            
            if await self.evaluate(hypothesis, micro_data):
                return self.generate_report(hypothesis, micro_data)
            
            # 修正假设，加入新数据
            macro_data = self.update_context(macro_data, micro_data)
        
        return "无法确定根因，建议人工介入"
```

**新工具接入示例**：
- 假设未来加入 **Splunk 日志分析**
- 只需创建 `SplunkSource()` 并注册到 `macro_sources`
- 无需修改循环逻辑

### 3.3 Batch Path - 大规模并发策略

**适用场景**：
- 定期巡检："每天 9 点检查所有核心交换机光功率"
- 批量审计："审计所有边界路由器 BGP 配置完整性"
- 合规检查:"检查 30+ 设备 MTU 是否为 9000"

**设计目标**：
- **高并发**：支持 100+ 设备同时检查
- **零幻觉**：逻辑由代码/配置定义，而非 LLM 推理
- **确定性**：相同输入保证相同输出

**架构设计**：Compiler-Executor Pattern

```
User Intent/YAML Config
         ↓
┌─────────────────────┐
│  Compiler (编译器)   │  ← LLM 仅在此介入（可选）
│  NL → Executable    │     将自然语言转为 JSON/SQL
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Map (并行分发)      │
│  NetBox → 设备列表   │
│  启动 N 个 Worker   │
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Executor (执行器)   │  ← 纯代码逻辑，零幻觉
│  优先 SuzieQ SQL    │
│  降级 CLI Fallback  │
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Validator (验证器)  │  ← Python operator 判断
│  阈值比对（非 LLM）  │     cpu > 80 → 报警
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Reporter (报告员)   │  ← LLM 总结异常，排序
│  生成人类可读报告    │
└─────────────────────┘
```

**YAML 驱动示例**：
```yaml
# config/inspections/daily_core_check.yaml
inspection_name: "每日核心网巡检"
targets: "role=core"  # NetBox 筛选条件

tasks:
  - name: "CPU 检查"
    tool: "suzieq"
    # 方式 A: 自然语言（LLM 编译为 SQL）
    intent: "检查 CPU 利用率"
    threshold:
      metric: "cpu_usage"
      operator: ">"
      value: 80
      severity: "critical"
  
  - name: "BGP 状态"
    tool: "suzieq"
    # 方式 B: 直接 SQL（零 LLM，最快）
    query: "bgp show where state != 'Established'"
    threshold:
      check_type: "exists"  # 有结果即报警
      severity: "high"
  
  - name: "光功率检查"
    tool: "cli"  # SuzieQ 无此数据，降级 CLI
    intent: "查找收光功率 < -25 dBm 的接口"
    threshold:
      metric: "rx_power"
      operator: "<"
      value: -25
      severity: "warning"
```

**代码实现（零幻觉验证器）**：
```python
import operator
from typing import Literal, List, Dict

class ThresholdValidator:
    """纯 Python 逻辑判断，不依赖 LLM"""
    
    OPS = {
        ">": operator.gt,
        "<": operator.lt,
        "==": operator.eq,
        "!=": operator.ne,
    }
    
    def validate(self, data: List[Dict], task: InspectionTask) -> List[Dict]:
        violations = []
        
        # 情况 1: 存在性检查
        if task.threshold.check_type == "exists":
            if len(data) > 0:
                return [{
                    "msg": "发现不符合预期的记录",
                    "data": data,
                    "severity": task.threshold.severity
                }]
        
        # 情况 2: 数值比对
        if task.threshold.metric:
            op_func = self.OPS[task.threshold.operator]
            for record in data:
                actual = record.get(task.threshold.metric)
                expected = task.threshold.value
                
                if actual is not None and op_func(actual, expected):
                    violations.append({
                        "device": record.get("hostname"),
                        "metric": task.threshold.metric,
                        "actual": actual,
                        "threshold": expected,
                        "severity": task.threshold.severity
                    })
        
        return violations
```

**工程化优势**：
1. **版本控制**：YAML 文件存入 Git，可追溯巡检逻辑变更
2. **权限分离**：Junior 工程师维护 YAML，Senior Review 后合并
3. **性能极致**：高频任务直接写 SQL（`query` 字段），LLM 零介入

## 四、关键技术点总结

### 4.1 统一数据源 Schema (The Interface)

**问题**：多种工具返回格式不一致
- SuzieQ: DataFrame
- CLI: 文本
- NetBox: JSON
- OpenConfig: gNMI/NETCONF XML

**解决方案**：Pydantic 标准化
```python
from pydantic import BaseModel
from typing import List, Dict, Any

class ToolOutput(BaseModel):
    """所有工具的统一输出格式"""
    source: str  # "suzieq" | "netbox" | "cli" | "openconfig"
    device: str
    timestamp: datetime
    data: List[Dict[str, Any]]  # 标准化为字典列表
    metadata: Dict[str, Any] = {}

# 工具适配器示例
class SuzieqAdapter:
    def query(self, table: str, **filters) -> ToolOutput:
        df = self.sq_obj.get(**filters)
        return ToolOutput(
            source="suzieq",
            device="multi",
            timestamp=datetime.now(),
            data=df.to_dict(orient="records")  # DataFrame → List[Dict]
        )

class CLIAdapter:
    def execute(self, command: str, device: str) -> ToolOutput:
        raw_text = self.nornir.run(task=netmiko_send_command, command_string=command)
        parsed = textfsm_parse(raw_text)  # TextFSM → List[Dict]
        return ToolOutput(
            source="cli",
            device=device,
            timestamp=datetime.now(),
            data=parsed
        )
```

**优势**：LLM 永远处理结构化 JSON，大幅降低幻觉

### 4.2 真理源校验 (SoT Validation)

**核心思想**：差异分析 (Diffing) 而非状态查询

**传统方式**（容易误导）：
```
Q: "Switch-A 的 BGP 邻居是谁？"
A: "172.16.1.2"  ← LLM 无法判断这是对是错
```

**SoT 校验方式**（自动发现问题）：
```python
class SoTComparator:
    async def compare(self, device: str, aspect: str) -> ComparisonResult:
        # 1. 从 NetBox 获取"应该是什么"（Design Intent）
        expected = await self.netbox.get_design(device, aspect)
        
        # 2. 从 SuzieQ/CLI 获取"实际是什么"（Operational State）
        actual = await self.suzieq.get_state(device, aspect)
        
        # 3. 对比差异
        diff = DeepDiff(expected, actual)
        
        return ComparisonResult(
            device=device,
            aspect=aspect,
            expected=expected,
            actual=actual,
            diff=diff,
            status="drift" if diff else "compliant"
        )
```

**应用场景**：
- BGP 邻居：NetBox 定义了 3 个邻居，但实际只起了 2 个 → **漂移报警**
- 接口状态：NetBox 标记为 "active"，但实际 "down" → **故障检测**
- VLAN 配置：预期 VLAN 100-200，实际有 VLAN 300 → **合规问题**

### 4.3 动态工具加载

**设计目标**：新工具接入无需修改核心代码

**实现方式**：
```python
# src/olav/tools/base.py
class BaseTool(ABC):
    """所有工具的基类"""
    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[ToolOutput] = ToolOutput
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolOutput:
        pass

# 工具注册表
class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}
    
    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    @classmethod
    def get_tool(cls, name: str) -> BaseTool:
        return cls._tools.get(name)

# 自动扫描 tools/ 目录
def auto_discover_tools():
    tools_dir = Path(__file__).parent
    for file in tools_dir.glob("*_tool.py"):
        module = importlib.import_module(f"olav.tools.{file.stem}")
        # 所有继承 BaseTool 的类会自动注册
```

**新工具示例**（零侵入）：
```python
# src/olav/tools/arista_eos_tool.py
class AristaEOSTool(BaseTool):
    """Arista EOS 专用工具"""
    name = "arista_eos"
    description = "Execute Arista EOS commands via eAPI"
    
    async def execute(self, device: str, command: str) -> ToolOutput:
        result = await self.eapi_client.execute(device, [command])
        return ToolOutput(
            source="arista_eos",
            device=device,
            data=result
        )

# 启动时自动注册，无需修改任何现有代码
ToolRegistry.register(AristaEOSTool())
```

### 4.4 写操作 HITL 中间件

**设计原则**：所有写操作必须经过 Human-in-the-Loop 审批

**实现方式**：
```python
class HITLMiddleware:
    """写操作拦截器"""
    
    WRITE_PATTERNS = [
        r"config", r"set", r"delete", r"shutdown",
        r"no shutdown", r"commit", r"apply"
    ]
    
    async def intercept(self, command: str, device: str) -> ApprovalResult:
        # 1. 检测是否为写操作
        if not self._is_write_operation(command):
            return ApprovalResult(approved=True, auto_pass=True)
        
        # 2. 触发 LangGraph Interrupt
        approval_request = ApprovalRequest(
            command=command,
            device=device,
            impact_analysis=await self._analyze_impact(command, device),
            timestamp=datetime.now()
        )
        
        # 3. 等待人工审批（通过 CLI 或 Web UI）
        approval = await self.approval_service.request(approval_request)
        
        # 4. 记录审计日志（OpenSearch）
        await self.audit_logger.log(approval_request, approval)
        
        return approval
    
    def _is_write_operation(self, command: str) -> bool:
        return any(re.search(p, command, re.I) for p in self.WRITE_PATTERNS)
```

**工作流集成**：
```python
class DeviceExecutionWorkflow(BaseWorkflow):
    async def execute_command(self, state: State):
        command = state["command"]
        device = state["device"]
        
        # HITL 拦截
        approval = await self.hitl.intercept(command, device)
        
        if not approval.approved:
            return {"status": "rejected", "reason": approval.reason}
        
        # 执行命令
        result = await self.cli_tool.execute(device=device, command=command)
        return {"status": "success", "result": result}
```

## 五、状态协调与 NetBox 双向同步 (Controlled State Reconciliation)

### 5.1 设计动机
传统“读取当前状态 → 告知用户”模式无法衡量合规性与配置漂移。OLAV 采用受控状态协调：以 NetBox 作为设计意图 (Design Intent, SoT)；以运行数据 (Operational State: SuzieQ/CLI/OpenConfig) 为现实。工作流自动检测漂移、分级、验证、生成修复提案，并通过 HITL 审批后执行，形成闭环与审计轨迹。

### 5.2 范围层次 (Scope Layers)
1. Device 基本属性：型号、角色、OS 版本、管理 IP
2. Interface & LAG：描述、速率、MTU、VLAN、channel 成员
3. Routing & Protocols：BGP/OSPF 邻居、VRF、EVPN、ACL 应用情况
4. Topology：LLDP/ARP/NDP 连接关系 vs 期望拓扑
5. Optics & Physical：光功率、错误计数 (CRC, FCS)
6. Security & Policy：ACL 是否完整、控制平面保护项是否缺失

### 5.3 工作流节点总览
```
User Trigger / Scheduled Cron
                    ↓
┌────────────────────────────────────────────┐
│ MacroCollect (并行采集: NetBox + SuzieQ)   │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ Normalize (结构统一 & 关键字段哈希)          │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ DriftDetect (期望 vs 实际 → 差异集合)        │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ Prioritize (风险/影响/角色/严重性评分)       │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ DeepVerify (微观二次验证/点查/CLI Fallback) │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ ProposalSynthesis (结构化修复提案生成)       │
└──────────┬─────────────────────────────────┘
                     ↓ (LangGraph Interrupt / HITL)
┌────────────────────────────────────────────┐
│ ApprovalGate (人工审核/风险备注)             │
└──────────┬─────────────────────────────────┘
                     ↓ (若批准)
┌────────────────────────────────────────────┐
│ Apply (执行写操作 + 回读确认)               │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ AuditMemory (审计日志 + 漂移快照存档)       │
└──────────┬─────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────┐
│ Report (LLM 仅总结已验证事实, 零推测)        │
└────────────────────────────────────────────┘
```

### 5.4 节点说明
- MacroCollect：多源并发获取设备列表、期望配置、实际状态表 (BGP/接口/VLAN)。
- Normalize：所有数据适配为统一 Pydantic 字段集；计算关键字段哈希 (如 BGP peer tuple)。
- DriftDetect：对比 expected vs actual，生成初步漂移记录集合。
- Prioritize：基于角色 (core>edge>access)、影响面 (全网/局部)、严重性 (安全>可用性>性能)、漂移持续时间（记忆索引中的出现频率）打分。
- DeepVerify：对高分漂移进行二次采样 (CLI/OpenConfig 精细指标)，排除误报（例如临时 flap）。
- ProposalSynthesis：非 LLM 逻辑先生成结构化 JSON patch；LLM 仅将 patch → 人类可读解释。
- ApprovalGate：LangGraph Interrupt；操作员确认每项变更的合理性与窗口；记录批注。
- Apply：调用写操作工具（受 HITL 中间件保护）；执行后即时回读验证结果。失败则自动回滚或标记人工处理。
- AuditMemory：写入 OpenSearch 审计索引 + 漂移历史 (episodic memory)；用于后续冷却期/重复抑制。
- Report：聚合执行结果、剩余未处理漂移、下一步建议；LLM 禁止发散，仅引用结构化数据。

### 5.5 数据结构 (Pydantic)
```python
class DriftRecord(BaseModel):
        device: str
        aspect: str  # e.g. "bgp_neighbor", "interface", "vlan"
        expected: Dict[str, Any]
        actual: Dict[str, Any]
        diff: Dict[str, Any]
        hash_key: str  # 规范化字段哈希
        first_seen: datetime
        last_seen: datetime
        severity: Literal['low','medium','high','critical'] | None
        risk_score: float | None

class ProposalAction(BaseModel):
        action_type: Literal['netbox_update','device_config_push']
        target: str
        commands: List[str] | None
        netbox_payload: Dict[str, Any] | None
        rationale: str  # 人类可读原因
        depends_on: List[str] = []

class ReconciliationReport(BaseModel):
        timestamp: datetime
        summary: str
        drift_processed: List[DriftRecord]
        actions_applied: List[ProposalAction]
        actions_rejected: List[ProposalAction]
        remaining_drift: List[DriftRecord]
        metrics: Dict[str, Any]
```

### 5.6 漂移检测算法
1. 规范化字段选择：BGP (local_as, peer_ip, remote_as, session_state)、接口 (name, admin_status, mtu, vlan_set)。
2. 构建 hash_key：`sha256(json.dumps(sorted_key_subset))`。
3. 每次采集生成当前 hash 集合，与上次快照比较：新增/删除/修改。
4. 新增记录 first_seen=now；修改更新 diff & last_seen；超过冷却期 (e.g. 3 cycles) 且重复出现 → 提升 severity。
5. 仅对 hash 变化的记录进入 DeepVerify，减少重复成本。

### 5.7 优先级与采样策略
风险评分公式示例：
```
Risk = RoleWeight * ImpactFactor * SeverityBase * PersistenceMultiplier
```
- RoleWeight：core=3, distribution=2, access=1
- ImpactFactor：影响 BGP/OSPF=高，单接口=低
- SeverityBase：安全策略漂移 > 邻居数量缺失 > 描述不一致
- PersistenceMultiplier：出现次数或持续时长加权 (e.g. 1 + cycles/5)
仅得分 Top N (如 20%) 进入 DeepVerify，其他批量标记为待观察。

### 5.8 HITL 安全控制
- 白名单字段：接口描述、NetBox 备注、无业务影响标签 → 可快速批准。
- 灰名单字段：MTU、VLAN、BGP remote-as → 需严格审批。
- 黑名单字段：核心路由策略、密码、AAA → 永不自动提案，仅报告。
- Apply 阶段再次二次校验命令匹配风险模式 (regex)；高风险命令强制多人复核 (future enhancement)。

### 5.9 性能优化策略
- 宏观查询批量化：SuzieQ 多表并行 (async gather)。
- 微观验证限流：Semaphore 控制同时设备 CLI 会话数。
- Hash 快照减轻全量 diff 成本；变化感知驱动后续链路。
- 漂移冷却期：降低重复验证；记忆索引存储最近 K 次状态。
- 分块处理：设备分 tranche (e.g. 50 台/批)；超时设备标记为隔离重试。

### 5.10 配置示例 (YAML)
```yaml
# config/reconciliation/policy.yaml
enabled: true
max_deep_verify: 30
cooldown_cycles: 3
role_weights:
    core: 3
    distribution: 2
    access: 1
whitelist_fields:
    - interface.description
    - device.comments
graylist_fields:
    - interface.mtu
    - bgp.remote_as
blacklist_fields:
    - device.enable_password
    - aaa.server_config
sampling:
    top_risk_percent: 20
report:
    include_raw_diff: false
    redact_sensitive: true
```

### 5.11 验证指标 (KPIs)
- 漂移检测召回率 (人工核实样本) ≥ 90%
- 漂移误报率 ≤ 5%
- DeepVerify 平均耗时 ≤ 2s/高风险项
- 自动修复成功率 ≥ 95%（不含人工拒绝）
- HITL 审批平均响应时间 ≤ 3 分钟

### 5.12 与现有策略关系
- Fast Path：可被 Reconciliation 引用作即时单项验证。
- Deep Path：共享 MacroCollect/DeepVerify 组件，减少重复实现。
- Batch Path：巡检结果输入 DriftDetect，形成统一报告；Reconciliation 可消费 Batch 巡检产生的异常作为候选。

### 5.13 实施阶段建议
Phase A：只读模式 (检测 + 报告)，禁用 Proposal/Apply。
Phase B：启用 ProposalSynthesis + HITL 审批，人工执行。
Phase C：自动执行低风险白名单字段，高风险继续 HITL。
Phase D：引入多审批人策略 (M-of-N) 与回滚编排。

## 七、迁移路径

### 5.1 当前状态
- ✅ 已实现：基础 Workflow 架构（Query/Execution/NetBox/DeepDive）
- ✅ 已实现：Schema-Aware Tools（SuzieQ）
- ⚠️ 待改进：硬编码的 Orchestrator

### 5.2 重构步骤

**Phase 1: 工作流注册机制**
1. 创建 `WorkflowRegistry` 类
2. 为现有 4 个 Workflow 添加装饰器注册
3. 测试向后兼容性

**Phase 2: 动态意图路由**
1. 实现 `DynamicIntentRouter`（语义索引 + LLM 分类）
2. 将 `root_agent_orchestrator.py` 重构为调用 Router
3. A/B 测试：硬编码分类 vs 动态路由

**Phase 3: 执行策略抽象**
1. 抽象 `FastPathStrategy` / `DeepPathStrategy` / `BatchPathStrategy`
2. Workflow 可声明支持的策略
3. 根据任务复杂度自动选择策略

**Phase 4: 巡检模式 YAML 驱动**
1. 实现 `InspectionConfig` Pydantic Schema
2. 创建 `ThresholdValidator`（纯 Python 逻辑）
3. 添加 `config/inspections/` 目录，支持 Git 版本控制

### 5.3 验证标准
- [ ] 新增工作流无需修改 Orchestrator 代码
- [ ] 语义路由准确率 > 95%（与硬编码对比）
- [ ] 巡检模式支持 100+ 设备并发
- [ ] 写操作 100% 经过 HITL 审批

## 八、FAQ
A

### Q1: 动态路由会增加延迟吗？
A: 语义初筛使用向量匹配（< 100ms），LLM 仅对 Top-3 分类（< 1s），总延迟可接受。

### Q2: 如何处理意图模糊的查询？
A: Router 返回多个候选，让用户选择；或进入 Clarification 对话流程。

### Q3: YAML 驱动的巡检是否过于复杂？
A: 提供 Web UI 可视化配置工具，生成 YAML；高级用户可直接编辑。

### Q4: 是否支持自定义执行策略？
A: 是，继承 `BaseStrategy` 并注册即可，Workflow 可声明 `preferred_strategies`。


### Q5: 如何保证 HITL 不被绕过？
A: 中间件在工具层强制拦截，即使 LLM 尝试直接调用也会被阻止；审计日志不可篡改。

---

## 九、LangServe API 平台与新一代 CLI 架构

### 9.1 总体架构设计 (C/S 架构)
OLAV 将从单机 CLI 工具转型为 C/S 架构，服务端通过 LangServe + FastAPI 暴露所有工作流为标准 API，客户端（CLI/Web/Bot）通过 HTTP/WebSocket 远程调用，实现多用户、认证、流式交互与 HITL 审批。

```
Client Layer (多种交互模式):
    - 新 CLI (交互式)
    - Web GUI (未来)
    - Slack/Teams Bot (未来)
Server Layer (LangServe + FastAPI):
    - API Gateway / Auth
    - Dynamic Intent Router
    - 多种 Workflow (LangGraph)
    - Postgres Checkpointer (会话/审计)
```

### 9.2 服务端设计
* 框架：FastAPI + LangServe，所有工作流通过 add_routes 暴露为 REST/WS API。
* 状态存储：PostgresSaver，支持多用户/多线程隔离。
* API 路由：
    - POST /v1/chat/invoke：单次对话
    - POST /v1/chat/stream：流式对话
    - GET/POST /v1/threads/{id}/state：HITL 审批与状态查询
    - POST /auth/token：JWT 登录
* 多模式支持：API 支持 configurable 参数，允许客户端指定 mode/user_id/role。
* 认证预留：FastAPI 层实现 JWT 校验，user_id/role 注入 LangGraph config，HITL/AuditLogger 感知操作者身份。
* 线程隔离与权限：thread_id 与 user_id 绑定，API 层校验访问权限。

### 9.3 新 CLI 客户端设计
* 通信：langserve.RemoteRunnable 或 httpx 异步 HTTP 客户端。
* UI 渲染：rich（Markdown/表格/动画），prompt_toolkit（输入框/补全）。
* 交互循环：
    1. 登录获取 Token
    2. 输入查询，调用 /stream 接口
    3. 实时渲染 token/tool_start/tool_end 事件
    4. HITL 审批弹窗，人工确认高风险操作

### 9.4 认证与多用户设计
* 用户模型：username/role/api_key
* 上下文传递：Token → FastAPI → LangGraph config → Agent/HITL/AuditLogger
* 权限控制：RBAC，Admin/Operator/Auditor 分级

### 9.5 实施路线图
1. Phase 1：Server 端基础建设，API 化所有工作流
2. Phase 2：新 CLI 客户端开发，流式交互与 HITL 审批
3. Phase 3：认证与多租户，RBAC 权限控制
4. Phase 4：WebGUI/Slack/Teams Bot 对接

### 9.6 总结
此架构将 OLAV 从工具升级为平台，实现解耦、安全、扩展与多模式交互。未来可无缝对接 Web、Bot、自动化等多种入口。
