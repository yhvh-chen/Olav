# Deep Dive Architecture V2: Supervisor-Inspector 模式

## 目录

1. [背景](#背景) - 当前问题分析
2. [新架构：Supervisor-Inspector](#新架构supervisor-inspector) - 核心设计
3. [Quick Analyzer：SuzieQ 快速扫描](#quick-analyzersuzieq-快速扫描) - 充分利用 SuzieQ 能力
4. [Inspector Checklist 驱动设计](#inspector-checklist-驱动设计) - 方向性指引 + Schema 查询
5. [L1-L4 故障覆盖率分析](#l1-l4-故障覆盖率分析) - 能力边界与补充策略
6. [State 设计](#state-设计) - 数据结构
7. [Prompt 设计](#prompt-设计) - 简短聚焦的 Prompt
8. [ETL 脚本](#etl-脚本-诊断报告索引) - 报告索引
9. [与归档方案对比](#与归档方案对比) - 三方架构比较
10. [迁移路径](#迁移路径) - 实施计划
11. [附录：Standard 模式的 Middleware 优化](#附录standard-模式的-middleware-优化) - ToolMiddleware 自动注入
12. [附录：Workflow 职责分离与 BatchExecutionWorkflow](#附录workflow-职责分离与-batchexecutionworkflow) - 批量并行执行

---

## 背景

### 当前问题

1. **单 Agent ReAct 的局限**：
   - 长 Prompt 导致 LLM 幻觉和指令遗忘
   - LLM 经常"偷懒"，只查一台设备就下结论
   - 没有系统性遍历故障路径上的所有设备
   - 没有按 L1→L5 分层检查

2. **SuzieQ 数据滞后**：
   - SuzieQ 是周期性采集（1-5分钟），数据可能过时
   - Agent 看到 "no data" 就下结论，没有升级到实时 CLI

3. **Prompt 已经很长**：
   - `react_diagnosis.yaml` 超过 100 行
   - 包含工具说明、分层策略、升级规则、输出格式
   - LLM 容易忽略关键指令

## 新架构：Supervisor-Inspector

参考 [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research) 的 Supervisor-Researcher 模式。

### 核心思想

1. **架构强制执行**：不依赖 LLM 遵循长 Prompt，用代码确保每台设备都被检查
2. **职责分离**：Supervisor 做分析和调度，Inspector 做具体检查
3. **并行执行**：多台设备可以并行检查
4. **短 Prompt**：每个组件只需要简短的、聚焦的 Prompt

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                                │
│            "SW1 下面的设备不能访问 R2 后面的服务器"               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Diagnosis Supervisor                          │
│                                                                  │
│  工具: kb_search (历史案例), suzieq_query (拓扑), log_search     │
│       netbox_api (获取设备类型/厂商信息)                         │
│  职责:                                                           │
│    1. 查询知识库，获取相似历史案例 ← Agentic RAG               │
│    2. 分析故障描述，确定源和目标                                  │
│    3. 查询拓扑，找出故障路径: [SW1, R1, R2, SW2]                 │
│    4. 从 NetBox 获取每台设备的 platform/vendor                   │
│    5. 结合历史案例，形成初步假设                                 │
│    6. Send() 分发 Inspector 任务（包含设备类型+相似案例）        │
│                                                                  │
│  Prompt: 简短，只关注"分析范围+调度"                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ Send() 并行分发（包含 device_info + similar_cases）
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  Device Inspector │ │  Device Inspector │ │  Device Inspector │
│       (SW1)       │ │       (R1)        │ │       (R2)        │
│  platform: ios    │ │  platform: iosxr  │ │  platform: junos  │
│                   │ │                   │ │                   │
│ 工具:             │ │ 工具:             │ │ 工具:             │
│  - nornir_cli     │ │  - nornir_cli     │ │  - nornir_cli     │
│  - nornir_netconf │ │  - nornir_netconf │ │  - nornir_netconf │
│  - schema_search  │ │  - schema_search  │ │  - schema_search  │
│                   │ │                   │ │                   │
│ 输入:             │ │ 输入:             │ │ 输入:             │
│  similar_cases    │ │  similar_cases    │ │  similar_cases    │
│  (参考历史检查点) │ │  (参考历史检查点) │ │  (参考历史检查点) │
│                   │ │                   │ │                   │
│ 输出: 层级报告    │ │ 输出: 层级报告    │ │ 输出: 层级报告    │
└───────────────────┘ └───────────────────┘ └───────────────────┘
                │               │               │
                └───────────────┼───────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Diagnosis Conclusion                          │
│                                                                  │
│  输入: 所有 Inspector 的检查报告 + 相似历史案例                  │
│  职责:                                                           │
│    1. 汇总所有异常发现                                           │
│    2. 参考相似案例的 root_cause                                  │
│    3. 分析因果关系（A 导致 B）                                   │
│    4. 确定根因（置信度最高的异常）                               │
│    5. 生成修复建议                                               │
│                                                                  │
│  Prompt: 简短，只关注"汇总+判断根因"                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Report Generator                              │
│                                                                  │
│  输入: 诊断结论 + 所有检查结果                                   │
│  职责:                                                           │
│    1. 生成结构化 DiagnosisReport 对象                            │
│    2. 渲染 Markdown 格式报告                                     │
│    3. 提取元数据 (tags, protocols, layers)                       │
│                                                                  │
│  输出: diagnosis_report (含 markdown_content)                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Report Indexer (Agentic RAG)                  │
│                                                                  │
│  职责:                                                           │
│    1. 生成 fault_description embedding                           │
│    2. 生成 root_cause embedding                                  │
│    3. 索引到 OpenSearch (diagnosis-reports)                      │
│                                                                  │
│  效果: 未来相似故障可被检索，形成知识积累                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Final Report                              │
│                                                                  │
│  根因: R1 接口 Gi0/0/0 处于 admin down 状态                      │
│  置信度: 95%                                                     │
│  证据链:                                                         │
│    - SW1 (ios): 所有接口 up，MAC 表正常                          │
│    - R1 (iosxr): Gi0/0/0 admin down ← 根因                       │
│    - R2 (junos): 未收到来自 R1 的流量                            │
│  建议: 在 R1 上启用该接口                                        │
│  报告已索引: ✓ (Case #abc123)                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 工具分配策略（关键设计决策）

> **实现状态**: ✅ 已完成 (2025-12-04)
> - `supervisor_node` 在 Round 0 调用 `kb_search` 和 `syslog_search`
> - 结果存入 State: `similar_cases`, `syslog_events`, `priority_layer`
> - `quick_analyzer_node` 只使用 SuzieQ + Nornir 工具
> - 详见 `src/olav/workflows/supervisor_driven.py`

### 核心原则

**Supervisor 是决策者，Quick Analyzer 是执行者。**

缩小故障范围主要靠**决策优化**，不是让执行者自己决定查什么。

### 工具分配矩阵

| 工具 | 分配给谁 | 调用时机 | 用途 |
|------|---------|---------|------|
| `kb_search` | **Supervisor** | Round 0 初始化 | 查历史案例，指导层级优先级 |
| `syslog_search` | **Supervisor** | Round 0 初始化 | 查触发事件，定位故障层级 |
| `suzieq_*` | Quick Analyzer | 每轮执行 | 收集指定层级的证据（60% 置信度） |
| `cli_show` | Quick Analyzer | 验证阶段 | 实时验证（95% 置信度） |
| `netconf_get` | Quick Analyzer | 验证阶段 | 结构化实时数据 |
| `kb_index_report` | Report Generator | 诊断完成后 | 索引新报告到知识库 |

### 为什么 RAG/Syslog 给 Supervisor？

**问题场景**：用户说 "R1 BGP 邻居 down"

**错误做法（工具给 Quick Analyzer）**：
```
Round 1: Supervisor 让 Quick Analyzer 查 L1
         → Quick Analyzer 自己查 KB，发现历史案例指向 L3
         → 但他只能在 L1 的报告里说 "建议查 L3"
         → Supervisor 不知道这个建议
Round 2: Supervisor 继续让查 L2...
Round 5: 终于查到 L3
```

**正确做法（工具给 Supervisor）**：
```
Round 0: Supervisor 查 KB → 历史案例 80% 指向 L3
         Supervisor 查 Syslog → 发现 "BGP-NEIGHBOR-DOWN" 日志
         → 直接决定先查 L3
Round 1: Quick Analyzer 查 L3 → 发现问题
         → 只用 1 轮就定位！
```

### Supervisor 的初始化流程

```python
async def supervisor_init_node(state: SupervisorDrivenState) -> dict:
    """Round 0: 使用 RAG + Syslog 确定层级优先级。"""
    query = state["query"]
    
    # 1. 查知识库获取历史经验
    similar_cases = kb_search(query=query, size=3)
    layer_hints = extract_layer_hints(similar_cases)
    # 结果: {"L3": 0.8, "L2": 0.15, "L1": 0.05}
    
    # 2. 查 Syslog 获取触发事件
    recent_events = syslog_search(
        keyword="DOWN|ERROR|NEIGHBOR",
        start_time="now-1h",
        limit=20
    )
    event_layer = infer_layer_from_syslog(recent_events)
    # 结果: "L3" (因为发现 BGP 相关日志)
    
    # 3. 综合决策层级优先级
    layer_priority = merge_hints(layer_hints, event_layer)
    # 结果: ["L3", "L2", "L1", "L4"]
    
    return {
        "layer_priority": layer_priority,
        "similar_cases": similar_cases,  # 传给 Quick Analyzer 参考
        "trigger_events": recent_events,
    }
```

### Quick Analyzer 只关注执行

Quick Analyzer **不需要** kb_search 和 syslog_search，因为：

1. **Supervisor 已经做了**：历史案例和触发事件在 Round 0 就查完了
2. **避免决策冲突**：如果 Quick Analyzer 自己查 KB 发现应该查 L3，但 Supervisor 让他查 L1，他应该听谁的？
3. **减少 Token 消耗**：每轮都查 KB/Syslog 是浪费

Quick Analyzer 的工具应该是：
- `suzieq_schema_search` - 发现可用字段
- `suzieq_query` - 查询历史数据
- `suzieq_health_check` - 断言检查
- `cli_show` - 实时验证
- `netconf_get` - 结构化数据

---

## Quick Analyzer：SuzieQ 快速扫描

### 问题：SuzieQ 能力未被充分利用

当前设计直接让 Inspector 去每台设备上 NETCONF/CLI 查询，**完全绕过了 SuzieQ 的内置分析能力**：

| SuzieQ 内置能力 | 当前使用情况 | 浪费程度 |
|----------------|-------------|---------|
| `path.show()` - 路由追踪 | ❌ 未使用 | **高** |
| `bgp.aver()` - BGP 断言检查 | ❌ 未使用 | **高** |
| `ospf.aver()` - OSPF 断言检查 | ❌ 未使用 | **高** |
| `interface.aver()` - 接口断言 | ❌ 未使用 | **高** |
| `topology.summarize()` - 拓扑分析 | 部分使用 | 中 |
| `lldp/arpnd` - L2 邻居分析 | 部分使用 | 中 |

### 解决方案：两阶段诊断

```
阶段1: Quick Analyzer (SuzieQ 历史数据, 置信度 ≤60%)
       ↓
       发现可疑点: [R1-BGP-Down, SW2-Interface-Flapping]
       ↓
阶段2: Supervisor 调度实时验证 (NETCONF/CLI, 置信度提升到 90%+)
```

### 改进后的完整架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Query                                      │
│                "SW1 下面的设备不能访问 R2 后面的服务器"                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Quick Analyzer (NEW)                                │
│                                                                              │
│  模式: ReAct (单 Agent, 快速)                                                │
│  工具: suzieq_path, suzieq_aver, suzieq_summarize                           │
│  职责:                                                                       │
│    1. path.show(src, dst) → 发现路径上的设备                                 │
│    2. 对路径上每台设备运行 aver() 断言检查                                    │
│    3. 汇总可疑点 + 置信度 (历史数据 ≤60%)                                     │
│                                                                              │
│  输出: QuickScanResult                                                       │
│    - suspected_issues: [{device, layer, issue, confidence: 0.5}]             │
│    - path_devices: [SW1, R1, R2, SW2]                                        │
│    - data_freshness: "2 minutes ago"                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Diagnosis Supervisor                                 │
│                                                                              │
│  输入:                                                                       │
│    - QuickScanResult (来自 Quick Analyzer)                                   │
│    - kb_search() 历史案例                                                    │
│    - log_search() 相关日志                                                   │
│                                                                              │
│  智能决策:                                                                    │
│    1. 如果 QuickScan 置信度 ≥50% → 优先验证这些点                            │
│    2. 如果 QuickScan 无发现 → 全路径 L1-L5 检查                              │
│    3. 结合历史案例调整检查优先级                                              │
│                                                                              │
│  输出: 排序后的 InspectionTask 列表 (按优先级)                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────┴───────────────┐
                    │      Parallel Inspectors      │
                    │  (只验证 Supervisor 指定的点)   │
                    │  (不再盲目全路径检查)           │
                    └───────────────────────────────┘
                                    │
                                    ▼
                          Diagnosis Conclusion
                                    │
                                    ▼
                           Report Generator
                                    │
                                    ▼
                            Report Indexer
```

### Quick Analyzer 工具设计

```python
# SuzieQ 高级分析工具（充分利用其内置能力）

@tool
def suzieq_path_trace(
    source: str,
    destination: str,
    vrf: str = "default"
) -> dict:
    """
    使用 SuzieQ 的 path.show() 追踪路由路径。
    
    返回:
        - path: 完整路径设备列表
        - hops: 每一跳的详细信息（接口、协议）
        - issues: 路径上发现的问题（MTU 不匹配、接口 down 等）
    """
    sq = get_sqobject("path")
    result = sq.show(
        source=source,
        dest=destination,
        vrf=vrf
    )
    return {
        "path": extract_path_devices(result),
        "hops": result.to_dict(orient="records"),
        "issues": extract_path_issues(result),
    }


@tool
def suzieq_health_check(
    hostname: str,
    checks: list[str] = ["bgp", "ospf", "interfaces", "mlag"]
) -> dict:
    """
    使用 SuzieQ 的 aver() 方法对设备进行健康检查。
    
    aver() 是 SuzieQ 的断言检查功能，可以快速发现异常。
    
    返回:
        - passed: 通过的检查项
        - failed: 失败的检查项（可疑故障点）
        - data_age: 数据新鲜度
    """
    results = {"passed": [], "failed": [], "data_age": None}
    
    for check in checks:
        sq = get_sqobject(check)
        aver_result = sq.aver(hostname=hostname)
        
        if aver_result.empty:
            continue
            
        # aver() 返回断言失败的记录
        failures = aver_result[aver_result["assert"] == "fail"]
        
        if failures.empty:
            results["passed"].append(check)
        else:
            results["failed"].append({
                "check": check,
                "issues": failures.to_dict(orient="records"),
                "layer": map_check_to_layer(check),
            })
    
    results["data_age"] = get_data_freshness(hostname)
    return results


@tool
def suzieq_topology_analyze(
    devices: list[str] | None = None
) -> dict:
    """
    使用 SuzieQ 的 topology.summarize() 分析网络拓扑。
    
    返回:
        - topology: 设备连接关系
        - anomalies: 拓扑异常（单点故障、环路等）
    """
    sq = get_sqobject("topology")
    
    if devices:
        result = sq.summarize(hostname=devices)
    else:
        result = sq.summarize()
    
    return {
        "topology": result.to_dict(orient="records"),
        "anomalies": detect_topology_anomalies(result),
    }
```

### 置信度机制

```python
class SuspectedIssue(TypedDict):
    """可疑故障点"""
    device: str
    layer: Literal["L1", "L2", "L3", "L4"]
    issue: str                    # "BGP peer down", "Interface flapping"
    confidence: float             # 0.0 - 1.0
    data_age_seconds: int         # 数据新鲜度
    source: Literal["suzieq", "realtime"]


def calculate_confidence(data_age_seconds: int, source: str) -> float:
    """
    计算置信度。
    
    规则:
    - 实时数据 (NETCONF/CLI): 95%
    - SuzieQ 历史数据: 最高 60%，随数据老化递减
    """
    if source == "realtime":
        return 0.95  # 实时数据高置信
    
    # SuzieQ 历史数据：越新置信度越高，但最高 60%
    if data_age_seconds < 60:
        return 0.60  # 1 分钟内
    elif data_age_seconds < 180:
        return 0.50  # 3 分钟内
    elif data_age_seconds < 300:
        return 0.40  # 5 分钟内
    else:
        return 0.25  # 超过 5 分钟的数据置信度很低


class QuickScanResult(TypedDict):
    """Quick Analyzer 输出"""
    suspected_issues: list[SuspectedIssue]
    path_devices: list[str]
    topology_anomalies: list[str]
    data_freshness: str           # "Data from 2 minutes ago"
    scan_duration_ms: float
```

### Supervisor 智能调度

Quick Analyzer 返回后，Supervisor 不再盲目全路径检查：

```python
async def plan_inspections(
    quick_scan: QuickScanResult,
    kb_cases: list[SimilarCase],
    logs: list[LogEntry]
) -> list[InspectionTask]:
    """
    根据 QuickScan 结果智能规划检查任务。
    
    策略:
    1. 优先验证 QuickScan 发现的可疑点 (置信度 ≥40%)
    2. 结合历史案例补充检查点
    3. 如果 QuickScan 无发现 → 降级到全路径检查
    """
    tasks = []
    
    # 1. 优先验证 QuickScan 发现的可疑点
    for issue in quick_scan["suspected_issues"]:
        if issue["confidence"] >= 0.4:  # 40% 以上值得验证
            tasks.append(InspectionTask(
                device=issue["device"],
                layer=issue["layer"],
                priority="high",
                reason=f"SuzieQ detected: {issue['issue']}",
                focus_area=issue["issue"],  # 告诉 Inspector 重点检查什么
            ))
    
    # 2. 结合历史案例补充检查点
    for case in kb_cases:
        if case["similarity"] >= 0.7:
            for checkpoint in case["key_checkpoints"]:
                if not any(t.device == checkpoint["device"] and t.layer == checkpoint["layer"] 
                          for t in tasks):
                    tasks.append(InspectionTask(
                        device=checkpoint["device"],
                        layer=checkpoint["layer"],
                        priority="medium",
                        reason=f"Similar case: {case['title']}",
                    ))
    
    # 3. 如果 QuickScan 完全没发现 → 降级到全路径检查
    if not quick_scan["suspected_issues"]:
        for device in quick_scan["path_devices"]:
            for layer in ["L1", "L2", "L3", "L4"]:
                tasks.append(InspectionTask(
                    device=device,
                    layer=layer,
                    priority="low",
                    reason="Full path scan (no quick findings)",
                ))
    
    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(tasks, key=lambda t: priority_order[t.priority])
```

### 效率对比

| 维度 | 改进前 (直接 Inspector) | 改进后 (Quick Analyzer + Inspector) |
|------|------------------------|-------------------------------------|
| **首次响应时间** | 等所有 Inspector 完成 | **秒级返回初步结论** |
| **LLM 调用次数** | N 设备 × M 层 = N×M 次 | 1 次扫描 + K 次验证 (**K << N×M**) |
| **SuzieQ 能力利用** | 只做数据查询 | **path/aver/summarize 全用上** |
| **用户体验** | 黑盒等待 | **渐进式结果展示** |
| **资源消耗** | 高 (大量实时查询) | 低 (优先历史数据) |

### Quick Analyzer Prompt

```yaml
# config/prompts/strategies/deep_dive/quick_analyzer.yaml

_type: prompt
input_variables:
  - fault_description
  - source_device
  - destination_device
template: |
  你是 SuzieQ 快速扫描专家。使用 SuzieQ 的高级分析功能快速定位可疑故障点。

  ## 故障描述
  {fault_description}

  ## 分析流程
  1. **路径追踪**: 使用 suzieq_path_trace 找出 {source_device} 到 {destination_device} 的路径
  2. **健康检查**: 对路径上每台设备运行 suzieq_health_check
  3. **汇总发现**: 列出所有可疑点，标注置信度

  ## 重要规则
  - 这是历史数据分析，置信度最高 60%
  - 即使发现问题，也只是"可疑"，需要后续实时验证
  - 如果数据超过 5 分钟，明确标注 "数据可能过时"

  ## 输出格式
  返回 QuickScanResult JSON，包含:
  - suspected_issues: 可疑点列表
  - path_devices: 路径设备
  - data_freshness: 数据新鲜度说明
```

---

### Inspector 的 ReAct 工作模式

Inspector 不是固定流程，而是一个**受限的 ReAct Agent**：

1. **目标明确**：必须完成 L1→L4 每层检查
2. **工具灵活**：根据设备类型自主选择 CLI 或 NETCONF
3. **厂商无关**：使用 OpenConfig 或查询 schema 获取正确命令

```
┌─────────────────────────────────────────────────────────────────┐
│                    Inspector ReAct 循环                          │
│                                                                  │
│  输入: device="R1", platform="cisco_iosxr"                       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 1 - 物理层检查                                        │ │
│  │                                                             │ │
│  │ Thought: 需要检查接口物理状态，R1 是 IOS-XR 设备            │ │
│  │                                                             │ │
│  │ Option A (NETCONF - 优先):                                  │ │
│  │   Action: nornir_netconf(                                   │ │
│  │     hostname="R1",                                          │ │
│  │     path="/interfaces/interface/state"  # OpenConfig        │ │
│  │   )                                                         │ │
│  │                                                             │ │
│  │ Option B (CLI - 备选):                                      │ │
│  │   Thought: 先查询 schema 获取正确命令                       │ │
│  │   Action: openconfig_schema_search("interface status")      │ │
│  │   Observation: IOS-XR 使用 "show interfaces brief"          │ │
│  │   Action: nornir_cli(hostname="R1", command="show ...")     │ │
│  │                                                             │ │
│  │ Observation: 接口 Gi0/0/0 状态 admin-down                   │ │
│  │ Result: L1 异常，置信度 0.9                                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 2 - 链路层检查                                        │ │
│  │ ...                                                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 3 - 网络层检查                                        │ │
│  │ ...                                                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 4 - 过滤/策略检查                                     │ │
│  │ ...                                                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  输出: InspectionResult(device="R1", anomalies=[...], ...)       │
└─────────────────────────────────────────────────────────────────┘
```

### Inspector Checklist 驱动设计

#### 问题：如何避免 LLM 幻觉命令？

直接在 Prompt 中给出具体命令容易导致幻觉：
- LLM 可能编造不存在的命令
- 不同厂商命令语法不同
- Prompt 维护成本高

#### 解决方案：方向性指引 + Schema 查询

```
Prompt 只说"检查方向"（做什么）
        ↓
Agent 必须调用 schema_search（怎么做）
        ↓
Schema 返回正确命令
        ↓
Agent 执行准确命令
```

**Inspector Prompt 结构**：

```yaml
## 你的任务
对设备 {device} ({platform}) 进行 {layer} 层检查。

## 检查清单（必须全部覆盖）
{checklist}

## 工具使用规则
1. ⚠️ 必须先用 schema_search 查询正确的命令/XPath
2. 不要猜测命令语法
3. 优先使用 NETCONF (OpenConfig)，CLI 作为备选

## 输出要求
对每个检查项报告：✓ 正常 / ✗ 异常 / ? 无法检查
```

#### 动态 Checklist 生成

Supervisor 根据 Quick Analyzer 结果动态生成 Checklist，**补充 SuzieQ 的盲区**：

```python
# 基础 Checklist（覆盖各层常见故障）
BASE_CHECKLIST = {
    "L1": [
        "接口物理状态 (Up/Down/Admin-Down)",
        "接口错误计数 (CRC, Input/Output Errors)",
        "光模块状态 (如适用)",
    ],
    "L2": [
        "VLAN 配置和状态",
        "MAC 地址表",
        "LLDP/CDP 邻居",
        "STP 状态 (Root Bridge, Port State, Blocked Ports)",  # SuzieQ 盲区
        "Trunk 允许 VLAN",
    ],
    "L3": [
        "路由表 (目标网段是否存在)",
        "BGP/OSPF 邻居状态",
        "ARP/ND 表",
        "ACL 是否阻断目标流量",  # SuzieQ 盲区
    ],
    "L4": [
        "NAT 转换状态 (如适用)",
        "QoS 队列丢包 (如适用)",
    ],
}

def generate_checklist(
    device: str,
    layer: str,
    quick_scan: QuickScanResult,
    similar_cases: list[SimilarCase]
) -> list[str]:
    """
    动态生成检查清单。
    
    策略:
    1. 基础 Checklist 保证覆盖率
    2. Quick Analyzer 发现的可疑点优先（标记 ⚠️）
    3. 历史案例中的关键检查点补充
    """
    checklist = BASE_CHECKLIST.get(layer, []).copy()
    
    # 1. 把 QuickScan 发现的可疑点提到最前面
    for issue in quick_scan.suspected_issues:
        if issue["device"] == device and issue["layer"] == layer:
            checklist.insert(0, f"⚠️ 重点: {issue['issue']} (QuickScan 置信度 {issue['confidence']:.0%})")
    
    # 2. 从相似历史案例中补充检查点
    for case in similar_cases:
        if case.similarity_score >= 0.7:
            # 历史案例可能提示需要额外检查某些项
            if "ACL" in case.root_cause and "ACL" not in str(checklist):
                checklist.append("⚠️ 历史案例提示: 检查 ACL 配置")
            if "MTU" in case.root_cause and "MTU" not in str(checklist):
                checklist.append("⚠️ 历史案例提示: 检查 MTU 配置")
    
    return checklist
```

#### 完成情况追踪

在 State 中跟踪 Checklist 完成情况，确保 Agent 不遗漏：

```python
class DeviceInspectorState(TypedDict):
    device: DeviceInfo
    checklist: list[str]              # 需要检查的项目
    checklist_status: dict[str, str]  # {"接口状态": "✓ 正常", "STP": "✗ 异常", ...}
    ...
```

---

### L1-L4 故障覆盖率分析

#### 覆盖率矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         故障覆盖率总览                                       │
├────────┬─────────────────────────┬─────────────────────────┬────────────────┤
│  层级  │  Quick Analyzer (SuzieQ) │  Inspector (实时验证)   │  综合覆盖率    │
├────────┼─────────────────────────┼─────────────────────────┼────────────────┤
│  L1    │  70%                    │  95%                    │  ~85%          │
├────────┼─────────────────────────┼─────────────────────────┼────────────────┤
│  L2    │  55%                    │  85%                    │  ~70%          │
├────────┼─────────────────────────┼─────────────────────────┼────────────────┤
│  L3    │  75%                    │  90%                    │  ~80%          │
├────────┼─────────────────────────┼─────────────────────────┼────────────────┤
│  L4    │  15%                    │  45%                    │  ~30%          │
├────────┼─────────────────────────┼─────────────────────────┼────────────────┤
│  总体  │  ~55%                   │  ~80%                   │  **~65%**      │
└────────┴─────────────────────────┴─────────────────────────┴────────────────┘
```

#### 详细故障类型分析

**Layer 1 - 物理层 (~85% 覆盖)**

| 故障类型 | Quick Analyzer | Inspector | 说明 |
|---------|---------------|-----------|------|
| 接口 Down | ✅ | ✅ | 完全覆盖 |
| 接口 Flapping | ✅ | ✅ | SuzieQ 有历史数据 |
| 光模块故障 | ⚠️ | ✅ | 需要确保采集 transceiver |
| CRC/Errors | ✅ | ✅ | 完全覆盖 |
| MTU 不匹配 | ✅ | ✅ | path.show() 检测 |
| PoE 故障 | ❌ | ⚠️ | **缺口** - 厂商特定 |

**Layer 2 - 链路层 (~70% 覆盖)**

| 故障类型 | Quick Analyzer | Inspector | 说明 |
|---------|---------------|-----------|------|
| VLAN 缺失 | ✅ | ✅ | 完全覆盖 |
| MAC Flapping | ✅ | ✅ | SuzieQ 可检测 |
| LLDP 邻居丢失 | ✅ | ✅ | 完全覆盖 |
| MLAG 问题 | ✅ | ✅ | mlag.aver() |
| **STP 问题** | ❌ | ✅ | **SuzieQ 盲区** - Checklist 补充 |
| Trunk 配置错误 | ⚠️ | ✅ | 需要配置数据 |

**Layer 3 - 网络层 (~80% 覆盖)**

| 故障类型 | Quick Analyzer | Inspector | 说明 |
|---------|---------------|-----------|------|
| 路由缺失 | ✅ | ✅ | path.show() + routes |
| 次优路由 | ✅ | ✅ | 完全覆盖 |
| BGP Peer Down | ✅ | ✅ | bgp.aver() |
| OSPF Neighbor Down | ✅ | ✅ | ospf.aver() |
| ARP 问题 | ✅ | ✅ | arpnd 表 |
| **ACL 阻断** | ❌ | ✅ | **SuzieQ 盲区** - Checklist 补充 |
| **Route Policy** | ❌ | ✅ | **SuzieQ 盲区** - Checklist 补充 |
| 认证失败 | ❌ | ⚠️ | 需要日志分析 |

**Layer 4 - 传输层 (~30% 覆盖)**

| 故障类型 | Quick Analyzer | Inspector | 说明 |
|---------|---------------|-----------|------|
| NAT 表满 | ❌ | ✅ | CLI 检查 |
| 防火墙阻断 | ❌ | ⚠️ | 厂商特定 |
| QoS 队列丢包 | ⚠️ | ✅ | 需要采集 |
| TCP/UDP 问题 | ❌ | ❌ | **超出范围** - 需要主机侧 |

#### SuzieQ 盲区与 Checklist 补充策略

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SuzieQ 盲区补充策略                                    │
├─────────────────────────────────┬───────────────────────────────────────────┤
│  SuzieQ 盲区                    │  Checklist 补充                            │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  STP 状态检测能力有限            │  L2 Checklist 强制包含 STP 检查            │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  不采集 ACL hit counters        │  L3 Checklist 强制包含 ACL 阻断检查        │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  不采集 Route Policy            │  L3 Checklist 包含策略路由检查             │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  认证状态不可见                  │  结合 Syslog 分析认证失败日志              │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  L4 NAT/FW 状态                 │  L4 Checklist 包含 NAT/FW 检查（如适用）   │
└─────────────────────────────────┴───────────────────────────────────────────┘
```

#### 能力边界说明

在最终报告中明确告知用户工具的能力边界：

```markdown
## 诊断范围说明

✅ **完全覆盖**
- L1: 接口状态、物理层错误、MTU
- L2: VLAN、MAC、LLDP/CDP、MLAG
- L3: 路由、BGP、OSPF、ARP

⚠️ **需要实时验证**
- L2: STP 状态（Quick Analyzer 不可见）
- L3: ACL/Policy 阻断（Quick Analyzer 不可见）

❌ **超出范围**
- L4: 端到端 TCP/UDP 连接状态（需要主机侧检查）
- 应用层问题（需要 APM 工具）
```

---

## State 设计

```python
from typing import Annotated, TypedDict, Literal
import operator
from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    """设备信息（从 NetBox 获取）"""
    name: str = Field(description="设备名称")
    platform: str = Field(description="平台类型: cisco_ios, cisco_iosxr, juniper_junos, arista_eos, ...")
    vendor: str = Field(description="厂商: cisco, juniper, arista, ...")
    device_type: str = Field(description="设备类型: router, switch, firewall, ...")
    management_ip: str = Field(description="管理 IP")


class LayerResult(BaseModel):
    """单层检查结果"""
    layer: Literal["L1", "L2", "L3", "L4"] = Field(description="检查的层级")
    status: Literal["normal", "anomaly", "unknown"] = Field(description="状态")
    method_used: Literal["netconf", "cli"] = Field(description="使用的方法")
    findings: list[str] = Field(description="发现的问题")
    confidence: float = Field(description="该层存在问题的置信度 0-1")
    raw_output: str = Field(description="原始输出（用于调试）")


class InspectionResult(BaseModel):
    """单台设备的完整检查结果"""
    device: DeviceInfo = Field(description="设备信息")
    layer_results: dict[str, LayerResult] = Field(
        description="每层检查结果: {L1: LayerResult, L2: LayerResult, ...}"
    )
    overall_status: Literal["healthy", "degraded", "faulty"] = Field(description="整体状态")
    anomalies: list[str] = Field(description="所有发现的异常")
    root_cause_candidate: str | None = Field(description="该设备上最可能的根因")
    confidence: float = Field(description="该设备存在问题的总体置信度 0-1")


class DiagnosisSupervisorState(TypedDict):
    """Supervisor 的状态"""
    messages: list  # 用户消息
    fault_description: str  # 故障描述
    source: str  # 源设备/主机
    destination: str  # 目标设备/主机
    fault_path: list[DeviceInfo]  # 故障路径设备列表（包含设备信息）
    initial_hypothesis: str  # 初步假设
    supervisor_iterations: int  # 迭代次数


class DeviceInspectorState(TypedDict):
    """单台设备 Inspector 的状态"""
    device: DeviceInfo  # 要检查的设备（包含 platform 等信息）
    inspector_messages: list  # Inspector 的消息历史
    current_layer: Literal["L1", "L2", "L3", "L4"] | None  # 当前检查的层
    completed_layers: list[str]  # 已完成的层
    layer_results: dict[str, LayerResult]  # 每层的检查结果
    tool_iterations: int  # 工具调用次数（防止无限循环）


class SimilarCase(BaseModel):
    """知识库中的相似案例"""
    case_id: str = Field(description="案例 ID")
    fault_description: str = Field(description="故障描述")
    root_cause: str = Field(description="根因")
    resolution: str = Field(description="解决方案")
    similarity_score: float = Field(description="相似度 0-1")
    timestamp: str = Field(description="案例时间")


class DiagnosisReport(BaseModel):
    """诊断报告（用于索引到知识库）"""
    report_id: str = Field(description="报告唯一 ID")
    timestamp: str = Field(description="报告生成时间")
    
    # 故障信息
    fault_description: str = Field(description="原始故障描述")
    source: str = Field(description="源设备/主机")
    destination: str = Field(description="目标设备/主机")
    fault_path: list[str] = Field(description="故障路径")
    
    # 诊断结果
    root_cause: str = Field(description="根因")
    root_cause_device: str = Field(description="根因所在设备")
    root_cause_layer: str = Field(description="根因所在层级 L1/L2/L3/L4")
    confidence: float = Field(description="置信度")
    
    # 证据链
    evidence_chain: list[str] = Field(description="证据链")
    device_summaries: dict[str, str] = Field(description="每台设备的检查摘要")
    
    # 解决方案
    recommended_action: str = Field(description="建议修复操作")
    resolution_applied: bool = Field(default=False, description="是否已应用修复")
    resolution_result: str | None = Field(default=None, description="修复结果")
    
    # 元数据（用于相似案例检索）
    tags: list[str] = Field(description="标签: [bgp, interface, acl, ...]")
    affected_protocols: list[str] = Field(description="涉及协议: [ospf, bgp, ...]")
    affected_layers: list[str] = Field(description="涉及层级: [L1, L2, ...]")
    
    # Markdown 格式报告
    markdown_content: str = Field(description="完整 Markdown 报告")


class DiagnosisState(TypedDict):
    """主状态"""
    messages: list
    
    # Supervisor 分析结果
    fault_path: list[DeviceInfo]
    initial_hypothesis: str
    similar_cases: list[SimilarCase]  # 知识库中的相似案例（Agentic RAG）
    
    # Inspector 执行结果 (自动合并)
    inspection_results: Annotated[list[InspectionResult], operator.add]
    
    # 最终结论
    root_cause: str
    root_cause_device: str
    confidence: float
    evidence_chain: list[str]
    recommended_action: str
    
    # 诊断报告（用于索引）
    diagnosis_report: DiagnosisReport
    report_indexed: bool  # 是否已索引到知识库
```

## Prompt 设计

### Supervisor Prompt（简短）

```yaml
# config/prompts/deep_dive/supervisor.yaml
_type: prompt
input_variables: []
template: |
  你是网络故障分析师。你的任务是分析故障范围，不是诊断具体问题。

  ## 你的职责（按顺序执行）
  1. 理解用户描述的故障现象
  2. 使用 kb_search 查询知识库中的相似案例
  3. 使用 suzieq_query(table="lldp") 查询网络拓扑
  4. 确定故障路径上的所有设备
  5. 使用 log_search 查找相关日志
  6. 结合相似案例，形成初步假设

  ## 输出格式
  调用 DispatchInspectors 工具，传入:
  - fault_path: ["SW1", "R1", "R2"]  # 需要检查的设备
  - hypothesis: "可能是 L2 或 L3 问题"  # 初步假设
  - similar_cases: [...]  # 相关历史案例（如有）

  ## 知识库查询示例
  kb_search(query="BGP 邻居 down", index="diagnosis-reports", size=3)
  -> 返回相似案例，参考其 root_cause 和 resolution

  ## 注意
  - 先查知识库，利用历史经验
  - 不要诊断具体问题，那是 Inspector 的工作
  - 确保路径上的所有设备都被包含
```

### Inspector Prompt（简短 + 动态命令选择）

```yaml
# config/prompts/deep_dive/inspector.yaml
_type: prompt
input_variables:
  - device_name
  - platform
  - vendor
template: |
  你是网络设备检查员。检查设备 {device_name} ({vendor} {platform}) 的各层状态。

  ## 可用工具
  1. nornir_netconf: OpenConfig YANG 查询（优先使用）
  2. nornir_cli: 厂商 CLI 命令（后备）
  3. schema_search: 查询正确的命令/XPath

  ## 检查流程（L1→L4 顺序执行）

  ### 每层检查步骤
  1. 先尝试 NETCONF:
     nornir_netconf(hostname="{device_name}", xpath="/interfaces/interface/state")
  
  2. 如果 NETCONF 失败或无数据，用 CLI:
     - 先查命令: schema_search(platform="{platform}", intent="接口状态")
     - 再执行: nornir_cli(hostname="{device_name}", command="<查到的命令>")

  ### L1 物理层: 接口状态、光功率、错误计数
  ### L2 链路层: MAC 表、ARP 表、LLDP 邻居
  ### L3 网络层: 路由表、BGP/OSPF 邻居状态
  ### L4 过滤层: ACL、策略路由、QoS 标记

  ## 输出格式
  每层完成后调用 report_layer_result:
  - layer: "L1" | "L2" | "L3" | "L4"
  - status: "normal" | "anomaly" | "unknown"
  - method_used: "netconf" | "cli"
  - findings: ["Gi0/0/0 admin-down", "高错误计数"]
  - confidence: 0.0-1.0

  ## 重要
  - 使用实时数据（NETCONF/CLI），不要用 SuzieQ
  - 根据 platform 选择正确的命令语法
  - 如果工具失败，记录错误并继续下一层
```

### Conclusion Prompt（简短）

```yaml
# config/prompts/deep_dive/conclusion.yaml
_type: prompt
input_variables:
  - similar_cases
template: |
  你是网络故障诊断专家。根据所有设备的检查报告，确定根因。

  ## 输入
  - 每台设备的 L1-L4 检查结果
  - 相似历史案例: {similar_cases}

  ## 分析方法
  1. 找出所有异常（status=anomaly）
  2. 参考相似案例的 root_cause
  3. 分析因果关系：哪个异常导致了其他问题？
  4. 置信度最高的异常通常是根因
  5. 如果多个异常，判断是否是级联故障

  ## 输出格式
  调用 generate_report 工具生成 Markdown 报告
```

### Report Generator Prompt

```yaml
# config/prompts/deep_dive/report_generator.yaml
_type: prompt
input_variables:
  - fault_description
  - fault_path
  - inspection_results
  - root_cause
  - evidence_chain
  - recommended_action
template: |
  生成诊断报告 Markdown 文档。

  ## 报告模板
  
  # 网络故障诊断报告
  
  **报告 ID**: {report_id}
  **时间**: {timestamp}
  
  ## 故障描述
  {fault_description}
  
  ## 故障路径
  {fault_path}
  
  ## 诊断结果
  
  ### 根因
  - **设备**: {root_cause_device}
  - **问题**: {root_cause}
  - **层级**: {root_cause_layer}
  - **置信度**: {confidence}%
  
  ### 证据链
  {evidence_chain}
  
  ## 设备检查摘要
  {device_summaries}
  
  ## 建议修复
  {recommended_action}
  
  ## 元数据
  - **标签**: {tags}
  - **涉及协议**: {affected_protocols}
  - **涉及层级**: {affected_layers}
```

## Agentic RAG 架构

### 知识库索引结构

```python
# OpenSearch 索引: diagnosis-reports
{
    "mappings": {
        "properties": {
            "report_id": {"type": "keyword"},
            "timestamp": {"type": "date"},
            
            # 故障描述（用于语义搜索）
            "fault_description": {"type": "text", "analyzer": "ik_smart"},
            "fault_description_embedding": {"type": "knn_vector", "dimension": 1536},
            
            # 诊断结果
            "root_cause": {"type": "text"},
            "root_cause_embedding": {"type": "knn_vector", "dimension": 1536},
            "root_cause_device": {"type": "keyword"},
            "root_cause_layer": {"type": "keyword"},
            "confidence": {"type": "float"},
            
            # 解决方案
            "recommended_action": {"type": "text"},
            "resolution_applied": {"type": "boolean"},
            "resolution_result": {"type": "text"},
            
            # 元数据（用于过滤）
            "tags": {"type": "keyword"},
            "affected_protocols": {"type": "keyword"},
            "affected_layers": {"type": "keyword"},
            "fault_path": {"type": "keyword"},
            
            # 完整报告
            "markdown_content": {"type": "text"}
        }
    }
}
```

### Agentic RAG 工作流

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agentic RAG 循环                              │
│                                                                  │
│  1. Supervisor 查询知识库                                        │
│     kb_search("BGP 邻居 down 无法 ping")                         │
│           ↓                                                      │
│     返回相似案例:                                                │
│       - Case#123: BGP hold timer 过期 → 检查 keepalive          │
│       - Case#456: 接口 down → 检查物理层                         │
│           ↓                                                      │
│  2. Supervisor 形成假设                                          │
│     hypothesis = "可能是 BGP 或物理层问题"                        │
│     priority_layers = ["L1", "L3"]  # 优先检查                   │
│           ↓                                                      │
│  3. Inspectors 检查设备                                          │
│     参考相似案例的 root_cause 作为检查重点                       │
│           ↓                                                      │
│  4. Conclusion 生成报告                                          │
│     结合当前发现 + 历史案例                                      │
│           ↓                                                      │
│  5. Report Indexer 索引新报告                                    │
│     → 下次类似故障可被检索                                       │
│                                                                  │
│  这就是 Agentic RAG: Agent 主动使用知识库辅助决策                │
└─────────────────────────────────────────────────────────────────┘
```

## 实现计划

### Phase 1: 核心框架（含 Agentic RAG）

```python
# src/olav/workflows/deep_dive_v2.py

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, Send
from datetime import datetime
import uuid

# 0. Supervisor 工具集
supervisor_tools = [
    suzieq_query,      # 查拓扑
    log_search,        # 查日志
    kb_search,         # 查知识库（Agentic RAG）
    netbox_get_device, # 获取设备信息
    dispatch_inspectors,  # 分发检查任务
]

# 1. Supervisor 节点（含知识库查询）
async def supervisor(state: DiagnosisState, config) -> Command:
    """分析故障范围，查询知识库，分发 Inspector 任务"""
    
    # Step 1: 查询知识库中的相似案例（Agentic RAG）
    similar_cases = await kb_search(
        query=state["messages"][-1].content,
        index="diagnosis-reports",
        size=5
    )
    
    # Step 2: 使用 SuzieQ 查拓扑
    topology = await suzieq_query(table="lldp", method="get")
    
    # Step 3: 确定故障路径
    fault_path = analyze_fault_path(topology, state["messages"])
    
    # Step 4: 从 NetBox 获取设备信息
    device_infos = [await netbox_get_device(d) for d in fault_path]
    
    # Step 5: Send() 并行分发到每台设备
    return Command(
        goto="aggregate_inspections",
        update={
            "fault_path": device_infos,
            "similar_cases": similar_cases,
            "initial_hypothesis": form_hypothesis(similar_cases)
        },
        send=[
            Send("device_inspector", {"device": dev, "similar_cases": similar_cases})
            for dev in device_infos
        ]
    )

# 2. Inspector 子图（见 Phase 2）

# 3. Conclusion 节点
async def conclusion(state: DiagnosisState, config):
    """汇总结果，确定根因，参考历史案例"""
    # 分析所有 inspection_results
    # 参考 similar_cases 的 root_cause
    # 确定当前案例的 root_cause
    pass

# 4. Report Generator 节点
async def generate_report(state: DiagnosisState, config):
    """生成 Markdown 诊断报告"""
    report = DiagnosisReport(
        report_id=str(uuid.uuid4()),
        timestamp=datetime.now().isoformat(),
        fault_description=state["fault_description"],
        source=state["source"],
        destination=state["destination"],
        fault_path=[d.name for d in state["fault_path"]],
        root_cause=state["root_cause"],
        root_cause_device=state["root_cause_device"],
        root_cause_layer=determine_layer(state["root_cause"]),
        confidence=state["confidence"],
        evidence_chain=state["evidence_chain"],
        device_summaries=summarize_devices(state["inspection_results"]),
        recommended_action=state["recommended_action"],
        tags=extract_tags(state),
        affected_protocols=extract_protocols(state),
        affected_layers=extract_layers(state),
        markdown_content=render_markdown(state)
    )
    return {"diagnosis_report": report}

# 5. Report Indexer 节点（Agentic RAG 的写入端）
async def index_report(state: DiagnosisState, config):
    """将诊断报告索引到知识库"""
    report = state["diagnosis_report"]
    
    # 生成 embeddings
    fault_embedding = await embedding_model.embed(report.fault_description)
    root_cause_embedding = await embedding_model.embed(report.root_cause)
    
    # 索引到 OpenSearch
    await opensearch_client.index(
        index="diagnosis-reports",
        id=report.report_id,
        body={
            **report.model_dump(),
            "fault_description_embedding": fault_embedding,
            "root_cause_embedding": root_cause_embedding
        }
    )
    
    return {"report_indexed": True}

# 构建图
builder = StateGraph(DiagnosisState)
builder.add_node("supervisor", supervisor)
builder.add_node("device_inspector", device_inspector)
builder.add_node("aggregate_inspections", lambda s: s)  # 收集点
builder.add_node("conclusion", conclusion)
builder.add_node("generate_report", generate_report)
builder.add_node("index_report", index_report)

builder.add_edge(START, "supervisor")
# device_inspector 由 Send() 并行分发
builder.add_edge("device_inspector", "aggregate_inspections")
builder.add_edge("aggregate_inspections", "conclusion")
builder.add_edge("conclusion", "generate_report")
builder.add_edge("generate_report", "index_report")
builder.add_edge("index_report", END)
```

### Phase 2: Inspector 子图（ReAct 模式）

```python
# Inspector 是独立的子图，使用 ReAct 循环
# 不是固定命令，而是让 Agent 根据设备类型动态选择

inspector_builder = StateGraph(DeviceInspectorState)

# Inspector 工具集
inspector_tools = [
    # OpenConfig NETCONF（优先）
    nornir_netconf,     # nornir_netconf(hostname, xpath) -> XML/JSON
    
    # CLI（后备）
    nornir_cli,         # nornir_cli(hostname, command) -> str
    
    # Schema 查询（帮助 Agent 选择正确的命令）
    schema_search,      # schema_search(platform, intent) -> 推荐的命令
    
    # 层级报告
    report_layer_result # report_layer_result(layer, status, findings, confidence)
]

async def inspector_react(state: DeviceInspectorState, config):
    """Inspector 的 ReAct 循环"""
    device = state["device"]  # DeviceInfo with platform, vendor
    
    # 构建 Agent（短 Prompt + 工具）
    prompt = prompt_manager.load(
        "deep_dive/inspector",
        device_name=device.name,
        platform=device.platform,
        vendor=device.vendor
    )
    
    agent = create_react_agent(
        llm=llm_factory.get_chat_model(),
        tools=inspector_tools,
        state_schema=DeviceInspectorState,
        prompt=prompt
    )
    
    # 运行直到完成所有层
    result = await agent.ainvoke({
        "device": device,
        "inspector_messages": [],
        "current_layer": "L1",
        "completed_layers": [],
        "layer_results": {},
        "tool_iterations": 0
    })
    
    # 返回检查结果
    return {
        "inspection_results": [InspectionResult(
            device=device,
            layer_results=result["layer_results"],
            overall_status=calculate_status(result["layer_results"]),
            anomalies=extract_anomalies(result["layer_results"]),
            root_cause_candidate=identify_candidate(result["layer_results"]),
            confidence=calculate_confidence(result["layer_results"])
        )]
    }


def calculate_status(layer_results: dict[str, LayerResult]) -> str:
    """根据各层结果计算整体状态"""
    anomaly_count = sum(1 for r in layer_results.values() if r.status == "anomaly")
    if anomaly_count == 0:
        return "healthy"
    elif anomaly_count <= 1:
        return "degraded"
    else:
        return "faulty"


def extract_anomalies(layer_results: dict[str, LayerResult]) -> list[str]:
    """提取所有异常"""
    anomalies = []
    for layer, result in layer_results.items():
        if result.status == "anomaly":
            anomalies.extend(result.findings)
    return anomalies
```

### schema_search 工具实现

```python
# src/olav/tools/schema_search.py
from langchain_core.tools import tool
from olav.core.opensearch import get_opensearch_client


@tool
def schema_search(platform: str, intent: str) -> dict:
    """
    根据设备平台和检查意图，查询正确的命令/XPath。
    
    Args:
        platform: 设备平台 (cisco_ios, cisco_iosxr, juniper_junos, arista_eos)
        intent: 检查意图 (接口状态, MAC表, 路由表, BGP邻居, etc.)
    
    Returns:
        {
            "netconf_xpath": "/interfaces/interface/state",  # OpenConfig path
            "cli_command": "show interfaces brief",           # 平台特定命令
            "expected_fields": ["name", "admin-status", "oper-status"]
        }
    """
    client = get_opensearch_client()
    
    # 1. 首先查 OpenConfig schema（厂商无关）
    openconfig_result = client.search(
        index="openconfig-schema",
        body={
            "query": {
                "multi_match": {
                    "query": intent,
                    "fields": ["description", "path", "module_name"]
                }
            },
            "size": 3
        }
    )
    
    # 2. 查询平台特定的 CLI 命令
    cli_result = client.search(
        index="cli-command-mapping",
        body={
            "query": {
                "bool": {
                    "must": [
                        {"term": {"platform": platform}},
                        {"match": {"intent": intent}}
                    ]
                }
            },
            "size": 1
        }
    )
    
    return {
        "netconf_xpath": openconfig_result["hits"]["hits"][0]["_source"]["path"] 
            if openconfig_result["hits"]["hits"] else None,
        "cli_command": cli_result["hits"]["hits"][0]["_source"]["command"]
            if cli_result["hits"]["hits"] else None,
        "expected_fields": openconfig_result["hits"]["hits"][0]["_source"].get("fields", [])
            if openconfig_result["hits"]["hits"] else []
    }
```

### kb_search 工具实现（Agentic RAG 核心）

```python
# src/olav/tools/kb_search.py
from langchain_core.tools import tool
from olav.core.opensearch import get_opensearch_client
from olav.core.llm import LLMFactory


@tool
def kb_search(query: str, index: str = "diagnosis-reports", size: int = 5) -> list[dict]:
    """
    查询知识库中的相似案例（Agentic RAG）。
    
    Args:
        query: 故障描述或关键词
        index: 索引名称，默认 diagnosis-reports
        size: 返回结果数量
    
    Returns:
        相似案例列表，每个包含:
        - case_id: 案例 ID
        - fault_description: 故障描述
        - root_cause: 根因
        - resolution: 解决方案
        - similarity_score: 相似度
    
    Example:
        kb_search("BGP 邻居 down 无法 ping 通")
        -> [
            {
                "case_id": "case-123",
                "fault_description": "BGP 邻居状态 Idle",
                "root_cause": "hold timer 过期",
                "resolution": "检查 keepalive 配置",
                "similarity_score": 0.92
            },
            ...
        ]
    """
    client = get_opensearch_client()
    embedding_model = LLMFactory.get_embedding_model()
    
    # 生成查询 embedding
    query_embedding = embedding_model.embed_query(query)
    
    # 混合搜索：语义 + 关键词
    result = client.search(
        index=index,
        body={
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        # 语义搜索（KNN）
                        {
                            "knn": {
                                "fault_description_embedding": {
                                    "vector": query_embedding,
                                    "k": size
                                }
                            }
                        },
                        # 关键词搜索
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "fault_description^2",
                                    "root_cause",
                                    "tags",
                                    "affected_protocols"
                                ]
                            }
                        }
                    ]
                }
            },
            "_source": [
                "report_id", "fault_description", "root_cause",
                "recommended_action", "confidence", "timestamp",
                "tags", "affected_protocols"
            ]
        }
    )
    
    cases = []
    for hit in result["hits"]["hits"]:
        source = hit["_source"]
        cases.append({
            "case_id": source["report_id"],
            "fault_description": source["fault_description"],
            "root_cause": source["root_cause"],
            "resolution": source["recommended_action"],
            "similarity_score": hit["_score"],
            "timestamp": source.get("timestamp"),
            "tags": source.get("tags", [])
        })
    
    return cases
```

### Phase 3: 集成到现有系统

1. 在 `WorkflowType` 中添加 `DEEP_DIVE_V2`
2. 在 `root_agent_orchestrator.py` 中注册新 workflow
3. CLI expert mode 路由到新 workflow

### Phase 4: ETL 脚本

```python
# src/olav/etl/init_diagnosis_kb.py
"""初始化诊断知识库索引"""

from opensearchpy import OpenSearch

def create_diagnosis_reports_index(client: OpenSearch):
    """创建 diagnosis-reports 索引"""
    
    index_body = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100
            },
            "analysis": {
                "analyzer": {
                    "ik_smart": {
                        "type": "custom",
                        "tokenizer": "ik_smart"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "report_id": {"type": "keyword"},
                "timestamp": {"type": "date"},
                
                # 故障描述（语义搜索）
                "fault_description": {
                    "type": "text",
                    "analyzer": "ik_smart"
                },
                "fault_description_embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib"
                    }
                },
                
                # 根因（语义搜索）
                "root_cause": {"type": "text"},
                "root_cause_embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib"
                    }
                },
                "root_cause_device": {"type": "keyword"},
                "root_cause_layer": {"type": "keyword"},
                "confidence": {"type": "float"},
                
                # 解决方案
                "recommended_action": {"type": "text"},
                "resolution_applied": {"type": "boolean"},
                "resolution_result": {"type": "text"},
                
                # 元数据（过滤）
                "tags": {"type": "keyword"},
                "affected_protocols": {"type": "keyword"},
                "affected_layers": {"type": "keyword"},
                "fault_path": {"type": "keyword"},
                
                # 设备摘要
                "device_summaries": {"type": "object", "enabled": False},
                
                # 完整报告
                "markdown_content": {"type": "text", "index": False}
            }
        }
    }
    
    if not client.indices.exists("diagnosis-reports"):
        client.indices.create("diagnosis-reports", body=index_body)
        print("Created index: diagnosis-reports")
    else:
        print("Index diagnosis-reports already exists")


if __name__ == "__main__":
    from olav.core.opensearch import get_opensearch_client
    client = get_opensearch_client()
    create_diagnosis_reports_index(client)
```

## 与历史架构的对比

### 三方案对比总表

| 维度 | Legacy DeepPath V1 | LangChain deepagents | **新 Supervisor-Inspector (V2)** |
|------|---------------------|----------------------|----------------------------------|
| **架构模式** | 单 Agent 假设循环 | 通用 Agent 框架 + 子代理 | 专用 Supervisor-Inspector 模式 |
| **LLM 调用** | 5次/轮 (观察→假设→验证→更新→结论) | 可变（取决于任务复杂度） | 3次固定 (Supervisor + Conclusion + Report) + N 次 Inspector |
| **Prompt 长度** | 50-80 行/步骤 | 自动注入 (Middleware) | **< 30 行/组件** |
| **并行能力** | ❌ 串行迭代 | ✅ 子代理可并行 | ✅ Send() 并行 Inspector |
| **设备遍历** | ⚠️ 依赖 LLM 决定 | ⚠️ 依赖 LLM 决定 | ✅ **架构强制遍历** |
| **分层检查** | ⚠️ Prompt 指导 | ❌ 无分层概念 | ✅ **L1→L4 强制执行** |
| **知识积累** | ❌ 无 | ⚠️ 可选 Memory Backend | ✅ **Agentic RAG 自动索引** |
| **网络专用** | ✅ 针对网络设计 | ❌ 通用框架 | ✅ **网络诊断专用** |
| **HITL 支持** | ❌ | ✅ interrupt_on | ✅ LangGraph interrupt |
| **代码复杂度** | 低 (~500行) | 高 (框架 + Middleware) | 中 (~800行) |

### Legacy DeepPath V1 (archive/strategies/deep_path_v1.py)

```
┌──────────────────────────────────────────────────────────┐
│                    DeepPath V1 架构                       │
│                                                          │
│  User Query: "为什么 R1 无法建立 BGP 邻居？"              │
│         ↓                                                │
│  ┌──────────────────────────────────────────┐            │
│  │ Iteration 1:                              │            │
│  │   1. Initial Observation (LLM决定查什么)  │ ← 50行Prompt│
│  │   2. Execute Tools (SuzieQ/CLI)           │            │
│  │   3. Hypothesis Generation (LLM生成假设)  │ ← 40行Prompt│
│  │   4. Verification Plan (LLM决定如何验证)  │ ← 30行Prompt│
│  │   5. Execute Verification                 │            │
│  │   6. Confidence Update (LLM评估)          │ ← 30行Prompt│
│  └──────────────────────────────────────────┘            │
│         ↓ confidence < 0.8?                              │
│  ┌──────────────────────────────────────────┐            │
│  │ Iteration 2-5: 重复上述步骤               │            │
│  └──────────────────────────────────────────┘            │
│         ↓                                                │
│  ┌──────────────────────────────────────────┐            │
│  │ Conclusion Synthesis (LLM总结)            │ ← 40行Prompt│
│  └──────────────────────────────────────────┘            │
│                                                          │
│  问题:                                                   │
│  1. 每次迭代 5 次 LLM 调用，成本高                        │
│  2. LLM 可能"偷懒"，只查一台设备                         │
│  3. 没有强制遍历故障路径上的所有设备                      │
│  4. 没有分层检查 (L1→L4)                                 │
│  5. 假设-验证循环可能陷入死循环                           │
│  6. Prompt 累计 200+ 行，LLM 容易忽略关键指令             │
└──────────────────────────────────────────────────────────┘
```

**V1 的关键代码结构** (archive/strategies/deep_path_v1.py):
```python
class DeepPathStrategy:
    async def execute(self, user_query: str, context: dict) -> dict:
        state = ReasoningState(original_query=user_query)
        
        # Step 1: 初始观察 (LLM 决定查什么)
        await self._collect_initial_observations(state, context)
        
        while state.iteration < self.max_iterations:
            state.iteration += 1
            
            # Step 2: 生成假设 (LLM 分析数据)
            await self._generate_hypotheses(state)
            
            # Step 3: 验证假设 (LLM 决定验证方法)
            state.current_hypothesis = state.hypotheses[0]
            await self._verify_hypothesis(state)
            
            # Step 4: 更新置信度 (LLM 评估结果)
            await self._update_hypothesis_confidence(state)
            
            if state.current_hypothesis.confidence >= 0.8:
                break
        
        # Step 5: 总结结论 (LLM 综合分析)
        await self._synthesize_conclusion(state)
```

**V1 的问题**:
1. **LLM 决定一切**: 查什么设备、用什么工具、验证什么假设——全靠 LLM 遵循 Prompt
2. **没有强制遍历**: 如果 LLM "偷懒"只查一台设备，架构无法阻止
3. **假设循环低效**: 一个假设验证失败后，可能重复类似的假设
4. **Prompt 过长**: 每个步骤 30-50 行 Prompt，累计 200+ 行，LLM 容易忽略

### LangChain deepagents (archive/deepagents/)

```
┌──────────────────────────────────────────────────────────┐
│                    deepagents 架构                        │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                    Main Agent                       │  │
│  │  Middleware: Todo + Filesystem + SubAgent + HITL    │  │
│  │                                                     │  │
│  │  Built-in Tools:                                    │  │
│  │    - write_todos / read_todos (任务管理)            │  │
│  │    - ls / read_file / write_file (文件操作)         │  │
│  │    - execute (Shell 命令)                           │  │
│  │    - task (委派子代理)                              │  │
│  └────────────────────────────────────────────────────┘  │
│         ↓ task() 委派                                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Sub-Agent Pool                         │  │
│  │  - research-agent (调研)                            │  │
│  │  - data-analyzer (数据分析)                         │  │
│  │  - custom sub-agents...                             │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  优点:                                                   │
│  1. 通用框架，可用于任何领域                             │
│  2. Middleware 自动注入工具说明，减少 Prompt            │
│  3. SubAgent 隔离上下文，避免 Token 爆炸                 │
│  4. Backend 支持持久化 (FileSystem/Store)               │
│                                                          │
│  对网络诊断的局限:                                       │
│  1. 没有网络专用工具 (SuzieQ/NETCONF/CLI)               │
│  2. 没有分层检查概念 (L1→L4)                            │
│  3. 没有拓扑感知 (故障路径遍历)                          │
│  4. 没有知识库 (历史案例检索)                            │
│  5. 通用设计导致网络场景下效率低                         │
└──────────────────────────────────────────────────────────┘
```

**deepagents 的适用场景**:
- 通用编程任务 (代码生成、调试)
- 研究任务 (文档检索、总结)
- 文件操作任务 (批量处理)

**不适合网络诊断的原因**:
- 没有 SuzieQ/NETCONF/CLI 集成
- 没有 OSI 分层检查逻辑
- 没有网络拓扑感知
- 没有网络知识库

### 新 Supervisor-Inspector (V2) 优势

```
┌──────────────────────────────────────────────────────────┐
│                    V2 架构优势                            │
│                                                          │
│  vs DeepPath V1:                                         │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 1. 架构强制 vs LLM 依赖                             │  │
│  │    V1: LLM 决定查哪些设备 → 可能遗漏               │  │
│  │    V2: 代码强制遍历 fault_path 上的所有设备        │  │
│  │                                                     │  │
│  │ 2. 分层检查 vs 随机检查                            │  │
│  │    V1: LLM 可能跳过某些层                          │  │
│  │    V2: Inspector 必须完成 L1→L4 才返回             │  │
│  │                                                     │  │
│  │ 3. 并行执行 vs 串行迭代                            │  │
│  │    V1: 一次只能验证一个假设                        │  │
│  │    V2: Send() 并行检查多台设备                     │  │
│  │                                                     │  │
│  │ 4. 短 Prompt vs 长 Prompt                          │  │
│  │    V1: 每步 30-50 行，累计 200+ 行                 │  │
│  │    V2: 每组件 < 30 行，职责单一                    │  │
│  │                                                     │  │
│  │ 5. 知识积累 vs 无状态                              │  │
│  │    V1: 每次诊断独立，不学习                        │  │
│  │    V2: Agentic RAG 自动索引历史案例                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  vs deepagents:                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 1. 网络专用 vs 通用框架                            │  │
│  │    deepagents: 需要大量定制才能用于网络             │  │
│  │    V2: 原生支持 SuzieQ/NETCONF/CLI                 │  │
│  │                                                     │  │
│  │ 2. 分层检查 vs 无结构                              │  │
│  │    deepagents: 没有 OSI 分层概念                   │  │
│  │    V2: L1→L4 强制检查流程                          │  │
│  │                                                     │  │
│  │ 3. 拓扑感知 vs 文件感知                            │  │
│  │    deepagents: 擅长文件操作                        │  │
│  │    V2: 擅长网络拓扑遍历                            │  │
│  │                                                     │  │
│  │ 4. 网络知识库 vs 通用 Memory                       │  │
│  │    deepagents: StoreBackend 存任意数据             │  │
│  │    V2: diagnosis-reports 索引 + 语义搜索           │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 迭代总结

| 版本 | 时间 | 特点 | 问题 |
|------|------|------|------|
| **DeepPath V1** | 2024-Q3 | 假设-验证循环 | LLM 偷懒、Prompt 过长、无并行 |
| **deepagents 评估** | 2024-Q4 | 参考 LangChain 通用框架 | 非网络专用、无分层、无拓扑感知 |
| **Supervisor-Inspector V2** | 2025-Q1 | 专用架构 + Agentic RAG | 当前方案 |

### 为什么不直接用 deepagents?

1. **网络专用需求**: 需要 SuzieQ/NETCONF/CLI 集成，deepagents 只有通用文件/Shell 工具
2. **分层检查逻辑**: OSI L1→L4 检查是网络诊断核心，deepagents 没有这个概念
3. **拓扑感知**: 网络诊断需要沿故障路径遍历设备，deepagents 是文件导向的
4. **知识库结构**: 网络诊断报告有特定结构 (设备、协议、层级)，通用 Memory 不够

**但可以借鉴的设计**:
- ✅ Middleware 模式（工具说明自动注入）
- ✅ SubAgent 隔离（Inspector 类似 SubAgent）
- ✅ Backend 抽象（State/Filesystem/Store）
- ✅ HITL 配置（interrupt_on）

## 迁移路径

1. **Phase 1**: 实现 Supervisor-Inspector 框架，与现有 deep_path 并存
2. **Phase 2**: 通过 E2E 测试验证新架构效果
3. **Phase 3**: 如果效果好，逐步替换 deep_path
4. **Phase 4**: 删除旧 deep_path 代码

---

## 附录：Standard 模式的 Middleware 优化

### 当前问题

Standard 模式 (`QueryDiagnosticWorkflow`) 的 Prompt 也存在冗长问题：

1. **`macro_analysis.yaml`**: 60+ 行，包含工具说明
2. **`micro_diagnosis.yaml`**: 类似长度
3. **`react_diagnosis.yaml`**: 100+ 行（DeepPath V1 使用）
4. **每个 `*_capability_guide.yaml`**: 50-80 行

**问题**：工具说明重复出现在多个 Prompt 中，维护困难。

### 解决方案：ToolMiddleware 自动注入

借鉴 deepagents 的 Middleware 模式，实现工具说明自动注入：

```python
# src/olav/middleware/tool_middleware.py
"""Tool Middleware - 自动注入工具说明到 Prompt"""

from typing import TYPE_CHECKING
from langchain_core.tools import BaseTool
from olav.core.prompt_manager import prompt_manager

if TYPE_CHECKING:
    from langchain_core.messages import SystemMessage


class ToolMiddleware:
    """
    自动注入工具说明到 System Prompt。
    
    Usage:
        middleware = ToolMiddleware()
        enriched_prompt = middleware.enrich_prompt(
            base_prompt="你是网络诊断专家...",
            tools=[suzieq_query, netconf_tool, cli_tool]
        )
    """
    
    # 工具名到 capability_guide 的映射
    TOOL_GUIDE_MAPPING = {
        "suzieq_query": "suzieq",
        "suzieq_schema_search": "suzieq",
        "netconf_tool": "netconf",
        "cli_tool": "cli",
        "netbox_api_call": "netbox",
        "netbox_schema_search": "netbox",
    }
    
    def __init__(self):
        self._guide_cache: dict[str, str] = {}
    
    def get_tool_guide(self, tool_name: str) -> str:
        """获取工具的 capability guide"""
        if tool_name in self._guide_cache:
            return self._guide_cache[tool_name]
        
        guide_prefix = self.TOOL_GUIDE_MAPPING.get(tool_name)
        if not guide_prefix:
            return ""
        
        guide = prompt_manager.load_tool_capability_guide(guide_prefix)
        self._guide_cache[tool_name] = guide
        return guide
    
    def enrich_prompt(
        self,
        base_prompt: str,
        tools: list[BaseTool],
        include_guides: bool = True
    ) -> str:
        """
        自动注入工具说明到 Prompt。
        
        Args:
            base_prompt: 基础 System Prompt（简短，职责聚焦）
            tools: 当前节点可用的工具列表
            include_guides: 是否包含详细 capability guide
        
        Returns:
            增强后的 Prompt
        """
        # 1. 生成工具概览表
        tool_table = self._generate_tool_table(tools)
        
        # 2. 收集相关的 capability guides
        guides = []
        if include_guides:
            seen_guides = set()
            for tool in tools:
                guide_prefix = self.TOOL_GUIDE_MAPPING.get(tool.name)
                if guide_prefix and guide_prefix not in seen_guides:
                    guide = self.get_tool_guide(tool.name)
                    if guide:
                        guides.append(f"### {guide_prefix.upper()} 工具详情\n{guide}")
                        seen_guides.add(guide_prefix)
        
        # 3. 组装最终 Prompt
        enriched = f"""{base_prompt}

## 可用工具

{tool_table}
"""
        
        if guides:
            enriched += f"""
## 工具使用指南

{chr(10).join(guides)}
"""
        
        return enriched
    
    def _generate_tool_table(self, tools: list[BaseTool]) -> str:
        """生成工具概览表"""
        lines = ["| 工具 | 用途 |", "|------|------|"]
        for tool in tools:
            # 提取 docstring 第一行作为用途
            desc = tool.description.split("\n")[0] if tool.description else "无描述"
            lines.append(f"| `{tool.name}` | {desc} |")
        return "\n".join(lines)


# 全局实例
tool_middleware = ToolMiddleware()
```

### 简化后的 Prompt 示例

**Before** (macro_analysis.yaml - 60+ 行):
```yaml
template: |
  You are a SuzieQ macro analysis expert...
  
  ## Available Tools
  | Tool | Purpose |
  | suzieq_query | Query network state... |
  | suzieq_schema_search | Discover tables... |
  ...（重复的工具说明）
  
  ## Chain of Thought
  ...（分析流程）
  
  ## Examples
  ...（使用示例）
```

**After** (macro_analysis_v2.yaml - 15 行):
```yaml
_type: prompt
input_variables:
  - user_query
template: |
  你是 SuzieQ 宏观分析专家。分析用户请求并使用工具获取数据。

  ## 用户请求
  {user_query}

  ## 分析流程
  1. 使用 suzieq_schema_search 发现正确的表名
  2. 使用 suzieq_query 获取数据
  3. 如果数据为空，记录 "需要微观诊断"

  ## 重要
  - 不要猜测表名，必须先查 schema
  - 如果工具返回空数据，不要编造结果
```

**工具说明由 ToolMiddleware 自动注入！**

### 集成到 QueryDiagnosticWorkflow

```python
# src/olav/workflows/query_diagnostic.py (修改后)

from olav.middleware.tool_middleware import tool_middleware

class QueryDiagnosticWorkflow(BaseWorkflow):
    
    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        
        macro_tools = [suzieq_query, suzieq_schema_search, ...]
        
        async def macro_analysis_node(state: QueryDiagnosticState):
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(macro_tools)
            
            # 加载简短的基础 Prompt
            base_prompt = prompt_manager.load_prompt(
                "workflows/query_diagnostic", 
                "macro_analysis_v2",  # 简化版
                user_query=state["messages"][0].content
            )
            
            # Middleware 自动注入工具说明
            enriched_prompt = tool_middleware.enrich_prompt(
                base_prompt=base_prompt,
                tools=macro_tools,
                include_guides=True  # 首次调用包含详细指南
            )
            
            response = await llm_with_tools.ainvoke([
                SystemMessage(content=enriched_prompt),
                *state["messages"]
            ])
            
            return {...}
```

### 优势

| 维度 | 当前方式 | Middleware 方式 |
|------|---------|-----------------|
| **Prompt 长度** | 60-100 行 | 15-20 行 |
| **工具说明维护** | 每个 Prompt 都要改 | 只改 capability_guide |
| **一致性** | 容易不一致 | 自动保持一致 |
| **可测试性** | 难以测试 | Middleware 可单独测试 |
| **复用性** | 无法复用 | 跨 Workflow 复用 |

### 实现计划

1. **Phase 1**: 创建 `src/olav/middleware/tool_middleware.py`
2. **Phase 2**: 简化 `macro_analysis.yaml` 和 `micro_diagnosis.yaml`
3. **Phase 3**: 在 `QueryDiagnosticWorkflow` 中集成 Middleware
4. **Phase 4**: 扩展到其他 Workflow (NetBox, DeviceExecution)

---

## 附录：Workflow 职责分离与 BatchExecutionWorkflow

### 问题分析

当前 Workflow 设计存在**职责重叠**问题：

| Workflow | 当前职责 | 问题 |
|----------|---------|------|
| `QueryDiagnosticWorkflow` | 查询 + 诊断 | 纯查询不需要诊断逻辑 |
| `DeviceExecutionWorkflow` | 单/多设备配置 | 多设备串行执行效率低 |
| `DeepDiveWorkflow` | 复杂排错 + 批量任务 | 职责不单一 |

用户请求 "给所有交换机添加 VLAN 100" 需要：
1. **设备发现**：从 NetBox/SuzieQ 获取设备列表
2. **任务分解**：拆分成 N 个设备子任务
3. **并行执行**：LangGraph `Send()` 并行配置
4. **统一 HITL**：一次审批覆盖所有设备
5. **聚合报告**：汇总成功/失败设备

### 解决方案：职责分离

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Workflow 职责矩阵                                   │
├─────────────────────────┬───────────────┬───────────────┬───────────────────┤
│ Workflow                │ 核心职责       │ 设备范围      │ 执行方式          │
├─────────────────────────┼───────────────┼───────────────┼───────────────────┤
│ QueryDiagnosticWorkflow │ 只读查询       │ 单/多设备     │ SuzieQ + NETCONF  │
├─────────────────────────┼───────────────┼───────────────┼───────────────────┤
│ DeviceExecutionWorkflow │ 单设备配置变更  │ 单设备        │ HITL + NETCONF    │
├─────────────────────────┼───────────────┼───────────────┼───────────────────┤
│ BatchExecutionWorkflow  │ 多设备批量变更  │ 多设备并行    │ 统一HITL + Send() │
│ (NEW)                   │               │               │                   │
├─────────────────────────┼───────────────┼───────────────┼───────────────────┤
│ DeepDiveWorkflow        │ 只专注复杂排错  │ 多设备递归    │ Supervisor-Inspector│
├─────────────────────────┼───────────────┼───────────────┼───────────────────┤
│ NetBoxManagementWorkflow│ CMDB 管理      │ N/A          │ NetBox API        │
└─────────────────────────┴───────────────┴───────────────┴───────────────────┘
```

### BatchExecutionWorkflow 设计

```
用户请求: "给所有交换机添加 VLAN 100"
           ↓
    ┌──────────────────────────────────────────────────────────────────────────┐
    │                      BatchExecutionWorkflow                               │
    ├──────────────────────────────────────────────────────────────────────────┤
    │                                                                          │
    │  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐           │
    │  │  Task Planner │────▶│  Device      │────▶│ HITL Approval │           │
    │  │               │     │  Resolver    │     │ (统一审批)     │           │
    │  └───────────────┘     └───────────────┘     └───────────────┘           │
    │         │                    │                     │ approved            │
    │         ▼                    ▼                     ▼                     │
    │  ┌─────────────────────────────────────────────────────────────────┐     │
    │  │                    Parallel Executor                             │     │
    │  │  ┌─────────────────────────────────────────────────────────────┐│     │
    │  │  │              LangGraph Send() Fan-Out                        ││     │
    │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            ││     │
    │  │  │  │Worker 1 │ │Worker 2 │ │Worker 3 │ │Worker N │            ││     │
    │  │  │  │Switch-A │ │Switch-B │ │Switch-C │ │Switch-N │            ││     │
    │  │  │  │VLAN 100 │ │VLAN 100 │ │VLAN 100 │ │VLAN 100 │            ││     │
    │  │  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘            ││     │
    │  │  │       │           │           │           │                  ││     │
    │  │  │       ▼           ▼           ▼           ▼                  ││     │
    │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            ││     │
    │  │  │  │ Result  │ │ Result  │ │ Result  │ │ Result  │            ││     │
    │  │  │  │ ✓ OK    │ │ ✓ OK    │ │ ✗ Fail  │ │ ✓ OK    │            ││     │
    │  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘            ││     │
    │  │  └─────────────────────────────────────────────────────────────┘│     │
    │  └─────────────────────────────────────────────────────────────────┘     │
    │                              │                                           │
    │                              ▼                                           │
    │                    ┌───────────────┐                                     │
    │                    │ Result        │                                     │
    │                    │ Aggregator    │                                     │
    │                    └───────────────┘                                     │
    │                              │                                           │
    │                              ▼                                           │
    │                    ┌───────────────┐                                     │
    │                    │ Final Report  │                                     │
    │                    │ 成功: 3台     │                                     │
    │                    │ 失败: 1台     │                                     │
    │                    └───────────────┘                                     │
    │                                                                          │
    └──────────────────────────────────────────────────────────────────────────┘
```

### State 设计

```python
# src/olav/workflows/batch_execution.py

from typing import Annotated
from langgraph.graph import add_messages

class DeviceTask(TypedDict):
    """单设备任务"""
    device: str
    operation: str      # "add_vlan", "change_mtu", etc.
    parameters: dict    # {"vlan_id": 100, "name": "Guest"}
    
class DeviceResult(TypedDict):
    """单设备执行结果"""
    device: str
    success: bool
    output: str | None
    error: str | None
    execution_time_ms: float

class BatchExecutionState(TypedDict):
    """BatchExecutionWorkflow 状态"""
    messages: Annotated[list, add_messages]
    
    # Task Planning
    user_intent: str                    # 原始用户请求
    operation_type: str                 # "add_vlan", "change_mtu", etc.
    operation_params: dict              # {"vlan_id": 100, "name": "Guest"}
    
    # Device Resolution
    device_filter: dict                 # NetBox filter or SuzieQ query
    resolved_devices: list[str]         # ["Switch-A", "Switch-B", ...]
    
    # HITL Approval
    change_plan: str                    # Markdown 格式变更计划
    approval_status: str | None         # "pending" | "approved" | "rejected"
    
    # Parallel Execution
    device_tasks: list[DeviceTask]      # Fan-out 任务
    device_results: list[DeviceResult]  # Fan-in 结果
    
    # Final Report
    summary: dict                       # {"total": 10, "success": 9, "failed": 1}
```

### 关键节点实现

```python
from langgraph.constants import Send
from langgraph.graph import StateGraph, END

class BatchExecutionWorkflow(BaseWorkflow):
    """批量设备配置变更 Workflow"""
    
    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        workflow = StateGraph(BatchExecutionState)
        
        # 1. Task Planner: 解析用户意图
        async def task_planner(state: BatchExecutionState):
            """解析 '给所有交换机添加 VLAN 100' -> operation + params"""
            llm = LLMFactory.get_chat_model(json_mode=True)
            
            system_prompt = """
            解析用户的批量配置请求，提取：
            1. operation_type: 操作类型 (add_vlan, change_mtu, configure_interface, etc.)
            2. operation_params: 操作参数 (vlan_id, mtu_value, interface_name, etc.)
            3. device_filter: 设备过滤条件 (role=switch, site=DC1, name_regex=SW-*)
            
            返回 JSON 格式。
            """
            
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=state["user_intent"])
            ])
            
            parsed = json.loads(response.content)
            return {
                "operation_type": parsed.get("operation_type"),
                "operation_params": parsed.get("operation_params", {}),
                "device_filter": parsed.get("device_filter", {}),
            }
        
        # 2. Device Resolver: 查询设备列表
        async def device_resolver(state: BatchExecutionState):
            """使用 NetBox/SuzieQ 解析设备列表"""
            filter_config = state.get("device_filter", {})
            
            # 优先使用 NetBox
            if "role" in filter_config or "site" in filter_config:
                result = await netbox_api_call.ainvoke({
                    "endpoint": "/dcim/devices/",
                    "method": "GET",
                    **filter_config
                })
                devices = [d["name"] for d in result.get("results", [])]
            else:
                # Fallback: SuzieQ device table
                result = await suzieq_query.ainvoke({
                    "table": "device",
                    "columns": ["hostname"],
                })
                devices = [d["hostname"] for d in result]
            
            return {"resolved_devices": devices}
        
        # 3. Change Plan Generator: 生成变更计划供 HITL 审批
        async def change_plan_generator(state: BatchExecutionState):
            """生成 Markdown 格式变更计划"""
            devices = state["resolved_devices"]
            op_type = state["operation_type"]
            op_params = state["operation_params"]
            
            plan = f"""
## 批量配置变更计划

**操作类型**: {op_type}
**操作参数**: {json.dumps(op_params, ensure_ascii=False)}
**影响设备**: {len(devices)} 台

### 设备列表
{chr(10).join(f"- {d}" for d in devices[:20])}
{f"... 还有 {len(devices) - 20} 台设备" if len(devices) > 20 else ""}

### 预期变更
每台设备将执行:
```
{generate_config_snippet(op_type, op_params)}
```

### 回滚策略
- NETCONF: 使用 commit confirmed (自动回滚)
- CLI: 保留配置备份

**请审批此变更计划 (Y/N)**
            """
            
            return {"change_plan": plan, "approval_status": "pending"}
        
        # 4. HITL Approval (统一审批)
        async def hitl_approval(state: BatchExecutionState):
            """LangGraph interrupt 统一审批"""
            from langgraph.types import interrupt
            
            if state.get("approval_status") in ("approved", "rejected"):
                return state
            
            response = interrupt({
                "action": "batch_approval_required",
                "change_plan": state["change_plan"],
                "device_count": len(state["resolved_devices"]),
            })
            
            approved = response.get("approved", False) if isinstance(response, dict) else bool(response)
            return {"approval_status": "approved" if approved else "rejected"}
        
        # 5. Fan-Out: 生成并行任务
        def fan_out_tasks(state: BatchExecutionState) -> list[Send]:
            """为每个设备生成 Send() 任务"""
            if state.get("approval_status") != "approved":
                return []  # 被拒绝，不执行
            
            return [
                Send("device_worker", {
                    "device": device,
                    "operation_type": state["operation_type"],
                    "operation_params": state["operation_params"],
                })
                for device in state["resolved_devices"]
            ]
        
        # 6. Device Worker: 单设备执行
        async def device_worker(task: dict) -> DeviceResult:
            """执行单设备配置变更（无 LLM，纯工具调用）"""
            device = task["device"]
            op_type = task["operation_type"]
            op_params = task["operation_params"]
            
            start_time = time.perf_counter()
            
            try:
                # 根据 operation_type 生成 NETCONF payload
                config_payload = generate_netconf_config(op_type, op_params)
                
                result = await netconf_tool.ainvoke({
                    "hostname": device,
                    "operation": "edit-config",
                    "config": config_payload,
                    "target": "candidate",
                    "commit_confirmed": 60,  # 60秒自动回滚
                })
                
                return DeviceResult(
                    device=device,
                    success=not result.get("error"),
                    output=result.get("output"),
                    error=result.get("error"),
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
            except Exception as e:
                return DeviceResult(
                    device=device,
                    success=False,
                    error=str(e),
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                )
        
        # 7. Result Aggregator: 汇总结果
        async def result_aggregator(state: BatchExecutionState):
            """汇总所有设备执行结果"""
            results = state.get("device_results", [])
            
            success_count = sum(1 for r in results if r["success"])
            failed_count = len(results) - success_count
            
            summary = {
                "total": len(results),
                "success": success_count,
                "failed": failed_count,
                "success_rate": f"{success_count / len(results) * 100:.1f}%" if results else "N/A",
                "failed_devices": [r["device"] for r in results if not r["success"]],
            }
            
            return {"summary": summary}
        
        # 8. Final Report: 生成最终报告
        async def final_report(state: BatchExecutionState):
            """生成 Markdown 执行报告"""
            summary = state.get("summary", {})
            results = state.get("device_results", [])
            
            report = f"""
## 批量配置变更报告

### 执行摘要
- **操作类型**: {state["operation_type"]}
- **总设备数**: {summary.get("total", 0)}
- **成功**: {summary.get("success", 0)} ✓
- **失败**: {summary.get("failed", 0)} ✗
- **成功率**: {summary.get("success_rate", "N/A")}

### 失败设备
{chr(10).join(f"- {d}" for d in summary.get("failed_devices", [])) or "无"}

### 详细结果
| 设备 | 状态 | 耗时(ms) | 错误信息 |
|------|------|----------|----------|
{chr(10).join(
    f"| {r['device']} | {'✓' if r['success'] else '✗'} | {r['execution_time_ms']:.0f} | {r.get('error', '-')} |"
    for r in results
)}
            """
            
            return {
                "messages": state["messages"] + [AIMessage(content=report)]
            }
        
        # Build Graph
        workflow.add_node("task_planner", task_planner)
        workflow.add_node("device_resolver", device_resolver)
        workflow.add_node("change_plan_generator", change_plan_generator)
        workflow.add_node("hitl_approval", hitl_approval)
        workflow.add_node("device_worker", device_worker)
        workflow.add_node("result_aggregator", result_aggregator)
        workflow.add_node("final_report", final_report)
        
        workflow.set_entry_point("task_planner")
        workflow.add_edge("task_planner", "device_resolver")
        workflow.add_edge("device_resolver", "change_plan_generator")
        workflow.add_edge("change_plan_generator", "hitl_approval")
        
        # Fan-out after approval
        workflow.add_conditional_edges(
            "hitl_approval",
            fan_out_tasks,  # Returns list[Send] for parallel execution
        )
        
        # Fan-in: all workers -> aggregator
        workflow.add_edge("device_worker", "result_aggregator")
        workflow.add_edge("result_aggregator", "final_report")
        workflow.add_edge("final_report", END)
        
        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["hitl_approval"],
        )
```

### 与 BatchPathStrategy 的区别

| 维度 | BatchPathStrategy (现有) | BatchExecutionWorkflow (新) |
|------|--------------------------|----------------------------|
| **用途** | 只读合规检查 | 写操作配置变更 |
| **HITL** | 无 (只读安全) | 必须 (写操作风险) |
| **驱动方式** | YAML 配置文件 | 自然语言请求 |
| **验证方式** | 阈值断言 (无 LLM) | 配置验证 (NETCONF get-config) |
| **并行机制** | asyncio.gather() | LangGraph Send() |
| **失败处理** | 汇总报告 | 自动回滚 (commit confirmed) |

### Intent Classifier 更新

```python
class WorkflowType(Enum):
    QUERY_DIAGNOSTIC = "query_diagnostic"
    DEVICE_EXECUTION = "device_execution"      # 单设备配置
    BATCH_EXECUTION = "batch_execution"        # 多设备批量配置 (NEW)
    NETBOX_MANAGEMENT = "netbox_management"
    DEEP_DIVE = "deep_dive"                    # 只专注复杂排错

# Intent 分类规则
BATCH_TRIGGERS = [
    r"所有.*设备",
    r"所有.*交换机",
    r"所有.*路由器",
    r"批量",
    r"全部",
    r"every\s+device",
    r"all\s+(switches|routers|devices)",
]

def classify_intent(query: str) -> WorkflowType:
    """分类用户意图到正确的 Workflow"""
    
    # 1. 批量配置变更 (最高优先级检查)
    is_batch = any(re.search(p, query, re.I) for p in BATCH_TRIGGERS)
    is_write = any(kw in query.lower() for kw in ["配置", "添加", "修改", "删除", "设置"])
    
    if is_batch and is_write:
        return WorkflowType.BATCH_EXECUTION
    
    # 2. 复杂排错 (DeepDive 只处理排错)
    is_troubleshoot = any(kw in query.lower() for kw in [
        "为什么", "排查", "故障", "不通", "down", "flapping", "排错"
    ])
    if is_troubleshoot:
        return WorkflowType.DEEP_DIVE
    
    # 3. 单设备配置变更
    if is_write and not is_batch:
        return WorkflowType.DEVICE_EXECUTION
    
    # 4. NetBox 管理
    if any(kw in query.lower() for kw in ["设备清单", "ip分配", "机架", "站点", "netbox"]):
        return WorkflowType.NETBOX_MANAGEMENT
    
    # 5. 默认: 查询诊断
    return WorkflowType.QUERY_DIAGNOSTIC
```

### 实现计划

1. **Phase 1**: 创建 `src/olav/workflows/batch_execution.py` 基础框架
2. **Phase 2**: 实现 LangGraph `Send()` 并行执行
3. **Phase 3**: 更新 Intent Classifier 支持批量场景
4. **Phase 4**: 修改 DeepDiveWorkflow 只专注排错
5. **Phase 5**: E2E 测试验证并行效率

---

## 实施 TODO 清单

### Phase 1: Standard Mode 优化 ✅

- [x] **TODO-1**: ToolMiddleware 集成到 QueryDiagnosticWorkflow
  - 使用简化版 Prompt (macro_analysis.yaml, micro_diagnosis.yaml)
  - 修改 workflow 节点使用 `tool_middleware.enrich_prompt()`
  - **完成**: 2024-12-04

- [x] **TODO-2**: 测试 ToolMiddleware
  - 运行 CLI 测试验证自动注入功能
  - 确认 Prompt 长度减少且功能不变
  - **完成**: 15/15 测试通过

- [x] **TODO-3**: 清理旧 Prompt
  - 归档 macro_analysis_legacy.yaml, micro_diagnosis_legacy.yaml
  - V2 版本已重命名为默认名称
  - **归档位置**: config/prompts/archive/workflows/query_diagnostic/

### Phase 2: BatchExecutionWorkflow ✅

- [x] **TODO-4**: 创建 batch_execution.py 完整实现
  - Task Planner → Device Resolver → Change Plan → HITL → Parallel Executor → Aggregator
  - LangGraph Send() 并行执行
  - Intent Classifier 自动识别批量操作关键词
  - **完成**: 5/5 测试通过

### Phase 3: Quick Analyzer & Checklist-Driven Inspector ⚠️ 废弃

> **注意**: 此方案已废弃，改用 Phase 3.1 的 Supervisor-Driven 架构

- [x] **TODO-5**: Quick Analyzer 工具实现 ✅ (保留，工具仍有用)
  - 位置: `src/olav/tools/suzieq_analyzer_tool.py`
  - 工具:
    - `suzieq_path_trace`: 路径追踪 (source → destination)
    - `suzieq_health_check`: 设备健康检查 (aver 断言)
    - `suzieq_topology_analyze`: 拓扑分析与异常检测

- [x] ~~**TODO-6**: Checklist 驱动的 Inspector~~ ⚠️ 废弃
  - 原因: 静态 Checklist YAML 过度工程化，不够智能
  - 废弃文件:
    - `src/olav/tools/inspector_checklist.py` → 移至 archive/
    - `config/checklists/*.yaml` → 移至 archive/
    - `config/prompts/tools/inspector.yaml` → 移至 archive/

### Phase 3.1: Supervisor-Driven 架构 🚧 (新方案)

**核心思想**: Supervisor 动态生成检查计划 + 跟踪 L1-L4 置信度，Quick Analyzer 专注 ReAct 执行

```
┌─────────────────────────────────────────────────────────────────┐
│                        告警/用户查询                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Diagnosis Supervisor                          │
│                                                                  │
│  State (结构化，代码强制填充):                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ layer_coverage:                                          │    │
│  │   L1: { checked: false, confidence: 0%, findings: [] }  │    │
│  │   L2: { checked: false, confidence: 0%, findings: [] }  │    │
│  │   L3: { checked: true,  confidence: 55%, findings: [...]}│    │
│  │   L4: { checked: false, confidence: 0%, findings: [] }  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  职责:                                                           │
│    1. 分析告警，确定故障路径                                     │
│    2. 检查 layer_coverage，找出置信度缺口                        │
│    3. 动态生成检查任务 (针对缺口层级)                            │
│    4. 派发给 Quick Analyzer                                      │
│    5. 接收结果，更新 layer_coverage                              │
│    6. 循环直到所有层置信度足够 或 问题已定位                     │
│                                                                  │
│  终止条件:                                                       │
│    - 所有层 confidence >= 50%                                   │
│    - 或 已定位根因 (某层 confidence = 95% + 明确问题)            │
│    - 或 达到最大轮次 (防止无限循环)                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │  检查任务 (动态生成)   │
                    │  "检查 L2 VLAN/MAC"   │
                    └───────────┬───────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Quick Analyzer (ReAct)                        │
│                                                                  │
│  工具:                                                           │
│    - suzieq_schema_search (必须先调用)                          │
│    - suzieq_query                                               │
│    - suzieq_path_trace                                          │
│    - suzieq_health_check                                        │
│                                                                  │
│  输入: Supervisor 的检查任务                                     │
│  输出: 该层的发现 + 置信度                                       │
│                                                                  │
│  特点:                                                           │
│    - 可以"偷懒"，只需完成当前任务                                │
│    - Supervisor 会检测遗漏并补派任务                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  LayerResult          │
                    │  layer: "L2"          │
                    │  confidence: 55%      │
                    │  findings: [...]      │
                    └───────────────────────┘
                                │
                                ▼
                        (返回 Supervisor，循环)
```

#### 核心数据结构

```python
class LayerStatus(TypedDict):
    """单层检查状态"""
    checked: bool
    confidence: float          # 0.0 - 1.0
    findings: list[str]        # 发现的问题
    last_checked: str | None   # ISO timestamp

class SupervisorState(TypedDict):
    """Supervisor 状态 - 代码强制填充所有层"""
    messages: list[BaseMessage]
    query: str
    path_devices: list[str]
    
    # 核心: L1-L4 置信度跟踪
    layer_coverage: dict[str, LayerStatus]  # {"L1": ..., "L2": ..., "L3": ..., "L4": ...}
    
    # 控制
    current_round: int
    max_rounds: int            # 默认 5
    root_cause_identified: bool
    final_report: str | None
```

#### 为什么这样设计更好？

| 对比 | 静态 Checklist (废弃) | Supervisor-Driven (新) |
|------|---------------------|----------------------|
| 检查计划 | YAML 预定义，一刀切 | Supervisor 根据告警动态生成 |
| 完整性保证 | 靠 Checklist 遍历 | 靠 State 结构 + 置信度缺口检测 |
| 灵活性 | 低，需要维护多套 YAML | 高，LLM 自适应 |
| Quick Analyzer | 必须遍历 Checklist | 只需完成当前任务 |
| 过度工程 | 是 | 否 |

#### ✅ 实施完成 (2024-01)

**已完成 TODO 列表**:

- [x] **TODO-7**: 移除静态 Checklist 代码
  - ✅ 移动 `inspector_checklist.py` → `archive/deprecated_checklist/`
  - ✅ 移动 `config/checklists/` → `archive/deprecated_checklist/`
  - ✅ 移动 `config/prompts/tools/inspector.yaml` → `archive/deprecated_checklist/`
  - ✅ 更新 `src/olav/tools/__init__.py` 移除导出

- [x] **TODO-8**: 实现 SupervisorState 数据结构
  - ✅ 位置: `src/olav/workflows/supervisor_driven.py`
  - ✅ `LayerStatus` 类 (with to_dict/from_dict/update methods)
  - ✅ `SupervisorDrivenState(dict)` LangGraph 兼容状态
  - ✅ `create_initial_state()` 初始化函数

- [x] **TODO-9**: 实现 Supervisor 节点
  - ✅ `supervisor_node`: 分析置信度缺口，生成检查任务
  - ✅ `should_continue_investigation`: 检查终止条件
  - ✅ Prompt: `config/prompts/workflows/deep_dive/supervisor_plan.yaml`

- [x] **TODO-10**: 实现 Quick Analyzer 节点
  - ✅ ReAct 模式，使用 SuzieQ 工具
  - ✅ `quick_analyzer_node`: 执行检查任务
  - ✅ Prompt: `config/prompts/workflows/deep_dive/quick_analyzer.yaml`

- [x] **TODO-11**: Workflow 集成
  - ✅ `create_supervisor_driven_workflow()` 构建 LangGraph 图
  - ✅ `SupervisorDrivenWorkflow` 类 (包装器)
  - ✅ 注册到 `WorkflowRegistry` (name: `supervisor_driven_deep_dive`)
  - ✅ 7 个 examples + 6 个 triggers

- [x] **TODO-12**: 测试
  - ✅ 单元测试: `tests/unit/test_supervisor_driven.py` (33 tests)
  - ✅ 所有测试通过

**关键文件**:
- `src/olav/workflows/supervisor_driven.py` - 核心实现
- `config/prompts/workflows/deep_dive/supervisor_plan.yaml` - Supervisor prompt
- `config/prompts/workflows/deep_dive/quick_analyzer.yaml` - Quick Analyzer prompt
- `config/prompts/workflows/deep_dive/conclusion.yaml` - 结论报告 prompt

### Phase 4: DeepDive Workflow 集成 🚧
        return 0.50
    elif data_age_seconds < 300:
        return 0.40
    else:
        return 0.25
```

#### 工具实现

```python
@tool
def suzieq_path_trace(
    source: str,
    destination: str,
    vrf: str = "default",
) -> QuickScanResult:
    """
    使用 SuzieQ path.show() 追踪网络路径。
    
    Args:
        source: 源设备或 IP
        destination: 目标设备或 IP
        vrf: VRF 名称
    
    Returns:
        QuickScanResult: 包含路径设备列表和可疑故障点
    """
    ...


@tool
def suzieq_health_check(
    hostname: str | None = None,
    checks: list[str] | None = None,
) -> dict:
    """
    使用 SuzieQ aver (assert) 进行健康检查。
    
    默认检查:
    - interfaces: 所有接口 Up
    - bgp: 所有 BGP Peer Established
    - ospf: 所有 OSPF Neighbor Full
    - mlag: MLAG 一致性
    
    Returns:
        {"device": str, "checks": [{"name": str, "passed": bool, "failures": [...]}]}
    """
    ...


@tool  
def suzieq_topology_analyze(
    devices: list[str] | None = None,
) -> dict:
    """
    使用 SuzieQ topology.summarize() 分析网络拓扑。
    
    检测:
    - 拓扑变化
    - 单点故障
    - 潜在环路
    
    Returns:
        {"topology": [...], "anomalies": [...]}
    """
    ...
```

### TODO-6: Checklist-Driven Inspector

#### 基础 Checklist 配置

```yaml
# config/checklists/base_checklist.yaml

L1:
  - id: interface_state
    name: "接口物理状态"
    description: "检查接口 Up/Down/Admin-Down 状态"
    schema_hints: ["interface state", "interface status"]
    
  - id: interface_errors
    name: "接口错误计数"
    description: "检查 CRC, Input/Output Errors"
    schema_hints: ["interface counters", "interface errors"]
    
  - id: optical_status
    name: "光模块状态"
    description: "检查 SFP/QSFP 光功率 (如适用)"
    schema_hints: ["transceiver", "optical power"]
    optional: true

L2:
  - id: vlan_config
    name: "VLAN 配置"
    description: "检查 VLAN 是否存在且 active"
    schema_hints: ["vlan", "vlan state"]
    
  - id: mac_table
    name: "MAC 地址表"
    description: "检查 MAC 是否学习正确"
    schema_hints: ["mac address table", "mac-address"]
    
  - id: lldp_neighbors
    name: "LLDP/CDP 邻居"
    description: "验证物理连接"
    schema_hints: ["lldp neighbor", "cdp neighbor"]
    
  - id: stp_state
    name: "STP 状态"
    description: "检查 STP Root Bridge、端口状态、Blocked Ports"
    schema_hints: ["spanning-tree", "stp state"]
    suzieq_blind_spot: true  # SuzieQ 盲区，必须实时检查
    
  - id: trunk_vlans
    name: "Trunk 允许 VLAN"
    description: "验证 Trunk 配置正确"
    schema_hints: ["trunk allowed vlan", "switchport trunk"]

L3:
  - id: routing_table
    name: "路由表"
    description: "检查目标网段路由是否存在"
    schema_hints: ["routing table", "ip route", "show route"]
    
  - id: bgp_neighbors
    name: "BGP 邻居状态"
    description: "检查 BGP Peer 是否 Established"
    schema_hints: ["bgp neighbor", "bgp summary"]
    
  - id: ospf_neighbors
    name: "OSPF 邻居状态"
    description: "检查 OSPF Neighbor 是否 Full"
    schema_hints: ["ospf neighbor", "ospf adjacency"]
    
  - id: arp_table
    name: "ARP/ND 表"
    description: "验证 ARP 解析正常"
    schema_hints: ["arp table", "neighbor table"]
    
  - id: acl_check
    name: "ACL 阻断检查"
    description: "检查 ACL 是否阻断目标流量"
    schema_hints: ["access-list", "acl", "ip access-list"]
    suzieq_blind_spot: true

L4:
  - id: nat_state
    name: "NAT 转换状态"
    description: "检查 NAT 表和转换状态 (如适用)"
    schema_hints: ["nat translation", "show nat"]
    optional: true
    
  - id: qos_drops
    name: "QoS 队列丢包"
    description: "检查 QoS 队列是否有丢包 (如适用)"
    schema_hints: ["qos policy", "queue drops"]
    optional: true
```

#### Checklist 加载器

```python
# src/olav/agents/checklist.py

from pathlib import Path
import yaml
from typing import TypedDict


class ChecklistItem(TypedDict):
    id: str
    name: str
    description: str
    schema_hints: list[str]
    optional: bool
    suzieq_blind_spot: bool


class Checklist:
    """动态 Checklist 管理器"""
    
    def __init__(self, config_path: Path = None):
        self.config_path = config_path or Path("config/checklists/base_checklist.yaml")
        self._base_checklist = self._load_base_checklist()
    
    def _load_base_checklist(self) -> dict[str, list[ChecklistItem]]:
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def generate_for_device(
        self,
        device: str,
        layer: str,
        quick_scan: QuickScanResult | None = None,
        similar_cases: list[dict] | None = None,
    ) -> list[ChecklistItem]:
        """
        动态生成设备 + 层级的检查清单。
        
        优先级:
        1. QuickScan 发现的可疑点 (标记 ⚠️ 重点)
        2. 历史案例提示的检查点
        3. 基础 Checklist
        """
        items = self._base_checklist.get(layer, []).copy()
        
        # 1. 把 QuickScan 发现的可疑点插入最前面
        if quick_scan:
            for issue in quick_scan.get("suspected_issues", []):
                if issue["device"] == device and issue["layer"] == layer:
                    items.insert(0, ChecklistItem(
                        id=f"quickscan_{issue['issue'][:20]}",
                        name=f"⚠️ 重点: {issue['issue']}",
                        description=f"QuickScan 发现，置信度 {issue['confidence']:.0%}",
                        schema_hints=[],
                        optional=False,
                        suzieq_blind_spot=False,
                    ))
        
        # 2. 从相似案例补充检查点
        if similar_cases:
            for case in similar_cases:
                if case.get("similarity_score", 0) >= 0.7:
                    root_cause = case.get("root_cause", "")
                    if "ACL" in root_cause and not any("acl" in i["id"] for i in items):
                        items.append(ChecklistItem(
                            id="case_acl",
                            name="⚠️ 历史案例提示: ACL 检查",
                            description=f"相似案例根因涉及 ACL",
                            schema_hints=["access-list", "acl"],
                            optional=False,
                            suzieq_blind_spot=True,
                        ))
        
        return items
```

#### Inspector Agent 实现

```python
# src/olav/agents/inspector_agent.py

from langgraph.graph import StateGraph
from langchain_core.messages import SystemMessage

class DeviceInspectorState(TypedDict):
    """Inspector Agent State"""
    device: DeviceInfo
    layer: str
    checklist: list[ChecklistItem]
    checklist_status: dict[str, str]  # {item_id: "✓ 正常" | "✗ 异常" | "? 无法检查"}
    findings: list[str]
    messages: list


async def inspector_agent(state: DeviceInspectorState) -> DeviceInspectorState:
    """
    执行单台设备的层级检查。
    
    强制规则:
    1. 必须先调用 schema_search 获取正确命令
    2. 优先 NETCONF (OpenConfig)，CLI 备选
    3. 每个 Checklist 项都必须检查
    """
    llm = LLMFactory.get_chat_model()
    
    # 生成 Checklist 文本
    checklist_text = "\n".join(
        f"- [{item['id']}] {item['name']}: {item['description']}"
        for item in state["checklist"]
    )
    
    prompt = f"""你是网络设备检查专家。对设备 {state['device']['name']} ({state['device']['platform']}) 进行 {state['layer']} 层检查。

## 检查清单（必须全部覆盖）
{checklist_text}

## 工具使用规则
1. ⚠️ 必须先用 schema_search 或 openconfig_schema_search 查询正确的命令/XPath
2. 不要猜测命令语法，厂商命令不同
3. 优先使用 NETCONF (OpenConfig)，CLI 作为备选

## 输出要求
对每个检查项报告状态:
- ✓ 正常: 检查通过
- ✗ 异常: 发现问题，描述详情
- ? 无法检查: 说明原因

当前设备信息:
- 名称: {state['device']['name']}
- 平台: {state['device']['platform']}
- 厂商: {state['device']['vendor']}
"""
    
    # Inspector 是一个 ReAct Agent，使用工具完成检查
    # ... (ReAct 循环实现)
```

---

## 参考

- [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [LangChain deepagents](https://github.com/langchain-ai/deepagents) (archive/deepagents/)
- [LangGraph Send API](https://langchain-ai.github.io/langgraph/how-tos/send-api/)
- [LangGraph Subgraphs](https://langchain-ai.github.io/langgraph/how-tos/subgraphs/)
- Legacy DeepPath V1: archive/strategies/deep_path_v1.py
