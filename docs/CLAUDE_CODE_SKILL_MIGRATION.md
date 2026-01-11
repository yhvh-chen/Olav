# Claude Code Skill 兼容性迁移指南

## 实现状态总览

> **最后检查时间**: 2026-01-09
>
> **结论**: 设计已部分实施，核心模块完成，部分迁移任务待完成。

### ✅ 已完成的实现

| 模块 | 设计 | 实现文件 | 状态 |
|------|------|----------|------|
| **Markdown 报告** | report_formatter.py | `src/olav/tools/report_formatter.py` ✅ | 354行，支持多语言 |
| **统一搜索工具** | `search()` | `src/olav/tools/capabilities.py:search()` ✅ | FTS + Vector 混合检索 |
| **知识库 Schema** | knowledge_chunks 表 | `src/olav/core/database.py:init_knowledge_db()` ✅ | 完整 FTS + HNSW 索引 |
| **Embedding 工具** | KnowledgeEmbedder | `src/olav/tools/knowledge_embedder.py` ✅ | Ollama/OpenAI 双后端 |
| **索引脚本** | index_knowledge.py | `scripts/index_knowledge.py` ✅ | 增量索引支持 |
| **迁移脚本** | migrate_to_claude_code.py | `scripts/migrate_to_claude_code.py` ✅ | 628行自动化 |
| **Skill 双格式加载** | SKILL.md + *.md | `src/olav/core/skill_loader.py` ✅ | 支持两种格式 |
| **agent_dir 配置** | settings.agent_dir | `config/settings.py:agent_dir` ✅ | 可配置目录名 |
| **knowledge.db** | 数据库文件 | `.olav/data/knowledge.db` ✅ | 已创建 |
| **Skill Frontmatter 升级** | name + version | `.olav/skills/quick-query.md` ✅ | 已更新格式 |

### ⚠️ 部分完成

| 模块 | 设计 | 当前状态 | 差距 |
|------|------|----------|------|
| **硬编码路径** | 使用 settings.agent_dir | 仍有 20+ 处 `.olav` 硬编码 | 需更新 storage_tools, agent.py 等 |
| **Commands 格式** | .md Markdown | 仍为 .py Python | 需创建 .md 并移动 .py 到 scripts/ |
| **Skill 目录结构** | skills/*/SKILL.md | 仍为 skills/*.md 平铺 | 需运行迁移脚本 |
| **OLAV.md → CLAUDE.md** | 根目录 CLAUDE.md | 仍为 .olav/OLAV.md | 需移动并重命名 |

### ❌ 待实现

| 模块 | 设计文件 | 状态 |
|------|----------|------|
| `search-knowledge.py` 桥接脚本 | `.olav/commands/` | ❌ 未创建 |
| `reload-knowledge.py` 桥接脚本 | `.olav/commands/` | ❌ 未创建 |
| `sync_knowledge.py` 增量同步脚本 | `scripts/` | ❌ 未创建 |
| `tests/unit/test_search_tool.py` | 单元测试 | ❌ 未创建 |
| `tests/unit/test_knowledge_indexer.py` | 单元测试 | ❌ 未创建 |
| `tests/e2e/test_claude_code_compat.py` | E2E测试 | ❌ 未创建 |
| `tests/e2e/test_knowledge_e2e.py` | E2E测试 | ❌ 未创建 |

---

## 概述

本文档描述如何将 OLAV 的 Skill 架构迁移为 Claude Code Skill 标准格式，实现以下目标：

1. **HTML → Markdown**：将复杂的 Jinja2 HTML 报告简化为 Skill 控制的 Markdown 输出
2. **标准化目录结构**：遵循 Claude Code Plugin/Skill 标准
3. **即插即用**：用户只需将 `.olav/` 重命名为 `.claude/` 即可在 Claude Code 中运行

---

## 兼容性检查清单

> **问题**：把 `.olav` 改为 `.claude` 是否直接可用？
>
> **答案**：**不能直接使用**，需要完成以下适配工作。

### 目录结构差异

| 项目 | OLAV 当前 | Claude Code 标准 | 状态 | 修改 |
|------|-----------|------------------|------|------|
| 根目录 | `.olav/` | `.claude/` | ⚠️ 需重命名 | 重命名目录 |
| Skill 格式 | `skills/*.md` | `skills/*/SKILL.md` | ❌ 不兼容 | 每个 skill 需独立目录 |
| Commands | `commands/*.py` | `commands/*.md` | ❌ 不兼容 | Python 桥接 → Markdown 指令 |
| Settings | `settings.json` | `settings.json` ✅ | ✅ 兼容 | - |
| Knowledge | `knowledge/*.md` | 无标准 | ⚠️ 自定义 | 保留，通过 search 工具访问 |
| 系统指令 | `OLAV.md` | `CLAUDE.md` | ⚠️ 需重命名 | 重命名 |

### Skill Frontmatter 差异

| 字段 | OLAV 当前 | Claude Code 标准 | 状态 |
|------|-----------|------------------|------|
| `name` | ❌ 使用 `id` | ✅ 必需 | 需修改 |
| `description` | ✅ 有 | ✅ 必需 | ✅ 兼容 |
| `version` | ❌ 无 | ✅ 推荐 | 需添加 |
| `triggers` | ❌ 使用 `examples` | ❌ 无此字段 | Claude Code 用 description 匹配 |
| `allowed-tools` | ❌ 使用 `tools` | ✅ 标准字段 | 需修改字段名 |
| `intent` | ✅ 自定义 | ❌ 非标准 | 可保留但无作用 |
| `complexity` | ✅ 自定义 | ❌ 非标准 | 可保留但无作用 |

### Commands 格式差异

| 项目 | OLAV 当前 | Claude Code 标准 |
|------|-----------|------------------|
| 格式 | Python 脚本 | Markdown 指令 |
| 调用方式 | Agent 内部调用 | `/command-name` 用户触发 |
| 工具访问 | 直接调用 `@tool` | `allowed-tools: Bash(*)` |
| 参数 | Python `sys.argv` | `$1`, `$2`, `$ARGUMENTS` |

**示例对比**：

```python
# OLAV 当前: .olav/commands/nornir-execute.py
from olav.tools.network import nornir_execute
result = nornir_execute.invoke({"device": sys.argv[1], "command": sys.argv[2]})
```

```markdown
# Claude Code 标准: .claude/commands/nornir-execute.md
---
description: Execute network command on device
argument-hint: [device] [command]
allowed-tools: Bash(python:*)
---

Execute network command: !`python ${CLAUDE_PLUGIN_ROOT}/scripts/nornir-execute.py $1 $2`
```

---

## 第一部分：HTML → Markdown 迁移

### 1.1 当前问题

| 问题 | 描述 |
|------|------|
| Jinja2 依赖 | 需要 Jinja2 模板引擎，~400行代码 |
| 模板维护 | 4个 `.html.j2` 模板文件需要维护 |
| 不可移植 | HTML 输出在终端不可读 |
| Skill 不控制 | 输出格式硬编码在 Python 中 |

### 1.2 迁移方案

**核心原则**：Skill 完全控制输出格式，Python 工具只负责执行

#### 新的 Skill Frontmatter 字段

```yaml
---
name: device-inspection
description: Comprehensive L1-L4 network device inspection
version: 1.0.0

# 输出控制（新增）
output:
  format: markdown          # markdown | json | table
  language: zh-CN           # zh-CN | en-US
  sections:                 # 输出章节
    - summary
    - details  
    - recommendations
---
```

#### 输出格式模板（内嵌在 Skill 中）

```markdown
## Output Templates

### Summary Template (Markdown)
\`\`\`
# {inspection_type} Report

**Inspection Time**: {timestamp}
**Total Devices**: {device_count}
**Overall Status**: {status_emoji} {status_text}

## Device Summary
{device_table}
\`\`\`

### Device Status Row
\`\`\`
| {device_name} | {ip} | {status_emoji} | L1:{l1} L2:{l2} L3:{l3} L4:{l4} |
\`\`\`
```

### 1.3 实现步骤

#### Step 1: 添加 Markdown 报告生成器

创建 `src/olav/tools/report_formatter.py`：

```python
"""Skill-controlled Markdown report formatter."""

from datetime import datetime
from typing import Any

def format_inspection_report(
    results: dict[str, list[dict[str, Any]]],
    skill_config: dict[str, Any],
) -> str:
    """Generate Markdown report based on skill output configuration.
    
    Args:
        results: Raw inspection results from nornir_bulk_execute
        skill_config: Skill frontmatter with output configuration
        
    Returns:
        Formatted Markdown string
    """
    output_config = skill_config.get("output", {})
    lang = output_config.get("language", "en-US")
    
    # Language strings
    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en-US"])
    
    lines = []
    
    # Header
    lines.append(f"# {strings['title']}")
    lines.append("")
    lines.append(f"**{strings['time']}**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**{strings['devices']}**: {len(results)}")
    lines.append("")
    
    # Summary table
    lines.append(f"## {strings['summary']}")
    lines.append("")
    lines.append(f"| {strings['device']} | {strings['status']} | {strings['details']} |")
    lines.append("|--------|--------|---------|")
    
    for device, device_results in results.items():
        success_count = sum(1 for r in device_results if r.get("success"))
        total = len(device_results)
        status = "✅" if success_count == total else "⚠️" if success_count > 0 else "❌"
        lines.append(f"| {device} | {status} | {success_count}/{total} |")
    
    lines.append("")
    
    # Details (if enabled)
    if "details" in output_config.get("sections", ["summary", "details"]):
        lines.append(f"## {strings['details']}")
        lines.append("")
        for device, device_results in results.items():
            lines.append(f"### {device}")
            lines.append("")
            for result in device_results:
                cmd = result.get("command", "unknown")
                if result.get("success"):
                    lines.append(f"**`{cmd}`** ✅")
                    lines.append("```")
                    lines.append(result.get("output", "")[:500])  # Truncate
                    lines.append("```")
                else:
                    lines.append(f"**`{cmd}`** ❌ {result.get('error', 'Unknown error')}")
                lines.append("")
    
    return "\n".join(lines)


LANG_STRINGS = {
    "en-US": {
        "title": "Inspection Report",
        "time": "Inspection Time",
        "devices": "Total Devices",
        "summary": "Summary",
        "device": "Device",
        "status": "Status", 
        "details": "Details",
    },
    "zh-CN": {
        "title": "巡检报告",
        "time": "巡检时间",
        "devices": "设备总数",
        "summary": "概览",
        "device": "设备",
        "status": "状态",
        "details": "详细信息",
    },
}
```

#### Step 2: 修改 generate_report 工具

```python
@tool
def generate_report(
    results: dict[str, list[dict[str, Any]]],
    skill_id: str = "device-inspection",
    output_path: str | None = None,
) -> str:
    """Generate inspection report using skill-defined format.
    
    The output format (markdown/json/table) and language are controlled
    by the skill's frontmatter configuration.
    """
    # Load skill configuration
    skill_loader = get_skill_loader()
    skill = skill_loader.load(skill_id)
    
    # Generate report based on skill config
    report_content = format_inspection_report(results, skill.frontmatter)
    
    # Save to file
    if output_path:
        Path(output_path).write_text(report_content, encoding="utf-8")
        return f"Report saved to: {output_path}"
    
    return report_content
```

#### Step 3: 删除 HTML 模板依赖

```bash
# 删除 Jinja2 模板
rm -rf .olav/inspect_templates/

# 从 pyproject.toml 移除 jinja2（如果不再需要）
# jinja2 仍用于 LangChain prompts，保留
```

---

## 第二部分：Claude Code Skill 标准架构

### 2.1 目录结构对比

| OLAV 当前 | Claude Code 标准 | 迁移后 |
|-----------|-----------------|--------|
| `.olav/OLAV.md` | `CLAUDE.md` (根目录) | `CLAUDE.md` |
| `.olav/skills/*.md` | `skills/*/SKILL.md` | `skills/*/SKILL.md` |
| `.olav/knowledge/` | `knowledge/` | `knowledge/` (全局知识) |
| `.olav/commands/` | `commands/*.md` | `commands/*.md` |
| `.olav/settings.json` | `.claude/settings.json` | `.{agent}/settings.json` |
| `.olav/config/nornir/` | (保持) | `config/nornir/` |
| `.olav/data/` | `.claude/data/` | `.{agent}/data/` (含 knowledge.db) |

> **注意**：不使用 `skills/*/references/` 存放知识，统一使用 `knowledge.db` + `search()` 工具。

### 2.2 目标目录结构

```
project-root/
├── CLAUDE.md                          # 系统提示（从 .olav/OLAV.md 移动）
├── .{agent}/                          # 可重命名为 .claude, .olav, .cursor 等
│   ├── settings.json                  # Agent 配置
│   └── memory.json                    # Agent 记忆（可选）
├── commands/                          # Slash Commands
│   ├── query.md                       # /query 命令
│   ├── inspect.md                     # /inspect 命令
│   ├── diagnose.md                    # /diagnose 命令
│   └── search-docs.md                 # /search-docs 命令 (知识库搜索)
├── skills/                            # Skills（核心能力）
│   ├── quick-query/
│   │   └── SKILL.md                   # Skill 定义（必需）
│   ├── device-inspection/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── generate-report.py
│   ├── deep-analysis/
│   │   └── SKILL.md
│   └── config-backup/
│       └── SKILL.md
├── agents/                            # SubAgents（可选）
│   ├── macro-analyzer.md
│   └── micro-analyzer.md
├── knowledge/                         # 全局知识库（别名、拓扑等小型文件）
│   ├── aliases.md
│   ├── conventions.md
│   └── solutions/
├── docs/                              # 原始文档（仅用于索引到 knowledge.db）
│   ├── vendor/                        # 厂商文档 (Markdown)
│   ├── wiki/                          # 团队 Wiki
│   └── runbooks/                      # 运维手册
└── config/                            # 运行时配置
    └── nornir/
        └── config.yaml
