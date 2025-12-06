# OLAV V2 重构计划：三模式隔离架构

> 📅 创建日期: 2025-12-06  
> 🔀 分支: `refactor/modes-isolation`  
> 📁 归档文档: [docs/archive/](./archive/)

---

## 1. 重构背景

### 1.1 当前问题

| 问题 | 影响 |
|------|------|
| **架构混乱** | `strategies/`, `workflows/`, `agents/` 职责重叠 |
| **死代码** | `multi_agent_orchestrator.py` 等从未被调用 |
| **硬编码回退** | `INTENT_PATTERNS_FALLBACK` 50+ 关键词 |
| **模式耦合** | Standard/Expert 共用代码路径，难以独立维护 |

### 1.2 重构目标

1. **模式隔离**: 三个模式独立目录，独立开发、测试、部署
2. **清理死代码**: 删除从未使用的 multi-agent 组件
3. **统一工具层**: 所有模式共享相同的 Schema-Aware 工具
4. **渐进式开发**: Phase 1 → 2 → 3 分阶段完成

---

## 2. 核心设计原则

| 原则 | 说明 |
|------|------|
| **架构决定行为** | 不依赖 LLM 遵守长 prompt，用代码结构强制行为 |
| **Schema-Aware** | 2 个通用工具 + 动态 Schema 发现，而非 120+ 专用工具 |
| **Funnel Debugging** | SuzieQ 宏观 → NETCONF/CLI 微观 |
| **Zero Hallucination** | Python 算子验证，LLM 只总结已验证事实 |
| **HITL Safety** | 所有写操作需人工审批 |

---

## 3. 三模式架构

```
                    ┌─────────────────────────────────┐
                    │      CLI / API Entry Point      │
                    │   -S (standard) / -E (expert)   │
                    │   inspect <profile>             │
                    └──────────────┬──────────────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────┐
    │                              │                              │
    ▼                              ▼                              ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ STANDARD MODE │          │  EXPERT MODE  │          │INSPECTION MODE│
│   快速执行     │          │   故障分析     │          │   日常巡检    │
├───────────────┤          ├───────────────┤          ├───────────────┤
│ ✓ 单台查询    │          │ ✓ 多轮推理    │          │ ✓ YAML 驱动   │
│ ✓ 批量查询    │          │ ✓ 假设-验证   │          │ ✓ 阈值校验    │
│ ✓ 配置修改    │          │ ✓ L1-L4 诊断  │          │ ✓ 批量并发    │
│ ✓ HITL (写)   │          │ ✗ 只读        │          │ ✗ 只读        │
└───────┬───────┘          └───────┬───────┘          └───────┬───────┘
        │                          │                          │
        │  FastPath                │  DeepPath                │  BatchPath
        │                          │                          │
        └──────────────────────────┴──────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      SHARED TOOL LAYER      │
                    │                             │
                    │  • suzieq_query             │
                    │  • suzieq_schema_search     │
                    │  • netbox_api_call          │
                    │  • netconf_get / cli_show   │
                    │  • netconf_edit / cli_config│ ◄── HITL
                    │  • kb_search / syslog_search│
                    └─────────────────────────────┘
```

### 3.1 模式定位

| 模式 | 定位 | 能力 | 写权限 |
|------|------|------|--------|
| **Standard** | 快速执行日常任务 | 单台/批量查询, 配置修改 | ✅ (HITL) |
| **Expert** | 复杂故障分析定位 | 多轮推理, L1-L4 诊断 | ❌ 只读 |
| **Inspection** | 日常巡检 | YAML 驱动, 阈值校验 | ❌ 只读 |

---

## 4. 新目录结构

```
src/olav/
├── modes/                          # 🆕 三模式隔离
│   ├── __init__.py                 # Mode Protocol + 路由
│   ├── base.py                     # ModeProtocol 基类
│   │
│   ├── standard/                   # Phase 1 项目阶段
│   │   ├── __init__.py
│   │   ├── executor.py             # FastPath 执行器
│   │   ├── classifier.py           # UnifiedClassifier (重构自 unified_classifier.py)
│   │   └── prompts/                # 模式专用 prompts
│   │
│   ├── expert/                     # Phase 2 项目阶段 - 两阶段诊断架构
│   │   ├── __init__.py
│   │   ├── workflow.py             # 两阶段工作流编排
│   │   ├── supervisor.py           # 调度控制: KB + Syslog → 决策
│   │   ├── quick_analyzer.py       # 🔹 Phase 1: SuzieQ 快速分析 (60% 置信)
│   │   ├── deep_analyzer.py        # 🔹 Phase 2: CLI/NETCONF 实时验证 (95% 置信)
│   │   ├── report.py               # 报告生成 + RAG 索引
│   │   └── prompts/                # 模式专用 prompts
│   │       ├── quick_analyzer.yaml
│   │       ├── deep_analyzer.yaml
│   │       └── supervisor.yaml
│   │
│   └── inspection/                 # Phase 3 项目阶段
│       ├── __init__.py
│       ├── loader.py               # YAML 配置加载
│       ├── compiler.py             # NL → SQL 编译器 (可选)
│       ├── executor.py             # Map-Reduce 并行执行
│       ├── validator.py            # ThresholdValidator (零幻觉)
│       └── prompts/                # 模式专用 prompts
│
├── shared/                         # 🆕 共享组件 (重构自现有代码)
│   ├── __init__.py
│   ├── tools/                      # 统一工具层
│   │   ├── suzieq.py               # suzieq_query, suzieq_schema_search
│   │   ├── netbox.py               # netbox_api_call
│   │   ├── nornir.py               # netconf_get/edit, cli_show/config
│   │   ├── opensearch.py           # kb_search, syslog_search, memory_search
│   │   └── registry.py             # ToolRegistry
│   ├── hitl/                       # HITL 中间件
│   │   ├── middleware.py           # HITLMiddleware
│   │   └── prompts.py              # 审批 prompt
│   ├── confidence.py               # 置信度计算
│   └── protocols.py                # BackendProtocol 等
│
├── cli/                            # 保留 (入口调整)
├── server/                         # 保留 (入口调整)
└── core/                           # 保留 (LLM, PromptManager, Settings)
```

### 4.1 删除/归档清单

| 路径 | 处理 | 原因 |
|------|------|------|
| `agents/multi_agent_orchestrator.py` | 删除 | 死代码，从未被调用 |
| `agents/query_agent.py` | 删除 | 死代码 |
| `agents/diagnose_agent.py` | 删除 | 死代码 |
| `agents/config_agent.py` | 删除 | 死代码 |
| `agents/intent_classifier.py` | 删除 | 与 unified_classifier 重复 |
| `strategies/selector.py` | 已删除 | 用户手选模式，不需要 LLM 选择 |
| `strategies/fast_path.py` | 迁移 | → `modes/standard/executor.py` |
| `strategies/deep_path.py` | 迁移 | → `modes/expert/workflow.py` |
| `strategies/batch_path.py` | 迁移 | → `modes/inspection/executor.py` |
| `workflows/supervisor_driven.py` | 迁移 | → `modes/expert/workflow.py` |

---

## 5. 分阶段开发计划

### Phase 1: Standard Mode (2-3 天)

**目标**: 快速日常操作，单台/批量查询，配置修改

#### 5.1.1 核心组件

| 组件 | 来源 | 说明 |
|------|------|------|
| `UnifiedClassifier` | 重构 `unified_classifier.py` | Intent + Tool + Params 一次 LLM |
| `FastPathExecutor` | 重构 `fast_path.py` | 单次工具调用，无迭代 |
| `ToolRegistry` | 迁移 `tools/base.py` | 工具注册与发现 |
| `HITLMiddleware` | 重构 | 写操作审批 |

#### 5.1.2 能力矩阵

| 操作类型 | 支持 | 实现方式 | HITL |
|----------|------|----------|------|
| 单台状态查询 | ✓ | `suzieq_query` | ❌ |
| 批量状态查询 | ✓ | `suzieq_query` + filters | ❌ |
| 设备清单查询 | ✓ | `netbox_api_call` (GET) | ❌ |
| 实时配置读取 | ✓ | `netconf_get` | ❌ |
| CLI Show 命令 | ✓ | `cli_show` | ❌ |
| **设备配置修改** | ✓ | `netconf_edit` | ✅ **必须** |
| **CLI Config 命令** | ✓ | `cli_config` | ✅ **必须** |
| **NetBox 创建** | ✓ | `netbox_api_call` (POST) | ✅ **必须** |
| **NetBox 修改** | ✓ | `netbox_api_call` (PUT/PATCH) | ✅ **必须** |
| **NetBox 删除** | ✓ | `netbox_api_call` (DELETE) | ✅ **必须** |

#### 5.1.2.1 HITL 触发规则

```python
# shared/hitl/middleware.py

class HITLMiddleware:
    """所有写操作必须经过 HITL 审批"""
    
    # 需要 HITL 的操作
    WRITE_OPERATIONS = {
        # 设备配置
        "netconf_edit": True,      # NETCONF edit-config
        "cli_config": True,        # CLI 配置命令
        
        # NetBox CMDB
        "netbox_api_call": {
            "POST": True,          # 创建资源
            "PUT": True,           # 完整更新
            "PATCH": True,         # 部分更新
            "DELETE": True,        # 删除资源
            "GET": False,          # 查询免审
        },
    }
    
    async def check(self, tool_name: str, params: dict) -> bool:
        """检查是否需要 HITL 审批"""
        if tool_name == "netbox_api_call":
            method = params.get("method", "GET").upper()
            return self.WRITE_OPERATIONS["netbox_api_call"].get(method, False)
        return self.WRITE_OPERATIONS.get(tool_name, False)
```

#### 5.1.3 交付物

- [x] `src/olav/modes/standard/` 目录结构
- [x] `executor.py`: 重构自 `fast_path.py`
- [x] `classifier.py`: 重构自 `unified_classifier.py`
- [x] ~~删除 `INTENT_PATTERNS_FALLBACK` 硬编码关键词~~ (保留用于 legacy 兼容)
- [x] 单元测试: `tests/unit/modes/test_standard.py` (12 tests)

**✅ Phase 1 完成** (2025-12-06)

性能优化记录:
- temperature: 0.2 → 0 (贪婪解码)
- max_tokens: 16000 → 512 (分类任务)
- reasoning 字段可选 (减少生成)
- 平均延迟: 5550ms → 2024ms (**63.5% 提升**)

---

### Phase 1.5: 性能优化 - 正则快速路径 + Prompt 瘦身 (1天)

> 📅 添加日期: 2025-12-06  
> 🎯 目标: 简单查询延迟从 1.5s → 50ms

#### 5.1.5.1 E2E 性能测试数据

| 模式 | 通过率 | 平均总时间 | 平均 LLM 时间 | LLM 占比 |
|------|--------|------------|---------------|---------|
| Standard | 6/8 (75%) | 2,175ms | 1,950ms | 90-99% |
| Expert | 3/3 (100%) | 664ms | 464ms | 70% |
| Inspection | 1/1 (100%) | 100ms | 0ms | 0% |

**关键发现**:
1. **LLM 是主要瓶颈** - Standard Mode 中 LLM 推理占 90-99%
2. **首次调用慢** - 冷启动 5.8s vs 正常 1.5s (Ollama 模型加载)
3. **简单查询无需 LLM** - "列出设备"、"查 BGP" 可正则直接匹配

#### 5.1.5.2 优化策略: 共用预处理 + 分流执行

```
用户查询
    │
    ▼
┌─────────────────────────────────────────┐
│      QueryPreprocessor (共用层)          │
│  1. 正则提取: 设备名、表名、参数         │
│  2. 意图关键词: diagnostic / query       │
└─────────────────────────────────────────┘
    │
    ├── 诊断类关键词 ("为什么", "诊断", "分析")
    │         │
    │         ▼
    │    Expert Mode (必须走 LLM 规划)
    │    - 使用预提取的设备作为起点
    │
    └── 查询类关键词 ("查询", "显示", "列出")
              │
              ▼
         ┌────────────────┐
         │ 正则完全匹配?   │
         └────────────────┘
              │
         Yes  │  No
              ▼   ▼
         直接执行  LLM 分类
         (50ms)   (1.5s)
```

