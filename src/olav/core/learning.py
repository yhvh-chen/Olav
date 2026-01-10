"""Learning Module - Agentic self-learning capabilities for OLAV v0.8.

This module provides functions for the agent to learn from interactions
and update its own knowledge base.

Phase 7: Auto-embedding of solutions to knowledge base for semantic search.
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def save_solution(
    title: str,
    problem: str,
    process: list[str],
    root_cause: str,
    solution: str,
    commands: list[str],
    tags: list[str],
    knowledge_dir: Path = None,
) -> str:
    """Save a successful troubleshooting case to the knowledge base.

    This enables the agent to learn from past successes and build a solutions
    library over time.

    Args:
        knowledge_dir: Directory to save solutions (defaults to agent_dir/knowledge/solutions)

    Args:
        title: Case title (filename-safe)
        problem: Problem description
        process: List of troubleshooting steps
        root_cause: Root cause analysis
        solution: Solution implemented
        commands: Key commands used
        tags: Tags for indexing (with # prefix)
        knowledge_dir: Solutions directory path

    Returns:
        Path to created file

    Example:
        >>> save_solution(
        ...     "crc-errors-r1",
        ...     "Network intermittent packet loss",
        ...     ["1. Check interfaces", "2. Check CRC"],
        ...     "Aging optical module",
        ...     "Replace optical module",
        ...     ["show interfaces counters", "show interfaces transceiver"],
        ...     ["#物理层", "#CRC", "#光模块"]
        ... )
    """
    if knowledge_dir is None:
        from config.settings import settings
        knowledge_dir = Path(settings.agent_dir) / "knowledge" / "solutions"

    knowledge_dir = Path(knowledge_dir)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    # Create filename
    safe_title = title.lower().replace(" ", "-").replace("/", "-")
    filename = f"{safe_title}.md"
    filepath = knowledge_dir / filename

    # Format tags
    tag_line = " ".join(tags) if tags else "#uncategorized"

    # Build markdown content
    content = f"""# 案例: {title}

> **创建时间**: {datetime.now().strftime("%Y-%m-%d")}
> **自动保存**: 由 OLAV Agent 根据成功案例自动生成

## 问题描述
{problem}

## 排查过程
"""

    # Add steps
    for i, step in enumerate(process, 1):
        content += f"{i}. {step}\n"

    content += f"""
## 根因
{root_cause}

## 解决方案
{solution}

## 关键命令
"""

    # Add commands
    for cmd in commands:
        content += f"- {cmd}\n"

    content += f"""
## 标签
{tag_line}

## 相关案例
- 自动关联相似案例待实现
"""

    # Write file
    filepath.write_text(content, encoding="utf-8")

    # Phase 7: Auto-embed solution to knowledge base for semantic search
    _auto_embed_solution(str(filepath))

    return str(filepath)


def _auto_embed_solution(filepath: str) -> None:
    """Auto-embed solution markdown to knowledge base (Phase 7).

    This function is called automatically after save_solution writes a solution
    file. It embeds the solution to the DuckDB vector store for semantic search.

    Args:
        filepath: Path to the solution markdown file

    Phase 7: Learning loop auto-trigger - solutions are automatically indexed
    """
    try:
        from olav.tools.knowledge_embedder import KnowledgeEmbedder

        path = Path(filepath)

        # Only auto-embed solutions in knowledge/solutions/
        if "knowledge/solutions" not in str(path):
            return

        if not path.exists():
            logger.warning(f"Solution file not found: {filepath}")
            return

        # Embed to knowledge base with source_id=2 (solution)
        embedder = KnowledgeEmbedder()
        count = embedder.embed_file(path, source_id=2, platform="solution")

        logger.info(f"✅ Auto-embedded solution {path.name}: {count} chunks")

    except Exception as e:
        # Non-blocking: log warning but don't interrupt solution saving
        logger.warning(f"Auto-embedding failed for solution {filepath}: {e}")


def _auto_embed_aliases(filepath: str) -> None:
    """Auto-embed aliases knowledge file to vector store (Phase 7).

    This function is called automatically after update_aliases modifies the
    aliases file. It re-embeds the entire aliases file for semantic search.

    Args:
        filepath: Path to the aliases.md file

    Phase 7: Learning loop auto-trigger - aliases are automatically updated
    """
    try:
        from olav.tools.knowledge_embedder import KnowledgeEmbedder

        path = Path(filepath)

        # Only auto-embed aliases.md in knowledge/
        if "knowledge/aliases.md" not in str(path):
            return

        if not path.exists():
            logger.warning(f"Aliases file not found: {filepath}")
            return

        # Embed aliases to knowledge base
        embedder = KnowledgeEmbedder()
        count = embedder.embed_file(path, source_id=2, platform="aliases")

        logger.info(f"✅ Auto-embedded aliases {path.name}: {count} chunks")

    except Exception as e:
        # Non-blocking: log warning but don't interrupt alias updates
        logger.warning(f"Auto-embedding failed for aliases {filepath}: {e}")


def update_aliases(
    alias: str,
    actual_value: str,
    alias_type: str,
    platform: str = "unknown",
    notes: str = "",
    aliases_file: Path = None,
) -> bool:
    """Update the aliases knowledge base with a new alias.

    Args:
        aliases_file: Path to aliases file (defaults to agent_dir/knowledge/aliases.md)
        alias: The alias (e.g., "核心路由器")
        actual_value: What it maps to (e.g., "R1, R2, R3, R4")
        alias_type: Type of alias (device, interface, vlan, etc.)
        platform: Platform if applicable
        notes: Additional notes
        aliases_file: Path to aliases.md

    Returns:
        True if successful, False otherwise

    Example:
        >>> update_aliases(
        ...     "新交换机",
        ...     "SW4",
        ...     "device",
        ...     "cisco_ios",
        ...     "三层交换机"
        ... )
    """
    if aliases_file is None:
        from config.settings import settings
        aliases_file = Path(settings.agent_dir) / "knowledge" / "aliases.md"

    aliases_file = Path(aliases_file)

    try:
        content = aliases_file.read_text(encoding="utf-8")

        # Parse existing aliases
        in_table = False
        table_end = 0
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if "| 别名 |" in line:
                in_table = True
            elif in_table and line.startswith("|---"):
                table_end = i + 1
                break

        # Format new entry
        new_entry = f"| {alias} | {actual_value} | {alias_type} | {platform} | {notes} |"

        # Insert into table
        if table_end > 0:
            lines.insert(table_end, new_entry)
            updated_content = "\n".join(lines)
            aliases_file.write_text(updated_content, encoding="utf-8")
            # Phase 7: Auto-embed updated aliases
            _auto_embed_aliases(str(aliases_file))
            return True
        else:
            # No table found, append to end
            new_content = content + f"\n{new_entry}\n"
            aliases_file.write_text(new_content, encoding="utf-8")
            # Phase 7: Auto-embed updated aliases
            _auto_embed_aliases(str(aliases_file))
            return True

    except Exception as e:
        print(f"Error updating aliases: {e}")
        return False


def learn_from_interaction(
    query: str,
    response: str,
    success: bool,
    knowledge_dir: Path = None,
) -> dict[str, str]:
    """Analyze an interaction and extract learnings.

    This is a simplified learning function. A more sophisticated version
    would use LLM-based analysis to extract structured learnings.

    Args:
        query: The user's query
        response: The agent's response
        success: Whether the interaction was successful
        knowledge_dir: Knowledge base directory (defaults to agent_dir/knowledge)

    Returns:
        Dictionary with actions taken:
        - "saved_solution": Path if saved
        - "updated_aliases": True if updated
        - "learnings": Count of learnings extracted
    """
    if knowledge_dir is None:
        from config.settings import settings
        knowledge_dir = Path(settings.agent_dir) / "knowledge"

    actions = {}
    learnings = 0

    # Check if this should be a solution case
    if success and any(term in query for term in ["故障", "问题", "不通", "错误", "慢"]):
        # Would require LLM to properly extract structured data
        # For now, just note that we should save
        learnings += 1
        actions["should_save_solution"] = True

    # Check for alias mentions
    if "是" in query or "是指" in query:
        learnings += 1
        actions["should_update_aliases"] = True

    actions["learnings"] = str(learnings)

    return actions


def get_learning_guidance() -> str:
    """Get learning guidance for the system prompt.

    Returns:
        Formatted learning instructions
    """
    return """## 学习行为 (Self-Learning)

你是OLAV,可以从成功案例中学习的AI助手。

### 自动学习场景

**1. 学习设备别名**
当用户澄清别名含义时:
- User: "核心交换机是哪台设备?"
- User: "核心交换机是R1和R2"
- Agent: update_aliases("核心交换机", "R1, R2", "device")

**2. 保存成功案例**
解决重要问题后,自动保存到knowledge/solutions/:
- 问题描述和症状
- 排查过程
- 根因分析
- 解决方案
- 关键命令
- 标签(便于检索)

**3. 完善技能模式**
发现可复用的排查模式后,更新skills/*.md:
- 添加新的故障场景
- 完善排查步骤
- 提供更多示例

### 学习原则

- ✅ **主动积累**: 成功后立即记录
- ✅ **结构化**: 使用标准格式便于后续检索
- ✅ **可验证**: 保存的信息可以被验证
- ⚠️ **谨慎写入**: 重大写入前仍需用户确认

### 不学习的场景

- ❌ 不学习危险操作
- ❌ 不学习临时命令
- ❌ 不学习用户特定偏好(除非明确要求)

### 知识库权限

你可以读写:
- `agent_dir/knowledge/aliases.md` (设备别名)
- `agent_dir/knowledge/solutions/*.md` (案例库)
- `agent_dir/skills/*.md` (技能模式)

你应该谨慎:
- `agent_dir/imports/` (能力定义 - 由人类维护)
- `.env` (敏感配置 - 不可访问)
- Root CLAUDE.md (核心规则 - 由人类维护)
"""


def suggest_solution_filename(
    problem_type: str,
    device: str = "",
    symptom: str = "",
) -> str:
    """Suggest a filename for a solution case.

    Args:
        problem_type: Type of problem (e.g., "CRC", "BGP")
        device: Device name (optional)
        symptom: Symptom description (optional)

    Returns:
        Suggested filename (without .md extension)

    Examples:
        >>> suggest_solution_filename("CRC", "R1", "optical power")
        'crc-errors-r1-optical-power'
        >>> suggest_solution_filename("OSPF", "", "timer mismatch")
        'ospf-timer-mismatch'
    """
    parts = [problem_type.lower()]

    if device:
        parts.append(device.lower())

    if symptom and len(symptom) > 0:
        # Simplify symptom
        symptom_simple = symptom.lower().replace(" ", "-")[:30]
        parts.append(symptom_simple)

    return "-".join(parts)