```

> **知识库设计**：大型文档（厂商手册、Wiki）索引到 `.{agent}/data/knowledge.db`，通过 `search()` 工具检索。小型元数据（别名、拓扑）保留在 `knowledge/` 目录。

### 2.3 Skill 格式标准化

#### 当前格式 (.olav/skills/quick-query.md)

```yaml
---
id: quick-query
intent: query
complexity: simple
description: "Simple status query..."
examples:
  - "R1 interface status"
---
```

#### Claude Code 标准格式 (skills/quick-query/SKILL.md)

```yaml
---
name: Quick Query
description: Execute simple network status queries that require 1-2 commands. Use when user asks to check, show, or display device status.
version: 1.0.0

# Claude Code 标准字段
triggers:
  - "check"
  - "show" 
  - "status"
  - "display"
  - "query"

# OLAV 扩展字段（保持兼容）
intent: query
complexity: simple

# 输出控制
output:
  format: markdown
  language: auto  # 自动检测用户语言
---

# Quick Query Skill

## When to Use
- Query device interface status
- Query routing table
- Query ARP/MAC table
- Simple status checks

## Execution Strategy
...
```

---

## 第三部分：迁移脚本

### 3.1 自动迁移脚本

创建 `scripts/migrate_to_claude_code.py`：

```python
#!/usr/bin/env python3
"""Migrate .olav structure to Claude Code Skill standard."""

import shutil
import re
from pathlib import Path
import json

def migrate_skills(src_dir: Path, dest_dir: Path):
    """Migrate flat skill files to SKILL.md structure."""
    skills_src = src_dir / "skills"
    skills_dest = dest_dir / "skills"
    
    for skill_file in skills_src.glob("*.md"):
        skill_name = skill_file.stem
        skill_dir = skills_dest / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # Read and transform frontmatter
        content = skill_file.read_text(encoding="utf-8")
        new_content = transform_skill_frontmatter(content, skill_name)
        
        # Write as SKILL.md
        (skill_dir / "SKILL.md").write_text(new_content, encoding="utf-8")
        print(f"  ✅ {skill_name} → skills/{skill_name}/SKILL.md")

def transform_skill_frontmatter(content: str, skill_name: str) -> str:
    """Transform OLAV frontmatter to Claude Code standard."""
    # Extract frontmatter
    if not content.startswith("---"):
        return content
        
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    
    frontmatter = parts[1].strip()
    body = parts[2].strip()
    
    # Parse and transform
    lines = frontmatter.split("\n")
    new_lines = []
    
    for line in lines:
        if line.startswith("id:"):
            # Convert id to name (title case)
            name = skill_name.replace("-", " ").title()
            new_lines.append(f"name: {name}")
        elif line.startswith("description:"):
            new_lines.append(line)
        elif line.startswith("intent:") or line.startswith("complexity:"):
            new_lines.append(line)  # Keep for compatibility
        elif line.startswith("examples:"):
            # Convert examples to triggers
            continue  # Handle separately
        else:
            new_lines.append(line)
    
    # Add version
    new_lines.append("version: 1.0.0")
    
    # Add output config
    new_lines.append("")
    new_lines.append("output:")
    new_lines.append("  format: markdown")
    new_lines.append("  language: auto")
    
    new_frontmatter = "\n".join(new_lines)
    return f"---\n{new_frontmatter}\n---\n\n{body}"

def migrate_system_prompt(src_dir: Path, dest_dir: Path):
    """Move OLAV.md to CLAUDE.md at root."""
    src_file = src_dir / "OLAV.md"
    dest_file = dest_dir / "CLAUDE.md"
    
    if src_file.exists():
        content = src_file.read_text(encoding="utf-8")
        # Update references
        content = content.replace(".olav/", "")
        content = content.replace("OLAV.md", "CLAUDE.md")
        dest_file.write_text(content, encoding="utf-8")
        print(f"  ✅ OLAV.md → CLAUDE.md")

def migrate_knowledge(src_dir: Path, dest_dir: Path):
    """Move knowledge to root level."""
    src_knowledge = src_dir / "knowledge"
    dest_knowledge = dest_dir / "knowledge"
    
    if src_knowledge.exists():
        shutil.copytree(src_knowledge, dest_knowledge, dirs_exist_ok=True)
        print(f"  ✅ knowledge/ → knowledge/")

def migrate_settings(src_dir: Path, dest_dir: Path, agent_name: str):
    """Move settings to .{agent}/ directory."""
    src_settings = src_dir / "settings.json"
    agent_dir = dest_dir / f".{agent_name}"
    agent_dir.mkdir(parents=True, exist_ok=True)
    
    if src_settings.exists():
        shutil.copy(src_settings, agent_dir / "settings.json")
        print(f"  ✅ settings.json → .{agent_name}/settings.json")