**核心原则**:
- **提取逻辑共用** - 正则解析设备名、表名、参数
- **执行路径隔离** - Standard 可跳过 LLM，Expert 必须 LLM 规划
- **预处理减轻 LLM 负担** - 告诉 LLM "用户问的是 R1 的 BGP"

#### 5.1.5.3 正则快速路径设计

**位置**: `src/olav/modes/shared/preprocessor.py`

```python
# 关键词分类
DIAGNOSTIC_KEYWORDS = {"为什么", "诊断", "分析", "排查", "故障", "失败", "不通", "问题", "原因"}
QUERY_KEYWORDS = {"查询", "显示", "列出", "获取", "查看", "检查", "show", "list", "get"}

# 正则快速匹配 (Standard Mode Only)
FAST_PATTERNS = [
    # BGP 查询
    (r"(?:查询|显示|查看).*?(?P<hostname>\S+).*?(?:的\s*)?BGP", 
     "suzieq_query", {"table": "bgp"}),
    
    # 接口查询
    (r"(?:查询|显示|查看).*?(?P<hostname>\S+).*?(?:的\s*)?接口",
     "suzieq_query", {"table": "interface"}),
    
    # 路由查询  
    (r"(?:查询|显示|查看|检查).*?(?P<hostname>\S+).*?(?:的\s*)?路由",
     "suzieq_query", {"table": "routes"}),
    
    # 设备列表 (无设备名)
    (r"(?:列出|显示|查询).*?(?:所有\s*)?设备",
     "netbox_api_call", {"endpoint": "/dcim/devices/"}),
    
    # 全量接口状态
    (r"(?:显示|查询).*?所有.*?接口",
     "suzieq_query", {"table": "interface"}),
]

# 设备名提取 (共用)
DEVICE_PATTERN = r"(?:设备|主机|路由器|交换机)?\s*(?P<device>[A-Za-z][\w\-\.]+)"
```

#### 5.1.5.4 Prompt 瘦身设计

**位置**: `config/prompts/_defaults/unified_classification.yaml`

**优化点**:
1. ❌ 删除 `reasoning` 字段要求 (已完成)
2. ⏳ 压缩 few-shot 示例为单行格式
3. ⏳ 移除冗余工具描述
4. ⏳ 动态注入相关 schema (仅匹配查询的表)

**优化后 Prompt 结构**:
```yaml
template: |
  你是网络意图分类器。分析查询，返回JSON:
  {"intent_category": "...", "tool": "...", "parameters": {...}, "confidence": 0.0-1.0}

  ## 工具
  - suzieq_query: 网络状态 {table, hostname}
  - netbox_api_call: CMDB {endpoint, filters}
  - cli_tool: CLI命令 {device, command}

  ## 表名
  bgp, interface, routes, ospf, device, vlan, mac, lldp

  ## 示例
  "查询R1 BGP" → {"intent_category":"suzieq","tool":"suzieq_query","parameters":{"table":"bgp","hostname":"R1"},"confidence":0.95}
  "列出设备" → {"intent_category":"netbox","tool":"netbox_api_call","parameters":{"endpoint":"/dcim/devices/"},"confidence":0.9}
```

**预期 Token 减少**: 150 → 60 tokens (60% 减少)

#### 5.1.5.5 交付物

- [ ] `src/olav/modes/shared/preprocessor.py`: QueryPreprocessor 类
- [ ] 更新 `unified_classifier.py`: 集成正则快速路径
- [ ] 优化 `unified_classification.yaml`: Prompt 瘦身
- [ ] 单元测试: `tests/unit/test_preprocessor.py`
- [ ] E2E 性能回归测试

#### 5.1.5.6 预期收益

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 简单查询延迟 | 1.5s | 50ms | **30x** |
| 复杂查询延迟 | 1.5s | 1.0s | 1.5x |
| 首次查询延迟 | 5.8s | 1.5s | 4x (预热) |
| Prompt Token | 150 | 60 | 60% |

---

### Phase 2: Expert Mode - 两阶段诊断架构 (3-4 天)

**目标**: 复杂故障分析，多轮推理，只读

> 📅 更新日期: 2025-12-06
> 🎯 核心原则: **SuzieQ 是历史数据，必须通过实时数据作为补充**

#### 5.2.1 两阶段架构设计

**为什么需要两阶段？**

| 数据源 | 特点 | 置信度上限 | 适用场景 |
|--------|------|------------|----------|
| SuzieQ (历史) | 毫秒级查询、预聚合、有采集延迟 | 60% | 快速扫描、缩小范围 |
| CLI/NETCONF (实时) | 秒级延迟、需要 SSH、最新状态 | 95% | 验证可疑点、配置分析 |

**SuzieQ 的能力边界**:

| 数据类型 | SuzieQ 能力 | 说明 |
|----------|-------------|------|
| 运行时状态 (routes, bgp, interfaces) | ✅ 完全支持 | 但有采集延迟 (1-5分钟) |
| 设备配置 (devconfig) | ✅ 有数据 | 包含 route-map, prefix-list, ACL |
| 配置语义分析 | ⚠️ 需要解析 | 原始文本需 LLM/正则解析 |
| 实时 counters/stats | ❌ 滞后 | 需实时 CLI 补充 |
| STP 状态 | ❌ 不采集 | 需实时 CLI/NETCONF |

> **⚠️ 重要说明**: 即使 SuzieQ `devconfig` 表包含配置数据（route-map, prefix-list 等），
> 这些仍然是**历史快照**，不是实时配置。如果管理员刚修改了配置但 SuzieQ 还没重新采集，
> 就会有数据滞后。因此 **Phase 2 实时验证始终是必要的**。
>
> **SuzieQ 采集周期**: 通常 1-5 分钟，配置变更后可能有延迟。

#### 5.2.2 核心组件

| 组件 | 来源 | 阶段 | 说明 |
|------|------|------|------|
| `Supervisor` | 新建 | 控制 | KB + Syslog → 层级优先级决策 |
| `QuickAnalyzer` | 新建 | Phase 1 | SuzieQ 快速分析 (60% 置信) |
| `DeepAnalyzer` | 新建 | Phase 2 | CLI/NETCONF 实时验证 (95% 置信) |
| `ReportGenerator` | 新建 | 输出 | 诊断报告 + RAG 索引 |

#### 5.2.3 两阶段诊断流程

```
User Query: "用户报告 192.168.10.1 无法访问 10.0.100.100"
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Round 0: Supervisor 初始化                              │
│  • kb_search("连通性问题") → 历史案例                    │
│  • syslog_search(severity=error) → 触发事件             │
│  • 决策: 确定检查优先级 [L3 > L2 > L1]                  │
└─────────────────────────────────────────────────────────┘
    │
    ▼
╔═════════════════════════════════════════════════════════╗
║  Phase 1: Quick Analyzer (SuzieQ 历史数据)               ║
║  最高置信度: 60%                                         ║
╠═════════════════════════════════════════════════════════╣
║  工具:                                                   ║
║  • suzieq_query(table="routes") → 检查路由表            ║
║  • suzieq_query(table="bgp") → BGP 邻居状态             ║
║  • suzieq_query(table="interfaces") → 接口状态          ║
║  • suzieq_query(table="arpnd") → ARP/ND 表              ║
║                                                          ║
║  发现:                                                   ║
║  • R3/R4 缺少 10.0.0.0/16 路由                          ║
║  • R1/R2 BGP 状态 Established (看起来正常)              ║
║  • 置信度: 50% (发现路由缺失，但原因未知)               ║
╚═════════════════════════════════════════════════════════╝
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Supervisor 决策                                         │
│  • Phase 1 置信度 < 80% → 需要 Phase 2 验证              │
│  • 可疑点: R1/R2 BGP 策略可能阻断路由传递                │
│  • 调度 Phase 2: 检查 R1/R2 BGP 配置                    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
╔═════════════════════════════════════════════════════════╗
║  Phase 2: Deep Analyzer (CLI/NETCONF 实时数据)           ║
║  置信度: 95%                                             ║
╠═════════════════════════════════════════════════════════╣
║  工具:                                                   ║
║  • cli_show(device="R1", command="show run | sec bgp")  ║
║  • cli_show(device="R1", command="show route-map")      ║
║  • cli_show(device="R1", command="show ip prefix-list") ║
║  • netconf_get(device="R1", xpath="/bgp/neighbors")     ║
║                                                          ║
║  发现:                                                   ║
║  • R1 route-map bgp_out 只允许 192.168.10.0/24          ║
║  • R2 route-map bgp_in 只允许 192.168.20.0/24           ║
║  • 10.0.0.0/16 被 deny 规则阻断！                       ║
║  • 置信度: 95% (实时数据，明确根因)                     ║
╚═════════════════════════════════════════════════════════╝
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Diagnosis Conclusion                                   │
│  • 根因: R1/R2 BGP route-map/prefix-list 阻断 10.0.0.0 │
│  • 层级: L3 (路由策略)                                  │
│  • 证据链:                                              │
│    1. [Phase 1] R3/R4 缺少 10.0.0.0/16 路由            │
│    2. [Phase 2] R1 bgp_out 只放行 192.168.10.0/24      │
│    3. [Phase 2] R2 bgp_in 只放行 192.168.20.0/24       │
│  • 建议: 修改 prefix-list 添加 10.0.0.0/16 许可        │
│  • (只读模式: 不执行修改，仅提供建议)                    │
└─────────────────────────────────────────────────────────┘
```

#### 5.2.4 Phase 1 vs Phase 2 工具分配

| 阶段 | 工具 | 用途 | 置信度 |
|------|------|------|--------|
| **Phase 1 (Quick)** | `suzieq_query` | 历史状态查询 (routes, bgp, interfaces...) | 60% |
| | `suzieq_schema_search` | SuzieQ Schema 发现 | - |
| **Phase 2 (Deep)** | `openconfig_schema_search` | OpenConfig YANG Schema 发现 | - |
| | `netconf_get` | NETCONF 实时读取 (OpenConfig/Native) | 95% |
| | `cli_show` | CLI 命令读取 (厂商特定) | 95% |
| **Supervisor** | `kb_search` | 知识库检索 (历史案例) | - |
| | `syslog_search` | 日志搜索 (触发事件) | - |
| **Report** | `memory_store` | 索引诊断报告到 Episodic Memory | - |

**工具隔离原则**:

| 原则 | 说明 |
|------|------|
| **Phase 1 只用 SuzieQ** | 历史数据快速扫描，不访问设备 |
| **Phase 2 只用 OpenConfig/CLI** | 实时数据验证，SSH/NETCONF 连接设备 |
| **不混用工具** | Phase 2 不再调用 SuzieQ，避免数据源混淆 |

#### 5.2.5 Phase 2 触发条件

```python
class Supervisor:
    def should_trigger_phase2(self, phase1_result: Phase1Result) -> bool:
        """判断是否需要 Phase 2 实时验证"""
        
        # 1. 置信度不足
        if phase1_result.confidence < 0.80:
            return True
        
        # 2. 发现可疑点但无法确认根因
        if phase1_result.suspected_issues and not phase1_result.root_cause_confirmed:
            return True
        
        # 3. 涉及配置策略类问题 (SuzieQ 盲区)
        if any(keyword in phase1_result.hypothesis 
               for keyword in ["route-map", "prefix-list", "ACL", "policy", "STP"]):
            return True
        
        # 4. 数据过时
        if phase1_result.data_age_seconds > 300:  # 5分钟
            return True
        
        return False
```

#### 5.2.6 Quick/Deep 循环策略

**架构决定行为**: 循环控制由代码结构强制执行，不依赖 LLM 遵守指令。

