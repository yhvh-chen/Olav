# OLAV Configuration Refactoring Plan

## Overview

This document outlines the plan to refactor OLAV's configuration system for better user experience, easier model switching, and simplified prompt management.

## Goals

1. **User-Friendly Configuration**: Single YAML file for common settings
2. **Easy Model Switching**: Centralized LLM/Embedding configuration with presets
3. **Thinking Mode Control**: Global and per-strategy thinking toggle
4. **English Prompts**: All prompts in English for broader compatibility
5. **Docker-Friendly**: Minimal volume mounts needed

---

## Current Problems

### 1. Scattered Configuration
- `.env` - secrets and endpoints
- `config/settings.py` - Python constants
- `src/olav/core/settings.py` - EnvSettings class
- `config/rules/*.yaml` - HITL and sync rules

### 2. Complex Prompt Structure
- 40+ YAML files across 8 directories
- 16 unused prompt files
- 3 missing prompt files (code references non-existent files)
- Directory structure follows code modules, not user mental model

### 3. Model Configuration Buried in Code
- LLM settings spread across multiple files
- No easy way to switch between OpenAI/Ollama/Azure
- Thinking mode (`reasoning` parameter) inconsistently applied

---

## Proposed Architecture

### File Structure

```
config/
├── olav.yaml                 # Main configuration (user-facing)
├── .env                      # Secrets only (API keys, passwords)
├── prompts/                  # Prompt templates (English)
│   ├── _defaults/            # Built-in defaults (read-only reference)
│   │   ├── answer_formatting.yaml
│   │   ├── intent_classification.yaml
│   │   ├── tool_selection.yaml
│   │   └── ...
│   └── overrides/            # User customizations (optional)
│       └── .gitkeep
├── inspections/              # Inspection profiles
│   ├── bgp_peer_audit.yaml
│   ├── daily_core_check.yaml
│   └── interface_health.yaml
└── rules/                    # Business rules
    └── sync_rules.yaml
```

### Docker Volume Mounts

```yaml
# docker-compose.yml
services:
  olav-server:
    volumes:
      - ./config/olav.yaml:/app/config/olav.yaml:ro
      - ./.env:/app/.env:ro
      # Optional: for prompt customization
      - ./config/prompts/overrides:/app/config/prompts/overrides:ro
```

---

## Main Configuration: `olav.yaml`

```yaml
# OLAV Configuration
# Changes take effect on restart (hot-reload planned for future)

# =============================================================================
# Model Configuration
# =============================================================================
models:
  # Preset configurations for quick switching
  # Options: openrouter, ollama-local, azure, openai-direct
  preset: ollama-local
  
  # Or customize individual settings:
  # llm:
  #   provider: ollama          # openai | ollama | azure_openai
  #   model: qwen3:30b
  #   base_url: http://localhost:11434
  #   temperature: 0.2
  #   max_tokens: 16000
  #
  # embedding:
  #   provider: ollama
  #   model: nomic-embed-text:latest
  #   base_url: http://localhost:11434

# =============================================================================
# Thinking Mode (Reasoning)
# =============================================================================
# Controls extended thinking for models that support it (qwen3, deepseek-r1, etc.)
thinking:
  # Global default
  enabled: false
  
  # Per-strategy overrides
  strategies:
    fast_path: false      # Simple queries - always concise
    deep_path: true       # Complex diagnosis - allow thinking
    batch_path: false     # Batch operations - concise

# =============================================================================
# Answer Style
# =============================================================================
answer:
  style: concise          # concise | detailed | technical
  language: en            # en | zh-CN (affects system prompts)
  format: auto            # auto | table | prose | json
  include_raw_data: false # Include raw JSON in responses

# =============================================================================
# Query Behavior
# =============================================================================
query:
  default_time_range: 24h
  max_results: 100
  prefer_summary: true    # Use summarize() over get() when possible

# =============================================================================
# Diagnosis (Deep Dive / Expert Mode)
# =============================================================================
diagnosis:
  max_iterations: 10
  confidence_threshold: 0.8
  methodology: funnel     # funnel (macro→micro) | parallel | layer-by-layer

# =============================================================================
# Safety & HITL
# =============================================================================
safety:
  # Operations requiring human approval
  require_approval:
    - config_change
    - device_restart
    - interface_shutdown
    - delete_operation
  
  # Operations auto-approved
  auto_approve:
    - show_command
    - read_query
    - status_check

# =============================================================================
# Feature Flags
# =============================================================================
features:
  agentic_rag: true           # Episodic memory for query optimization
  dynamic_router: true        # Semantic intent routing
  schema_aware_tools: true    # SuzieQ/OpenConfig schema discovery

# =============================================================================
# Advanced: Prompt Overrides
# =============================================================================
# Override specific prompts without modifying defaults
# Place custom YAML files in config/prompts/overrides/
prompt_overrides:
  # Example: override answer formatting
  # fast_path/answer_formatting: |
  #   You are a network operations expert...
```

---

## Model Presets