def create_commands(dest_dir: Path):
    """Create slash command stubs."""
    commands_dir = dest_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    
    # Query command
    query_cmd = '''---
description: Query network device status
argument-hint: [device] [query]
---

Execute a quick network query.

1. Parse device alias from knowledge/aliases.md
2. Use Quick Query skill to find appropriate command
3. Execute command and return concise results
'''
    (commands_dir / "query.md").write_text(query_cmd)
    
    # Inspect command
    inspect_cmd = '''---
description: Run comprehensive device inspection
argument-hint: [scope]
---

Run comprehensive L1-L4 inspection on specified devices.

1. Parse inspection scope (all, device list, or filter)
2. Use Device Inspection skill for systematic inspection
3. Generate markdown report
'''
    (commands_dir / "inspect.md").write_text(inspect_cmd)
    
    print(f"  ✅ Created commands/query.md, commands/inspect.md")

def main():
    """Run migration."""
    src_dir = Path(".olav")
    dest_dir = Path("claude-code-migration")
    agent_name = "claude"  # Can be changed to any name
    
    print(f"\n🚀 Migrating .olav → Claude Code Skill Standard")
    print(f"   Source: {src_dir.absolute()}")
    print(f"   Destination: {dest_dir.absolute()}")
    print()
    
    # Clean destination
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir()
    
    # Run migrations
    print("📁 Migrating components:")
    migrate_system_prompt(src_dir, dest_dir)
    migrate_skills(src_dir, dest_dir)
    migrate_knowledge(src_dir, dest_dir)
    migrate_settings(src_dir, dest_dir, agent_name)
    create_commands(dest_dir)
    
    # Copy config
    config_src = src_dir / "config"
    if config_src.exists():
        shutil.copytree(config_src, dest_dir / "config", dirs_exist_ok=True)
        print(f"  ✅ config/ → config/")
    
    print()
    print("✅ Migration complete!")
    print()
    print("📋 Next steps:")
    print(f"   1. Review files in {dest_dir}/")
    print(f"   2. Copy to your project root")
    print(f"   3. Rename .{agent_name}/ to your preferred name")
    print()
    print("📝 Directory mapping:")
    print(f"   .{agent_name}/          → Agent settings (rename to .claude, .cursor, etc.)")
    print(f"   CLAUDE.md            → System prompt (rename to match agent)")
    print(f"   skills/              → Skill definitions")
    print(f"   commands/            → Slash commands")
    print(f"   knowledge/           → Shared knowledge base")

if __name__ == "__main__":
    main()
```

### 3.2 运行迁移

```bash
# 运行迁移脚本
uv run python scripts/migrate_to_claude_code.py

# 查看生成的结构
tree claude-code-migration/

# 如果满意，应用到项目
cp -r claude-code-migration/* ./
rm -rf .olav/  # 备份后删除
```

---

## 第四部分：兼容性设计

### 4.1 Agent 名称可配置

用户可以将 `.{agent}/` 目录重命名为任意名称：

| Agent 框架 | 目录名 | 系统提示 |
|-----------|--------|----------|
| Claude Code | `.claude/` | `CLAUDE.md` |
| Cursor | `.cursor/` | `CURSOR.md` |
| OLAV | `.olav/` | `OLAV.md` |
| Custom | `.myagent/` | `MYAGENT.md` |

### 4.2 Skill Loader 兼容性

更新 `skill_loader.py` 以支持两种结构：

```python
def find_skills(self) -> list[Path]:
    """Find all skill files, supporting both formats."""
    skills = []
    
    # Format 1: Claude Code standard (skills/*/SKILL.md)
    for skill_dir in self.skills_path.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills.append(skill_file)
    
    # Format 2: OLAV legacy (skills/*.md)
    for skill_file in self.skills_path.glob("*.md"):
        if skill_file.name != "SKILL.md":
            skills.append(skill_file)
    
    return skills
```

### 4.3 输出语言自动检测

```python
def detect_language(user_message: str) -> str:
    """Detect user's language from message."""
    # Simple heuristic: check for Chinese characters
    if re.search(r'[\u4e00-\u9fff]', user_message):
        return "zh-CN"
    return "en-US"