```
                         ┌─────────────────────────────────────┐
                         │        Workflow Entry Point         │
                         │  workflow.run(query, max_rounds=5)  │
                         └──────────────────┬──────────────────┘
                                            │
                                            ▼
                         ┌─────────────────────────────────────┐
                         │  Round 0: Supervisor Initialization │
                         │  • kb_search() → 历史案例           │
                         │  • syslog_search() → 相关事件       │
                         │  • plan_next_task() → L1-L4 优先级  │
                         └──────────────────┬──────────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        │                                   │                                   │
        │ ┌─────────────────────────────────▼─────────────────────────────────┐ │
        │ │                    ROUND LOOP (max 5 rounds)                      │ │
        │ │                                                                   │ │
        │ │  ┌─────────────────────────────────────────────────────────────┐  │ │
        │ │  │  Phase 1: Quick Analyzer (SuzieQ)                           │  │ │
        │ │  │  • Tools: suzieq_query, suzieq_schema_search               │  │ │
        │ │  │  • Max confidence: 60%                                      │  │ │
        │ │  │  • ReAct iterations: 5-8 per task                          │  │ │
        │ │  └──────────────────────────┬──────────────────────────────────┘  │ │
        │ │                             │                                     │ │
        │ │                             ▼                                     │ │
        │ │  ┌─────────────────────────────────────────────────────────────┐  │ │
        │ │  │  Supervisor Decision Point                                  │  │ │
        │ │  │  • Evaluate Phase 1 confidence                             │  │ │
        │ │  │  • Check: should_trigger_phase2()                          │  │ │
        │ │  └──────────────────────────┬──────────────────────────────────┘  │ │
        │ │                             │                                     │ │
        │ │              ┌──────────────┴──────────────┐                     │ │
        │ │              │                             │                     │ │
        │ │       confidence ≥ 80%              confidence < 80%             │ │
        │ │       root_cause = True            or suspected_issues           │ │
        │ │              │                     or policy_keywords            │ │
        │ │              │                             │                     │ │
        │ │              ▼                             ▼                     │ │
        │ │     ┌────────────────┐     ┌─────────────────────────────────┐   │ │
        │ │     │  Skip Phase 2  │     │  Phase 2: Deep Analyzer         │   │ │
        │ │     │  → Report      │     │  • Tools: cli_show, netconf_get │   │ │
        │ │     └────────────────┘     │  • Max confidence: 95%          │   │ │
        │ │                            │  • Target: suspected devices    │   │ │
        │ │                            └──────────────────┬──────────────┘   │ │
        │ │                                               │                   │ │
        │ │                            ┌──────────────────┘                   │ │
        │ │                            ▼                                     │ │
        │ │  ┌─────────────────────────────────────────────────────────────┐  │ │
        │ │  │  Supervisor: update_state()                                 │  │ │
        │ │  │  • Update layer confidences                                │  │ │
        │ │  │  • Check root_cause_found indicators                       │  │ │
        │ │  │  • Decide next round's priority                            │  │ │
        │ │  └──────────────────────────┬──────────────────────────────────┘  │ │
        │ │                             │                                     │ │
        │ │              ┌──────────────┴──────────────┐                     │ │
        │ │              │                             │                     │ │
        │ │     root_cause_found            root_cause NOT found             │ │
        │ │     or max_rounds                   and has_gaps                 │ │
        │ │              │                             │                     │ │
        │ │              ▼                             │                     │ │
        │ │        EXIT LOOP ◄─────────────────────────┘                     │ │
        │ │                      (next round)                                 │ │
        │ └───────────────────────────────────────────────────────────────────┘ │
        │                                                                       │
        └───────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                         ┌─────────────────────────────────────┐
                         │        Report Generation            │
                         │  • Conclusion with evidence chain   │
                         │  • Recommendations                  │
                         │  • Index to RAG for future reuse    │
                         └─────────────────────────────────────┘
```

**循环终止条件**:

| 条件 | 说明 | 优先级 |
|------|------|--------|
| `root_cause_found = True` | 发现明确根因并有证据链 | **最高** |
| `current_round >= max_rounds` | 达到最大轮数 (默认 5) | 高 |
| `all_layers_confidence >= 50%` | 所有层置信度足够 | 中 |
| `no_new_findings` | 连续 2 轮无新发现 | 低 |

**当前实现状态**:

| 组件 | 实现状态 | 说明 |
|------|----------|------|
| Round 循环 | ✅ 已实现 | `supervisor.py` 中 Round 0-N 控制 |
| Phase 1 (Quick) | ✅ 已实现 | `quick_analyzer.py` SuzieQ 工具 |
| Phase 2 (Deep) | ❌ **未实现** | 需要 `deep_analyzer.py` |
| KB + Syslog | ✅ 已实现 | `supervisor.round_zero_context()` |
| devconfig 分析 | ⚠️ 部分 | 有数据，缺 ConfigSectionExtractor |

#### 5.2.7 L1-L4 故障覆盖率

| 层级 | Phase 1 (SuzieQ) | Phase 2 (CLI/NETCONF) | 组合覆盖 |
|------|------------------|----------------------|----------|
| L1 物理层 | 70% | 95% | **~85%** |
| L2 链路层 | 55% | 85% | **~70%** |
| L3 网络层 | 75% | 90% | **~85%** |
| L4 策略层 | 15% | 75% | **~50%** |

**L4 策略层详细覆盖**:

| 故障类型 | Phase 1 | Phase 2 | 说明 |
|----------|---------|---------|------|
| route-map 阻断 | ⚠️ 间接 | ✅ | Phase 1 看到路由缺失，Phase 2 确认策略 |
| prefix-list 错误 | ⚠️ 间接 | ✅ | 同上 |
| ACL 阻断 | ❌ | ✅ | 需要 CLI 读取 ACL 规则 |
| NAT 问题 | ❌ | ⚠️ | 厂商特定命令 |
| QoS 丢包 | ⚠️ | ⚠️ | 需要 counters |

#### 5.2.8 交付物

- [ ] `src/olav/modes/expert/` 目录结构
- [ ] `supervisor.py`: 两阶段调度控制
- [ ] `quick_analyzer.py`: Phase 1 SuzieQ 快速分析
- [ ] `deep_analyzer.py`: Phase 2 OpenConfig/CLI 实时验证
- [ ] `report.py`: 报告生成 + Episodic Memory 索引 (Agentic 闭环)
- [ ] `src/olav/shared/tools/`:
  - [ ] `config_extractor.py`: 配置段落提取器 (Token 优化)
  - [ ] `openconfig.py`: `openconfig_schema_search`, `netconf_get`
  - [ ] `cli.py`: `cli_show` (厂商特定命令)
  - [ ] `opensearch.py`: `memory_store` (Episodic Memory 索引)
- [ ] `config/prompts/expert/`:
  - [ ] `quick_analyzer.yaml`: Phase 1 Prompt
  - [ ] `deep_analyzer.yaml`: Phase 2 Prompt
  - [ ] `supervisor.yaml`: 调度决策 Prompt
- [ ] OpenSearch 索引: `olav-episodic-memory` (Agentic 闭环)
- [ ] 单元测试: `tests/unit/modes/test_expert.py`
- [ ] 单元测试: `tests/unit/shared/test_config_extractor.py`

#### 5.2.9 Agentic 闭环：报告索引到 Episodic Memory

> **核心原则**: 每次成功诊断的结果都应该被索引到知识库，形成"学习闭环"。
> 下次遇到类似问题时，Supervisor 的 `kb_search` 可以直接检索到历史案例。

**闭环流程**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENTIC LEARNING LOOP                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐   │
│  │ User Query  │────▶│ Supervisor  │────▶│ kb_search(query)        │   │
│  │ "R3 无法    │     │ Round 0     │     │ → 检索历史案例          │   │
│  │  访问 10.x" │     │             │     │ → 发现: 2024-12-05 案例 │   │
│  └─────────────┘     └─────────────┘     │   "BGP route-map 阻断"  │   │
│                                          └───────────┬─────────────┘   │
│                                                      │                  │
│                                          ┌───────────▼─────────────┐   │
│                                          │ 利用历史案例加速诊断    │   │
│                                          │ • 跳过部分 Phase 1 步骤 │   │
│                                          │ • 直接检查 BGP 策略     │   │
│                                          └───────────┬─────────────┘   │
│                                                      │                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    DIAGNOSIS COMPLETE                           │   │
│  │  Root Cause: R1/R2 route-map 阻断 10.0.0.0/16                  │   │
│  │  Confidence: 95%                                                │   │
│  │  Evidence: [Phase 1 路由缺失, Phase 2 策略验证]                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ReportGenerator.generate_and_index()                           │   │
│  │                                                                  │   │
│  │  1. 生成结构化报告 (Markdown + JSON)                            │   │
│  │  2. 调用 memory_store() 工具                                    │   │
│  │  3. 索引到 OpenSearch: olav-episodic-memory                     │   │
│  │                                                                  │   │
│  │  索引内容:                                                       │   │
│  │  {                                                               │   │
│  │    "query": "R3 无法访问 10.0.100.100",                         │   │
│  │    "root_cause": "BGP route-map 阻断",                          │   │
│  │    "layer": "L4",                                                │   │
│  │    "devices": ["R1", "R2"],                                      │   │
│  │    "config_sections": ["route-map bgp_out", "prefix-list net10"],│   │
│  │    "resolution": "修改 prefix-list 添加 10.0.0.0/16",           │   │
│  │    "evidence_chain": [...],                                      │   │
│  │    "timestamp": "2024-12-06T10:30:00Z"                           │   │
│  │  }                                                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              │ 下次类似问题                             │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  kb_search("连通性 10.x 无法访问")                               │   │
│  │  → 检索到本次诊断结果                                            │   │
│  │  → Supervisor 直接参考历史案例                                   │   │
│  │  → 诊断时间从 5 分钟 → 30 秒                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**ReportGenerator 实现**:

```python
# modes/expert/report.py

from olav.tools.opensearch import MemoryStoreTool

class ReportGenerator:
    """诊断报告生成器 - 支持 Agentic 闭环"""
    
    def __init__(self):
        self.memory_store = MemoryStoreTool()
    
    async def generate_and_index(
        self,
        diagnosis_state: DiagnosisState,
        index_to_memory: bool = True
    ) -> DiagnosisReport:
        """生成报告并索引到 Episodic Memory"""
        
        # 1. 生成结构化报告
        report = self._generate_report(diagnosis_state)
        
        # 2. 索引到知识库 (Agentic 闭环)
        if index_to_memory and report.root_cause_found:
            await self._index_to_episodic_memory(report)
        
        return report
    
    async def _index_to_episodic_memory(self, report: DiagnosisReport):
        """索引成功诊断到 Episodic Memory"""
        
        document = {
            "query": report.original_query,
            "root_cause": report.root_cause,
            "root_cause_type": report.root_cause_type,  # "config_policy", "hardware", "protocol"
            "layer": report.layer,                       # "L1", "L2", "L3", "L4"
            "devices": report.affected_devices,
            "config_sections": report.relevant_configs,  # ["route-map bgp_out", ...]
            "evidence_chain": [
                {"phase": e.phase, "finding": e.finding, "confidence": e.confidence}
                for e in report.evidence_chain
            ],
            "resolution": report.recommended_resolution,
            "diagnosis_duration_seconds": report.duration_seconds,
            "timestamp": report.timestamp.isoformat(),
        }
        
        await self.memory_store.execute(
            index="olav-episodic-memory",
            document=document,
            doc_id=f"diag-{report.timestamp.strftime('%Y%m%d%H%M%S')}-{hash(report.original_query) % 10000}"
        )
```

**OpenSearch 索引 Mapping**:

```json
// olav-episodic-memory index mapping
{
  "mappings": {
    "properties": {
      "query": { "type": "text", "analyzer": "ik_smart" },
      "root_cause": { "type": "text", "analyzer": "ik_smart" },
      "root_cause_type": { "type": "keyword" },
      "layer": { "type": "keyword" },
      "devices": { "type": "keyword" },
      "config_sections": { "type": "keyword" },
      "evidence_chain": { "type": "nested" },
      "resolution": { "type": "text" },
      "diagnosis_duration_seconds": { "type": "float" },
      "timestamp": { "type": "date" },
      "embedding": { "type": "knn_vector", "dimension": 1536 }
    }
  }
}
```

