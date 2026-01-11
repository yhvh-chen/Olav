"""Slash Commands - Quick command system for OLAV CLI.

Provides fast, dedicated commands for common operations.
Commands are prefixed with '/' (e.g., /devices, /help).
"""

from collections.abc import Callable

# Registry for slash commands
SLASH_COMMANDS: dict[str, Callable] = {}


def register_command(name: str) -> Callable:
    """Decorator to register a slash command.

    Args:
        name: Command name (without / prefix)

    Returns:
        Decorator function

    Example:
        @register_command("devices")
        def cmd_devices(args: str) -> str:
            return "Device list..."
    """

    def decorator(func: Callable) -> Callable:
        SLASH_COMMANDS[name] = func
        return func

    return decorator


async def execute_command(
    full_command: str,
    agent=None,
    memory=None,
) -> str | None:
    """Execute a slash command.

    Args:
        full_command: Full command string (e.g., "/devices core")
        agent: OLAV agent instance (optional)
        memory: Agent memory manager (optional)

    Returns:
        Command output string

    Raises:
        EOFError: If /quit or /exit command is executed
    """
    full_command = full_command.strip()

    # Must start with /
    if not full_command.startswith("/"):
        raise ValueError(f"Not a slash command: {full_command}")

    # Parse command and args
    parts = full_command[1:].split(None, 1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    # Look up command
    if cmd_name not in SLASH_COMMANDS:
        return f"Unknown command: /{cmd_name}. Type /help for available commands."

    # Execute command
    try:
        func = SLASH_COMMANDS[cmd_name]

        # Check if function is async
        import inspect

        if inspect.iscoroutinefunction(func):
            # Call async function directly (we're already in async context)
            result = await func(args)
        else:
            result = func(args)
        return result
    except EOFError:
        raise
    except Exception as e:
        return f"Error executing /{cmd_name}: {str(e)}"


# =============================================================================
# Slash Command Implementations
# =============================================================================


@register_command("devices")
async def cmd_devices(args: str) -> str:
    """List devices or filter devices.

    Usage:
        /devices [filter]

    Examples:
        /devices              - List all devices
        /devices role:core    - List core devices
        /devices site:DC1     - List devices in DC1
    """
    from olav.tools.network import list_devices

    filter_expr = args.strip() if args else None
    try:
        # list_devices is a LangChain StructuredTool, use .invoke()
        if filter_expr:
            # Parse filter like "role:core" into kwargs
            if ":" in filter_expr:
                key, value = filter_expr.split(":", 1)
                result = list_devices.invoke({key.strip(): value.strip()})
            else:
                # Treat as alias search
                result = list_devices.invoke({"alias": filter_expr})
        else:
            result = list_devices.invoke({})
        return result
    except Exception as e:
        return f"Error listing devices: {str(e)}"


@register_command("skills")
async def cmd_skills(args: str) -> str:
    """List skills or view skill details.

    Usage:
        /skills [name]

    Examples:
        /skills           - List all skills
        /skills health    - Show health-check skill details
    """
    from olav.core.skill_loader import get_skill_loader

    loader = get_skill_loader()

    if args:
        # Show specific skill
        skill_name = args.strip()
        skill = loader.get(skill_name)
        if skill:
            return f"Skill: {skill.name}\n\n{skill.content}"
        else:
            return f"Skill '{skill_name}' not found"
    else:
        # List all skills
        skills = loader.load_all()
        output = []
        for skill_name, skill in skills.items():
            status = "✅" if skill_name.startswith("_") is False else "❌"
            output.append(f"{status} {skill_name}: {skill.description}")
        return "\n".join(output)


@register_command("inspect")
async def cmd_inspect(args: str) -> str:
    """Run quick inspection on devices.

    Usage:
        /inspect [scope] [--layer L1|L2|L3|L4|all] [--report]

    Examples:
        /inspect all
        /inspect R1, R2, R5
        /inspect role:core --layer L3
        /inspect all --report

    Layers:
        L1    - Physical layer (interfaces, inventory)
        L2    - Data link (VLANs, STP, MAC)
        L3    - Network (routing, OSPF, BGP)
        L4    - Transport (CPU, memory, errors)
        all   - All layers (default)
    """
    import subprocess
    import sys
    from pathlib import Path

    try:
        from config.settings import settings

        # Use network_inspect.py to avoid shadowing Python's built-in inspect module
        inspect_script = Path(settings.agent_dir) / "commands" / "network_inspect.py"

        cmd_args = args.split() if args else ["all"]
        result = subprocess.run(
            [sys.executable, str(inspect_script)] + cmd_args,
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return output if output.strip() else "Inspection complete."

    except Exception as e:
        return f"Error executing inspect: {str(e)}"


@register_command("query")
async def cmd_query(args: str) -> str:
    """Execute quick network query.

    Usage:
        /query [device] [query]

    Examples:
        /query R1 interface status
        /query S1 version
        /query R1 bgp neighbors
        /query all cpu

    Common Queries:
        interface status   - Show interface status
        version           - Show device version
        bgp               - Show BGP summary
        ospf              - Show OSPF neighbors
        route             - Show routing table
        vlan              - Show VLAN configuration
        cpu               - Show CPU usage
        memory            - Show memory stats
    """
    import subprocess
    import sys
    from pathlib import Path

    if not args:
        return "Usage: /query <device> <query>\nExample: /query R1 interface status"

    try:
        from config.settings import settings

        query_script = Path(settings.agent_dir) / "commands" / "query.py"

        result = subprocess.run(
            [sys.executable, str(query_script)] + args.split(),
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return output if output.strip() else "Query complete."

    except Exception as e:
        return f"Error executing query: {str(e)}"


@register_command("reload")
async def cmd_reload(args: str) -> str:
    """Reload skills and capabilities.

    Usage:
        /reload
    """
    try:
        from olav.core.skill_loader import get_skill_loader

        loader = get_skill_loader()
        loader.reload()
        return "✅ Skills and capabilities reloaded successfully"
    except Exception as e:
        return f"Error reloading: {str(e)}"


@register_command("clear")
async def cmd_clear(args: str) -> str:
    """Clear session memory.

    Usage:
        /clear
    """
    try:
        from olav.cli.memory import AgentMemory

        memory = AgentMemory()
        memory.clear()
        return "✅ Session memory cleared"
    except Exception as e:
        return f"Error clearing memory: {str(e)}"


@register_command("history")
async def cmd_history(args: str) -> str:
    """Show command history statistics.

    Usage:
        /history
    """
    try:
        from olav.cli.memory import AgentMemory

        memory = AgentMemory()
        stats = memory.get_stats()
        return f"""Session History Stats:
  Total Messages: {stats["total_messages"]}
  User Messages: {stats["user_messages"]}
  Assistant Messages: {stats["assistant_messages"]}
  Tool Messages: {stats["tool_messages"]}
  Memory File: {stats["memory_file"]}"""
    except Exception as e:
        return f"Error showing history: {str(e)}"


@register_command("help")
async def cmd_help(args: str) -> str:
    """Show help information.

    Usage:
        /help [command]
    """
    if args:
        # Show specific command help
        cmd_name = args.strip().lstrip("/")
        if cmd_name in SLASH_COMMANDS:
            func = SLASH_COMMANDS[cmd_name]
            doc = func.__doc__ or "No documentation available"
            return f"Help for /{cmd_name}:\n\n{doc}"
        else:
            return f"Unknown command: /{cmd_name}"
    else:
        # Show general help
        return """OLAV CLI Commands:

  Workflow Commands:
    /backup [filter] [type] [options]  - Backup device configurations
    /analyze [src] [dst] [options]     - Analyze network path
    /inspect [scope] [--layer] [--report] - Device inspection
    /query [device] [query]            - Quick device query
    /search <query>                    - Web search for troubleshooting

  Device Commands:
    /devices [filter]   - List devices (e.g., /devices role:core)
    /skills [name]      - List skills or view skill details

  Session Commands:
    /reload             - Reload skills and capabilities
    /clear              - Clear session memory
    /history            - Show session statistics
    /help [command]     - Show this help or command-specific help
    /quit, /exit        - Exit OLAV

  Input Features:
    @file.txt           - Include file content in your query
    !command            - Execute shell command
    Multi-line          - Press Enter twice to submit

  Examples:
    olav> /backup role:core running
    olav> /analyze R1 R3 --error "packet loss"
    olav> /inspect all --layer L3
    olav> /query R1 bgp neighbors
    olav> /search cisco bgp flapping troubleshooting
    olav> @config.txt analyze this configuration
    olav> !ping 8.8.8.8
"""


@register_command("backup")
async def cmd_backup(args: str) -> str:
    """Execute backup workflow.

    Usage:
        /backup [filter] [type] [--commands "cmd1,cmd2"]

    Examples:
        /backup role:core running
        /backup site:lab all
        /backup R1,R2 running
        /backup all custom --commands "show version"

    Filters:
        role:core    - Devices with role="core"
        site:lab     - Devices at site="lab"
        group:test   - Devices in "test" group
        R1,R2,R3     - Specific device list
        all          - All devices

    Backup Types:
        running      - show running-config
        startup      - show startup-config
        all          - Both running and startup
        custom       - Use --commands parameter
    """
    import subprocess
    import sys
    from pathlib import Path

    try:
        from config.settings import settings

        backup_script = Path(settings.agent_dir) / "commands" / "backup.py"
        result = subprocess.run(
            [sys.executable, str(backup_script)] + args.split(),
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return output

    except Exception as e:
        return f"Error executing backup: {str(e)}"


@register_command("analyze")
async def cmd_analyze(args: str) -> str:
    """Execute network path analysis workflow.

    Usage:
        /analyze [source] [destination] [--error "desc"] [--plan] [--interactive]

    Examples:
        /analyze R1 R3
        /analyze R1 R3 --error "high latency"
        /analyze R1 R3 --plan
        /analyze R1 R3 --interactive

    Performs deep analysis using:
        - Phase 1: Macro analysis (path tracing, fault domain)
        - Phase 2: Micro analysis (layer-by-layer troubleshooting)
        - Phase 3: Synthesis (root cause, recommendations)
    """
    import subprocess
    import sys
    from pathlib import Path

    try:
        from config.settings import settings

        analyze_script = Path(settings.agent_dir) / "commands" / "analyze.py"
        result = subprocess.run(
            [sys.executable, str(analyze_script)] + args.split(),
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return output

    except Exception as e:
        return f"Error executing analyze: {str(e)}"


@register_command("search")
async def cmd_search(args: str) -> str:
    """Search the web for troubleshooting information.

    Usage:
        /search <query>
        /search bgp flapping cisco
        /search "ospf neighbor stuck in exstart"

    Examples:
        /search cisco ios xr bgp community filtering
        /search juniper mx series interface crc errors
        /search arista eos vxlan troubleshooting
    """
    if not args.strip():
        return "Usage: /search <query>\nExample: /search bgp flapping cisco"

    query = args.strip()

    try:
        from langchain_community.tools import DuckDuckGoSearchResults

        search = DuckDuckGoSearchResults(max_results=5)
        results = search.invoke(query)

        if not results:
            return f"No results found for: {query}"

        return f"🔍 Search results for: {query}\n\n{results}"

    except ImportError:
        return "Error: DuckDuckGo search not available.\nInstall with: uv add duckduckgo-search"
    except Exception as e:
        return f"Search error: {str(e)}"


@register_command("quit")
async def cmd_quit(args: str) -> str:
    """Exit OLAV.

    Usage:
        /quit
    """
    raise EOFError


@register_command("exit")
async def cmd_exit(args: str) -> str:
    """Exit OLAV (alias for /quit).

    Usage:
        /exit
    """
    raise EOFError


# =============================================================================
# Command Help Utilities
# =============================================================================


def get_all_commands() -> dict[str, str]:
    """Get all registered commands with descriptions.

    Returns:
        Dictionary mapping command names to descriptions
    """
    commands = {}
    for name, func in SLASH_COMMANDS.items():
        # Extract first line of docstring
        doc = func.__doc__ or ""
        first_line = doc.split("\n")[0] if doc else "No description"
        commands[name] = first_line.strip()
    return commands


def is_slash_command(text: str) -> bool:
    """Check if text is a slash command.

    Args:
        text: Input text

    Returns:
        True if text starts with /
    """
    return text.strip().startswith("/")