```

---

## 第五部分：实施清单

### Phase 1: HTML → Markdown (预计 2 小时)

- [ ] 创建 `src/olav/tools/report_formatter.py`
- [ ] 更新 `inspection_tools.py` 使用新格式化器
- [ ] 添加 Skill `output` frontmatter 字段
- [ ] 更新 `device-inspection.md` 添加输出模板
- [ ] 删除 `.olav/inspect_templates/` 目录
- [ ] 测试 Markdown 报告输出

### Phase 2: 目录结构迁移 (预计 3 小时)

- [ ] 创建迁移脚本 `scripts/migrate_to_claude_code.py`
- [ ] 将 Skills 转换为 `skills/*/SKILL.md` 格式
- [ ] 移动 `OLAV.md` → `CLAUDE.md`
- [ ] 创建 `commands/` 目录和基础命令
- [ ] 更新 Skill Loader 支持两种格式
- [ ] 测试新结构

### Phase 3: 兼容性验证 (预计 1 小时)

- [ ] 测试重命名为 `.claude/`
- [ ] 测试重命名为 `.cursor/`
- [ ] 验证所有功能正常
- [ ] 更新文档

---
## 第七部分：用户知识库设计

> **设计决策**：统一使用知识库 (KB) + `search()` MCP 工具，不使用 Claude Code 的 `references/` 静态文件模式。
> 
> **理由**：网络运维场景的厂商文档量巨大（数千页），`references/` 模式需要手动维护静态文件，不可扩展。

### 7.1 统一 KB 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Knowledge Architecture               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户文档 (原始)              索引后存储                         │
│  ┌─────────────┐            ┌─────────────────────┐            │
│  │ docs/       │   index    │ .claude/data/       │            │
│  │  vendor/    │ ───────>   │   knowledge.db      │            │
│  │  wiki/      │            │   (FTS + Vector)    │            │
│  │  runbooks/  │            └─────────┬───────────┘            │
│  └─────────────┘                      │                        │
│                                       ▼                        │
│                          ┌─────────────────────┐               │
│                          │  search() MCP Tool  │               │
│                          │  - scope=knowledge  │               │
│                          │  - platform filter  │               │
│                          └─────────────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 知识库类型

| 类型 | 位置 | 说明 | 索引命令 |
|------|------|------|----------|
| **厂商文档** | `docs/vendor/cisco/` | Cisco, Huawei, Juniper 手册 | `--platform cisco_ios` |
| **团队 Wiki** | `docs/wiki/` | 内部知识库 | `--source team_wiki` |
| **运维手册** | `docs/runbooks/` | SOP, Runbook | `--source runbooks` |
| **拓扑文档** | `docs/topology/` | 网络架构图说明 | `--source topology` |

### 7.3 用户文档添加流程

```bash
# 1. 准备文档 (Markdown 格式)
#    - PDF 可使用 marker-pdf 转换
#    - Word 可使用 pandoc 转换
mkdir -p docs/vendor/cisco

# 2. 索引到知识库
uv run python scripts/index_knowledge.py \
  --source cisco_ios_xe_17 \
  --path docs/vendor/cisco/ \
  --platform cisco_ios

# 3. 验证索引
uv run python -c "
from olav.tools.capabilities import search
print(search('show ip interface', scope='knowledge', platform='cisco_ios'))
"
```

### 7.4 Claude Code 兼容方式

**不通过 MCP，而是通过 commands/ 桥接脚本**（与 DESIGN_V0.8.md 一致）：

```
.olav/commands/
├── nornir-execute.py        # Nornir 执行桥接
├── search-capabilities.py   # capabilities.db 查询桥接
├── search-knowledge.py      # knowledge.db 查询桥接 (新增)
└── reload-capabilities.py   # 能力重载桥接
```

**Claude Code skill script 调用示例**：

```markdown
---
name: search-docs
description: Search vendor documentation and team wiki
---

Search knowledge base for: $ARGUMENTS

Steps:
1. Execute: `!python .claude/commands/search-knowledge.py "$ARGUMENTS"`
2. Display results with source attribution
3. Suggest follow-up queries if needed
```

**桥接脚本示例** (`commands/search-knowledge.py`)：

```python
#!/usr/bin/env python3
"""Knowledge search bridge for Claude Code skill scripts."""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from olav.tools.capabilities import search

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not query:
        print("Usage: search-knowledge.py <query>")
        sys.exit(1)
    
    result = search(query, scope="knowledge")
    print(result)
```

### 7.5 与 capabilities 的区别

| 数据源 | search() scope | 内容 | 使用场景 |
|--------|----------------|------|----------|
| `capabilities.db` | `"capabilities"` | CLI/API 命令 | 查找执行命令 |
| `knowledge.db` | `"knowledge"` | 厂商文档、Wiki、**学习的知识** | 理解概念、排查故障 |
| 两者 | `"all"` (默认) | 合并结果 | 综合查询 |

### 7.6 Agentic 学习知识统一到 KB

**设计原则**：Agent 学习到的所有知识统一索引到 `knowledge.db`，而非分散在 Markdown 文件中。

#### 7.6.1 知识来源统一

| 知识类型 | 原设计位置 | 新设计 | 说明 |
|----------|-----------|--------|------|
| 设备别名 | `.olav/knowledge/aliases.md` | `knowledge.db` (type=alias) | 自动索引 |
| 成功案例 | `.olav/knowledge/solutions/*.md` | `knowledge.db` (type=solution) | 自动索引 |
| 厂商文档 | `docs/vendor/` | `knowledge.db` (type=vendor_doc) | 手动索引 |
| 团队 Wiki | `docs/wiki/` | `knowledge.db` (type=wiki) | 手动索引 |

#### 7.6.2 学习后自动索引

当 Agent 学习新知识并获得 HITL 审批后，自动索引到 KB：

```python
# src/olav/core/knowledge_writer.py
"""Write learned knowledge to DB after HITL approval."""

from pathlib import Path
import duckdb
from langchain_openai import OpenAIEmbeddings

def save_learned_knowledge(
    knowledge_type: str,  # "alias" | "solution" | "convention"
    content: str,
    title: str,
    metadata: dict | None = None,
) -> None:
    """Save learned knowledge to both Markdown and knowledge.db.
    
    This function is called AFTER HITL approval.
    """
    # 1. 写入 Markdown 文件 (版本控制)
    md_path = _get_markdown_path(knowledge_type, title)
    md_path.write_text(content, encoding="utf-8")
    
    # 2. 索引到 knowledge.db (语义搜索)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    embedding = embeddings.embed_query(content)
    
    conn = duckdb.connect(str(settings.knowledge_db_path))
    conn.execute("""
        INSERT INTO knowledge_chunks 
        (title, content, source_type, platform, embedding)
        VALUES (?, ?, ?, ?, ?)
    """, [title, content, knowledge_type, metadata.get("platform"), embedding])
    conn.close()
```

#### 7.6.3 Markdown 与 DB 的关系

```
                    HITL 审批
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  save_learned_knowledge()                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────────┐      ┌─────────────────────┐     │
│   │ Markdown 文件        │      │ knowledge.db        │     │
│   │ (Git 版本控制)       │      │ (语义搜索)          │     │
│   │                     │      │                     │     │
│   │ - 人类可读          │      │ - 向量索引          │     │
│   │ - 可审计回滚        │      │ - FTS 全文搜索      │     │
│   │ - 权威真理          │      │ - 快速检索          │     │
│   └─────────────────────┘      └─────────────────────┘     │
│                                                             │
│   写入 Markdown  ─────────────────>  自动索引到 DB          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**原则**：
- **Markdown 是权威真理** - Git 版本控制，可审计
- **DB 是搜索索引** - 从 Markdown 自动生成，可重建
- **HITL 审批后同时写入** - 保持一致性

### 7.7 知识库目录结构

```
项目根目录/
├── .claude/
│   └── data/
│       ├── capabilities.db      # CLI/API 命令数据库
│       └── knowledge.db         # 知识库 (FTS + Vector)
│
├── .olav/
│   └── knowledge/               # Markdown 权威真理 (Git 版本控制)
│       ├── aliases.md           # 设备别名 → 自动索引到 DB
│       ├── conventions.md       # 命名规范 → 自动索引到 DB
│       └── solutions/           # 成功案例 → 自动索引到 DB
│
├── docs/                         # 外部文档 (仅用于索引)
│   ├── vendor/
│   │   ├── cisco/               # Cisco 文档 (Markdown)
│   │   └── huawei/              # Huawei 文档 (Markdown)
│   ├── wiki/                    # 团队 Wiki
│   └── runbooks/                # 运维手册
│
└── scripts/
    ├── index_knowledge.py       # 索引外部文档
    └── sync_learned_knowledge.py # 同步学习的知识到 DB
```

---
## 第六部分：Data 目录与代码修改

### 6.1 Data 目录结构

当前 `.olav/data/` 包含运行时数据：

```
.olav/data/
├── configs/          # 设备配置备份
├── logs/             # 日志输出
└── reports/          # 生成的报告
```

**迁移决策**：运行时数据保持在 Agent 目录内（`.{agent}/data/`），因为：
1. 与 Agent 绑定，不应共享
2. 应该在 `.gitignore` 中
3. 用户可能需要清理

**更新迁移脚本**：添加 `data/` 目录迁移

### 6.2 需要修改的源代码文件

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `src/olav/tools/storage_tools.py` | 将 `.olav/` 路径改为可配置 | 🔴 高 |
| `src/olav/core/skill_loader.py` | 支持两种 Skill 格式 | 🔴 高 |
| `src/olav/tools/inspection_tools.py` | 使用 Markdown 报告 | 🔴 高 |
| `config/settings.py` | 添加 `agent_dir` 配置项 | 🟡 中 |
| `src/olav/agent.py` | 从配置读取 Agent 目录 | 🟡 中 |

### 6.3 需要修改的测试文件

| 测试文件 | 修改内容 |
|----------|----------|
| `tests/unit/test_skill_loader.py` | 添加 SKILL.md 格式测试 |
| `tests/unit/test_phase5_inspection_tools.py` | 更新为 Markdown 报告测试 |
| `tests/e2e/test_phase2_real.py` | 更新路径引用 |
| `tests/e2e/test_phase3_real.py` | 更新路径引用 |

### 6.4 storage_tools.py 修改方案

```python
# 当前硬编码
ALLOWED_WRITE_DIRS = [
    ".olav/data/configs",
    ".olav/data/logs",
    ...
]

# 修改为配置化
from config.settings import settings

def get_allowed_write_dirs() -> list[str]:
    agent_dir = settings.agent_dir  # 默认 ".olav"
    return [
        f"{agent_dir}/data/configs",
        f"{agent_dir}/data/logs",
        f"{agent_dir}/knowledge/solutions",
        f"{agent_dir}/data/reports",
        f"{agent_dir}/scratch",
    ]
```

### 6.5 skill_loader.py 修改方案

支持两种格式自动检测：

```python
def load_all(self) -> dict[str, Skill]:
    """扫描并加载所有技能 - 支持两种格式."""
    if self._index:
        return self._index

    # Format 1: Claude Code 标准 (skills/*/SKILL.md)
    for skill_dir in self.skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skill = self._parse_skill_header(skill_file)
                if skill:
                    self._index[skill.id] = skill

    # Format 2: OLAV 传统 (skills/*.md)
    for md_file in self.skills_dir.glob("*.md"):
        if md_file.name == "SKILL.md":
            continue  # 已在上面处理
        if md_file.name.startswith("_") or ".draft" in md_file.name:
            continue
        skill = self._parse_skill_header(md_file)
        if skill:
            # 避免覆盖已加载的
            if skill.id not in self._index:
                self._index[skill.id] = skill

    return self._index
```

### 6.6 config/settings.py 添加配置

```python
class Settings(BaseSettings):
    # 现有配置...
    
    # Agent 目录配置（新增）
    agent_dir: str = ".olav"
    agent_name: str = "OLAV"
    
    # Skills 格式（新增）
    skill_format: Literal["auto", "legacy", "claude-code"] = "auto"
