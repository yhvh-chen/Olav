#!/usr/bin/env python3
"""Migrate .olav structure to Claude Code Skill standard.

This script transforms the OLAV skill architecture to be compatible with
Claude Code and other Claude Code-compatible agent frameworks.

Usage:
    uv run python scripts/migrate_to_claude_code.py [--agent-name NAME] [--output-dir DIR]

Examples:
    # Default migration (agent name: claude)
    uv run python scripts/migrate_to_claude_code.py
    
    # Custom agent name
    uv run python scripts/migrate_to_claude_code.py --agent-name cursor
    
    # Dry run (preview only)
    uv run python scripts/migrate_to_claude_code.py --dry-run
"""

import argparse
import shutil
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Simple YAML parsing
    frontmatter = {}
    current_key = None
    current_list = []

    for line in frontmatter_text.split("\n"):
        line = line.rstrip()

        # List item
        if line.strip().startswith("- "):
            if current_key:
                current_list.append(line.strip()[2:].strip().strip('"'))
            continue

        # Key-value pair
        if ":" in line and not line.startswith(" "):
            # Save previous list if any
            if current_key and current_list:
                frontmatter[current_key] = current_list
                current_list = []

            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip().strip('"')

            if value:
                frontmatter[current_key] = value
            # If no value, might be start of a list

    # Save final list
    if current_key and current_list:
        frontmatter[current_key] = current_list

    return frontmatter, body


def transform_skill_frontmatter(content: str, skill_name: str) -> str:
    """Transform OLAV frontmatter to Claude Code standard."""
    frontmatter, body = parse_frontmatter(content)

    if not frontmatter:
        return content

    # Build new frontmatter
    new_fm = []

    # Name (convert from id or generate from filename)
    name = skill_name.replace("-", " ").title()
    new_fm.append(f"name: {name}")

    # Description
    if "description" in frontmatter:
        desc = frontmatter["description"]
        new_fm.append(f"description: {desc}")

    # Version (required in Claude Code)
    new_fm.append("version: 1.0.0")

    # Convert examples to triggers (if present)
    if "examples" in frontmatter:
        examples = frontmatter["examples"]
        if isinstance(examples, list):
            # Extract trigger keywords from examples
            triggers = []
            for ex in examples[:5]:  # Max 5 triggers
                # Extract first word as trigger
                words = ex.lower().split()
                if words and words[0] not in triggers:
                    triggers.append(words[0])
            if triggers:
                new_fm.append("triggers:")
                for t in triggers:
                    new_fm.append(f'  - "{t}"')

    # Keep OLAV-specific fields for compatibility
    new_fm.append("")
    new_fm.append("# OLAV compatibility fields")
    if "intent" in frontmatter:
        new_fm.append(f"intent: {frontmatter['intent']}")
    if "complexity" in frontmatter:
        new_fm.append(f"complexity: {frontmatter['complexity']}")

    # Add output configuration
    new_fm.append("")
    new_fm.append("# Output control")
    new_fm.append("output:")
    new_fm.append("  format: markdown")
    new_fm.append("  language: auto")

    new_frontmatter = "\n".join(new_fm)
    return f"---\n{new_frontmatter}\n---\n\n{body}"


def migrate_skills(src_dir: Path, dest_dir: Path, dry_run: bool = False) -> list[str]:
    """Migrate flat skill files to SKILL.md structure."""
    skills_src = src_dir / "skills"
    skills_dest = dest_dir / "skills"
    migrated = []

    if not skills_src.exists():
        return migrated

    for skill_file in skills_src.glob("*.md"):
        skill_name = skill_file.stem
        skill_dir = skills_dest / skill_name

        if dry_run:
            migrated.append(f"  [DRY] {skill_name} → skills/{skill_name}/SKILL.md")
            continue

        skill_dir.mkdir(parents=True, exist_ok=True)

        # Read and transform
        content = skill_file.read_text(encoding="utf-8")
        new_content = transform_skill_frontmatter(content, skill_name)

        # Write as SKILL.md
        (skill_dir / "SKILL.md").write_text(new_content, encoding="utf-8")

        # Create references directory
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        (refs_dir / ".gitkeep").touch()

        migrated.append(f"  ✅ {skill_name} → skills/{skill_name}/SKILL.md")

    return migrated


