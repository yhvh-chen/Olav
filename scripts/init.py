#!/usr/bin/env python
"""OLAV Initialization Script - One-time setup for all components.

This script initializes:
1. .olav/settings.json - Agent configuration (from defaults)
2. .olav/knowledge/aliases.md - Device aliases (from nornir hosts.yaml)
3. .olav/capabilities.db - Command whitelist database
4. .olav/data/knowledge.db - Knowledge base (empty, ready for indexing)

Usage:
    uv run python scripts/init.py           # Initialize all
    uv run python scripts/init.py --force   # Overwrite existing files
    uv run python scripts/init.py --check   # Check status only
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()


def init_settings(olav_dir: Path, force: bool = False) -> bool:
    """Generate .olav/settings.json from .env values with fallback to defaults.

    Args:
        olav_dir: Path to .olav directory
        force: Overwrite existing file

    Returns:
        True if created/updated, False if skipped
    """
    import os

    settings_file = olav_dir / "settings.json"

    if settings_file.exists() and not force:
        print("  ⏭️  settings.json already exists (use --force to overwrite)")
        return False

    # Read values from .env (already loaded by load_dotenv() in main)
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL_NAME", "gpt-4o")
    llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    # Settings structure with values from .env
    settings: dict[str, object] = {
        "agent": {
            "name": "OLAV",
            "description": "Network Operations AI Assistant",
            "version": "0.8",
        },
        "llm": {
            "provider": llm_provider,
            "model": llm_model,
            "temperature": llm_temperature,
            "max_tokens": llm_max_tokens,
        },
        "cli": {"banner": "default", "showBanner": True},
        "diagnosis": {
            "requireApprovalForMicroAnalysis": True,
            "autoApproveIfConfidenceBelow": 0.5,
        },
        "execution": {
            "useTextFSM": True,
            "textFSMFallbackToRaw": True,
            "enableTokenStatistics": True,
        },
        "learning": {"autoSaveSolutions": False, "autoLearnAliases": True},
        "subagents": {"enabled": True},
    }

    # Write settings.json
    settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ Created settings.json (from .env: {llm_provider}/{llm_model})")

    return True


def init_aliases_from_nornir(olav_dir: Path, force: bool = False) -> bool:
    """Generate .olav/knowledge/aliases.md from nornir hosts.yaml.

    Args:
        olav_dir: Path to .olav directory
        force: Overwrite existing file

    Returns:
        True if created/updated, False if skipped
    """
    aliases_file = olav_dir / "knowledge" / "aliases.md"
    hosts_file = olav_dir / "config" / "nornir" / "hosts.yaml"

    if aliases_file.exists() and not force:
        print("  ⏭️  aliases.md already exists (use --force to overwrite)")
        return False

    if not hosts_file.exists():
        print("  ⚠️  hosts.yaml not found, creating empty aliases.md template")
        hosts_data = {}  # type: ignore[assignment]
    else:
        try:
            import yaml

            loaded = yaml.safe_load(hosts_file.read_text(encoding="utf-8"))
            hosts_data = loaded if isinstance(loaded, dict) else {}  # type: ignore[assignment]
            print(f"  📖 Loaded {len(hosts_data)} devices from hosts.yaml")  # type: ignore[arg-type]
        except ImportError:
            print("  ⚠️  PyYAML not installed, creating empty aliases.md template")
            hosts_data = {}  # type: ignore[assignment]
        except Exception as e:
            print(f"  ⚠️  Error reading hosts.yaml: {e}")
            hosts_data = {}  # type: ignore[assignment]

    # Build aliases markdown
    content = """# Device Aliases

Agent should consult this file before executing commands to convert user-provided aliases to actual device names, IPs, or interfaces.

## Instructions
- When user mentions these aliases, automatically replace them with actual values
- Supports multiple types: device names, IP addresses, interface names, VLANs, etc.
- If user uses a new alias, ask for clarification and then update this file

## Alias Table