```

---

## 第八部分：网络运维知识库方案

### 设计决策

#### 决策 1：统一 KB，不使用 references/

**问题**：Claude Code 标准的 `references/` 模式需要手动维护静态 Markdown 文件，不适合网络运维场景。

**决策**：统一使用知识库 (KB) + `search()` 工具，不往 `references/` 写入知识。

| 方案 | 维护成本 | 搜索能力 | 文档规模 | Claude Code 兼容 |
|------|----------|----------|----------|------------------|
| `references/` 静态文件 | 高（手动同步） | Grep 关键词 | 受 context 限制 | ✅ 原生支持 |
| **统一 KB** | 低（索引一次） | 向量语义 | **无限制** | ✅ 通过 commands/ 桥接 |

#### 决策 2：通过 commands/ 桥接，不使用 MCP

**问题**：MCP 增加了部署复杂度，需要单独运行 MCP 服务器。

**决策**：通过 `.olav/commands/*.py` 桥接脚本暴露工具（与 DESIGN_V0.8.md 一致）。

```
.olav/commands/
├── nornir-execute.py        # Nornir 执行桥接
├── search-capabilities.py   # capabilities.db 查询桥接
├── search-knowledge.py      # knowledge.db 查询桥接
├── list-devices.py          # 设备列表桥接
└── reload-capabilities.py   # 能力重载桥接
```

**Claude Code skill script 调用**：

```markdown
---
name: search-docs
description: Search vendor docs and team wiki
---

Search for: $ARGUMENTS

Execute: `!python .claude/commands/search-knowledge.py "$ARGUMENTS"`
```

#### 决策 3：Agentic 学习的知识统一到 KB

**问题**：Agent 学习的知识分散在多个 Markdown 文件中，搜索效率低。

**决策**：Markdown 文件保留为权威真理（Git 版本控制），但同时自动索引到 `knowledge.db`。

```
学习流程:
1. Agent 请求写入 → HITL 审批
2. 审批通过 → 写入 Markdown (Git 版本控制)
3. 自动触发 → 索引到 knowledge.db (语义搜索)
```

---

### 8.1 网络运维场景分析

网络运维场景下，用户知识库的规模和类型与一般开发场景不同：

| 知识类型 | 典型规模 | 更新频率 | 查询模式 |
|----------|----------|----------|----------|
| 用户 Wiki | 50-500 页 | 频繁 | 关键词 + 语义 |
| Cisco 文档 | 数千页 | 季度 | 命令名、错误码 |
| Huawei 文档 | 数千页 | 季度 | 命令名、告警 ID |
| Juniper 文档 | 数千页 | 季度 | CLI 语法 |
| 运维 Runbook | 100-300 页 | 月度 | 故障场景、处理流程 |
| 网络拓扑文档 | 10-50 页 | 低频 | 设备名、链路 |

**关键挑战**：
- 厂商文档量巨大，无法全部放入上下文
- 查询模式混合：既有精确匹配（`BGP-5-ADJCHANGE`），也有语义搜索（"接口 flapping 怎么排查"）
- 多厂商环境需要跨平台检索

### 8.2 推荐方案：混合检索 (Hybrid Search)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Knowledge Query Architecture                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户查询: "show ip bgp 显示 %BGP-5-ADJCHANGE 错误怎么办"           │
│                          │                                          │
│                          ▼                                          │
│              ┌───────────────────────┐                              │
│              │   Query Preprocessor  │                              │
│              │   - 关键词提取        │                              │
│              │   - 意图分类          │                              │
│              └───────────┬───────────┘                              │
│                          │                                          │
│           ┌──────────────┴──────────────┐                           │
│           │                             │                           │
│           ▼                             ▼                           │
│  ┌─────────────────┐         ┌─────────────────┐                   │
│  │ Keyword Search  │         │ Semantic Search │                   │
│  │ (DuckDB FTS)    │         │ (DuckDB VSS)    │                   │
│  │                 │         │                 │                   │
│  │ - 错误码匹配    │         │ - 语义相似度    │                   │
│  │ - 命令名匹配    │         │ - 故障场景匹配  │                   │
│  │ - 告警 ID 匹配  │         │                 │                   │
│  └────────┬────────┘         └────────┬────────┘                   │
│           │                           │                             │
│           └───────────┬───────────────┘                             │
│                       ▼                                             │
│              ┌───────────────────────┐                              │
│              │   Result Fusion       │                              │
│              │   - RRF 算法合并      │                              │
│              │   - Top-K 截取        │                              │
│              └───────────┬───────────┘                              │
│                          ▼                                          │
│              ┌───────────────────────┐                              │
│              │   Context Builder     │                              │
│              │   - 格式化结果        │                              │
│              │   - 注入 LLM Prompt   │                              │
│              └───────────────────────┘                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.3 DuckDB 实现方案

利用 OLAV 已有的 DuckDB 基础设施，添加知识库支持：

#### 8.3.1 数据库 Schema 扩展

```sql
-- knowledge.sql (添加到 .claude/data/knowledge.db)

-- 知识库来源表
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- 'cisco_ios_xe', 'huawei_vrp', 'user_wiki'
    type TEXT NOT NULL,           -- 'vendor_doc', 'wiki', 'runbook'
    base_path TEXT,               -- 原始文档路径
    version TEXT,                 -- 文档版本
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 知识块表 (文档切分后的块)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES knowledge_sources(id),
    file_path TEXT NOT NULL,      -- 原始文件路径
    chunk_index INTEGER,          -- 块序号
    title TEXT,                   -- 章节标题
    content TEXT NOT NULL,        -- 块内容
    
    -- 元数据
    platform TEXT,                -- 'cisco_ios', 'huawei_vrp', 'juniper_junos'
    doc_type TEXT,                -- 'command_ref', 'config_guide', 'troubleshoot'
    keywords TEXT[],              -- 提取的关键词列表
    
    -- 向量 (使用 DuckDB VSS 扩展)
    embedding FLOAT[1536],        -- OpenAI text-embedding-3-small
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 全文搜索索引
CREATE INDEX IF NOT EXISTS idx_chunks_fts 
ON knowledge_chunks USING FTS(title, content, keywords);

-- 向量搜索索引 (HNSW)
CREATE INDEX IF NOT EXISTS idx_chunks_vector 
ON knowledge_chunks USING HNSW(embedding);
```

#### 8.3.2 合并到现有工具 (推荐方案)

**核心思路**：不创建独立的 `knowledge_tools.py`，而是扩展现有的 `search_capabilities` 工具，添加 `scope` 参数统一搜索能力和知识库。

```python
# src/olav/tools/capabilities.py (扩展现有文件)
"""Capabilities and knowledge search tools for OLAV."""

from typing import Literal
from pathlib import Path

import duckdb
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

from olav.core.database import get_database
from config.settings import settings


@tool
def search(
    query: str,
    scope: Literal["capabilities", "knowledge", "all"] = "all",
    platform: str | None = None,
    limit: int = 10,
) -> str:
    """Unified search for CLI commands, API endpoints, and documentation.

    This is the primary search tool combining:
    - Capabilities: CLI commands and API endpoints from the capability database
    - Knowledge: Vendor docs, user wiki, and runbooks from the knowledge base

    Args:
        query: Search query (command name, error code, or natural language)
        scope: What to search
            - "capabilities": Only CLI commands and API endpoints
            - "knowledge": Only documentation (vendor docs, wiki, runbooks)
            - "all": Search both (default, recommended)
        platform: Filter by platform (e.g., "cisco_ios", "huawei_vrp", "netbox")
        limit: Maximum results per scope (default: 10)

    Returns:
        Combined search results with source attribution

    Examples:
        >>> search("show ip interface", scope="capabilities", platform="cisco_ios")
        "## CLI Commands
        1. show ip interface brief (cisco_ios) - Display interface summary
        2. show ip interface (cisco_ios) - Display detailed interface info
        "

        >>> search("BGP-5-ADJCHANGE", scope="all", platform="cisco_ios")
        "## CLI Commands
        1. show ip bgp summary (cisco_ios) - Display BGP neighbor summary
        
        ## Documentation
        ### BGP Neighbor State Changes (cisco_ios_xe)
        The BGP-5-ADJCHANGE message indicates a BGP neighbor relationship change...
        "

        >>> search("OSPF 邻居建立失败", scope="knowledge")
        "## Documentation
        ### OSPF 故障排查手册 (team_wiki)
        常见原因：1. MTU 不匹配 2. Area ID 不一致...
        "
    """
    results = []
    
    # 1. 搜索 Capabilities (CLI/API)
    if scope in ("capabilities", "all"):
        cap_results = _search_capabilities(query, platform, limit)
        if cap_results:
            results.append("## CLI Commands & APIs\n" + cap_results)
    
    # 2. 搜索 Knowledge (文档)
    if scope in ("knowledge", "all"):
        doc_results = _search_knowledge(query, platform, limit)
        if doc_results:
            results.append("## Documentation\n" + doc_results)
    
    if not results:
        return f"No results found for: {query}"
    
    return "\n\n---\n\n".join(results)


def _search_capabilities(query: str, platform: str | None, limit: int) -> str:
    """Search CLI commands and API endpoints."""
    db = get_database()
    results = db.search_capabilities(query=query, platform=platform, limit=limit)
    
    if not results:
        return ""
    
    output = []
    for i, cap in enumerate(results, 1):
        name = cap["name"]
        plat = cap["platform"]
        desc = cap.get("description", "")
        is_write = cap["is_write"]
        
        line = f"{i}. {name} ({plat})"
        if desc:
            line += f" - {desc}"
        if is_write:
            line += " ⚠️ **REQUIRES APPROVAL**"
        output.append(line)
    
    return "\n".join(output)


def _search_knowledge(query: str, platform: str | None, limit: int) -> str:
    """Hybrid search on knowledge base (FTS + Vector)."""
    db_path = Path(settings.agent_dir) / "data" / "knowledge.db"
    
    if not db_path.exists():
        return ""  # 知识库未初始化
    
    conn = duckdb.connect(str(db_path), read_only=True)
    
    try:
        # FTS 关键词搜索
        fts_sql = f"""
        SELECT id, title, content, platform,
               fts_main_knowledge_chunks.match_bm25(id, '{query}') as score
        FROM knowledge_chunks
        WHERE score IS NOT NULL
        """
        if platform:
            fts_sql += f" AND platform = '{platform}'"
        fts_sql += f" ORDER BY score DESC LIMIT {limit}"
        
        fts_results = conn.execute(fts_sql).fetchall()
        
        # 向量语义搜索 (如果启用)
        vector_results = []
        if settings.enable_embedding:
            embeddings = OpenAIEmbeddings(model=settings.embedding_model)
            query_vec = embeddings.embed_query(query)
            
            vec_sql = f"""
            SELECT id, title, content, platform,
                   array_cosine_similarity(embedding, {query_vec}) as score
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
            """
            if platform:
                vec_sql += f" AND platform = '{platform}'"
            vec_sql += f" ORDER BY score DESC LIMIT {limit}"
            
            vector_results = conn.execute(vec_sql).fetchall()
        
        # RRF 融合
        combined = _rrf_fusion(fts_results, vector_results, limit)
        
        if not combined:
            return ""
        
        output = []
        for title, content, plat in combined:
            output.append(f"### {title} ({plat})\n{content[:500]}...")
        
        return "\n\n".join(output)
        
    finally:
        conn.close()


def _rrf_fusion(fts_results: list, vec_results: list, limit: int, k: int = 60) -> list:
    """Reciprocal Rank Fusion for combining search results."""
    scores = {}
    id_to_data = {}
    
    for rank, row in enumerate(fts_results):
        chunk_id, title, content, plat, _ = row
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank)
        id_to_data[chunk_id] = (title, content, plat)
    
    for rank, row in enumerate(vec_results):
        chunk_id, title, content, plat, _ = row
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank)
        if chunk_id not in id_to_data:
            id_to_data[chunk_id] = (title, content, plat)
    
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:limit]
    return [id_to_data[cid] for cid in sorted_ids]
```

### 8.4 Skill 集成

将知识库搜索能力集成到 `quick-query` 和 `deep-analysis` skill 中，无需单独的工具。

#### 8.4.1 quick-query Skill 更新

```markdown
---
name: quick-query
description: 快速查询网络设备状态，支持设备信息、接口状态、路由表等常见查询
version: 1.1.0
triggers:
  - 查询
  - 查看
  - 显示
  - show
---

# Quick Query Skill

## 查询流程

1. **搜索相关信息**
   - 使用 `search(query, scope="all")` 同时搜索命令和文档
   - 如果查询包含错误码或告警信息，优先查看文档

2. **选择合适的命令**
   - 从搜索结果的 "CLI Commands" 部分选择命令
   - 优先选择 Read-only 命令

3. **执行命令**
   - 使用 `nornir_execute(device, command)` 执行

4. **解读结果**
   - 参考搜索结果的 "Documentation" 部分理解输出
   - 如有异常，搜索相关故障文档

## 示例

用户: "R1 的 BGP 邻居状态"

```
Step 1: search("BGP neighbor status", platform="cisco_ios")
        → CLI: show ip bgp summary, show ip bgp neighbors
        → Docs: BGP Neighbor States 文档 (from knowledge.db)

Step 2: nornir_execute("R1", "show ip bgp summary")
        → 获取 BGP 邻居列表

Step 3: 解读结果，如有异常参考文档
```

## 知识来源

所有参考文档通过 `search()` 工具从 `knowledge.db` 检索，无需手动维护 `references/` 目录。
```

#### 8.4.2 deep-analysis Skill 更新

```markdown
---
name: deep-analysis
description: 深度分析网络故障，包括 BGP/OSPF 邻居问题、接口故障、路由异常等复杂问题排查
version: 1.1.0
triggers:
  - 分析
  - 排查
  - 故障
  - 为什么
  - troubleshoot
---

# Deep Analysis Skill

## 分析流程

### Phase 1: 信息收集

1. **搜索相关知识**
   ```
   search("<故障描述>", scope="all")
   ```
   - 查找相关的排查文档和命令

2. **收集设备信息**
   - 根据搜索结果执行诊断命令
   - 收集日志信息

### Phase 2: 问题定位

1. **参考文档分析**
   - 使用搜索结果中的 Documentation 部分
   - 对照故障现象和文档描述

2. **逐层排查**
   - L1: 物理层 (接口状态、光模块)
   - L2: 数据链路层 (MAC、VLAN、STP)
   - L3: 网络层 (IP、路由、ARP)
   - L4+: 传输层以上 (ACL、NAT)

### Phase 3: 解决方案

1. **搜索解决方案**
   ```
   search("<具体问题> 解决方案", scope="knowledge")
   ```

2. **提供修复建议**
   - 参考团队 runbook
   - 给出具体命令（需要 HITL 审批）

## 示例：BGP 邻居 Down

```
Step 1: search("BGP-5-ADJCHANGE neighbor down", scope="all")
        → Docs: BGP 状态机、常见故障原因
        → CLI: show ip bgp summary, show ip bgp neighbors

Step 2: nornir_execute("R1", "show ip bgp summary")
        → 确认邻居状态

Step 3: search("BGP neighbor stuck in Active state", scope="knowledge")
        → Docs: TCP 179 端口、AS 号配置检查

Step 4: nornir_execute("R1", "show ip bgp neighbors x.x.x.x")
        → 查看详细邻居信息

Step 5: 根据文档给出诊断结论和修复建议
```

## 知识来源

所有故障排查文档通过 `search(query, scope="knowledge")` 从 `knowledge.db` 检索：
- 厂商文档：故障排查指南、协议状态机
- 团队 Wiki：常见问题解决方案、内部 Runbook
```

### 8.5 配置更新

在 `config/settings.py` 中添加知识库相关配置：

```python
class Settings(BaseSettings):
    # 现有配置...
    
    # 知识库配置
    enable_embedding: bool = True
    embedding_model: str = "text-embedding-3-small"
    knowledge_db_path: str = ".claude/data/knowledge.db"
```
### 8.6 索引脚本

```python
# scripts/index_knowledge.py
"""Index vendor documentation and user knowledge into DuckDB."""

import argparse
from pathlib import Path

import duckdb
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_markdown(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split markdown content into chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    )
    return splitter.split_text(content)


def index_directory(
    conn: duckdb.DuckDBPyConnection,
    source_name: str,
    source_type: str,
    directory: Path,
    platform: str | None = None,
):
    """Index all markdown files in a directory."""
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    md_files = list(directory.rglob("*.md"))
    print(f"Indexing {len(md_files)} files from {directory}...")
    
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_markdown(content)
        
        for i, chunk in enumerate(chunks):
            title = chunk.split("\n")[0].lstrip("#").strip()[:100]
            embedding = embeddings.embed_query(chunk)
            
            conn.execute("""
                INSERT INTO knowledge_chunks 
                (file_path, chunk_index, title, content, platform, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [str(md_file), i, title, chunk, platform, embedding])
    
    conn.commit()
    print(f"✅ Indexed {source_name}: {len(md_files)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--platform")
    parser.add_argument("--db", default=".claude/data/knowledge.db")
    
    args = parser.parse_args()
    conn = duckdb.connect(args.db)
    conn.execute("INSTALL vss; LOAD vss;")
    
    index_directory(conn, args.source, "doc", Path(args.path), args.platform)
```

### 8.7 使用示例

```bash
# 索引 Cisco 文档
uv run python scripts/index_knowledge.py \
  --source cisco_ios_xe \
  --path ~/docs/cisco/ \
  --platform cisco_ios

# 索引团队 Wiki
uv run python scripts/index_knowledge.py \
  --source team_wiki \
  --path ~/wiki/network-ops/
```

### 8.8 方案对比总结

| 方案 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **纯 Grep** | <50 文件 | 简单，无依赖 | 无语义理解 |
| **DuckDB FTS** | 50-500 文件 | 快速，无 embedding 成本 | 无语义理解 |
| **混合检索 (推荐)** | 厂商文档 + Wiki | 精确 + 语义 | 需要 embedding |

### 8.9 Embedding 模型选择

| 模型 | 维度 | 成本 | 推荐场景 |
|------|------|------|----------|
| `text-embedding-3-small` | 1536 | $0.02/1M tokens | ✅ 推荐 |
| Ollama `nomic-embed-text` | 768 | 免费本地 | 离线环境 |

**成本估算**: 1000 页文档 ≈ $0.04 一次性索引成本

---

## 第九部分：Claude Code 兼容性完整迁移

> **结论**：完成以下迁移后，将 `.olav` 重命名为 `.claude` 即可在 Claude Code 中使用。

### 9.1 必须完成的结构迁移

#### Step 1: Skill 目录结构转换

```bash
# 当前: .olav/skills/quick-query.md
# 目标: .olav/skills/quick-query/SKILL.md

# 迁移脚本
mkdir -p .olav/skills/quick-query
mv .olav/skills/quick-query.md .olav/skills/quick-query/SKILL.md

# 对每个 skill 重复
for skill in config-backup deep-analysis device-inspection; do
  mkdir -p ".olav/skills/${skill}"
  mv ".olav/skills/${skill}.md" ".olav/skills/${skill}/SKILL.md"
done
```

#### Step 2: Skill Frontmatter 格式修改

**修改前** (OLAV):
```yaml
---
id: quick-query
intent: query
complexity: simple
description: "Simple status query"
examples:
  - "R1 interface status"
---
```

**修改后** (Claude Code):
```yaml
---
name: Quick Query
description: This skill should be used when the user asks to "check device status", "show interface", "query routing table", or needs simple 1-2 command network queries.
version: 1.0.0
---
```

#### Step 3: Commands 格式转换

**转换 Python 桥接脚本为 Markdown 指令**：

```bash
# 当前: .olav/commands/nornir-execute.py (Python)
# 目标: .olav/commands/nornir-execute.md (Markdown)

# 同时保留 Python 脚本到 scripts/ 目录
mkdir -p .olav/scripts
mv .olav/commands/*.py .olav/scripts/
```

**创建新的 Markdown Command**：

```markdown
# .olav/commands/nornir-execute.md
---
description: Execute network command on device via Nornir
argument-hint: [device] [command]
allowed-tools: Bash(python:*)
---

Execute the following network command:

Device: $1
Command: $2

!`python scripts/nornir-execute.py "$1" "$2"`

Parse the output and report:
- Command success/failure
- Key information from output
- Any errors or warnings
```

#### Step 4: 系统指令重命名

```bash
mv .olav/OLAV.md CLAUDE.md
```

### 9.2 可选保留的 OLAV 扩展

以下字段 Claude Code 不识别，但不会报错，可保留供 OLAV Agent 使用：

| 字段 | 用途 | 建议 |
|------|------|------|
| `intent` | OLAV Skill Router 分类 | 保留 |
| `complexity` | OLAV 任务复杂度判断 | 保留 |
| `output.format` | OLAV 报告格式控制 | 保留 |
| `triggers` | OLAV 触发词匹配 | 保留 |

### 9.3 最终目录结构

```
.claude/                              # 从 .olav/ 重命名
├── CLAUDE.md                         # 从 OLAV.md 重命名
├── settings.json                     # 保持不变
├── capabilities.db                   # 保持不变
├── skills/
│   ├── quick-query/
│   │   └── SKILL.md                  # 从 quick-query.md 移动
│   ├── deep-analysis/
│   │   └── SKILL.md
│   ├── device-inspection/
│   │   └── SKILL.md
│   └── config-backup/
│       └── SKILL.md
├── commands/
│   ├── nornir-execute.md             # 新增 Markdown 格式
│   ├── search-capabilities.md
│   ├── list-devices.md
│   └── smart-query.md
├── scripts/                          # 从 commands/*.py 移动
│   ├── nornir-execute.py
│   ├── search-capabilities.py
│   └── ...
├── knowledge/                        # 保持不变
│   ├── aliases.md
│   └── topology.md
├── config/                           # 保持不变
│   └── nornir/
└── data/                             # 运行时数据
    └── knowledge.db
```

### 9.4 验证清单

完成迁移后，验证以下功能：

- [ ] Claude Code 识别 `.claude/` 目录
- [ ] `/nornir-execute R1 "show version"` 命令可执行
- [ ] Skill 在相关对话中自动激活
- [ ] `CLAUDE.md` 系统指令生效
- [ ] `settings.json` 配置加载

---

## 附录 A：格式对照表

### Skill Frontmatter 字段映射

| OLAV 当前 | Claude Code 标准 | 说明 |
|-----------|-----------------|------|
| `id` | `name` | 标题格式 |
| `intent` | (保留) | OLAV 扩展 |
| `complexity` | (保留) | OLAV 扩展 |
| `description` | `description` | 相同 |
| `examples` | `triggers` | 触发词列表 |
| (无) | `version` | 新增，必需 |
| (无) | `output.format` | 新增，markdown/json/table |
| (无) | `output.language` | 新增，zh-CN/en-US/auto |

### 目录映射

| OLAV 路径 | Claude Code 路径 |
|-----------|-----------------|
| `.olav/OLAV.md` | `CLAUDE.md` |
| `.olav/skills/quick-query.md` | `skills/quick-query/SKILL.md` |
| `.olav/knowledge/` | `knowledge/` |
| `.olav/commands/` | `commands/` (桥接脚本) |
| `.olav/settings.json` | `.claude/settings.json` |
| `.olav/data/` | `.claude/data/` (运行时数据) |
| `.olav/inspect_templates/` | (删除，由 Skill 控制) |
| `.olav/reports/` | `reports/` |

---

## 附录 B：完整修改清单

### Phase 1: HTML → Markdown (预计 2 小时)

- [ ] 创建 `src/olav/tools/report_formatter.py`
- [ ] 更新 `inspection_tools.py` 使用新格式化器
- [ ] 添加 Skill `output` frontmatter 字段
- [ ] 更新 `device-inspection.md` 添加输出模板
- [ ] 删除 `.olav/inspect_templates/` 目录
- [ ] 更新 `tests/unit/test_phase5_inspection_tools.py`
- [ ] 测试 Markdown 报告输出

### Phase 2: 目录结构迁移 (预计 3 小时)

- [ ] 将 Skills 转换为 `skills/*/SKILL.md` 格式（每个 skill 独立目录）
- [ ] 移动 `OLAV.md` → `CLAUDE.md`（项目根目录）
- [ ] 将 `commands/*.py` 移动到 `scripts/`
- [ ] 创建新的 `commands/*.md` Markdown 指令文件
- [ ] 更新 `src/olav/core/skill_loader.py` 支持两种格式
- [ ] 更新 `tests/unit/test_skill_loader.py` 添加新格式测试
- [ ] 创建 `data/` 目录用于运行时数据
- [ ] 测试新结构

### Phase 3: Skill Frontmatter 格式迁移 (预计 2 小时)

- [ ] 将 `id` 改为 `name`（标题格式）
- [ ] 添加 `version` 字段
- [ ] 更新 `description` 为 Claude Code 触发格式（包含触发词）
- [ ] 更新 `config/settings.py` 添加 `agent_dir` 配置
- [ ] 更新所有硬编码的 `.olav/` 路径
- [ ] 更新 `src/olav/agent.py` 从配置读取目录
- [ ] 全面测试

### Phase 4: Commands 桥接脚本迁移 (预计 2 小时)

- [ ] 创建 `.olav/commands/nornir-execute.md` (Markdown 指令)
- [ ] 创建 `.olav/commands/search-capabilities.md`
- [ ] 创建 `.olav/commands/list-devices.md`
- [ ] 创建 `.olav/commands/smart-query.md`
- [ ] 创建 `.olav/commands/search-knowledge.md`
- [ ] 移动原 Python 脚本到 `.olav/scripts/`
- [ ] 测试 Claude Code 兼容性

### Phase 5: 兼容性验证 (预计 1 小时)

- [ ] 测试重命名为 `.claude/`
- [ ] 在 Claude Code 中测试 `/nornir-execute` 命令
- [ ] 在 Claude Code 中测试 Skill 自动激活
- [ ] 验证 `CLAUDE.md` 系统指令生效
- [ ] 验证所有功能正常
- [ ] 更新用户文档

### Phase 5: 知识库集成 (预计 4 小时)

#### 5.1 数据库与 Schema
- [ ] 创建 `scripts/knowledge_schema.sql` 数据库 schema（复用 capabilities.db，添加 knowledge 表）
- [ ] 在 `.olav/capabilities.db` 中添加 `knowledge` 表（FTS + Vector）
- [ ] 创建 `scripts/init_knowledge_db.py` 初始化脚本

#### 5.2 Embedding 配置（已存在，无需新增）
> **说明**：Embedding 配置已在 `config/settings.py` 和 `.env` 中统一定义：
> - `EMBEDDING_PROVIDER`: openai | ollama
> - `EMBEDDING_MODEL`: text-embedding-3-small / nomic-embed-text:latest
> - `EMBEDDING_BASE_URL`: 可选的自定义 URL
> - `EMBEDDING_API_KEY`: API 密钥（可复用 LLM_API_KEY）

#### 5.3 工具实现
- [ ] 扩展 `src/olav/tools/capabilities.py` 添加 `search()` 统一搜索工具
- [ ] 创建 `src/olav/core/knowledge_writer.py` 学习知识写入器（HITL 审批后写入）
- [ ] 创建 `src/olav/core/knowledge_indexer.py` 向量化索引器

#### 5.4 索引脚本
- [ ] 创建 `scripts/index_knowledge.py` 批量索引脚本（初始导入厂商文档/Wiki）
- [ ] 实现增量索引（检测新增/修改文件）

#### 5.5 Agentic 学习触发机制
> **问题**：用户上传文档后，如何触发向量化索引？
>
> **方案**：三种触发方式
>
> 1. **手动触发**（推荐初期使用）
>    ```bash
>    uv run python scripts/index_knowledge.py --source user_upload --path ./uploads/
>    ```
>
> 2. **Skill 触发**（Agentic 学习场景）
>    - 当 Agent 学习新知识并写入 `.olav/knowledge/*.md` 后
>    - Agent 调用 `reload_knowledge()` 工具自动重新索引
>    - 类似现有的 `reload_capabilities()` 模式
>
> 3. **Watch 模式**（未来增强）
>    - 后台监控 `.olav/knowledge/` 目录变化
>    - 自动触发增量索引
>    - 适合生产环境持续学习

#### 5.6 知识库文档管理

> **设计原则**：文件即真相（File as Source of Truth）
>
> - Markdown 文件是权威数据源
> - 向量库只是索引，可随时重建
> - 删除 = 删除文件 + 增量同步

**目录结构**：
```
.olav/knowledge/
├── vendor_docs/           # 厂商文档（手动导入）
│   └── cisco_ios_xe/
├── team_wiki/             # 团队 Wiki（手动导入）
│   └── bgp_troubleshooting.md
├── learned/               # Agentic 学习（HITL 后自动写入）
│   └── 2024-01-09_vlan_issue.md
└── user_uploads/          # 用户上传
    └── network_design.md
```

**数据库 Schema**：
```sql
CREATE TABLE knowledge (
    id VARCHAR PRIMARY KEY,
    file_path VARCHAR NOT NULL,      -- 源文件路径（用于同步）
    file_hash VARCHAR NOT NULL,      -- MD5，用于检测变更
    indexed_at TIMESTAMP,
    source VARCHAR,                  -- vendor_doc | wiki | learned | upload
    platform VARCHAR,                -- cisco_ios | juniper_junos | ...
    chunk_index INT,                 -- 分块索引
    content TEXT,
    embedding FLOAT[1536]
);

CREATE INDEX idx_knowledge_file_path ON knowledge(file_path);
```

**增量同步逻辑**：
```python
def sync_knowledge():
    """增量同步：检测新增、修改、删除"""
    current_files = scan_knowledge_dir()
    indexed_files = db.query("SELECT DISTINCT file_path, file_hash FROM knowledge")
    
    # 新增或修改
    for file in current_files:
        if file.path not in indexed_files:
            index_file(file)  # 新增
        elif file.hash != indexed_files[file.path].hash:
            delete_by_path(file.path)  # 删除旧版本
            index_file(file)           # 重新索引
    
    # 检测删除
    for indexed_path in indexed_files:
        if indexed_path not in current_files:
            delete_by_path(indexed_path)  # 清理孤儿记录
```

**用户操作**：
```bash
# 删除文档
rm .olav/knowledge/user_uploads/old_doc.md

# 增量同步（自动检测删除）
uv run python scripts/sync_knowledge.py
# Output: Synced: 0 added, 0 updated, 1 deleted

# 或一键重建（清空后重新索引全部）
uv run python scripts/rebuild_knowledge.py --force
```

#### 5.7 Skill 集成
- [ ] 更新 `skills/quick-query/SKILL.md` 添加知识库使用指导
- [ ] 更新 `skills/deep-analysis/SKILL.md` 添加知识库使用指导

#### 5.8 测试
- [ ] 创建 `tests/unit/test_search_tool.py` 测试统一搜索
- [ ] 测试混合检索功能（FTS + Vector）
- [ ] 测试 Agentic 学习后自动索引
- [ ] 测试 `reload_knowledge()` 触发机制
- [ ] 测试增量同步（新增、修改、删除）

### Phase 6: Commands 桥接脚本 (预计 2 小时)

> **说明**：桥接脚本已部分存在于 `.olav/commands/`，以下标记 ✅ 表示已实现

- [x] 创建 `.olav/commands/nornir-execute.py` Nornir 执行桥接 ✅
- [x] 创建 `.olav/commands/search-capabilities.py` capabilities.db 查询桥接 ✅
- [x] 创建 `.olav/commands/list-devices.py` 设备列表桥接 ✅
- [x] 创建 `.olav/commands/smart-query.py` 智能查询桥接 ✅
- [x] 创建 `.olav/commands/batch-query.py` 批量查询桥接 ✅
- [ ] 创建 `.olav/commands/search-knowledge.py` knowledge 查询桥接（统一 search 入口）
- [ ] 创建 `.olav/commands/reload-knowledge.py` 知识库重新索引桥接
- [ ] 更新 `skills/` 使用 `!python commands/*.py` 调用
- [ ] 测试 Claude Code 兼容性

### Phase 7: 测试套件更新 (预计 3 小时)

> **说明**：重构后需要更新现有测试并添加新测试

#### 7.1 需要更新的现有测试

| 测试文件 | 修改内容 | 优先级 |
|----------|----------|--------|
| `tests/unit/test_skill_loader.py` | 添加 `skills/*/SKILL.md` 格式测试 | 🔴 高 |
| `tests/unit/test_skill_router.py` | 更新 skill 路径引用 | 🔴 高 |
| `tests/unit/test_phase5_inspection_tools.py` | 更新为 Markdown 报告测试（移除 HTML） | 🔴 高 |
| `tests/e2e/test_phase2_real.py` | 更新 `.olav/` 路径为配置化 | 🟡 中 |
| `tests/e2e/test_phase3_real.py` | 更新 `.olav/` 路径为配置化 | 🟡 中 |
| `tests/e2e/test_skill_system_e2e.py` | 适配新目录结构 | 🟡 中 |
| `tests/e2e/test_commands_bridge_e2e.py` | 更新桥接脚本测试 | 🟡 中 |

#### 7.2 需要新增的测试

| 新测试文件 | 测试内容 | 优先级 |
|------------|----------|--------|
| `tests/unit/test_search_tool.py` | 统一搜索工具（capabilities + knowledge） | 🔴 高 |
| `tests/unit/test_knowledge_indexer.py` | 知识库索引（增量同步、删除检测） | 🔴 高 |
| `tests/unit/test_knowledge_writer.py` | Agentic 学习知识写入 | 🟡 中 |
| `tests/unit/test_report_formatter.py` | Markdown 报告格式化 | 🟡 中 |
| `tests/unit/test_agent_dir_config.py` | `agent_dir` 配置化测试 | 🟡 中 |
| `tests/e2e/test_claude_code_compat.py` | Claude Code 兼容性端到端测试 | 🔴 高 |
| `tests/e2e/test_knowledge_e2e.py` | 知识库端到端流程 | 🟡 中 |

#### 7.3 测试更新任务清单

**Unit Tests 更新**：
- [ ] 更新 `test_skill_loader.py` 添加 `skills/*/SKILL.md` 格式加载测试
- [ ] 更新 `test_skill_loader.py` 添加向后兼容性测试（旧格式仍可用）
- [ ] 更新 `test_phase5_inspection_tools.py` 移除 HTML 相关断言
- [ ] 更新 `test_phase5_inspection_tools.py` 添加 Markdown 报告格式断言

**Unit Tests 新增**：
- [ ] 创建 `tests/unit/test_search_tool.py`
  - [ ] 测试 FTS 搜索
  - [ ] 测试 Vector 搜索
  - [ ] 测试混合搜索（FTS + Vector）
  - [ ] 测试 scope 过滤（capabilities/knowledge/all）
- [ ] 创建 `tests/unit/test_knowledge_indexer.py`
  - [ ] 测试新增文件索引
  - [ ] 测试文件修改重新索引
  - [ ] 测试文件删除后孤儿记录清理
  - [ ] 测试 file_hash 变更检测
- [ ] 创建 `tests/unit/test_report_formatter.py`
  - [ ] 测试 Markdown 表格生成
  - [ ] 测试中英文语言切换
  - [ ] 测试 Skill output 配置解析

**E2E Tests 更新**：
- [ ] 更新 `test_phase2_real.py` 使用 `settings.agent_dir`
- [ ] 更新 `test_phase3_real.py` 使用 `settings.agent_dir`
- [ ] 更新 `test_commands_bridge_e2e.py` 添加新桥接脚本测试

**E2E Tests 新增**：
- [ ] 创建 `tests/e2e/test_claude_code_compat.py`
  - [ ] 测试 `.claude/` 目录重命名后功能正常
  - [ ] 测试 Skill 自动发现
  - [ ] 测试 Commands 执行
- [ ] 创建 `tests/e2e/test_knowledge_e2e.py`
  - [ ] 测试完整索引流程
  - [ ] 测试搜索返回结果
  - [ ] 测试 Agentic 学习后自动索引

#### 7.4 测试运行命令

```bash
# 运行全部测试
uv run pytest -v

# 运行特定 Phase 测试
uv run pytest tests/unit/test_skill_loader.py -v
uv run pytest tests/unit/test_search_tool.py -v
uv run pytest tests/e2e/test_claude_code_compat.py -v

# 运行知识库相关测试
uv run pytest tests/ -k "knowledge" -v

# 运行测试并生成覆盖率报告
uv run pytest --cov=src/olav --cov-report=html
```

---

## 附录 C：知识库快速开始

### C.1 初始化知识库

```bash
# 1. 确保 DuckDB VSS 扩展可用
uv run python -c "import duckdb; db = duckdb.connect(); db.execute('INSTALL vss; LOAD vss;')"

# 2. 初始化知识库表（添加到现有 capabilities.db）
uv run python scripts/init_knowledge_db.py
```

### C.2 索引文档

#### 批量索引（初始导入）

```bash
# 索引团队 Wiki
uv run python scripts/index_knowledge.py \
  --source team_wiki \
  --path ./docs/wiki/

# 索引 Cisco 文档（PDF 需先转 Markdown）
pip install marker-pdf  # 或 docling
marker_single cisco-ios-xe-config-guide.pdf ./docs/cisco/

uv run python scripts/index_knowledge.py \
  --source cisco_ios_xe \
  --path ./docs/cisco/ \
  --platform cisco_ios
```

#### 用户上传文档索引

```bash
# 用户上传后手动触发
uv run python scripts/index_knowledge.py \
  --source user_upload \
  --path ./uploads/new_doc.md
```

### C.3 Agentic 学习后自动索引

当 Agent 学习新知识并写入 `.olav/knowledge/*.md` 后，有两种方式触发索引：

#### 方式 1：Agent 主动调用（推荐）

```python
# Skill 中定义：学习完成后调用 reload_knowledge
tools:
  - search              # 统一搜索
  - reload_knowledge    # 重新索引知识库

# Agent 工作流：
# 1. 用户确认学习内容 (HITL)
# 2. 写入 .olav/knowledge/new_knowledge.md
# 3. 调用 reload_knowledge() 触发增量索引
```

#### 方式 2：Commands 桥接脚本

```bash
# Claude Code 调用
!python commands/reload-knowledge.py

# 或在 Skill 中使用
allowed-tools:
  - '/reload-knowledge'
```

### C.4 在 Agent 中使用

```python
from olav.agent import create_olav_agent

agent = create_olav_agent(
    enable_skill_routing=True,
    enable_knowledge=True,  # 启用知识库工具
)

# Agent 会自动使用 search() 查找相关文档
result = await agent.ainvoke({
    "messages": [{"role": "user", "content": "BGP-5-ADJCHANGE 错误怎么排查？"}]
})
```

### C.5 索引触发流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                     知识索引触发方式                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ 手动索引     │    │ Agentic     │    │ Watch 模式  │         │
│  │ (scripts/)  │    │ (HITL后)    │    │ (未来)      │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌─────────────────────────────────────────────────┐           │
│  │           knowledge_indexer.py                   │           │
│  │  • 检测新增/修改文件                              │           │
│  │  • 分块 (chunk) + Embedding                      │           │
│  │  • 写入 capabilities.db.knowledge 表             │           │
│  └─────────────────────────────────────────────────┘           │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────┐           │
│  │           capabilities.db                        │           │
│  │  • capabilities 表 (CLI/API)                     │           │
│  │  • knowledge 表 (文档/Wiki/学习)                 │           │
│  │  • FTS + Vector 索引                             │           │
│  └─────────────────────────────────────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