def migrate_system_prompt(
    src_dir: Path, dest_dir: Path, agent_name: str, dry_run: bool = False
) -> str | None:
    """Move OLAV.md to {AGENT}.md at root."""
    src_file = src_dir / "OLAV.md"
    agent_upper = agent_name.upper()
    dest_file = dest_dir / f"{agent_upper}.md"

    if not src_file.exists():
        return None

    if dry_run:
        return f"  [DRY] OLAV.md → {agent_upper}.md"

    content = src_file.read_text(encoding="utf-8")

    # Update references
    content = content.replace(".olav/", "")
    content = content.replace("OLAV.md", f"{agent_upper}.md")
    content = content.replace("OLAV", agent_upper)

    dest_file.write_text(content, encoding="utf-8")
    return f"  ✅ OLAV.md → {agent_upper}.md"


def migrate_knowledge(src_dir: Path, dest_dir: Path, dry_run: bool = False) -> str | None:
    """Move knowledge to root level."""
    src_knowledge = src_dir / "knowledge"
    dest_knowledge = dest_dir / "knowledge"

    if not src_knowledge.exists():
        return None

    if dry_run:
        return "  [DRY] knowledge/ → knowledge/"

    shutil.copytree(src_knowledge, dest_knowledge, dirs_exist_ok=True)
    return "  ✅ knowledge/ → knowledge/"


def migrate_settings(
    src_dir: Path, dest_dir: Path, agent_name: str, dry_run: bool = False
) -> str | None:
    """Move settings to .{agent}/ directory."""
    src_settings = src_dir / "settings.json"
    agent_dir = dest_dir / f".{agent_name}"

    if not src_settings.exists():
        return None

    if dry_run:
        return f"  [DRY] settings.json → .{agent_name}/settings.json"

    agent_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src_settings, agent_dir / "settings.json")
    return f"  ✅ settings.json → .{agent_name}/settings.json"


def migrate_config(src_dir: Path, dest_dir: Path, dry_run: bool = False) -> str | None:
    """Move config directory."""
    src_config = src_dir / "config"
    dest_config = dest_dir / "config"

    if not src_config.exists():
        return None

    if dry_run:
        return "  [DRY] config/ → config/"

    shutil.copytree(src_config, dest_config, dirs_exist_ok=True)
    return "  ✅ config/ → config/"


def migrate_data(
    src_dir: Path, dest_dir: Path, agent_name: str, dry_run: bool = False
) -> str | None:
    """Move data directory to .{agent}/data/."""
    src_data = src_dir / "data"
    agent_dir = dest_dir / f".{agent_name}"
    dest_data = agent_dir / "data"

    if not src_data.exists():
        return None

    if dry_run:
        return f"  [DRY] data/ → .{agent_name}/data/"

    agent_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_data, dest_data, dirs_exist_ok=True)
    return f"  ✅ data/ → .{agent_name}/data/"


def migrate_reports(src_dir: Path, dest_dir: Path, dry_run: bool = False) -> str | None:
    """Move reports directory."""
    src_reports = src_dir / "reports"
    dest_reports = dest_dir / "reports"

    if not src_reports.exists():
        return None

    if dry_run:
        return "  [DRY] reports/ → reports/"

    shutil.copytree(src_reports, dest_reports, dirs_exist_ok=True)
    return "  ✅ reports/ → reports/"