```yaml
# Built-in presets (in code, not config file)

presets:
  ollama-local:
    llm:
      provider: ollama
      model: qwen3:30b
      base_url: http://localhost:11434
    embedding:
      provider: ollama
      model: nomic-embed-text:latest
      base_url: http://localhost:11434
  
  openrouter:
    llm:
      provider: openai
      model: x-ai/grok-4.1-fast
      base_url: https://openrouter.ai/api/v1
    embedding:
      provider: openai
      model: text-embedding-3-small
      base_url: https://api.openai.com/v1
  
  openai-direct:
    llm:
      provider: openai
      model: gpt-4-turbo
      base_url: https://api.openai.com/v1
    embedding:
      provider: openai
      model: text-embedding-3-small
  
  azure:
    llm:
      provider: azure_openai
      model: gpt-4
      # base_url from AZURE_OPENAI_ENDPOINT env var
    embedding:
      provider: azure_openai
      model: text-embedding-ada-002
```

---

## Secrets: `.env`

Simplified to contain ONLY secrets:

```bash
# .env - Secrets only (never commit to git)

# API Keys
LLM_API_KEY=sk-xxxxxxxx
EMBEDDING_API_KEY=sk-xxxxxxxx        # Optional, defaults to LLM_API_KEY

# NetBox
NETBOX_URL=https://netbox.example.com
NETBOX_TOKEN=your-token

# Device Credentials
DEVICE_USERNAME=admin
DEVICE_PASSWORD=secure-password

# JWT (for API authentication)
JWT_SECRET_KEY=your-secret-key-min-32-chars

# Infrastructure (auto-detected in Docker)
# POSTGRES_URI=postgresql://olav:password@localhost:5432/olav
# OPENSEARCH_URL=http://localhost:9200
# REDIS_URL=redis://localhost:6379
```

---

## Prompt Consolidation

### Before (40+ files)
```
config/prompts/
├── agents/
│   ├── intent_router.yaml
│   ├── network_relevance_guard.yaml
│   └── ...
├── core/
├── strategies/
├── tools/
└── workflows/
```

### After (Consolidated)
```
config/prompts/
├── _defaults/                    # Built-in (English)
│   ├── system.yaml              # Base system prompt
│   ├── answer_formatting.yaml   # Response formatting
│   ├── intent_classification.yaml
│   ├── tool_selection.yaml
│   ├── safety_guard.yaml
│   ├── diagnosis.yaml           # Deep dive prompts
│   └── execution.yaml           # Config execution prompts
└── overrides/                   # User customizations
    └── .gitkeep
```

### Prompt Template Format

All prompts in English with i18n support via `{language}` variable:

```yaml
# config/prompts/_defaults/answer_formatting.yaml
_meta:
  name: Answer Formatting
  description: Controls how OLAV formats responses to user queries
  variables:
    - user_query
    - data_json
    - language

template: |
  You are a network operations expert. Answer the user's question based on the provided data.
  
  ## Rules
  - Be concise and direct
  - Single result: One sentence summary
  - Multiple results: Markdown table
  - Status indicators: ✅ Normal, ❌ Abnormal, ⚠️ Warning
  - Do NOT hallucinate or add information not in the data
  
  ## User Query
  {user_query}
  
  ## Data
  ```json
  {data_json}
  ```
  
  ## Response Language
  Respond in: {language}
```

---

## Implementation Plan

### Phase 1: Configuration Consolidation
1. Create `config/olav.yaml` with all settings
2. Create `OlavConfig` class to load and validate
3. Migrate from `config/settings.py` + multiple sources
4. Update `LLMFactory` to use new config

### Phase 2: Thinking Mode Control
1. Add `thinking` section to config
2. Update `LLMFactory.get_chat_model()` to check config
3. Ensure FastPath uses `reasoning=False` by default
4. Ensure DeepPath uses `reasoning=True` when enabled

### Phase 3: Prompt Refactoring
1. Audit all prompts and remove unused
2. Translate all prompts to English
3. Add `{language}` variable for i18n
4. Consolidate into fewer files
5. Implement override mechanism

### Phase 4: Model Presets
1. Define preset configurations
2. Add preset selection to config
3. Support runtime model switching (future)

---

## Migration Guide

### For Existing Users

1. **Backup current config:**
   ```bash
   cp -r config config.backup
   cp .env .env.backup
   ```

2. **Create new config:**
   ```bash
   cp config/olav.example.yaml config/olav.yaml
   ```

3. **Migrate settings:**
   - Move model settings from `.env` to `olav.yaml`
   - Keep only secrets in `.env`

4. **Test:**
   ```bash
   uv run python cli.py "Query R1 BGP status"
   ```

### Breaking Changes

1. `config/settings.py` deprecated → use `config/olav.yaml`
2. Prompt paths changed → update any custom integrations
3. Some environment variables moved → check migration table

### Environment Variable Migration