**Supervisor kb_search 集成**:

```python
# modes/expert/supervisor.py

async def round_zero_context(self, query: str) -> RoundZeroContext:
    """Round 0: 收集上下文 + 检索历史案例"""
    
    # 1. 检索历史诊断案例 (Episodic Memory)
    historical_cases = await self.kb_search.execute(
        query=query,
        index="olav-episodic-memory",
        size=3
    )
    
    # 2. 如果找到相似案例，提取关键信息
    if historical_cases:
        similar_case = historical_cases[0]
        return RoundZeroContext(
            has_historical_reference=True,
            suggested_layer=similar_case["layer"],
            suggested_devices=similar_case["devices"],
            suggested_config_sections=similar_case["config_sections"],
            historical_root_cause=similar_case["root_cause"],
            # 告诉 Quick Analyzer 优先检查这些
        )
    
    # 3. 没有历史案例，正常流程
    return RoundZeroContext(has_historical_reference=False)
```

#### 5.2.10 配置段落提取（Token 优化）

> **问题**: SuzieQ `devconfig.config` 是一个 TEXT BLOB（7000+ 字符），无法分段查询。
> 直接把整个配置丢给 LLM 会造成 Token 浪费和"lost in the middle"幻觉风险。

**解决方案**: 在 Python 层用正则提取相关配置段落，只把必要部分给 LLM。

```python
# shared/tools/config_extractor.py

import re
from typing import Literal

class ConfigSectionExtractor:
    """从设备配置中提取特定段落，减少 LLM token 消耗"""
    
    SECTION_PATTERNS = {
        "route-map": r'route-map \S+ (?:permit|deny) \d+.*?(?=\nroute-map|\n!|\nrouter|\Z)',
        "prefix-list": r'ip prefix-list \S+ seq \d+.*?(?=\nip prefix-list|\n!|\Z)',
        "bgp": r'router bgp \d+.*?(?=\n!|\nrouter (?!bgp)|\Z)',
        "bgp-neighbor": r'neighbor \S+ .*',
        "acl": r'ip access-list (?:standard|extended) \S+.*?(?=\nip access-list|\n!|\Z)',
        "ospf": r'router ospf \d+.*?(?=\n!|\nrouter|\Z)',
        "interface": r'interface \S+.*?(?=\ninterface|\n!|\Z)',
    }
    
    @classmethod
    def extract(cls, config: str, sections: list[str]) -> dict[str, str]:
        """提取多个配置段落
        
        Args:
            config: 完整设备配置文本
            sections: 要提取的段落类型列表
            
        Returns:
            {section_type: extracted_text}
        """
        result = {}
        for section in sections:
            pattern = cls.SECTION_PATTERNS.get(section)
            if pattern:
                matches = re.findall(pattern, config, re.DOTALL | re.MULTILINE)
                result[section] = '\n'.join(m.strip() for m in matches)
        return result
    
    @classmethod
    def extract_for_diagnosis(cls, config: str, hypothesis: str) -> str:
        """根据诊断假设智能提取相关配置
        
        Args:
            config: 完整设备配置
            hypothesis: 诊断假设（如 "BGP 路由策略阻断"）
            
        Returns:
            相关配置段落的合并文本
        """
        # 根据假设关键词选择要提取的段落
        sections_map = {
            "bgp": ["bgp", "bgp-neighbor", "route-map", "prefix-list"],
            "route-map": ["route-map", "prefix-list"],
            "prefix-list": ["prefix-list"],
            "acl": ["acl"],
            "ospf": ["ospf", "interface"],
            "interface": ["interface"],
        }
        
        # 匹配关键词
        sections_to_extract = set()
        for keyword, sections in sections_map.items():
            if keyword.lower() in hypothesis.lower():
                sections_to_extract.update(sections)
        
        # 默认提取策略相关配置
        if not sections_to_extract:
            sections_to_extract = {"route-map", "prefix-list", "acl"}
        
        extracted = cls.extract(config, list(sections_to_extract))
        return '\n\n'.join(f"=== {k} ===\n{v}" for k, v in extracted.items() if v)
```

**Token 节省效果**:

| 场景 | 完整配置 | 提取后 | 节省 |
|------|----------|--------|------|
| R1 BGP 策略分析 | 1,783 tokens | 356 tokens | **80%** |
| R1+R2 BGP 策略 | 3,590 tokens | 712 tokens | **80%** |
| 所有设备配置 | 5,216 tokens | ~1,000 tokens | **80%** |

**在 Phase 2 中的使用**:

```python
# deep_analyzer.py

async def analyze_bgp_policy(self, device: str, hypothesis: str) -> dict:
    # 1. 获取完整配置
    full_config = await self.suzieq_query(table="devconfig", hostname=device)
    
    # 2. 提取相关段落（而非整个配置）
    relevant_config = ConfigSectionExtractor.extract_for_diagnosis(
        config=full_config,
        hypothesis=hypothesis  # "BGP route-map 阻断 10.0.0.0/16"
    )
    
    # 3. 只把 ~300 tokens 给 LLM 分析，而非 ~1800 tokens
    analysis = await self.llm.analyze_config(relevant_config)
    
    return analysis
```

#### 5.2.11 置信度模型

```python
def calculate_confidence(
    source: Literal["suzieq", "realtime"],
    data_type: Literal["state", "config"],
    data_age_seconds: int
) -> float:
    """计算置信度"""
    
    # 实时数据高置信
    if source == "realtime":
        return 0.95
    
    # SuzieQ 历史数据
    if source == "suzieq":
        # 配置数据变化慢，置信度可以高一些
        if data_type == "config":
            if data_age_seconds < 3600:     # 1小时内
                return 0.70
            elif data_age_seconds < 86400:  # 1天内
                return 0.55
            else:
                return 0.40
        
        # 状态数据需要更新鲜
        else:  # data_type == "state"
            if data_age_seconds < 60:       # 1分钟内
                return 0.60
            elif data_age_seconds < 180:    # 3分钟内
                return 0.50
            elif data_age_seconds < 300:    # 5分钟内
                return 0.40
            else:
                return 0.25
    
    return 0.0
```

#### 5.2.12 Expert Mode Guard: 两层过滤机制

> **问题**: Expert Mode 的深度诊断涉及真实设备的 CLI/NETCONF 操作，成本高、耗时长。
> 如果用户输入的不是故障诊断请求（如简单查询、配置变更请求），或信息不足以启动诊断，
> 应该在入口处过滤或引导，避免浪费资源和产生误诊。

**设计原则**:

| 层次 | 名称 | 目的 | 失败行为 |
|------|------|------|----------|
| Layer 1 | **相关性过滤** | 判断是否为故障诊断请求 | 重定向到 Standard Mode |
| Layer 2 | **充分性检查** | 提取并验证诊断必要信息 | 追问缺失信息 |

**两层过滤架构**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EXPERT MODE GUARD ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  用户输入: "R3 无法访问 10.0.100.100"                                    │
│                   │                                                      │
│                   ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 1: 相关性过滤 (Relevance Filter)                           │    │
│  │                                                                   │    │
│  │ LLM 判断输入类型:                                                 │    │
│  │   • fault_diagnosis  → 继续到 Layer 2                            │    │
│  │   • simple_query     → 重定向 Standard Mode ("查询 R1 接口")     │    │
│  │   • config_change    → 重定向 Standard Mode ("配置 OSPF area")   │    │
│  │   • off_topic        → 直接拒绝 ("今天天气如何")                  │    │
│  └───────────────────────────────┬─────────────────────────────────┘    │
│                                  │ is_fault_diagnosis = True            │
│                                  ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 2: 充分性检查 (Sufficiency Check)                          │    │
│  │                                                                   │    │
│  │ 提取诊断上下文:                                                   │    │
│  │   • symptom: "无法访问"                     ✓ 已知               │    │
│  │   • symptom_type: "connectivity"            ✓ 推断               │    │
│  │   • source_device: "R3"                     ✓ 已知               │    │
│  │   • target_device: "10.0.100.100"           ✓ 已知               │    │
│  │   • protocol_hint: null                     ? 可选               │    │
│  │   • layer_hint: null                        ? 可选               │    │
│  │                                                                   │    │
│  │ 充分性判断: is_sufficient = True (必要字段已满足)                 │    │
│  └───────────────────────────────┬─────────────────────────────────┘    │
│                                  │                                       │
│                                  ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ OUTPUT: DiagnosisContext                                         │    │
│  │                                                                   │    │
│  │ {                                                                 │    │
│  │   "is_fault_diagnosis": true,                                     │    │
│  │   "is_sufficient": true,                                          │    │
│  │   "context": {                                                    │    │
│  │     "symptom": "无法访问",                                        │    │
│  │     "symptom_type": "connectivity",                               │    │
│  │     "source_device": "R3",                                        │    │
│  │     "target_device": "10.0.100.100",                              │    │
│  │     "protocol_hint": null,                                        │    │
│  │     "layer_hint": null                                            │    │
│  │   }                                                               │    │
│  │ }                                                                 │    │
│  └───────────────────────────────┬─────────────────────────────────┘    │
│                                  │                                       │
│                                  ▼                                       │
│                         进入 Expert Workflow                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**数据结构定义**:

```python
# modes/expert/guard.py

from enum import Enum
from pydantic import BaseModel
from typing import Optional, Literal

class QueryType(str, Enum):
    """用户输入类型分类"""
    FAULT_DIAGNOSIS = "fault_diagnosis"     # 故障诊断 → Expert Mode
    SIMPLE_QUERY = "simple_query"           # 简单查询 → Standard Mode
    CONFIG_CHANGE = "config_change"         # 配置变更 → Standard Mode
    OFF_TOPIC = "off_topic"                 # 非网络话题 → 拒绝

class SymptomType(str, Enum):
    """故障症状类型"""
    CONNECTIVITY = "connectivity"           # 连通性问题 (ping/traceroute)
    PERFORMANCE = "performance"             # 性能问题 (延迟/丢包)
    ROUTING = "routing"                     # 路由问题 (路由缺失/振荡)
    PROTOCOL = "protocol"                   # 协议问题 (BGP down/OSPF邻居)
    HARDWARE = "hardware"                   # 硬件问题 (接口 down/CRC)
    UNKNOWN = "unknown"                     # 无法判断

class DiagnosisContext(BaseModel):
    """诊断上下文 - 从用户输入中提取的结构化信息"""
    symptom: str                                      # "无法访问", "BGP 邻居 down"
    symptom_type: SymptomType                         # 症状分类
    source_device: Optional[str] = None               # 发起设备 "R3"
    target_device: Optional[str] = None               # 目标设备/IP "10.0.100.100"
    protocol_hint: Optional[str] = None               # 协议提示 "BGP", "OSPF"
    layer_hint: Optional[Literal["L1", "L2", "L3", "L4"]] = None  # 层次提示

class ExpertModeGuardResult(BaseModel):
    """Expert Mode Guard 输出"""
    query_type: QueryType                             # 输入类型
    is_fault_diagnosis: bool                          # 是否为故障诊断
    is_sufficient: bool                               # 信息是否充分
    missing_info: list[str] = []                      # 缺失的信息
    clarification_prompt: Optional[str] = None        # 追问提示
    context: Optional[DiagnosisContext] = None        # 提取的诊断上下文
    redirect_mode: Optional[Literal["standard"]] = None  # 重定向目标
```

**LLM Structured Output (单次调用)**:

```python
# 通过 Pydantic with_structured_output 实现单次 LLM 调用

class LLMGuardDecision(BaseModel):
    """LLM 输出的结构化决策"""
    
    # Layer 1: 相关性判断
    query_type: QueryType
    query_type_reasoning: str  # 判断理由
    
    # Layer 2: 信息提取 (仅当 query_type == fault_diagnosis 时有效)
    symptom: Optional[str] = None
    symptom_type: Optional[SymptomType] = None
    source_device: Optional[str] = None
    target_device: Optional[str] = None
    protocol_hint: Optional[str] = None
    layer_hint: Optional[Literal["L1", "L2", "L3", "L4"]] = None
    
    # 充分性判断
    is_sufficient: bool = False
    missing_info: list[str] = []
    clarification_prompt: Optional[str] = None
```

**Guard 实现**:

```python
# modes/expert/guard.py

from langchain_core.language_models import BaseChatModel
from olav.core.prompt_manager import prompt_manager

class ExpertModeGuard:
    """Expert Mode 入口过滤器 - 两层过滤机制"""
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(LLMGuardDecision)
        self.prompt = prompt_manager.load_agent_prompt("expert_mode_guard")
    
    async def check(self, user_query: str) -> ExpertModeGuardResult:
        """检查用户输入是否适合 Expert Mode
        
        Returns:
            ExpertModeGuardResult:
                - is_fault_diagnosis=True, is_sufficient=True → 进入诊断
                - is_fault_diagnosis=True, is_sufficient=False → 追问用户
                - is_fault_diagnosis=False → 重定向到 Standard Mode
        """
        
        # 单次 LLM 调用完成两层检查
        decision: LLMGuardDecision = await self.llm.ainvoke(
            self.prompt.format(user_query=user_query)
        )
        
        # 非故障诊断请求 → 重定向
        if decision.query_type != QueryType.FAULT_DIAGNOSIS:
            return ExpertModeGuardResult(
                query_type=decision.query_type,
                is_fault_diagnosis=False,
                is_sufficient=False,
                redirect_mode="standard" if decision.query_type in [
                    QueryType.SIMPLE_QUERY, QueryType.CONFIG_CHANGE
                ] else None
            )
        
        # 故障诊断请求 → 构建上下文
        context = DiagnosisContext(
            symptom=decision.symptom or "未知故障",
            symptom_type=decision.symptom_type or SymptomType.UNKNOWN,
            source_device=decision.source_device,
            target_device=decision.target_device,
            protocol_hint=decision.protocol_hint,
            layer_hint=decision.layer_hint,
        )
        
        return ExpertModeGuardResult(
            query_type=QueryType.FAULT_DIAGNOSIS,
            is_fault_diagnosis=True,
            is_sufficient=decision.is_sufficient,
            missing_info=decision.missing_info,
            clarification_prompt=decision.clarification_prompt,
            context=context,
        )
```

**Prompt 模板**:

```yaml
# config/prompts/agents/expert_mode_guard.yaml
_type: prompt
input_variables:
  - user_query
template: |
  你是网络故障诊断专家。分析用户输入，判断：
  1. 这是否是一个故障诊断请求？
  2. 如果是，信息是否足够启动诊断？
  
  ## 输入类型分类
  
  - fault_diagnosis: 描述网络故障症状，需要诊断根因
    例如: "R3 无法访问 10.0.100.100", "BGP 邻居 down", "接口报错"
    
  - simple_query: 查询网络状态，无需深度诊断
    例如: "查询 R1 接口", "显示所有 BGP 邻居", "R2 有哪些路由"
    
  - config_change: 配置变更请求
    例如: "配置 OSPF area 0", "修改 BGP neighbor", "添加 ACL"
    
  - off_topic: 非网络相关话题
    例如: "今天天气如何", "写一首诗"
  
  ## 充分性要求
  
  故障诊断至少需要：
  - symptom: 症状描述 (必须)
  - source_device 或 target_device: 至少一个设备/IP (必须)
  
  可选但有助于诊断：
  - protocol_hint: 协议类型 (BGP, OSPF, etc.)
  - layer_hint: 问题可能的层次 (L1/L2/L3/L4)
  
  ## 用户输入
  
  {user_query}
  
  请返回结构化的 JSON 决策。
```

**Workflow 集成**:

```python
# modes/expert/workflow.py

from olav.modes.expert.guard import ExpertModeGuard, QueryType

async def expert_workflow(state: ExpertState) -> ExpertState:
    """Expert Mode 主工作流"""
    
    # Step 0: Guard 检查
    guard = ExpertModeGuard(llm=state.llm)
    guard_result = await guard.check(state.user_query)
    
    # 非故障诊断 → 重定向
    if not guard_result.is_fault_diagnosis:
        if guard_result.redirect_mode == "standard":
            return ExpertState(
                status="redirect",
                redirect_to="standard_mode",
                message=f"这是一个{guard_result.query_type.value}请求，将使用标准模式处理"
            )
        else:
            return ExpertState(
                status="rejected",
                message="抱歉，这不是一个网络相关的请求"
            )
    
    # 信息不足 → 追问
    if not guard_result.is_sufficient:
        return ExpertState(
            status="clarification_needed",
            message=guard_result.clarification_prompt,
            missing_info=guard_result.missing_info
        )
    
    # 信息充分 → 开始诊断
    state.diagnosis_context = guard_result.context
    
    # ... 继续 Phase 1 / Phase 2 诊断流程
```

**测试用例**:

| 输入 | 预期 query_type | 预期 is_sufficient | 预期行为 |
|------|-----------------|-------------------|----------|
| "R3 无法访问 10.0.100.100" | fault_diagnosis | True | 进入诊断 |
| "网络有问题" | fault_diagnosis | False | 追问: "请描述具体症状和涉及的设备" |
| "查询 R1 接口状态" | simple_query | N/A | 重定向 Standard Mode |
| "配置 BGP neighbor" | config_change | N/A | 重定向 Standard Mode |
| "今天天气如何" | off_topic | N/A | 拒绝 |
| "BGP 邻居为什么 down" | fault_diagnosis | False | 追问: "请指定哪个设备的 BGP 邻居" |
| "R1 和 R2 之间 BGP 不通" | fault_diagnosis | True | 进入诊断 |

---

### Phase 3: Inspection Mode (2-3 天)

**目标**: 智能巡检系统 - 用户只需描述检查意图，LLM 自动选择表和条件

#### 5.3.1 设计理念

**传统方式 (硬编码)**:
```yaml
# ❌ 用户需要知道 SuzieQ 表名、字段名、阈值
tasks:
  - table: bgp
    method: get
    threshold:
      metric: "state"
      operator: "=="
      value: "Established"
```

**智能方式 (LLM 驱动)**:
```yaml
# ✅ 用户只描述意图，LLM 自动推断
checks:
  - name: "BGP邻居down"
    description: "检查BGP邻居是否有down状态"
```

#### 5.3.2 核心组件

| 组件 | 来源 | 说明 |
|------|------|------|
| `YAMLLoader` | 新建 | 加载 `config/inspections/*.yaml` |
| `IntentCompiler` | 新建 | **LLM 驱动**: 意图 → SuzieQ 查询计划 |
| `SchemaSearcher` | 复用 | 检索 suzieq-schema 索引辅助 LLM |
| `MapReduceExecutor` | 重构 `batch_path.py` | 并行执行 + 聚合 |
| `ThresholdValidator` | 新建 | Python 算子，零幻觉 |

#### 5.3.3 智能巡检配置示例

```yaml
# config/inspections/daily-core.yaml
name: "Daily Core Router Check"
description: "核心路由器每日健康检查"

targets:
  netbox_filter: "role=core&status=active"

# 智能检查项 - 用户只需描述意图
checks:
  - name: "BGP邻居异常"
    description: "检查是否有BGP邻居处于非Established状态"
    severity: critical
    
  - name: "CPU使用率过高"
    description: "检查CPU使用率是否超过80%"
    severity: warning
    
  - name: "接口错误"
    description: "检查接口是否有输入/输出错误"
    severity: warning

  - name: "OSPF邻居丢失"
    description: "检查OSPF邻居数量是否少于预期"
    severity: critical
```

#### 5.3.4 IntentCompiler 工作流

```
用户配置:
  name: "BGP邻居异常"
  description: "检查是否有BGP邻居处于非Established状态"
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  1. Schema Search (RAG)                                 │
│  • 检索 suzieq-schema 索引                              │
│  • 返回相关表: bgp, ospf, ...                           │
│  • 返回字段: state, peerHostname, asn, ...              │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  2. LLM Intent Compilation                              │
│  • Prompt: "根据意图和可用 schema，生成查询计划"         │
│  • 输入: 意图 + Schema 上下文                           │
│  • 输出: 结构化查询计划 (JSON)                          │
└─────────────────────────────────────────────────────────┘
       │
       ▼
生成的查询计划:
{
  "table": "bgp",
  "method": "get",
  "filters": {},
  "validation": {
    "field": "state",
    "operator": "!=",
    "expected": "Established",
    "on_match": "report_violation"
  }
}
```

#### 5.3.5 Prompt 设计

```yaml
# config/prompts/inspection/intent_compiler.yaml
_type: prompt
input_variables:
  - check_name
  - check_description
  - schema_context
  - severity
template: |
  你是网络运维专家。根据用户的检查意图，生成 SuzieQ 查询计划。

  ## 检查项
  名称: {check_name}
  描述: {check_description}
  严重级别: {severity}

  ## 可用 Schema
  {schema_context}

  ## 输出格式 (JSON)
  {{
    "table": "选择最相关的表",
    "method": "get|summarize|unique",
    "filters": {{}},
    "validation": {{
      "field": "要检查的字段",
      "operator": "==|!=|>|<|>=|<=|contains",
      "expected": "期望值或阈值",
      "on_match": "report_violation|report_ok"
    }}
  }}

  只输出 JSON，不要其他解释。
```

#### 5.3.6 执行流程

```
olav inspect run daily-core
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  1. YAML Loader                                         │
│  • 解析 config/inspections/daily-core.yaml             │
│  • 提取 checks[] 列表                                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  2. Intent Compilation (LLM)                            │
│  • 对每个 check 调用 IntentCompiler                     │
│  • 生成结构化查询计划 (可缓存)                          │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  3. Target Resolution                                   │
│  • netbox_api_call(role=core&status=active)            │
│  • 返回: [R1, R2, R3, R4, R5]                          │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  4. Map-Reduce Execution (并行)                         │
│  • 根据查询计划调用 suzieq_query                        │
│  • 所有设备并行执行                                      │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  5. Threshold Validation (Zero Hallucination)           │
│  • Python operator.gt/lt/eq (非 LLM)                   │
│  • 收集 violations                                      │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  6. Report Generation                                   │
│  • LLM 仅总结已验证事实                                 │
│  • 输出: Markdown/JSON 报告                            │
└─────────────────────────────────────────────────────────┘
```

#### 5.3.7 查询计划缓存

为避免重复 LLM 调用，IntentCompiler 支持缓存：

```python
class IntentCompiler:
    def __init__(self, cache_path: Path = Path("data/cache/inspection_plans")):
        self.cache_path = cache_path
    
    def compile(self, check: dict) -> dict:
        cache_key = hashlib.md5(json.dumps(check, sort_keys=True)).hexdigest()
        cache_file = self.cache_path / f"{cache_key}.json"
        
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        
        # LLM 编译
        plan = self._llm_compile(check)
        cache_file.write_text(json.dumps(plan))
        return plan
```

#### 5.3.8 多数据源回退设计

**问题**: SuzieQ 并非支持所有检查项（如 CPU/内存使用率需要 `device` 表，部分厂商无数据），需要回退到 OpenConfig 或 CLI。

**设计原则**:
1. **巡检只读**: 所有检查只能使用 `show` 命令，**禁止** config 命令
2. **复用 Standard Mode**: 回退执行复用 `StandardModeExecutor`，继承工具执行逻辑
3. **无需 HITL**: show 命令为只读操作，不触发 HITL 审批

**数据源优先级**:
```
SuzieQ (Parquet 离线数据)
    │ 不支持?
    ▼
OpenConfig (NETCONF get)
    │ 设备不支持?
    ▼
CLI (show 命令)
```