| Alias | Actual Value | Type | Platform | Notes |
|-------|--------------|------|----------|-------|
"""

    # Generate aliases from hosts.yaml
    for hostname, host_data in hosts_data.items():  # type: ignore[union-attr]
        if not isinstance(host_data, dict):
            continue

        ip: str = str(host_data.get("hostname") or "")  # type: ignore[arg-type]
        platform: str = str(host_data.get("platform") or "unknown")  # type: ignore[arg-type]
        data_val = host_data.get("data")  # type: ignore[attr-defined]
        data: dict[str, object] = data_val if isinstance(data_val, dict) else {}  # type: ignore[assignment]
        role_val = data.get("role")  # type: ignore[attr-defined]
        role: str = str(role_val) if role_val else ""  # type: ignore[arg-type]
        site_val = data.get("site")  # type: ignore[attr-defined]
        site: str = str(site_val) if site_val else ""  # type: ignore[arg-type]
        notes = f"{role}@{site}" if role and site else role or site or ""

        # Add hostname → IP alias
        content += f"| {hostname} | {ip} | device | {platform} | {notes} |\n"

        # Add custom aliases from data.aliases
        aliases_val = data.get("aliases")  # type: ignore[attr-defined]
        aliases: list[object] = aliases_val if isinstance(aliases_val, list) else []  # type: ignore[assignment]
        for alias in aliases:
            alias_str = str(alias)
            content += (
                f"| {alias_str} | {hostname} | device | {platform} | alias for {hostname} |\n"
            )

    content += """
## Usage Examples

### Example 1: Device Alias
User: "Check R1 CPU usage"
Agent Parsing:
- Alias: "R1" → 192.168.100.101
- Execute: nornir_execute("R1", "show processes cpu")

### Example 2: Natural Language
User: "Check the border router status"
Agent Parsing:
- Alias: "border-router-1" → R1
- Execute: nornir_execute("R1", "show version")

