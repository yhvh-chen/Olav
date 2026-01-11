"""OLAV v0.8 CLI Module - Phase 6 Enhanced CLI.

This module provides an enhanced CLI experience using prompt-toolkit:
- Persistent command history
- Slash commands for quick actions
- File references (@file.txt)
- Shell command execution (!command)
- Agent memory persistence
- Customizable banners
"""

from olav.cli.cli_main import main
from olav.cli.commands import (
    SLASH_COMMANDS,
    execute_command,
    register_command,
)
from olav.cli.display import (
    display_banner,
    get_banner,
    load_banner_from_config,
    print_error,
    print_success,
    print_welcome,
)
from olav.cli.memory import AgentMemory
from olav.cli.session import OlavPromptSession

__all__ = [
    "main",
    "OlavPromptSession",
    "AgentMemory",
    "SLASH_COMMANDS",
    "register_command",
    "execute_command",
    "display_banner",
    "get_banner",
    "load_banner_from_config",
    "print_welcome",
    "print_error",
    "print_success",
]
