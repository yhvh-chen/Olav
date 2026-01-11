# Claude Code Workflow 设计文档

## 概述

本文档描述将固定流程的 Skills（如深度分析、配置备份）包装为 Claude Code `/` Workflow 的设计方案。

## 设计目标

1. **减少 Skill 调用压力** - 固定流程无需每次"理解意图"
2. **提高可预测性** - 用户明确知道执行什么
3. **更好的参数传递** - 结构化参数而非自然语言提取
4. **减少 Token 消耗** - 模板化执行，减少 30-50% token

## 架构对比

### 当前架构

```
skills/
├── deep-analysis/SKILL.md     # 复杂的故障诊断流程
├── config-backup/SKILL.md     # 配置备份流程
├── device-inspection/         # 设备巡检
└── quick-query/               # 快速查询

commands/
├── diagnose.md                # /diagnose 命令
├── inspect.md                 # /inspect 命令
└── query.md                   # /query 命令
```

### 新增 Workflow

```
commands/
├── diagnose.md                # 已存在
├── inspect.md                 # 已存在
├── query.md                   # 已存在
├── backup.md                  # 新增：/backup workflow
└── analyze.md                 # 新增：/analyze workflow
```

## 两种方式对比

| 特性 | Skill 调用 | `/` Workflow |
|------|-----------|--------------|
| **触发方式** | 自然语言识别意图 | 明确的 `/analyze` 或 `/backup` |
| **参数传递** | 从对话中提取 | 结构化参数 `[filter] [options]` |
| **执行流程** | AI 决定步骤 | 预定义步骤 + AI 执行 |
| **可预测性** | 较低 | 较高 |
| **Context 消耗** | 每次重新理解意图 | 模板化，减少 token |

## Claude Code 官方规范兼容性

### ✅ 完全兼容

设计遵循 Claude Code 官方规范：

| 规范要素 | 官方格式 | 我们的格式 | 兼容性 |
|----------|----------|-----------|--------|
| 文件位置 | `.claude/commands/` | `commands/` | ✅ |
| 文件格式 | Markdown + YAML frontmatter | 相同 | ✅ |
| 必需字段 | `description` | 已有 | ✅ |
| 可选字段 | `allowed-tools`, `argument-hint`, `model` | 已有 | ✅ |

### 官方支持的参数化特性

1. **位置参数**: `$1`, `$2`, `$ARGUMENTS`
2. **条件逻辑**: `$IF(condition, then, else)`
3. **Bash 嵌入**: `!`command``
4. **文件引用**: `@path/to/file`

---

## 详细设计

### `/backup` Command

**文件**: `commands/backup.md`

```markdown
---
description: Backup device configurations with filtering
argument-hint: [filter] [type] [--commands "cmd1,cmd2"]
allowed-tools: nornir_execute, list_devices, save_device_config, Bash(echo:*)
model: sonnet
---

## Backup Network Configurations

Target devices: $1
Backup type: $2

### Supported Filters
- `role:core` - Devices with role="core"
- `site:lab` - Devices at site="lab"  
- `group:test` - Devices in "test" group
- `R1,R2,R3` - Specific device list
- `all` - All devices

### Backup Types
- `running` - Running configuration (show running-config)
- `startup` - Startup configuration (show startup-config)
- `all` - Both running and startup
- `custom` - Use --commands parameter

### Custom Commands
$IF($ARGUMENTS contains "--commands",
  Parse custom commands from --commands parameter and execute on each device,
  Use standard backup command based on type
)

### Workflow
1. Parse filter from $1 to identify target devices
2. Call list_devices() to get matching devices
3. For each device:
   - Execute backup command via nornir_execute()
   - Save output via save_device_config()
4. Report summary of backed up configurations

Follow skill methodology: @skills/config-backup/SKILL.md
```

**使用示例**:
```bash
/backup role:core running
/backup R1,R2 all
/backup all custom --commands "show mac address-table,show arp"
/backup SW1 custom --commands "show vlan,show interfaces trunk"
```

---

### `/analyze` Command

**文件**: `commands/analyze.md`