## Notes
- Aliases are auto-generated from hosts.yaml during init
- Agent can learn new aliases during conversations
- Run `uv run python scripts/init.py --force` to regenerate from hosts.yaml
"""

    # Ensure directory exists
    aliases_file.parent.mkdir(parents=True, exist_ok=True)
    aliases_file.write_text(content, encoding="utf-8")
    print(f"  ✅ Created aliases.md with {len(hosts_data)} device entries")  # type: ignore[arg-type]

    return True


def init_capabilities(olav_dir: Path, reload: bool = False) -> bool:
    """Initialize capabilities database from whitelist files.

    Args:
        olav_dir: Path to .olav directory
        reload: If True, delete and reload all commands

    Returns:
        True if initialized successfully
    """
    from olav.core.database import get_database

    db = get_database()

    # Check if already initialized
    try:
        result = db.conn.execute("SELECT COUNT(*) as count FROM capabilities").fetchall()
        count = result[0][0]
        if count > 0 and not reload:
            print(f"  ⏭️  capabilities.db already has {count} entries")
            return False
    except Exception as e:
        print(f"     Error accessing capabilities.db: {e}")

    if reload:
        print("  🔄 Reloading capabilities (deleting old entries)...")
        try:
            db.conn.execute("DELETE FROM capabilities WHERE cap_type = 'command'")
            db.conn.commit()
            print("     Cleared existing command capabilities")
        except Exception as e:
            print(f"     Warning: Could not clear capabilities: {e}")

    print("  🔄 Loading capabilities from whitelist files...")

    # Load whitelist files
    whitelist_dir = olav_dir / "imports" / "commands"
    total_loaded = 0

    if whitelist_dir.exists():
        for platform_file in whitelist_dir.glob("*.txt"):
            platform = platform_file.stem

            commands: list[str] = []
            for line in platform_file.read_text().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    commands.append(line)

            # Load into database
            count = 0
            for cmd in commands:
                try:
                    db.insert_capability(
                        cap_type="command",
                        platform=platform,
                        name=cmd,
                        source_file=str(platform_file),
                        is_write=False,
                    )
                    count += 1
                except Exception as e:
                    print(f"     Warning parsing {cmd}: {e}")

            print(f"     Loaded {count} commands for {platform}")
            total_loaded += count

    print(f"  ✅ Loaded {total_loaded} total capabilities")
    return True


def init_knowledge_db(olav_dir: Path) -> bool:
    """Initialize knowledge database schema.

    Args:
        olav_dir: Path to .olav directory

    Returns:
        True if initialized successfully
    """
    from olav.core.database import init_knowledge_db as _init_knowledge_db

    db_path = olav_dir / "data" / "knowledge.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        print("  ⏭️  knowledge.db already exists")
        return False

    _init_knowledge_db()
    print("  ✅ Created knowledge.db schema")
    return True


def init_directories(olav_dir: Path) -> None:
    """Ensure all required directories exist.

    Args:
        olav_dir: Path to .olav directory
    """
    directories = [
        olav_dir / "knowledge" / "solutions",
        olav_dir / "data",
        olav_dir / "reports",
        olav_dir / "scratch",
        olav_dir / "skills",
        olav_dir / "commands",
        olav_dir / "imports" / "commands",
        olav_dir / "imports" / "apis",
        olav_dir / "config" / "nornir",
    ]

    for dir_path in directories:
        dir_path.mkdir(parents=True, exist_ok=True)


def check_status(olav_dir: Path) -> None:
    """Check initialization status of all components.

    Args:
        olav_dir: Path to .olav directory
    """
    print("\n📋 OLAV Initialization Status")
    print("=" * 50)

    # Check settings.json
    settings_file = olav_dir / "settings.json"
    if settings_file.exists():
        print("✅ settings.json exists")
    else:
        print("❌ settings.json missing")

    # Check aliases.md
    aliases_file = olav_dir / "knowledge" / "aliases.md"
    if aliases_file.exists():
        print("✅ aliases.md exists")
    else:
        print("❌ aliases.md missing")

    # Check capabilities.db
    cap_db = olav_dir / "capabilities.db"
    if cap_db.exists():
        try:
            from olav.core.database import get_database

            db = get_database()
            result = db.conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()
            if result is not None:
                print(f"✅ capabilities.db exists ({result[0]} entries)")
            else:
                print("✅ capabilities.db exists")
        except Exception as e:
            print(f"⚠️  capabilities.db exists but error: {e}")
    else:
        print("❌ capabilities.db missing")

    # Check knowledge.db
    knowledge_db = olav_dir / "data" / "knowledge.db"
    if knowledge_db.exists():
        print("✅ knowledge.db exists")
    else:
        print("❌ knowledge.db missing")

    # Check hosts.yaml
    hosts_file = olav_dir / "config" / "nornir" / "hosts.yaml"
    if hosts_file.exists():
        print("✅ hosts.yaml exists")
    else:
        print("⚠️  hosts.yaml missing (copy from hosts.yaml.example)")

    print("=" * 50)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize OLAV environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python scripts/init.py                  # Initialize all components
    uv run python scripts/init.py --force          # Overwrite existing files
    uv run python scripts/init.py --check          # Check status only
    uv run python scripts/init.py --reload-commands # Reload commands from whitelists
        """,
    )
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--check", "-c", action="store_true", help="Check status only, don't initialize"
    )
    parser.add_argument(
        "--reload-commands",
        "-r",
        action="store_true",
        help="Reload commands from whitelist files (deletes and re-imports)",
    )
    parser.add_argument(
        "--olav-dir",
        type=Path,
        default=project_root / ".olav",
        help="Path to .olav directory",
    )

    args = parser.parse_args()
    olav_dir = args.olav_dir

    if args.check:
        check_status(olav_dir)
        return

    print("\n🚀 OLAV Initialization")
    print(f"   Directory: {olav_dir}")
    print(f"   Reload Commands: {args.reload_commands}")
    print(f"   Force: {args.force}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Ensure directories exist
    print("\n📁 Creating directories...")
    init_directories(olav_dir)
    print("  ✅ All directories ready")

    # Initialize settings.json
    print("\n⚙️  Initializing settings.json...")
    init_settings(olav_dir, args.force)

    # Initialize aliases.md from nornir
    print("\n📝 Initializing aliases.md from nornir...")
    init_aliases_from_nornir(olav_dir, args.force)

    # Initialize capabilities database
    print("\n🗃️  Initializing capabilities.db...")
    init_capabilities(olav_dir, reload=args.reload_commands)

    # Initialize knowledge database
    print("\n📚 Initializing knowledge.db...")
    init_knowledge_db(olav_dir)

    print("\n" + "=" * 50)
    print("✅ OLAV initialization complete!")
    print("\nNext steps:")
    print("  1. Edit .olav/config/nornir/hosts.yaml with your devices")
    print("  2. Run: uv run python scripts/init.py --reload-commands  (after adding commands)")
    print("  4. Run: uv run python scripts/init.py --force  (to regenerate aliases)")
    print("  3. Run: uv run olav.py  (to start the agent)")


if __name__ == "__main__":
    main()
