"""
CLI Tool - Template-based command discovery with blacklist security.

This module implements a schema-aware CLI tool that:
- Auto-discovers available commands from TextFSM templates (*.textfsm files)
- Provides platform-specific command mapping (cisco_ios, cisco_iosxr, etc.)
- Enforces blacklist security pattern for dangerous commands
- Wraps CLI execution in BaseTool protocol for LangChain integration

Code reused from archive/baseline_collector.py (TemplateManager):
- Lines 102-119: _parse_command_from_filename (command parsing from template filenames)
- Lines 121-128: _is_template_empty (template validity checking)
- Lines 130-168: _scan_templates (template discovery and caching)
- Lines 169-189: _load_blacklist (blacklist loading with defaults)
- Lines 191-258: get_commands_for_platform (platform-specific command mapping)

Author: OLAV Development Team
Date: 2025-01-21
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from olav.tools.base import BaseTool, ToolOutput

logger = logging.getLogger(__name__)

# Derive CONFIG_DIR and TEMPLATES_DIR without importing non-packaged root module
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "data" / "ntc-templates" / "ntc_templates" / "templates"


class CommandBlacklist:
    """
    Command blacklist manager with security defaults.
    
    Prevents execution of dangerous or disruptive commands:
    - Default blocks: traceroute, reload, write erase, etc.
    - Custom blocks: loaded from config/cli_blacklist.yaml (if exists)
    
    Attributes:
        blacklist: Set of blacklisted command patterns (lowercase)
    """
    
    DEFAULT_BLOCKS = {
        "traceroute",      # Network flooding risk
        "reload",          # Device reboot
        "write erase",     # Configuration wipe
        "format",          # Filesystem format
        "delete",          # File deletion
    }
    
    def __init__(self, blacklist_file: Optional[Path] = None):
        """
        Initialize blacklist from file or defaults.
        
        Args:
            blacklist_file: Path to blacklist file (YAML or txt format)
        """
        self.blacklist = self._load_blacklist(blacklist_file)
    
    def _load_blacklist(self, blacklist_file: Optional[Path] = None) -> Set[str]:
        """
        Load command blacklist from file with fallback to defaults.
        
        Reused from archive/baseline_collector.py lines 169-189.
        
        Args:
            blacklist_file: Path to blacklist file
            
        Returns:
            Set of blacklisted command patterns (lowercase)
        """
        blacklist = set()
        
        # Always block dangerous defaults unless explicitly allowed
        blacklist.update(self.DEFAULT_BLOCKS)
        
        # Try to load from file
        if blacklist_file is None:
            blacklist_file = CONFIG_DIR / "cli_blacklist.yaml"
        
        if blacklist_file.exists():
            try:
                with open(blacklist_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if line and not line.startswith('#'):
                            # YAML format: - command_pattern
                            if line.startswith('-'):
                                line = line[1:].strip()
                            blacklist.add(line.lower())
                logger.info(f"[CommandBlacklist] Loaded {len(blacklist)} blacklisted commands from {blacklist_file}")
            except Exception as e:
                logger.warning(f"[CommandBlacklist] Failed to load blacklist from {blacklist_file}: {e}")
                logger.info(f"[CommandBlacklist] Using {len(blacklist)} default blocks")
        else:
            logger.info(f"[CommandBlacklist] No blacklist file found at {blacklist_file}, using {len(blacklist)} defaults")
        
        return blacklist
    
    def is_blocked(self, command: str) -> bool:
        """
        Check if command matches any blacklist pattern.
        
        Args:
            command: CLI command to check
            
        Returns:
            True if command is blacklisted, False otherwise
        """
        cmd_lower = command.lower().strip()
        
        # Exact match or prefix match (e.g., "reload" blocks "reload in 5")
        for pattern in self.blacklist:
            if cmd_lower == pattern or cmd_lower.startswith(pattern + " "):
                return True
        
        return False


class TemplateManager:
    """
    TextFSM template manager for command discovery and mapping.
    
    Auto-discovers available CLI commands from .textfsm template files:
    - Scans ntc-templates directory for platform-specific templates
    - Caches platform → commands mapping for performance
    - Converts template filenames to CLI commands
    - Checks template validity (non-empty templates)
    
    Attributes:
        templates_dir: Path to ntc-templates directory
        blacklist: CommandBlacklist instance
        _cache: Platform → [(command, template_path, is_empty)] cache
    """
    
    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        blacklist: Optional[CommandBlacklist] = None
    ):
        """
        Initialize template manager with lazy-loading cache.
        
        Args:
            templates_dir: Path to ntc-templates directory (defaults to data/ntc-templates/)
            blacklist: CommandBlacklist instance (created if None)
        """
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.blacklist = blacklist or CommandBlacklist()
        self._cache: Dict[str, List[Tuple[str, Path, bool]]] = {}
        
        if not self.templates_dir.exists():
            logger.warning(f"[TemplateManager] Templates directory not found: {self.templates_dir}")
    
    def _parse_command_from_filename(self, filename: str) -> Optional[str]:
        """
        Extract CLI command from TextFSM template filename.
        
        Reused from archive/baseline_collector.py lines 102-119.
        
        Converts filenames like:
        - cisco_ios_show_ip_interface_brief.textfsm → "show ip interface brief"
        - cisco_iosxr_show_running_config.textfsm → "show running-config"
        
        Args:
            filename: Template filename (e.g., "cisco_ios_show_version.textfsm")
            
        Returns:
            CLI command string or None if parsing failed
        """
        # Remove .textfsm extension
        name = filename.replace('.textfsm', '')
        
        # Split by underscore
        parts = name.split('_')
        
        # Expected format: {vendor}_{platform}_{command...}
        # E.g., cisco_ios_show_ip_interface_brief
        if len(parts) < 3:
            return None
        
        # Extract command parts (skip vendor and platform)
        command_parts = parts[2:]
        
        # Join with spaces
        command = ' '.join(command_parts)
        
        # Handle special cases
        command = command.replace('running', 'running-config')
        command = command.replace('startup', 'startup-config')
        
        return command
    
    def _is_template_empty(self, template_path: Path) -> bool:
        """
        Check if TextFSM template contains only comments/whitespace.
        
        Reused from archive/baseline_collector.py lines 121-128.
        
        Args:
            template_path: Path to TextFSM template file
            
        Returns:
            True if template is empty (no parsing rules), False otherwise
        """
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Remove comments and whitespace
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                non_comment_lines = [line for line in lines if not line.startswith('#')]
                return len(non_comment_lines) == 0
        except Exception as e:
            logger.warning(f"[TemplateManager] Failed to read template {template_path}: {e}")
            return True
    
    def _scan_templates(self, platform: str) -> List[Tuple[str, Path, bool]]:
        """
        Scan templates directory for platform-specific TextFSM templates.
        
        Reused from archive/baseline_collector.py lines 130-168.
        
        Args:
            platform: Platform identifier (e.g., "cisco_ios", "cisco_iosxr")
            
        Returns:
            List of (command, template_path, is_empty) tuples
        """
        commands = []
        
        if not self.templates_dir.exists():
            logger.warning(f"[TemplateManager] Templates directory not found: {self.templates_dir}")
            return commands
        
        # Find all templates for platform: {platform}_*.textfsm
        pattern = f"{platform}_*.textfsm"
        template_files = list(self.templates_dir.glob(pattern))
        
        logger.info(f"[TemplateManager] Found {len(template_files)} templates for {platform}")
        
        for template_path in template_files:
            # Parse command from filename
            command = self._parse_command_from_filename(template_path.name)
            
            if command is None:
                logger.warning(f"[TemplateManager] Failed to parse command from {template_path.name}")
                continue
            
            # Check if template is empty
            is_empty = self._is_template_empty(template_path)
            
            # Skip blacklisted commands
            if self.blacklist.is_blocked(command):
                logger.info(f"[TemplateManager] Skipping blacklisted command: {command}")
                continue
            
            commands.append((command, template_path, is_empty))
        
        return commands
    
    def get_commands_for_platform(self, platform: str) -> List[Tuple[str, Path, bool]]:
        """
        Get all available CLI commands for a platform.
        
        Reused from archive/baseline_collector.py lines 191-258 (simplified).
        
        Uses cached results for performance:
        1. Check cache for platform
        2. If not cached, scan templates directory
        3. Filter blacklisted commands
        4. Cache results
        
        Args:
            platform: Platform identifier (e.g., "cisco_ios", "cisco_iosxr", "juniper_junos")
            
        Returns:
            List of (command, template_path, is_empty) tuples
            
        Example:
            >>> manager = TemplateManager()
            >>> commands = manager.get_commands_for_platform("cisco_ios")
            >>> for cmd, path, is_empty in commands:
            ...     print(f"{cmd}: {'raw text' if is_empty else 'structured'}")
            show version: structured
            show ip interface brief: structured
            show running-config: raw text
        """
        # Allow generic 'ios' alias to reuse cisco_ios templates
        if platform == "ios":
            platform_lookup = "cisco_ios"
        else:
            platform_lookup = platform
        
        # Check cache first
        if platform_lookup in self._cache:
            logger.debug(f"[TemplateManager] Using cached commands for {platform_lookup}")
            return self._cache[platform_lookup]
        
        # Scan templates directory
        commands = self._scan_templates(platform_lookup)
        
        # Cache results
        self._cache[platform_lookup] = commands
        
        logger.info(f"[TemplateManager] Cached {len(commands)} commands for {platform_lookup}")
        
        return commands
    
    def get_command_template(self, platform: str, command: str) -> Optional[Tuple[Path, bool]]:
        """
        Get template path for a specific command on a platform.
        
        Args:
            platform: Platform identifier
            command: CLI command to lookup
            
        Returns:
            Tuple of (template_path, is_empty) or None if not found
        """
        commands = self.get_commands_for_platform(platform)
        
        # Normalize command for comparison
        cmd_normalized = command.lower().strip()
        
        for cmd, template_path, is_empty in commands:
            if cmd.lower() == cmd_normalized:
                return (template_path, is_empty)
        
        return None


class CLITemplateTool(BaseTool):
    """
    CLI Template Discovery Tool - BaseTool implementation.
    
    Provides LLM with:
    - Platform-specific command discovery (e.g., "What commands are available for cisco_ios?")
    - Template availability checking (e.g., "Does 'show version' have TextFSM parsing?")
    - Command validation against blacklist (e.g., "Is 'reload' safe to execute?")
    
    Use Cases:
    1. **Command Discovery**: LLM asks "What commands can I run on cisco_ios?"
    2. **Template Lookup**: LLM asks "Is there a template for 'show ip bgp summary' on cisco_ios?"
    3. **Safety Check**: LLM asks "Is 'reload' command safe to execute?"
    
    Attributes:
        name: Tool identifier
        description: Tool purpose description
        manager: TemplateManager instance for command discovery
    """
    
    name = "cli_template_discover"
    description = """Discover available CLI commands and templates for network devices.
    
    Use this tool to:
    - List available commands for a platform (e.g., cisco_ios, cisco_iosxr)
    - Check if a command has TextFSM parsing support
    - Validate commands against blacklist before execution
    
    This tool provides command discovery, NOT execution.
    Use cli_execute tool for actual command execution.
    
    **Platform Identifiers**:
    - Cisco IOS: "cisco_ios" or "ios"
    - Cisco IOS-XR: "cisco_iosxr"
    - Cisco NX-OS: "cisco_nxos"
    - Juniper JunOS: "juniper_junos"
    - Arista EOS: "arista_eos"
    
    **Example Queries**:
    - "List all commands for cisco_ios"
    - "Does 'show ip bgp summary' have TextFSM template for cisco_ios?"
    - "Is 'reload' command safe to execute?"
    """
    
    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        blacklist_file: Optional[Path] = None
    ):
        """
        Initialize CLI template discovery tool.
        
        Args:
            templates_dir: Path to ntc-templates directory
            blacklist_file: Path to command blacklist file
        """
        blacklist = CommandBlacklist(blacklist_file)
        self.manager = TemplateManager(templates_dir, blacklist)
    
    async def execute(
        self,
        platform: str,
        command: Optional[str] = None,
        list_all: bool = False
    ) -> ToolOutput:
        """
        Discover CLI commands and templates for a platform.
        
        Args:
            platform: Platform identifier (e.g., "cisco_ios", "cisco_iosxr")
            command: Optional command to lookup (e.g., "show version")
            list_all: If True, return all available commands for platform
            
        Returns:
            ToolOutput with command discovery results
            
        Example (List all commands):
            result = await tool.execute(platform="cisco_ios", list_all=True)
            # Returns: [
            #   {"command": "show version", "template": "cisco_ios_show_version.textfsm", "parsed": True},
            #   {"command": "show running-config", "template": "cisco_ios_show_running_config.textfsm", "parsed": False},
            #   ...
            # ]
            
        Example (Check specific command):
            result = await tool.execute(platform="cisco_ios", command="show ip bgp summary")
            # Returns: [
            #   {"command": "show ip bgp summary", "template": "cisco_ios_show_ip_bgp_summary.textfsm", "parsed": True, "available": True}
            # ]
        """
        metadata = {
            "platform": platform,
            "command": command,
            "list_all": list_all
        }
        
        # List all commands for platform
        if list_all:
            commands = self.manager.get_commands_for_platform(platform)
            
            if not commands:
                return ToolOutput(
                    source="cli_template",
                        device="platform",
                    data=[{
                        "status": "NO_TEMPLATES",
                        "platform": platform,
                        "message": f"No templates found for platform: {platform}",
                        "hint": "Check platform identifier (e.g., cisco_ios, cisco_iosxr)"
                    }],
                    metadata=metadata,
                    error=f"No templates found for platform: {platform}"
                )
            
            # Format results
            results = []
            for cmd, template_path, is_empty in commands:
                results.append({
                    "command": cmd,
                    "template": template_path.name,
                    "parsed": not is_empty,  # True if template has parsing rules
                    "path": str(template_path)
                })
            
            return ToolOutput(
                source="cli_template",
                    device="platform",
                data=results,
                metadata={**metadata, "total_commands": len(results)}
            )
        
        # Lookup specific command
        if command:
            # Check blacklist first
            if self.manager.blacklist.is_blocked(command):
                return ToolOutput(
                    source="cli_template",
                        device="platform",
                    data=[{
                        "command": command,
                        "platform": platform,
                        "available": False,
                        "blacklisted": True,
                        "message": f"Command '{command}' is blacklisted for safety",
                        "hint": "Use alternative diagnostic commands instead"
                    }],
                    metadata=metadata,
                    error=f"Command '{command}' is blacklisted"
                )
            
            # Lookup template
            template_info = self.manager.get_command_template(platform, command)
            
            if template_info is None:
                return ToolOutput(
                    source="cli_template",
                        device="platform",
                    data=[{
                        "command": command,
                        "platform": platform,
                        "available": False,
                        "message": f"No template found for '{command}' on {platform}",
                        "hint": "Command may still be executable, but output will be raw text"
                    }],
                    metadata=metadata
                )
            
            template_path, is_empty = template_info
            
            return ToolOutput(
                source="cli_template",
                    device="platform",
                data=[{
                    "command": command,
                    "platform": platform,
                    "available": True,
                    "template": template_path.name,
                    "parsed": not is_empty,
                    "path": str(template_path),
                    "blacklisted": False
                }],
                metadata=metadata
            )
        
        # No command specified and list_all=False
        return ToolOutput(
            source="cli_template",
                device="platform",
            data=[{
                "status": "PARAM_ERROR",
                "message": "Must specify either 'command' or 'list_all=True'",
                "hint": "Use list_all=True to see all available commands"
            }],
            metadata=metadata,
            error="Missing required parameter: command or list_all"
        )


# Note: Do not register CLITemplateTool with ToolRegistry yet
# This tool is for command discovery only, not execution
# Registration will be done after integration with existing nornir_tool_refactored.py