```markdown
---
description: Deep network analysis with customizable workflow
argument-hint: [source] [destination] [--error "desc"] [--plan] [--interactive]
allowed-tools: nornir_execute, list_devices, task, write_todos
model: opus
---

## Deep Network Analysis

Analyze network path from $1 to $2

### Options

**--error "description"**
Provide error description to guide diagnosis:
$IF($ARGUMENTS contains "--error",
  Extract error description and use it to focus the analysis,
  Ask user to describe the observed issue
)

**--plan**
Show analysis plan before execution:
$IF($ARGUMENTS contains "--plan",
  Generate and display analysis plan. Wait for user confirmation before proceeding,
  Execute analysis steps directly
)

**--interactive**
Pause after each step:
$IF($ARGUMENTS contains "--interactive",
  After each diagnostic step pause and ask for user feedback or direction,
  Run analysis continuously until completion
)

### Analysis Methodology

#### Phase 1: Macro Analysis
Use macro-analyzer subagent to:
- Trace path from $1 to $2
- Identify all intermediate devices
- Check BGP/OSPF neighbor status
- Determine fault domain

#### Phase 2: Micro Analysis  
Use micro-analyzer subagent to:
- TCP/IP layer-by-layer troubleshooting on identified problem device
- Physical layer: interface status, CRC errors, optical power
- Data link layer: VLAN, MAC table, STP
- Network layer: IP config, routing, ARP

#### Phase 3: Synthesis
- Combine macro and micro analysis results
- Identify root cause
- Provide actionable recommendations

Follow skill methodology: @skills/deep-analysis/SKILL.md
```

**使用示例**:
```bash
/analyze R1 R5
/analyze R1 R5 --error "ping fails with 50% packet loss"
/analyze 10.1.1.1 10.5.1.1 --plan
/analyze Server1 Database1 --interactive --error "connection timeout"
```

---

## 交互式 Plan 设计

当用户使用 `--plan` 参数时，系统显示分析计划：

```
User: /analyze R1 R5 --error "BGP not up" --plan

OLAV: 📋 Analysis Plan for R1 → R5 (BGP Issue)

Step 1: [Macro] Topology Discovery
  - Check LLDP/CDP neighbors on path
  - Trace route from R1 to R5

Step 2: [Macro] BGP Neighbor Status
  - R1: show bgp neighbors
  - R5: show bgp neighbors
  - Compare advertised/received routes

Step 3: [Micro] Deep Dive on Identified Issues
  - Layer-by-layer check if needed

Proceed? [y/n/modify step X]
```

---

## 代码影响评估

```
Impact Assessment:
┌─────────────────────────────────────┐
│  Changes Required                   │
├─────────────────────────────────────┤
│  ✅ Add commands/backup.md         │  ← 新文件
│  ✅ Add commands/analyze.md        │  ← 新文件  
│  ⚪ Update CLAUDE.md (optional)    │  ← 文档更新
│                                     │
│  ❌ No Python code changes needed  │
│  ❌ Existing skills remain valid   │
│  ❌ No breaking changes to API     │
└─────────────────────────────────────┘

Backward Compatibility: 100%
- "backup R1 config" → Still works (skill-based)
- "/backup R1 running" → New workflow (command-based)
```

---

## 与其他 Agent 工具的兼容性

| 工具 | 兼容性 | 原因 |
|------|--------|------|
| **Claude Code CLI** | ✅ | 官方格式 |
| **Claude Code Action (GitHub)** | ✅ | 读取相同格式 |
| **其他 Claude Code 插件** | ✅ | 标准 frontmatter |
| **自定义 Agent 实现** | ✅ | YAML + Markdown 通用 |

---

## 实施计划

### Phase 1: 添加基础 Workflow（低风险）
1. 创建 `commands/backup.md`
2. 创建 `commands/analyze.md`
3. 测试基本功能

### Phase 2: 添加高级参数支持
1. 实现 `--commands` 自定义命令
2. 实现 `--plan` 显示计划
3. 实现 `--interactive` 交互模式

### Phase 3: Skill 精简（可选）
1. 保留 Skills 作为"AI 自主判断"入口
2. Workflows 作为"用户明确指定"入口
3. Commands 内部引用 Skills 的方法论

---

## 总结

| 问题 | 答案 |
|------|------|
| **破坏性大不大？** | **很小**，只需添加 `.md` 文件 |
| **收益如何？** | **明显**：减少 token、提高可预测性、更好的参数传递 |
| **如何传递自定义信息？** | 通过 `argument-hint` 定义参数格式，支持 `--error`, `--commands`, `--plan` 等选项 |
| **与官方规范兼容？** | **完全兼容** Claude Code 官方规范 |
| **可被其他工具使用？** | **是的**，标准格式可被任何支持 Claude Code 的 Agent 使用 |