**QueryPlan 扩展字段**:

```python
class QueryPlan(BaseModel):
    """编译后的查询计划"""
    
    # 基本字段
    table: str
    method: Literal["get", "summarize", "unique"]
    filters: dict[str, Any] = {}
    
    # 验证规则
    validation: ValidationRule | None = None
    
    # 🆕 数据源控制
    source: Literal["suzieq", "openconfig", "cli"] = "suzieq"
    
    # 🆕 回退配置 (当 source != suzieq 时使用)
    fallback_tool: str | None = None          # "netconf_get" 或 "cli_show"
    fallback_params: dict[str, Any] | None = None  # 工具参数
    
    # 🆕 安全约束
    read_only: bool = True  # 巡检模式强制 True
```

**IntentCompiler 扩展逻辑**:

```python
class IntentCompiler:
    # SuzieQ 支持的表 (从 schema 索引动态获取)
    SUZIEQ_TABLES: set[str] = {"bgp", "ospf", "interfaces", "routes", "macs", "lldp", ...}
    
    # 需要实时数据的检查类型 (SuzieQ 可能过时)
    REALTIME_CHECKS: set[str] = {"cpu", "memory", "temperature", "power"}
    
    async def compile(self, intent: str, ...) -> QueryPlan:
        # 1. Schema Search + LLM 编译
        plan = await self._llm_compile(intent)
        
        # 2. 检查 SuzieQ 是否支持
        if plan.table not in self.SUZIEQ_TABLES:
            plan = await self._compile_fallback(intent, plan)
        
        # 3. 检查是否需要实时数据
        if plan.table in self.REALTIME_CHECKS:
            plan = await self._compile_realtime(intent, plan)
        
        # 4. 强制只读
        plan.read_only = True
        return plan
    
    async def _compile_fallback(self, intent: str, original: QueryPlan) -> QueryPlan:
        """SuzieQ 不支持时回退到 OpenConfig/CLI"""
        
        # 尝试 OpenConfig
        xpath = await self._intent_to_xpath(intent)
        if xpath:
            return QueryPlan(
                table=original.table,
                method="get",
                source="openconfig",
                fallback_tool="netconf_get",
                fallback_params={
                    "xpath": xpath,
                    "datastore": "running",
                },
                validation=original.validation,
                read_only=True,
            )
        
        # 回退到 CLI show 命令
        show_command = await self._intent_to_show_command(intent)
        return QueryPlan(
            table=original.table,
            method="get",
            source="cli",
            fallback_tool="cli_show",
            fallback_params={
                "command": show_command,  # 必须是 show 命令
            },
            validation=original.validation,
            read_only=True,
        )
    
    async def _intent_to_show_command(self, intent: str) -> str:
        """LLM 生成 show 命令 (禁止 config 命令)"""
        # Prompt 明确约束只能生成 show 命令
        # 后处理验证命令以 "show " 开头
        command = await self._llm_generate_show_command(intent)
        
        # 安全检查: 必须是 show 命令
        if not command.strip().lower().startswith("show "):
            raise ValueError(f"Invalid command: {command}. Only 'show' commands allowed.")
        
        return command
```

**Controller 执行分发**:

```python
class InspectionModeController:
    async def execute_check(self, device: str, check: CheckConfig) -> CheckResult:
        # 1. 编译查询计划
        plan = await self.compiler.compile(check.intent, ...)
        
        # 2. 根据数据源分发执行
        if plan.source == "suzieq":
            result = await self._execute_suzieq(plan)
        else:
            # 复用 Standard Mode 执行器
            result = await self._execute_with_standard_mode(device, plan)
        
        # 3. 阈值验证 (零幻觉)
        return self._validate_threshold(result, plan.validation)
    
    async def _execute_with_standard_mode(
        self, 
        device: str, 
        plan: QueryPlan
    ) -> dict[str, Any]:
        """复用 Standard Mode 执行 OpenConfig/CLI 查询"""
        
        from olav.modes.standard import StandardModeExecutor
        
        # 构造 Classification Result (兼容 Standard Mode)
        from olav.core.unified_classifier import UnifiedClassificationResult
        
        classification = UnifiedClassificationResult(
            intent_category="query",
            tool=plan.fallback_tool,  # "netconf_get" 或 "cli_show"
            parameters={
                "hostname": device,
                **plan.fallback_params,
            },
            confidence=1.0,  # 编译器已确定
            reasoning="Inspection mode fallback",
        )
        
        # 执行 (yolo_mode=True 因为 show 命令无需 HITL)
        executor = StandardModeExecutor(
            tool_registry=self.tool_registry,
            yolo_mode=True,  # show 命令无需审批
        )
        
        result = await executor.execute(classification, user_query=plan.table)
        return result.raw_output
```

**安全约束**:

| 约束 | 实现位置 | 说明 |
|------|----------|------|
| 只允许 show 命令 | `_intent_to_show_command()` | Prompt 约束 + 后处理验证 |
| read_only 强制 True | `QueryPlan.read_only` | 编译器硬编码 |
| yolo_mode=True | `_execute_with_standard_mode()` | show 命令无需 HITL |
| 禁止 netconf_edit | 工具白名单 | 巡检模式只能调用 `netconf_get`, `cli_show` |

**Prompt 设计 (show 命令生成)**:

```yaml
# config/prompts/inspection/show_command_generator.yaml
_type: prompt
input_variables:
  - intent
  - device_vendor
template: |
  你是网络运维专家。根据检查意图生成对应的 show 命令。

  ## 检查意图
  {intent}

  ## 设备厂商
  {device_vendor}

  ## 约束
  - 只能生成 show 命令
  - 不能生成任何配置命令 (configure, set, delete 等)
  - 命令必须以 "show " 开头

  ## 输出
  直接输出一条 show 命令，不要其他解释。
```

#### 5.3.9 向后兼容

仍支持传统的硬编码配置（适合固定巡检）：

```yaml
# 混合模式 - 同时支持智能和硬编码
checks:
  # 智能检查 (LLM 推断)
  - name: "BGP状态异常"
    description: "检查BGP邻居状态"
    severity: critical
  
  # 硬编码检查 (精确控制)
  - name: "CPU使用率"
    table: device           # 指定表 = 跳过 LLM
    method: get
    threshold:
      metric: "cpuUsage"
      operator: "<"
      value: 80
    severity: warning
```

#### 5.3.10 交付物

- [ ] `src/olav/modes/inspection/` 目录结构
- [ ] `loader.py`: YAML 配置加载
- [ ] `compiler.py`: IntentCompiler (LLM 驱动意图编译 + 多数据源回退)
- [ ] `executor.py`: Map-Reduce 并行执行
- [ ] `validator.py`: ThresholdValidator
- [ ] `config/prompts/inspection/intent_compiler.yaml`
- [ ] `config/prompts/inspection/show_command_generator.yaml` 🆕
- [ ] `config/inspections/` 智能配置示例
- [ ] 单元测试: `tests/unit/modes/test_inspection.py`

---

## 6. 共享组件

以下组件在三个模式间 100% 共享：

| 组件 | 新路径 | 来源 |
|------|--------|------|
| `ToolRegistry` | `shared/tools/registry.py` | `tools/base.py` |
| `suzieq_*` | `shared/tools/suzieq.py` | `tools/suzieq_*.py` |
| `netbox_*` | `shared/tools/netbox.py` | `tools/netbox_*.py` |
| `nornir_*` | `shared/tools/nornir.py` | `tools/nornir_*.py` |
| `opensearch_*` | `shared/tools/opensearch.py` | `tools/opensearch_*.py` |
| `HITLMiddleware` | `shared/hitl/middleware.py` | 新建 |
| `Confidence` | `shared/confidence.py` | 新建 |
| `BackendProtocol` | `shared/protocols.py` | `execution/backends/protocol.py` |

---

## 7. 配置重构

### 7.1 config/ 目录分析

| 路径 | 当前状态 | 重构建议 |
|------|----------|----------|
| `config/prompts/` | 按 agents/strategies/workflows 组织 | 按 modes/ 重组 |
| `config/inspections/` | ✅ 已有 4 个巡检配置 | 完善 YAML schema |
| `config/settings.py` | ✅ 已有 InspectionConfig | 添加 StandardConfig/ExpertConfig |
| `config/rules/` | 存在 | 保留，inspection 使用 |

**现有 config/inspections/ 内容**:
- `bgp_peer_audit.yaml` - BGP 邻居审计
- `daily_core_check.yaml` - 日常核心检查
- `intent_based_audit.yaml` - 意图驱动审计
- `interface_health.yaml` - 接口健康检查

**现有 config/settings.py 结构** (329 行):
- ✅ `Paths` - 路径配置
- ✅ `LLMConfig` - LLM 配置
- ✅ `EmbeddingConfig` - Embedding 配置
- ✅ `InfrastructureConfig` - 基础设施配置
- ✅ `AgentConfig` - Agent 通用配置
- ✅ `InspectionConfig` - 巡检配置 (已存在!)
- ✅ `ToolConfig` - 工具配置
- ⚠️ 缺少 `StandardModeConfig` 和 `ExpertModeConfig`

### 7.2 Prompts 重组

```
config/prompts/
├── shared/                         # 共享 prompts
│   ├── tool_descriptions/          # 工具描述
│   └── hitl/                       # HITL 审批
│
├── standard/                       # Standard Mode
│   ├── classifier.yaml             # UnifiedClassifier prompt
│   └── answer_formatting.yaml      # 答案格式化
│
├── expert/                         # Expert Mode (两阶段架构)
│   ├── supervisor.yaml             # 调度决策 prompt
│   ├── quick_analyzer.yaml         # Phase 1: SuzieQ 快速分析
│   ├── deep_analyzer.yaml          # Phase 2: CLI/NETCONF 实时验证
│   └── report.yaml                 # 报告生成
│
└── inspection/                     # Inspection Mode
    └── summary.yaml                # 巡检总结
```

### 7.3 Settings 拆分

**现有结构** (`config/settings.py`):
```python
# 已存在的配置类
class InspectionConfig:       # ✅ 巡检配置 (已完善)
    ENABLED = False
    SCHEDULE_TIME = "09:00"
    DEFAULT_PROFILE = "daily_core_check"
    PARALLEL_DEVICES = 10
    ...
```

**需要添加**:
```python
# config/settings.py 新增

class StandardModeConfig:
    """Standard mode specific settings."""
    CONFIDENCE_THRESHOLD: float = 0.7      # FastPath 置信度阈值
    ENABLE_MEMORY_RAG: bool = True         # 启用 Episodic Memory
    MAX_RETRIES: int = 2                   # 工具重试次数
    CACHE_TTL_SECONDS: int = 300           # 缓存 TTL

class ExpertModeConfig:
    """Expert mode - 两阶段诊断配置"""
    MAX_ROUNDS: int = 5                    # 最大诊断轮次
    KB_SEARCH_TOP_K: int = 5               # KB 搜索返回数量
    SYSLOG_LOOKBACK_HOURS: int = 24        # Syslog 回溯时间
    
    # Phase 1: Quick Analyzer (SuzieQ)
    PHASE1_MAX_ITERATIONS: int = 5         # Phase 1 最大 ReAct 迭代
    PHASE1_CONFIDENCE_CAP: float = 0.60    # Phase 1 置信度上限 (历史数据)
    
    # Phase 2: Device Inspector (CLI/NETCONF)
    PHASE2_CONFIDENCE: float = 0.95        # Phase 2 置信度 (实时数据)
    PHASE2_TRIGGER_THRESHOLD: float = 0.80 # 低于此置信度触发 Phase 2
    PARALLEL_INSPECTORS: int = 4           # 并行检查设备数
    
    # 配置策略类问题关键词 (触发 Phase 2)
    CONFIG_POLICY_KEYWORDS: list = [
        "route-map", "prefix-list", "ACL", 
        "policy", "STP", "filter"
    ]
```

