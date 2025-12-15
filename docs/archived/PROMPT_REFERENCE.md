# OLAV Prompt Reference

This document describes all available prompts and how to customize them.

## Prompt Structure

```
config/prompts/
├── _defaults/           # Built-in prompts (English)
│   ├── answer_formatting.yaml
│   ├── unified_classification.yaml
│   ├── network_guard.yaml
│   ├── intent_router.yaml
│   ├── parameter_extraction.yaml
│   ├── diagnosis.yaml
│   ├── config_execution.yaml
│   ├── strategy_selection.yaml
│   └── netbox_comparison.yaml
└── overrides/           # User customizations
    └── README.md
```

## How to Customize

### Method 1: Override File (Recommended)

Create a YAML file in `config/prompts/overrides/` with the same name as the prompt to override:

```bash
# Copy default as starting point
cp config/prompts/_defaults/answer_formatting.yaml config/prompts/overrides/

# Edit the copy
vim config/prompts/overrides/answer_formatting.yaml
```

### Method 2: Inline Override in olav.yaml

Add to `config/olav.yaml`:

```yaml
prompt_overrides:
  answer_formatting: |
    Your custom prompt here...
```

## Prompt Reference

### answer_formatting.yaml

**Purpose**: Formats tool output into human-readable responses

**Used by**: FastPath strategy

**Variables**:
- `user_query`: The user's original question
- `data_json`: JSON data from tool execution

**Thinking**: Disabled by default (fast_path)

---

### unified_classification.yaml

**Purpose**: Classifies user intent and selects the appropriate tool

**Used by**: UnifiedClassifier

**Variables**: None (query passed as message)

**Output**: JSON with intent_category, tool, parameters

---

### network_guard.yaml

**Purpose**: Filters out non-network-related queries

**Used by**: NetworkRelevanceGuard

**Variables**: None (query passed as message)

**Output**: JSON with is_relevant, category, reason

---

### intent_router.yaml

**Purpose**: Routes queries to the most appropriate workflow

**Used by**: DynamicIntentRouter

**Variables**:
- `query`: User's query
- `candidates_desc`: Description of candidate workflows

---

### parameter_extraction.yaml

**Purpose**: Extracts structured parameters from natural language

**Used by**: FastPath strategy

**Variables**:
- `user_query`: User's query
- `schema_context`: Available schema information
- `tool_guides`: Capability guides for tools

---

### diagnosis.yaml

**Purpose**: Guides multi-step network troubleshooting

**Used by**: DeepPath strategy, DeepDive workflow

**Variables**:
- `user_query`: Problem description
- `findings`: Previous diagnostic findings
- `available_tools`: Available tools list

**Thinking**: Enabled by default (deep_path)

---

### config_execution.yaml

**Purpose**: Plans and executes configuration changes

**Used by**: DeviceExecution workflow

**Variables**:
- `user_request`: Configuration request
- `device_info`: Target device information
- `current_config`: Current configuration

**HITL**: Always required

---

### strategy_selection.yaml

**Purpose**: Selects execution strategy (fast/deep/batch)

**Used by**: StrategySelector

**Variables**:
- `user_query`: User's query
- `context`: Additional context

---

### netbox_comparison.yaml

**Purpose**: Compares CMDB with network state

**Used by**: Sync module

**Variables**:
- `netbox_data`: Data from NetBox
- `network_data`: Data from devices
- `sync_rules`: Comparison rules

---

## Thinking Mode Control

Thinking mode (extended reasoning) can be controlled:

### Global Setting (olav.yaml)
```yaml
thinking:
  enabled: false  # Global default
  strategies:
    fast_path: false  # Always concise
    deep_path: true   # Allow thinking
```

### Per-Prompt Setting (_meta)
```yaml
_meta:
  supports_thinking: true  # Prompt can use thinking
```

When `thinking.enabled=false` for a strategy, prompts automatically get `/nothink` prefix for supported models (qwen3, etc.).

---

## Language Support

All prompts are in English by default. The response language is controlled by:

```yaml
# olav.yaml
answer:
  language: en  # en | zh-CN
```

This variable is passed to prompts as `{language}` for response localization.