def create_commands(dest_dir: Path, dry_run: bool = False) -> list[str]:
    """Create slash command stubs."""
    commands_dir = dest_dir / "commands"
    created = []

    if dry_run:
        return ["  [DRY] Would create commands/query.md, commands/inspect.md, commands/diagnose.md"]

    commands_dir.mkdir(parents=True, exist_ok=True)

    # Query command
    query_cmd = """---
description: Query network device status
argument-hint: [device] [query]
allowed-tools: Read, nornir_execute, list_devices, search_capabilities
---

Execute a quick network query.

## Steps
1. Parse device alias from knowledge/aliases.md
2. Use Quick Query skill to find appropriate command
3. Execute command via nornir_execute
4. Return concise, formatted results

## Examples
- /query R1 interface status
- /query all BGP neighbors
- /query S1 version
"""
    (commands_dir / "query.md").write_text(query_cmd, encoding="utf-8")
    created.append("  ✅ commands/query.md")

    # Inspect command
    inspect_cmd = """---
description: Run comprehensive device inspection
argument-hint: [scope]
allowed-tools: Read, nornir_bulk_execute, list_devices, generate_report
---

Run comprehensive L1-L4 inspection on specified devices.

## Steps
1. Parse inspection scope (all, device list, or filter)
2. Use Device Inspection skill for systematic L1-L4 checks
3. Execute all inspection commands in parallel
4. Generate markdown report

## Scope Examples
- /inspect all
- /inspect R1, R2, R3
- /inspect all core routers
- /inspect devices in site:DC1
"""
    (commands_dir / "inspect.md").write_text(inspect_cmd, encoding="utf-8")
    created.append("  ✅ commands/inspect.md")

    # Diagnose command
    diagnose_cmd = """---
description: Diagnose network connectivity issues
argument-hint: [source] [destination]
allowed-tools: Read, nornir_execute, list_devices, search_capabilities
---

Diagnose network connectivity issues between two points.

## Steps
1. Identify source and destination devices/IPs
2. Use Deep Analysis skill for systematic troubleshooting
3. Execute diagnostic commands (ping, traceroute, route checks)
4. Analyze results and provide recommendations

## Examples
- /diagnose R1 to R5
- /diagnose 10.1.1.1 to 10.5.1.1
- /diagnose Server1 cannot reach Database1
"""
    (commands_dir / "diagnose.md").write_text(diagnose_cmd, encoding="utf-8")
    created.append("  ✅ commands/diagnose.md")

    return created


def create_readme(dest_dir: Path, agent_name: str, dry_run: bool = False) -> str | None:
    """Create migration README."""
    if dry_run:
        return "  [DRY] Would create README.md"

    readme = f"""# Claude Code Skill Compatible Structure

This directory contains a Claude Code Skill-compatible agent configuration.

## Directory Structure

```
./
├── {agent_name.upper()}.md              # System prompt
├── .{agent_name}/                   # Agent settings
│   └── settings.json
├── commands/                    # Slash commands
│   ├── query.md                # /query command
│   ├── inspect.md              # /inspect command
│   └── diagnose.md             # /diagnose command
├── skills/                      # Agent skills
│   ├── quick-query/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── device-inspection/
│   │   ├── SKILL.md
│   │   └── references/
│   └── deep-analysis/
│       ├── SKILL.md
│       └── references/
│           └── user-runbooks/   # 📚 User documentation
├── knowledge/                   # Shared knowledge
│   ├── aliases.md
│   ├── conventions.md
│   └── user-docs/              # 📚 User documentation
└── config/                      # Runtime config
    └── nornir/
```

## Usage

### With Claude Code
```bash
# Rename .{agent_name}/ to .claude/
mv .{agent_name}/ .claude/
mv {agent_name.upper()}.md CLAUDE.md
```

### With Cursor
```bash
# Rename .{agent_name}/ to .cursor/
mv .{agent_name}/ .cursor/
mv {agent_name.upper()}.md CURSOR.md
```

### With Custom Agent
```bash
# Rename to your agent name
mv .{agent_name}/ .myagent/
mv {agent_name.upper()}.md MYAGENT.md
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/query [device] [query]` | Quick device status query |
| `/inspect [scope]` | Comprehensive L1-L4 inspection |
| `/diagnose [src] [dst]` | Network connectivity diagnosis |

## Skills

| Skill | When to Use |
|-------|-------------|
| Quick Query | Simple status checks (1-2 commands) |
| Device Inspection | Full health check (L1-L4) |
| Deep Analysis | Complex troubleshooting |

## 📚 Adding Your Own Documentation

### Global Documentation
Place company-wide documentation in `knowledge/user-docs/`:
```bash
cp my-network-guide.md knowledge/user-docs/
```

### Skill-Specific Documentation
Place skill-specific runbooks in `skills/*/references/user-runbooks/`:
```bash
cp bgp-troubleshooting.md skills/deep-analysis/references/user-runbooks/
```

Documents will be automatically available to the agent.
"""
    (dest_dir / "README.md").write_text(readme, encoding="utf-8")
    return "  ✅ README.md"