**环境变量** (`src/olav/core/settings.py`):
```python
# 已存在，结构良好 (251 行)
class EnvSettings(BaseSettings):
    # ... 现有配置 ...
    
    # 需要添加:
    default_mode: str = "standard"         # 默认模式
    standard_confidence: float = 0.7       # Standard 置信度
    expert_max_iterations: int = 5         # Expert 最大迭代
    expert_kb_top_k: int = 5               # KB 搜索数量
```

---

## 8. 测试重构

### 8.1 当前测试分析

**当前测试规模**:
- 单元测试: 37 个文件
- E2E 测试: 14 个文件
- 集成测试: 存在
- 手动测试: 存在
- 性能测试: 存在

**需要归档/删除的测试**:
| 文件 | 原因 |
|------|------|
| `test_selector.py` | 测试已删除的 `selector.py` |
| `test_multi_agent.py` | 测试从未使用的多代理架构 |

**需要按模式重组的测试**:
| 现有文件 | 目标位置 |
|----------|----------|
| `test_fast_path_fallback.py` | `modes/test_standard.py` |
| `test_strategies.py` | `modes/test_standard.py` |
| `test_strategy_executor.py` | `modes/test_standard.py` |
| `test_supervisor_driven.py` | `modes/test_expert.py` |
| `test_deep_dive_workflow.py` | `modes/test_expert.py` |
| `test_inspection_workflow.py` | `modes/test_inspection.py` |
| `test_batch_strategy.py` | `modes/test_inspection.py` |

### 8.2 新测试结构

```
tests/
├── conftest.py                     # 共享 fixtures
│
├── unit/
│   ├── modes/                      # 🆕 模式测试
│   │   ├── test_standard.py        # Standard mode 单元测试
│   │   ├── test_expert.py          # Expert mode 单元测试
│   │   └── test_inspection.py      # Inspection mode 单元测试
│   ├── shared/                     # 🆕 共享组件测试
│   │   ├── test_tools.py           # 共享工具测试
│   │   ├── test_hitl.py            # HITL 中间件测试
│   │   └── test_confidence.py      # 置信度计算测试
│   ├── archive/                    # 🆕 归档旧测试
│   │   ├── test_selector.py        # 已删除的 selector
│   │   └── test_multi_agent.py     # 未使用的多代理
│   └── ...                         # 保留其他测试
│
├── e2e/
│   ├── test_standard_mode.py       # Standard mode E2E (重命名)
│   ├── test_expert_mode.py         # Expert mode E2E (新增)
│   └── test_inspection_mode.py     # Inspection mode E2E (新增)
│
└── integration/
    ├── test_shared_tools.py        # 共享工具集成测试
    └── test_cross_mode.py          # 跨模式集成测试
```

**测试迁移矩阵**:

| 现有测试 | 归属模式 | 操作 |
|----------|----------|------|
| `test_fast_path_fallback.py` | Standard | 移动到 `modes/test_standard.py` |
| `test_strategies.py` | Standard | 移动到 `modes/test_standard.py` |
| `test_supervisor_driven.py` | Expert | 移动到 `modes/test_expert.py` |
| `test_deep_dive_workflow.py` | Expert | 移动到 `modes/test_expert.py` |
| `test_inspection_workflow.py` | Inspection | 移动到 `modes/test_inspection.py` |
| `test_batch_strategy.py` | Inspection | 移动到 `modes/test_inspection.py` |
| `test_selector.py` | ❌ 死测试 | 归档到 `archive/` |
| `test_multi_agent.py` | ❌ 死测试 | 归档到 `archive/` |
| `test_suzieq_*.py` | Shared | 移动到 `shared/test_tools.py` |
| `test_cli_tool.py` | Shared | 移动到 `shared/test_tools.py` |
| `test_auth.py` | Core | 保持不变 |
| `test_cache.py` | Core | 保持不变 |

### 8.3 测试覆盖目标

| 模式 | 单元测试 | E2E 测试 | 覆盖率目标 |
|------|----------|----------|------------|
| Standard | 工具调用, 分类器, HITL | 完整查询流程 | 80% |
| Expert | 各组件独立 | 诊断流程 | 70% |
| Inspection | YAML 加载, 阈值校验 | 完整巡检流程 | 80% |
| Shared | 所有共享组件 | - | 90% |

---

## 9. 环境变量

### 9.1 当前 .env 分析

**现有结构** (`src/olav/core/settings.py` - 251 行):
- ✅ LLM 配置 (provider, api_key, base_url, model_name)
- ✅ Embedding 配置
- ✅ Vision 配置
- ✅ PostgreSQL/OpenSearch/Redis 配置
- ✅ NetBox 配置
- ✅ Device 凭证
- ✅ API Server 配置
- ✅ CORS 配置
- ✅ Feature Flags (`expert_mode`, `use_dynamic_router`)
- ✅ LangSmith 配置
- ✅ Collector 配置
- ✅ Agentic RAG 配置

**结论**: 环境变量结构良好，只需添加模式相关变量。

### 9.2 新增环境变量

```bash
# .env 新增

# Mode Settings (可选，有默认值)
OLAV_DEFAULT_MODE=standard          # 默认模式: standard/expert
OLAV_STANDARD_CONFIDENCE=0.7        # Standard 置信度阈值
OLAV_EXPERT_MAX_ITERATIONS=5        # Expert 最大迭代次数
OLAV_EXPERT_KB_TOP_K=5              # KB 搜索返回数量
OLAV_EXPERT_SYSLOG_LOOKBACK=24      # Syslog 回溯时间 (小时)

# Inspection Mode (已在 config/settings.py 中配置)
# OLAV_INSPECTION_PARALLEL=10       # 并发数 (使用 InspectionConfig)
# OLAV_INSPECTION_REPORT_FORMAT=markdown
```

---

## 10. E2E 测试计划

### 10.1 现有测试分析

当前 `tests/e2e/` 已有以下测试文件：

| 文件 | 覆盖范围 | 状态 |
|------|----------|------|
| `test_cli_capabilities.py` | CLI 调用 + 5 类测试 | ✅ 可复用 |
| `test_agent_capabilities.py` | API 调用 + 7 类测试 | ✅ 可复用 |
| `test_standard_mode_tools.py` | Standard Mode 工具链 | ⚠️ 需完善 |
| `test_expert_mode_fault_injection.py` | Expert Mode 故障注入 | ⚠️ 需完善 |
| `test_cache.py` | 测试缓存 + 性能日志 | ✅ 已实现 |

### 10.2 测试分层架构

```
tests/
├── unit/                           # 单元测试 (无 LLM)
│   ├── modes/
│   │   ├── test_standard_classifier.py
│   │   ├── test_expert_supervisor.py
│   │   └── test_inspection_compiler.py
│   └── shared/
│       ├── test_hitl_middleware.py
│       └── test_confidence.py
│
├── integration/                    # 集成测试 (Mock LLM)
│   ├── test_standard_workflow.py
│   ├── test_expert_workflow.py
│   └── test_inspection_workflow.py
│
└── e2e/                           # 端到端测试 (Real LLM)
    ├── test_standard_mode.py      # Phase 1 里程碑
    ├── test_expert_mode.py        # Phase 2 里程碑
    ├── test_inspection_mode.py    # Phase 3 里程碑
    ├── test_debug_mode.py         # Debug 输出验证
    └── fixtures/
        ├── sample_queries.yaml    # 标准测试查询
        └── expected_outputs.yaml  # 期望输出
```

### 10.3 Phase 1 里程碑测试 (Standard Mode)

```python
# tests/e2e/test_standard_mode.py
class TestStandardModeE2E:
    """Standard Mode 端到端测试 - Phase 1 里程碑"""
    
    # === 查询类 (Read-Only) ===
    
    @pytest.mark.parametrize("query,expected_tool,expected_keywords", [
        # SuzieQ 查询
        ("查询 R1 的 BGP 状态", "suzieq_query", ["BGP", "state"]),
        ("show interfaces on R1", "suzieq_query", ["interface"]),
        ("summarize all devices", "suzieq_query", ["device"]),
        ("查询所有设备的 OSPF 邻居", "suzieq_query", ["OSPF", "neighbor"]),
        
        # NetBox 查询
        ("列出 NetBox 中所有设备", "netbox_api_call", ["device"]),
        ("查询 R1 在 NetBox 中的信息", "netbox_api_call", ["R1"]),
        
        # Schema 发现
        ("有哪些 SuzieQ 表可用？", "suzieq_schema_search", ["table"]),
        ("BGP 表有哪些字段？", "suzieq_schema_search", ["field"]),
    ])
    def test_standard_query(self, query, expected_tool, expected_keywords):
        """验证 Standard Mode 查询正确分类和执行"""
        result = run_with_debug(query, mode="standard")
        
        # 验证工具选择
        assert result.tool_called == expected_tool
        
        # 验证输出包含关键词
        for kw in expected_keywords:
            assert kw.lower() in result.output.lower()
        
        # 验证性能
        assert result.duration_ms < 30000  # 30s 超时
    
    # === 写入类 (HITL) ===
    
    @pytest.mark.hitl
    @pytest.mark.parametrize("query,expected_tool", [
        ("配置 R1 接口 Loopback100 IP 为 10.0.0.1", "netconf_edit"),
        ("在 NetBox 中创建新设备 R99", "netbox_api_call"),
        ("更新 R1 在 NetBox 中的描述", "netbox_api_call"),
    ])
    def test_standard_write_requires_hitl(self, query, expected_tool):
        """验证写操作触发 HITL"""
        result = run_with_debug(query, mode="standard", yolo=False)
        
        # 验证 HITL 触发
        assert result.hitl_triggered
        assert result.approval_required
        
        # 验证工具选择正确
        assert result.tool_called == expected_tool
    
    # === 边界条件 ===
    
    def test_standard_unknown_device(self):
        """未知设备应优雅处理"""
        result = run_with_debug("查询 NONEXISTENT 的状态", mode="standard")
        assert result.success
        assert "no data" in result.output.lower() or "not found" in result.output.lower()
    
    def test_standard_chinese_english_mixed(self):
        """中英文混合查询"""
        result = run_with_debug("check R1 的 BGP neighbors", mode="standard")
        assert result.success
        assert "BGP" in result.output
```

### 10.4 Phase 2 里程碑测试 (Expert Mode)

```python
# tests/e2e/test_expert_mode.py
class TestExpertModeE2E:
    """Expert Mode 端到端测试 - Phase 2 里程碑"""
    
    # === 故障诊断 ===
    
    @pytest.mark.slow
    @pytest.mark.parametrize("symptom,expected_checks", [
        # BGP 故障
        (
            "R1 无法与 R2 建立 BGP",
            ["bgp", "interface", "route"]
        ),
        # OSPF 故障
        (
            "R1 的 OSPF 邻居丢失",
            ["ospf", "interface"]
        ),
        # 连通性故障
        (
            "R1 无法 ping R2 的 Loopback",
            ["route", "interface", "ping"]
        ),
    ])
    def test_expert_multi_step_diagnosis(self, symptom, expected_checks):
        """验证 Expert Mode 多步诊断"""
        result = run_with_debug(symptom, mode="expert")
        
        # 验证多步执行
        assert len(result.steps) >= 2, "Expert Mode 应执行多步"
        
        # 验证检查了相关表
        tables_checked = [s["table"] for s in result.steps if "table" in s]
        for check in expected_checks:
            assert any(check in t.lower() for t in tables_checked)
        
        # 验证有根因分析
        assert "root cause" in result.output.lower() or "根因" in result.output
    
    # === KB 引用 ===
    
    @pytest.mark.slow
    def test_expert_uses_kb(self):
        """验证 Expert Mode 引用 Knowledge Base"""
        result = run_with_debug(
            "R1 BGP 状态异常，之前解决过类似问题吗？",
            mode="expert"
        )
        
        # 验证 KB 搜索
        assert result.kb_searched
        if result.kb_hits > 0:
            assert "历史案例" in result.output or "previous" in result.output.lower()
    
    # === 迭代限制 ===
    
    @pytest.mark.slow
    def test_expert_respects_max_iterations(self):
        """验证 Expert Mode 遵守最大迭代限制"""
        result = run_with_debug(
            "分析整个网络的健康状态",  # 复杂查询
            mode="expert"
        )
        
        # 验证迭代次数 <= 配置值
        assert result.iterations <= 5  # OLAV_EXPERT_MAX_ITERATIONS
```

