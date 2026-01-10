"""Slash Commands - Quick command system for OLAV CLI.

Provides fast, dedicated commands for common operations.
Commands are prefixed with '/' (e.g., /devices, /help).
"""

import asyncio
from typing import Callable, Dict, Optional
import re


# Registry for slash commands
SLASH_COMMANDS: Dict[str, Callable] = {}


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
) -> Optional[str]:
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
        /inspect <scope>

    Examples:
        /inspect all core routers
        /inspect R1, R2, R5
    """
    if not args:
        return "Usage: /inspect <scope>\nExample: /inspect all core routers"

    # This would trigger InspectorAgent
    # For now, return a message
    return f"Inspection queued for: {args}\n(Use agent query for full inspection)"


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
  Total Messages: {stats['total_messages']}
  User Messages: {stats['user_messages']}
  Assistant Messages: {stats['assistant_messages']}
  Tool Messages: {stats['tool_messages']}
  Memory File: {stats['memory_file']}"""
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

  Slash Commands:
    /devices [filter]   - List devices (e.g., /devices role:core)
    /skills [name]      - List skills or view skill details
    /inspect <scope>    - Run quick inspection
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
    olav> /devices role:core
    olav> @config.txt analyze this configuration
    olav> !ping 8.8.8.8
    olav> Check R1 interface status
"""


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


def get_all_commands() -> Dict[str, str]:
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
