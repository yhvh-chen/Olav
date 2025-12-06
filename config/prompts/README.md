# OLAV Prompts 目录说明

## Standard 模式 (-S) Prompt 使用情况

Standard 模式使用 `fast_path` 策略，**跳过 LLM 路由**，直接执行单工具调用。

### 调用链路

```
用户查询 (CLI: olav -S "查询...")
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  RootAgentOrchestrator.route()                                  │
│  ├─ NetworkRelevanceGuard.check()                               │
│  │     └─ agents/network_relevance_guard.yaml ✅                │
│  │                                                              │
│  ├─ classify_intent() [关键字匹配 + DynamicRouter，无 LLM 路由]  │
│  │                                                              │
│  └─ _execute_standard_mode()                                    │
│       └─ execute_with_mode(mode="standard")                     │
│            └─ FastPathStrategy.execute()                        │
│                 ├─ _extract_parameters()                        │
│                 │    └─ strategies/fast_path/parameter_extraction.yaml ✅
│                 │                                               │
│                 └─ _format_answer()                             │
│                      └─ strategies/fast_path/answer_formatting.yaml ✅
└─────────────────────────────────────────────────────────────────┘
```

### Standard 模式使用的 Prompts（必须有 `/no_think`）

| Prompt 文件 | 使用位置 | 说明 |
|------------|----------|------|
| `agents/network_relevance_guard.yaml` | `NetworkRelevanceGuard` | 判断查询是否与网络相关 |
| `strategies/fast_path/parameter_extraction.yaml` | `FastPathStrategy._extract_parameters()` | 从用户查询提取工具参数 |
| `strategies/fast_path/answer_formatting.yaml` | `FastPathStrategy._format_answer()` | 格式化工具输出为用户回答 |

### Fallback 路径使用的 Prompts（当 fast_path 失败时）

| Prompt 文件 | 使用位置 | 说明 |
|------------|----------|------|
| `workflows/query_diagnostic/macro_analysis.yaml` | `QueryDiagnosticWorkflow` | SuzieQ 宏观分析 |
| `workflows/query_diagnostic/micro_diagnosis.yaml` | `QueryDiagnosticWorkflow` | NETCONF/CLI 微观诊断 |

---

## `/no_think` 标记说明

Ollama 的 qwen3/deepseek-r1 等思考模型在 prompt 中使用 `/no_think` 标记来禁用扩展思考模式。

### 格式要求

- **开头**: 在 template 的第一行添加 `/no_think`
- **结尾**: 在 template 的最后一行添加 `/no_think`

### 示例

```yaml
_type: prompt
input_variables:
  - user_query
template: |
  /no_think
  Your prompt content here...
  
  {user_query}
  
  Output JSON: {...}
  /no_think
```

### 效果

使用 `/no_think` 后，Ollama 返回的响应中：
- `content` 字段只包含干净的回答
- `thinking` 字段（如果有）包含分离的思考过程

---

## 目录结构

```
config/prompts/
├── agents/                        # Agent 级别 prompts
│   ├── network_relevance_guard.yaml  ✅ Standard 模式使用
│   ├── intent_classifier/            # Intent 分类器 (API 模式)
│   └── plan_modification.yaml        # 计划修改 (Expert 模式)
│
├── strategies/                    # 策略层 prompts
│   ├── fast_path/                    ✅ Standard 模式使用
│   │   ├── answer_formatting.yaml
│   │   └── parameter_extraction.yaml
│   ├── deep_path/                    # Expert 模式
│   └── batch_path/                   # Inspection 模式
│
├── workflows/                     # Workflow 级别 prompts
│   ├── query_diagnostic/             # 查询诊断 workflow
│   │   ├── macro_analysis.yaml       (Fallback)
│   │   └── micro_diagnosis.yaml      (Fallback)
│   ├── device_execution/             # 设备执行 workflow
│   ├── netbox_management/            # NetBox 管理 workflow
│   ├── deep_dive/                    # 深度分析 workflow
│   └── inspection/                   # 巡检 workflow
│
├── core/                          # 核心 prompts
│   └── unified_classification.yaml   # 统一分类器 (UnifiedClassifier)
│
├── tools/                         # 工具描述 prompts
│   ├── suzieq_capability_guide.yaml
│   ├── netconf_capability_guide.yaml
│   └── ...
│
├── rag/                           # RAG 相关 prompts
├── sync/                          # 同步相关 prompts
├── overrides/                     # 覆盖层 (优先加载)
└── _defaults/                     # 默认层 (新 prompt 系统)
```

---

## 已删除的幽灵代码

### Prompt 文件

| 已删除文件 | 原因 |
|-----------|------|
| `workflows/orchestrator/intent_classification.yaml` | Standard 模式使用关键字匹配，不调用 LLM 分类 |
| `core/strategy_selection.yaml` | Standard 模式直接映射 mode→strategy，跳过 StrategySelector |
| `agents/intent_router.yaml` | DynamicOrchestrator 已有异常处理和 fallback |

### Python 代码

| 已删除代码 | 位置 | 原因 |
|-----------|------|------|
| `_execute_with_strategy()` | `root_agent_orchestrator.py` | 死代码，从未被调用 |
| `_llm_based_selection()` | `selector.py` | LLM fallback 已删除，改为纯规则匹配 |
| `execute_with_strategy_selection()` | `executor.py` | 依赖已删除的 LLM fallback |

---

## 模式对比

| 模式 | CLI 标志 | 策略 | LLM 调用次数 | Prompt 使用 |
|------|----------|------|-------------|-------------|
| Standard | `-S` (默认) | fast_path | 2-3 次 | 本 README 中的 3 个 |
| Expert | `-E` | SupervisorDrivenWorkflow | 多次 | workflows/deep_dive/* |
| Inspection | `inspect` 子命令 | batch_path | 多次 | strategies/batch_path/* |

---

## 设计原则

1. **Fail Fast**: 找不到 prompt 文件直接报错，而不是静默 fallback
2. **明确边界**: Standard 模式只用 3 个 prompt，不留冗余 fallback
3. **删除而非包装**: 不需要的代码直接删除，不用 try-except 掩盖