### 10.5 Phase 3 里程碑测试 (Inspection Mode)

```python
# tests/e2e/test_inspection_mode.py
class TestInspectionModeE2E:
    """Inspection Mode 端到端测试 - Phase 3 里程碑"""
    
    # === 智能巡检 ===
    
    @pytest.mark.slow
    def test_inspection_smart_compile(self):
        """验证智能巡检意图编译"""
        # 使用智能配置
        config = {
            "name": "Test Inspection",
            "checks": [
                {
                    "name": "BGP邻居异常",
                    "description": "检查是否有BGP邻居处于非Established状态",
                    "severity": "critical"
                }
            ],
            "targets": {"netbox_filter": "role=core"}
        }
        
        result = run_inspection_with_debug(config)
        
        # 验证 LLM 生成查询计划
        assert result.plans_generated > 0
        assert "bgp" in str(result.generated_plans).lower()
        
        # 验证执行结果
        assert result.success
        assert result.report is not None
    
    # === 并行执行 ===
    
    @pytest.mark.slow
    def test_inspection_parallel_execution(self):
        """验证并行执行性能"""
        result = run_inspection_with_debug("daily-core.yaml")
        
        # 验证并行执行 (多设备同时查询)
        assert result.parallel_tasks > 1
        
        # 验证汇总报告
        assert "summary" in result.report.lower() or "总结" in result.report
    
    # === 阈值验证 ===
    
    def test_inspection_threshold_validation(self):
        """验证阈值检查 (Zero Hallucination)"""
        # 使用硬编码配置 (绕过 LLM)
        config = {
            "name": "Threshold Test",
            "checks": [
                {
                    "name": "CPU Check",
                    "table": "device",
                    "method": "get",
                    "threshold": {
                        "metric": "cpuUsage",
                        "operator": "<",
                        "value": 80
                    }
                }
            ]
        }
        
        result = run_inspection_with_debug(config)
        
        # 验证阈值由 Python 计算 (非 LLM)
        assert result.threshold_checks > 0
        assert not result.llm_threshold_eval  # LLM 不参与阈值判断
```

### 10.6 Debug 模式设计

#### 10.6.1 Debug 输出内容

```python
@dataclass
class DebugOutput:
    """Debug 模式输出结构"""
    
    # 基本信息
    query: str
    mode: str  # standard/expert/inspection
    timestamp: str
    duration_ms: float
    
    # LLM 调用详情
    llm_calls: list[LLMCallDetail]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    
    # 工具调用链
    tool_calls: list[ToolCallDetail]
    
    # 工作流状态
    graph_states: list[GraphStateSnapshot]
    transitions: list[str]  # node1 -> node2
    
    # 流式传输
    stream_chunks: list[StreamChunk]
    stream_latency_ms: float  # 首 chunk 延迟
    
    # 执行时间分解
    time_breakdown: dict[str, float]  # {classify: 100ms, tool: 200ms, ...}


@dataclass
class LLMCallDetail:
    """LLM 调用详情"""
    call_id: str
    model: str
    prompt: str  # 完整 prompt
    response: str  # 完整响应
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float
    temperature: float
    
    # Thinking 模式分析
    thinking_content: str | None  # <think> 内容 (Ollama)
    thinking_tokens: int


@dataclass
class ToolCallDetail:
    """工具调用详情"""
    tool_name: str
    input_args: dict
    output: str
    duration_ms: float
    success: bool
    error: str | None


@dataclass
class GraphStateSnapshot:
    """LangGraph 状态快照"""
    node: str
    state: dict
    timestamp: str
```

#### 10.6.2 Debug CLI 使用

```bash
# 启用 Debug 模式
uv run olav.py query "查询 R1 BGP 状态" --debug

# Debug 输出到文件
uv run olav.py query "查询 R1 BGP 状态" --debug --debug-output debug_output.json

# Debug 仅显示 LLM 调用
uv run olav.py query "查询 R1 BGP 状态" --debug --debug-llm

# Debug 仅显示工具链
uv run olav.py query "查询 R1 BGP 状态" --debug --debug-tools

# Debug 显示 Graph 状态
uv run olav.py query "查询 R1 BGP 状态" --debug --debug-graph
```

#### 10.6.3 Debug 实现

```python
# src/olav/core/debug.py
class DebugContext:
    """Debug 上下文管理器"""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.output = DebugOutput(...)
        self._llm_interceptor: LLMInterceptor | None = None
        self._tool_interceptor: ToolInterceptor | None = None
    
    def __enter__(self):
        if self.enabled:
            # 安装 LLM 拦截器
            self._llm_interceptor = LLMInterceptor(self.output)
            self._llm_interceptor.install()
            
            # 安装工具拦截器
            self._tool_interceptor = ToolInterceptor(self.output)
            self._tool_interceptor.install()
        
        return self
    
    def __exit__(self, *args):
        if self.enabled:
            self._llm_interceptor.uninstall()
            self._tool_interceptor.uninstall()


class LLMInterceptor:
    """LLM 调用拦截器 - 记录完整 prompt/response"""
    
    def install(self):
        # Monkey-patch LangChain ChatModel
        original_invoke = ChatOpenAI.invoke
        
        def intercepted_invoke(self, messages, **kwargs):
            start = time.perf_counter()
            response = original_invoke(messages, **kwargs)
            duration = (time.perf_counter() - start) * 1000
            
            # 记录调用详情
            self.debug_output.llm_calls.append(LLMCallDetail(
                prompt=str(messages),
                response=str(response),
                duration_ms=duration,
                ...
            ))
            
            return response
        
        ChatOpenAI.invoke = intercepted_invoke
```

#### 10.6.4 Debug 输出示例

```json
{
  "query": "查询 R1 BGP 状态",
  "mode": "standard",
  "timestamp": "2025-12-06T10:30:00",
  "duration_ms": 2345.67,
  
  "llm_calls": [
    {
      "call_id": "llm-001",
      "model": "qwen2.5:32b",
      "prompt": "你是网络运维专家...\n\n用户: 查询 R1 BGP 状态",
      "response": "```json\n{\"tool\": \"suzieq_query\", \"params\": {...}}\n```",
      "prompt_tokens": 256,
      "completion_tokens": 45,
      "duration_ms": 1200.5,
      "thinking_content": "用户想查询BGP状态，应该使用suzieq_query工具...",
      "thinking_tokens": 30
    }
  ],
  
  "tool_calls": [
    {
      "tool_name": "suzieq_query",
      "input_args": {"table": "bgp", "hostname": "R1", "method": "get"},
      "output": "[{\"hostname\": \"R1\", \"peer\": \"192.168.1.2\", \"state\": \"Established\"}]",
      "duration_ms": 450.2,
      "success": true
    }
  ],
  
  "graph_states": [
    {"node": "classify", "state": {"intent": "query"}, "timestamp": "..."},
    {"node": "execute_tool", "state": {"tool": "suzieq_query"}, "timestamp": "..."},
    {"node": "format_response", "state": {"output": "..."}, "timestamp": "..."}
  ],
  
  "time_breakdown": {
    "classify": 1200.5,
    "tool_execution": 450.2,
    "response_format": 694.97
  },
  
  "stream_latency_ms": 150.3,
  "total_prompt_tokens": 256,
  "total_completion_tokens": 45
}
```

### 10.7 测试执行策略

#### 10.7.1 每阶段里程碑验证

```bash
# Phase 1 完成后
uv run pytest tests/e2e/test_standard_mode.py -v --html=reports/phase1.html

# Phase 2 完成后
uv run pytest tests/e2e/test_expert_mode.py -v --html=reports/phase2.html

# Phase 3 完成后
uv run pytest tests/e2e/test_inspection_mode.py -v --html=reports/phase3.html

# 全量回归
uv run pytest tests/e2e/ -v --html=reports/full_regression.html
```

#### 10.7.2 Debug 模式用于优化

```bash
# 1. 运行测试收集 Debug 输出
OLAV_DEBUG=true uv run pytest tests/e2e/test_standard_mode.py::test_standard_query -v

# 2. 分析 LLM Token 消耗
python scripts/analyze_debug_output.py tests/e2e/logs/debug_*.json --metric tokens

# 3. 分析延迟瓶颈
python scripts/analyze_debug_output.py tests/e2e/logs/debug_*.json --metric latency

# 4. 分析 Thinking 内容 (Ollama)
python scripts/analyze_debug_output.py tests/e2e/logs/debug_*.json --metric thinking
```

#### 10.7.3 Prompt 优化循环

```
┌─────────────────────────────────────────────────────────┐
│  1. 运行测试 + Debug                                    │
│  OLAV_DEBUG=true uv run pytest test_xxx.py             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  2. 分析 Debug 输出                                     │
│  • Token 消耗过高？→ 精简 Prompt                        │
│  • Thinking 冗余？→ 添加 /no_think                      │
│  • 工具选择错误？→ 调整 Tool Description                │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  3. 修改 Prompt (config/prompts/)                       │
│  • 精简 system prompt                                   │
│  • 优化 tool description                                │
│  • 添加 few-shot examples                               │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  4. 重新运行测试验证                                    │
│  • Token 减少？✓                                        │
│  • 准确率保持？✓                                        │
│  • 延迟降低？✓                                          │
└─────────────────────────────────────────────────────────┘
    │
    └──────────────────────────────────────────────────────┐
                                                           │
    ┌──────────────────────────────────────────────────────┘
    │
    ▼
  重复直到满意
```

### 10.8 测试交付物

| 阶段 | 测试文件 | 用例数 | 验证内容 |
|------|----------|--------|----------|
| Phase 1 | `test_standard_mode.py` | 15+ | 查询、写入HITL、边界条件 |
| Phase 2 | `test_expert_mode.py` | 10+ | 多步诊断、KB引用、迭代限制 |
| Phase 3 | `test_inspection_mode.py` | 10+ | 智能编译、并行执行、阈值验证 |
| Debug | `test_debug_mode.py` | 5+ | Debug 输出格式、拦截器功能 |

---

## 11. 时间估算

| 阶段 | 工作量 | 预计时间 |
|------|--------|----------|
| Phase 1: Standard Mode | 中 | 2-3 天 |
| Phase 2: Expert Mode | 大 | 3-4 天 |
| Phase 3: Inspection Mode | 中 | 2-3 天 |
| 共享组件重构 | 小 | 1 天 |
| 配置/Prompt 重组 | 小 | 1 天 |
| 测试编写 | 中 | 2-3 天 |
| Debug 模式实现 | 中 | 1-2 天 |
| 集成与调试 | 中 | 2 天 |

**总计**: 约 15-19 天 (3-4 周)

---

## 12. 回滚计划

每个 Phase 独立可回滚：

1. **Phase 1 回滚**: 恢复 `strategies/fast_path.py` 入口
2. **Phase 2 回滚**: 恢复 `workflows/supervisor_driven.py` 入口
3. **Phase 3 回滚**: 恢复 `strategies/batch_path.py` 入口

所有变更都应该是渐进式的，确保每个阶段都可以独立回滚。

---

## 13. 下一步行动

1. ✅ 创建分支: `refactor/modes-isolation`
2. ✅ 归档旧文档
3. ⬜ 删除死代码 (multi-agent 组件)
4. ⬜ 创建 `src/olav/modes/` 目录结构
5. ⬜ Phase 1: Standard Mode 重构
6. ⬜ Phase 2: Expert Mode 重构
7. ⬜ Phase 3: Inspection Mode 重构
8. ⬜ 实现 Debug 模式
9. ⬜ 测试编写与集成

---

**文档版本**: 2.1  
**维护者**: AI Assistant  
**最后更新**: 2025-12-06