def create_user_docs_structure(dest_dir: Path, dry_run: bool = False) -> list[str]:
    """Create user documentation directories."""
    created = []

    if dry_run:
        return ["  [DRY] Would create knowledge/user-docs/ and skills/*/references/user-runbooks/"]

    # Global user docs
    user_docs = dest_dir / "knowledge" / "user-docs"
    user_docs.mkdir(parents=True, exist_ok=True)

    readme = """# User Documentation

Place your company-specific documentation here.

## Supported Formats
- Markdown (.md) - Recommended
- Text (.txt)

## Examples
- Network architecture diagrams
- Runbooks and SOPs
- Device inventory lists
- IP address plans

## Usage
Documents placed here will be available to all skills.
Reference them with: `@knowledge/user-docs/your-doc.md`
"""
    (user_docs / "README.md").write_text(readme, encoding="utf-8")
    created.append("  ✅ knowledge/user-docs/README.md")

    # Per-skill user runbooks
    for skill_name in ["deep-analysis", "device-inspection"]:
        runbooks = dest_dir / "skills" / skill_name / "references" / "user-runbooks"
        runbooks.mkdir(parents=True, exist_ok=True)
        (runbooks / ".gitkeep").touch()

        runbook_readme = f"""# User Runbooks for {skill_name.replace('-', ' ').title()}

Place your custom troubleshooting runbooks and documentation here.

These documents will be available when using the {skill_name} skill.

## Example Files
- `bgp-troubleshooting.md` - Custom BGP troubleshooting guide
- `vendor-specific-commands.md` - Vendor-specific command reference
"""
        (runbooks / "README.md").write_text(runbook_readme, encoding="utf-8")
        created.append(f"  ✅ skills/{skill_name}/references/user-runbooks/")

    return created


def main():
    """Run migration."""
    parser = argparse.ArgumentParser(
        description="Migrate .olav to Claude Code Skill standard"
    )
    parser.add_argument(
        "--agent-name",
        default="claude",
        help="Agent name for directory and files (default: claude)",
    )
    parser.add_argument(
        "--output-dir",
        default="claude-code-migration",
        help="Output directory (default: claude-code-migration)",
    )
    parser.add_argument(
        "--source-dir",
        default=".olav",
        help="Source .olav directory (default: .olav)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )

    args = parser.parse_args()

    src_dir = Path(args.source_dir)
    dest_dir = Path(args.output_dir)
    agent_name = args.agent_name.lower()
    dry_run = args.dry_run

    print()
    print("🚀 Migrating to Claude Code Skill Standard")
    print(f"   Source: {src_dir.absolute()}")
    print(f"   Destination: {dest_dir.absolute()}")
    print(f"   Agent Name: {agent_name}")
    if dry_run:
        print("   Mode: DRY RUN (no files will be written)")
    print()

    if not src_dir.exists():
        print(f"❌ Error: Source directory '{src_dir}' does not exist")
        return 1

    # Clean destination (unless dry run)
    if not dry_run:
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir()

    # Run migrations
    print("📁 Migrating components:")

    result = migrate_system_prompt(src_dir, dest_dir, agent_name, dry_run)
    if result:
        print(result)

    results = migrate_skills(src_dir, dest_dir, dry_run)
    for r in results:
        print(r)

    result = migrate_knowledge(src_dir, dest_dir, dry_run)
    if result:
        print(result)

    result = migrate_settings(src_dir, dest_dir, agent_name, dry_run)
    if result:
        print(result)

    result = migrate_config(src_dir, dest_dir, dry_run)
    if result:
        print(result)

    result = migrate_data(src_dir, dest_dir, agent_name, dry_run)
    if result:
        print(result)

    result = migrate_reports(src_dir, dest_dir, dry_run)
    if result:
        print(result)

    results = create_commands(dest_dir, dry_run)
    for r in results:
        print(r)

    results = create_user_docs_structure(dest_dir, dry_run)
    for r in results:
        print(r)

    result = create_readme(dest_dir, agent_name, dry_run)
    if result:
        print(result)

    print()
    if dry_run:
        print("📋 Dry run complete. No files were written.")
        print("   Run without --dry-run to perform migration.")
    else:
        print("✅ Migration complete!")
        print()
        print("📋 Next steps:")
        print(f"   1. Review files in {dest_dir}/")
        print("   2. Copy to your project root")
        print(f"   3. Rename .{agent_name}/ and {agent_name.upper()}.md as needed")
        print()
        print("📝 Quick commands:")
        print("   # For Claude Code:")
        print(f"   cp -r {dest_dir}/* ./")
        print(f"   mv .{agent_name}/ .claude/")
        print(f"   mv {agent_name.upper()}.md CLAUDE.md")

    return 0


if __name__ == "__main__":
    exit(main())