| Old Variable | New Location | Notes |
|-------------|--------------|-------|
| `LLM_PROVIDER` | `olav.yaml: models.llm.provider` | Or use preset |
| `LLM_MODEL_NAME` | `olav.yaml: models.llm.model` | |
| `LLM_BASE_URL` | `olav.yaml: models.llm.base_url` | |
| `LLM_API_KEY` | `.env` (unchanged) | Stays in .env |
| `EXPERT_MODE` | `olav.yaml: features.expert_mode` | |
| `USE_DYNAMIC_ROUTER` | `olav.yaml: features.dynamic_router` | |

---

## Files to Delete (Cleanup)

### Unused Prompts
```
config/prompts/rag/schema_search.yaml
config/prompts/strategies/deep_path/confidence_update.yaml
config/prompts/tools/cli_capability_guide.yaml
config/prompts/tools/cli_command_generator.yaml
config/prompts/tools/netbox_capability_guide.yaml
config/prompts/tools/netconf_capability_guide.yaml
config/prompts/tools/suzieq_capability_guide.yaml
config/prompts/tools/suzieq_query.yaml
config/prompts/workflows/deep_dive/conclusion.yaml
config/prompts/workflows/deep_dive/execute_todo.yaml
config/prompts/workflows/deep_dive/final_summary.yaml
config/prompts/workflows/deep_dive/funnel_diagnosis.yaml
config/prompts/workflows/deep_dive/supervisor_plan.yaml
config/prompts/workflows/deep_dive/task_planning.yaml
config/prompts/workflows/deep_dive/topology_analysis.yaml
config/prompts/workflows/orchestrator/intent_classification.yaml
```

### Deprecated Config Files
```
config/settings.py              → merged into olav.yaml
config/__init__.py              → not needed
config/rules/hitl_config.yaml   → merged into olav.yaml
config/rules/deep_dive_config.yaml → merged into olav.yaml
config/netbox-extra/            → empty, delete
```

---

## Implementation Progress

### Completed ✅

| Item | Description | Status |
|------|-------------|--------|
| `config/olav.yaml` | User-facing configuration file | ✅ Created |
| `src/olav/core/config_loader.py` | Configuration loader with defaults | ✅ Created |
| `src/olav/core/prompt_manager.py` | Updated with two-layer resolution | ✅ Updated |
| `docs/PROMPT_REFERENCE.md` | Prompt documentation | ✅ Created |
| Default prompts | 9 English prompt files in `_defaults/` | ✅ Created |
| Override structure | `prompts/overrides/README.md` | ✅ Created |

### Default Prompts Created

```
config/prompts/_defaults/
├── answer_formatting.yaml      # FastPath response formatting
├── config_execution.yaml       # Device configuration with HITL
├── diagnosis.yaml              # Deep dive troubleshooting
├── intent_router.yaml          # Workflow routing
├── netbox_comparison.yaml      # CMDB sync comparison
├── network_guard.yaml          # Query filtering
├── parameter_extraction.yaml   # Tool parameter extraction
├── strategy_selection.yaml     # Strategy selection
└── unified_classification.yaml # Intent + tool classification
```

### Pending Tasks ⏳

| Item | Description | Priority |
|------|-------------|----------|
| LLMFactory update | Use `olav.yaml` for model config | High |
| FastPath integration | Use new prompts in fast_path.py | High |
| Docker compose update | Add volume mounts for config | Medium |
| Remove unused prompts | Archive/delete 16 unused files | Low |
| Migration script | Help users migrate from old config | Low |

---

## Testing Checklist

- [ ] Model preset switching works
- [ ] Thinking mode respects config (enabled/disabled)
- [ ] FastPath returns concise answers (no thinking)
- [ ] DeepPath shows reasoning when enabled
- [ ] Prompt overrides load correctly
- [ ] Docker volume mounts work
- [ ] Backward compatibility with existing .env
- [ ] All prompts work in English
- [ ] Language setting affects response language

---

## Usage Examples

### Basic Usage (New API)

```python
from src.olav.core.prompt_manager import prompt_manager

# Load prompt with variables
prompt = prompt_manager.load(
    "answer_formatting",
    user_query="Show BGP neighbors",
    data_json='{"neighbors": [...]}'
)

# Load with explicit thinking control
prompt = prompt_manager.load(
    "diagnosis",
    thinking=True,  # Enable thinking for this call
    user_query="Why is BGP session down?",
    findings="Previous findings...",
    available_tools="suzieq_query, netconf_get"
)
```

### Configuration Access

```python
from src.olav.core.config_loader import get_config

config = get_config()

# Check thinking mode
if config.is_thinking_enabled("fast_path"):
    # Use extended reasoning
    pass

# Get specific settings
max_age = config.get("query.max_age_hours", 72)
model = config.get("llm.model", "qwen3:30b")
```

### Legacy Compatibility

```python
# Old API still works
prompt = prompt_manager.load_prompt("agents", "intent_router", query="...")
prompt = prompt_manager.load_agent_prompt("root_agent", context="...")
```

---

## Future Enhancements

1. **Hot Reload**: Watch config file for changes
2. **Web UI Config Editor**: Edit olav.yaml from browser
3. **Model Benchmarking**: Compare response quality across models
4. **Prompt Versioning**: Track prompt changes over time

