"""
CLI Tool - Template-based command discovery with blacklist security.

This module implements a schema-aware CLI tool that:
- Auto-discovers available commands from TextFSM templates (*.textfsm files)
- Provides platform-specific command mapping (cisco_ios, cisco_iosxr, etc.)
- Enforces blacklist security pattern for dangerous commands
- Wraps CLI execution in BaseTool protocol for LangChain integration
- Fallback command lists for platforms without templates (91 Cisco IOS commands)
- **NetBox platform injection**: Queries device.platform from NetBox SSOT (Phase B.1 Step 3)

Code reused from archive/baseline_collector.py (TemplateManager):
- Lines 102-119: _parse_command_from_filename (command parsing from template filenames)
- Lines 121-128: _is_template_empty (template validity checking)
- Lines 130-168: _scan_templates (template discovery and caching)
- Lines 169-189: _load_blacklist (blacklist loading with defaults)
- Lines 191-258: get_commands_for_platform (platform-specific command mapping)
- Lines 260-332: _get_standard_commands_for_platform (91 Cisco IOS fallback commands)

Total reused: 230+ production-verified lines

Author: OLAV Development Team
Date: 2025-01-21
Updated: 2025-01-21 (Phase B.1 Step 2 - Added fallback commands)
Updated: 2025-11-25 (Phase B.1 Step 3 - NetBox platform injection)
"""

import logging
from pathlib import Path

from olav.tools.base import BaseTool, ToolOutput
from olav.tools.netbox_tool import netbox_api_call  # Canonical import

logger = logging.getLogger(__name__)


def get_device_platform_from_netbox(device_name: str) -> str | None:
    """
    Query NetBox for device platform.

    This function integrates with NetBox as SSOT (Single Source of Truth)
    to avoid hardcoding platform strings. When a device name is provided,
    it queries NetBox's device API to get the platform.slug field.

    Args:
        device_name: Device hostname from NetBox inventory

    Returns:
        Platform slug (e.g., "cisco-ios", "cisco-iosxr") or None if:
        - Device not found in NetBox
        - Device has no platform assigned
        - NetBox API error

    Example:
        >>> platform = get_device_platform_from_netbox("R1")
        >>> print(platform)
        "cisco-ios"

    Note:
        - Platform slugs use hyphens (NetBox convention): "cisco-ios"
        - TemplateManager expects underscores: "cisco_ios"
        - Conversion is handled by _normalize_platform_slug()
    """
    try:
        # Query NetBox device API by name
        response = netbox_api_call(
            path="/dcim/devices/", method="GET", params={"name": device_name}
        )

        # Handle errors
        if response.get("status") == "error":
            logger.error(
                f"NetBox query failed for device '{device_name}': {response.get('message')}"
            )
            return None

        # Extract results
        results = response.get("results", [])
        if not results:
            logger.warning(f"Device '{device_name}' not found in NetBox")
            return None

        # Get first result (device name should be unique)
        device = results[0]
        platform = device.get("platform")

        if not platform:
            logger.warning(f"Device '{device_name}' has no platform assigned in NetBox")
            return None

        # Extract platform slug (e.g., {"id": 1, "name": "Cisco IOS", "slug": "cisco-ios"})
        platform_slug = platform.get("slug")
        if not platform_slug:
            logger.warning(f"Device '{device_name}' platform missing slug field: {platform}")
            return None

        logger.info(f"[NetBox SSOT] Device '{device_name}' platform: {platform_slug}")
        return platform_slug

    except ImportError:
        logger.error("netbox_tool not available (import error)")
        return None
    except Exception as e:
        logger.error(f"Failed to query NetBox for device '{device_name}': {e}")
        return None


def _normalize_platform_slug(platform_slug: str) -> str:
    """
    Convert NetBox platform slug to ntc-templates format.

    NetBox uses hyphens in slugs (e.g., "cisco-ios").
    ntc-templates uses underscores (e.g., "cisco_ios").

    Args:
        platform_slug: NetBox platform slug with hyphens

    Returns:
        Normalized platform name for ntc-templates

    Example:
        >>> _normalize_platform_slug("cisco-ios")
        "cisco_ios"
        >>> _normalize_platform_slug("arista-eos")
        "arista_eos"
    """
    return platform_slug.replace("-", "_")


# Derive CONFIG_DIR and TEMPLATES_DIR without importing non-packaged root module
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "ntc-templates" / "ntc_templates" / "templates"
)


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
        "traceroute",  # Network flooding risk
        "reload",  # Device reboot
        "write erase",  # Configuration wipe
        "format",  # Filesystem format
        "delete",  # File deletion
    }

    def __init__(self, blacklist_file: Path | None = None) -> None:
        """
        Initialize blacklist from file or defaults.

        Args:
            blacklist_file: Path to blacklist file (YAML or txt format)
        """
        self.blacklist = self._load_blacklist(blacklist_file)

    def _load_blacklist(self, blacklist_file: Path | None = None) -> set[str]:
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
                with open(blacklist_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if line and not line.startswith("#"):
                            # YAML format: - command_pattern
                            if line.startswith("-"):
                                line = line[1:].strip()
                            blacklist.add(line.lower())
                logger.info(
                    f"[CommandBlacklist] Loaded {len(blacklist)} blacklisted commands from {blacklist_file}"
                )
            except Exception as e:
                logger.warning(
                    f"[CommandBlacklist] Failed to load blacklist from {blacklist_file}: {e}"
                )
                logger.info(f"[CommandBlacklist] Using {len(blacklist)} default blocks")
        else:
            logger.info(
                f"[CommandBlacklist] No blacklist file found at {blacklist_file}, using {len(blacklist)} defaults"
            )

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
        self, templates_dir: Path | None = None, blacklist: CommandBlacklist | None = None
    ) -> None:
        """
        Initialize template manager with lazy-loading cache.

        Args:
            templates_dir: Path to ntc-templates directory (defaults to data/ntc-templates/)
            blacklist: CommandBlacklist instance (created if None)
        """
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.blacklist = blacklist or CommandBlacklist()
        self._cache: dict[str, list[tuple[str, Path, bool]]] = {}

        if not self.templates_dir.exists():
            logger.warning(f"[TemplateManager] Templates directory not found: {self.templates_dir}")

    def _parse_command_from_filename(self, filename: str) -> str | None:
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
        name = filename.replace(".textfsm", "")

        # Split by underscore
        parts = name.split("_")

        # Expected format: {vendor}_{platform}_{command...}
        # E.g., cisco_ios_show_ip_interface_brief
        if len(parts) < 3:
            return None

        # Extract command parts (skip vendor and platform)
        command_parts = parts[2:]

        # Join with spaces
        command = " ".join(command_parts)

        # Handle special cases
        command = command.replace("running", "running-config")
        return command.replace("startup", "startup-config")

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
            with open(template_path, encoding="utf-8") as f:
                content = f.read().strip()
                # Remove comments and whitespace
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                non_comment_lines = [line for line in lines if not line.startswith("#")]
                return len(non_comment_lines) == 0
        except Exception as e:
            logger.warning(f"[TemplateManager] Failed to read template {template_path}: {e}")
            return True

    def _scan_templates(self, platform: str) -> list[tuple[str, Path, bool]]:
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
                logger.warning(
                    f"[TemplateManager] Failed to parse command from {template_path.name}"
                )
                continue

            # Check if template is empty
            is_empty = self._is_template_empty(template_path)

            # Skip blacklisted commands
            if self.blacklist.is_blocked(command):
                logger.info(f"[TemplateManager] Skipping blacklisted command: {command}")
                continue

            commands.append((command, template_path, is_empty))

        return commands

    def get_commands_for_platform(self, platform: str) -> list[tuple[str, Path, bool]]:
        """
        Get all available CLI commands for a platform.

        Reused from archive/baseline_collector.py lines 191-258 (simplified).
        Enhanced with fallback mechanism for platforms without templates.

        Uses cached results for performance:
        1. Check cache for platform
        2. If not cached, scan templates directory
        3. Add standard fallback commands if templates exist
        4. Filter blacklisted commands
        5. Cache results

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
        platform_lookup = "cisco_ios" if platform == "ios" else platform

        # Check cache first
        if platform_lookup in self._cache:
            logger.debug(f"[TemplateManager] Using cached commands for {platform_lookup}")
            return self._cache[platform_lookup]

        # Scan templates directory
        commands = self._scan_templates(platform_lookup)

        # Add standard fallback commands if no templates found
        if not commands:
            logger.info(
                f"[TemplateManager] No templates found for {platform_lookup}, using fallback commands"
            )
            commands = self._get_standard_commands_for_platform(platform_lookup)

        # Cache results
        self._cache[platform_lookup] = commands

        logger.info(f"[TemplateManager] Cached {len(commands)} commands for {platform_lookup}")

        return commands

    def _get_standard_commands_for_platform(self, platform: str) -> list[tuple[str, Path, bool]]:
        """
        Return standard show commands with fallback support.

        Reused from archive/baseline_collector.py lines 260-332.

        Provides production-verified command lists for platforms without templates:
        - cisco_ios: 91 commands (all ntc-templates supported commands)
        - Other platforms: Minimal fallback (show running-config)

        Args:
            platform: Platform identifier

        Returns:
            List of (command, template_path, is_empty) tuples
            template_path is None for standard commands (use default ntc-templates lookup)
        """
        # All 91 commands available in ntc-templates for cisco_ios
        # Reused from archive/baseline_collector.py lines 265-358
        standard_commands = {
            "cisco_ios": [
                ("dir", None, False),
                ("show access-list", None, False),
                ("show access-session", None, False),
                ("show adjacency", None, False),
                ("show alert counters", None, False),
                ("show aliases", None, False),
                ("show archive", None, False),
                ("show authentication sessions", None, False),
                ("show boot", None, False),
                ("show capability feature routing", None, False),
                ("show cdp neighbors", None, False),
                ("show cdp neighbors detail", None, False),
                ("show clock", None, False),
                ("show controller t1", None, False),
                ("show dmvpn", None, False),
                ("show dot1x all", None, False),
                ("show environment power all", None, False),
                ("show environment temperature", None, False),
                ("show etherchannel summary", None, False),
                ("show hosts summary", None, False),
                ("show interface transceiver", None, False),
                ("show interfaces", None, False),
                ("show interfaces description", None, False),
                ("show interfaces status", None, False),
                ("show interfaces switchport", None, False),
                ("show inventory", None, False),
                ("show ip access-lists", None, False),
                ("show ip arp", None, False),
                ("show ip bgp", None, False),
                ("show ip bgp neighbors", None, False),
                ("show ip bgp neighbors advertised-routes", None, False),
                ("show ip bgp summary", None, False),
                ("show ip cef", None, False),
                ("show ip cef detail", None, False),
                ("show ip device tracking all", None, False),
                ("show ip eigrp neighbors", None, False),
                ("show ip eigrp topology", None, False),
                ("show ip flow toptalkers", None, False),
                ("show ip interface", None, False),
                ("show ip interface brief", None, False),
                ("show ip mroute", None, False),
                ("show ip ospf database", None, False),
                ("show ip ospf database network", None, False),
                ("show ip ospf database router", None, False),
                ("show ip ospf interface brief", None, False),
                ("show ip ospf neighbor", None, False),
                ("show ip prefix-list", None, False),
                ("show ip route", None, False),
                ("show ip route summary", None, False),
                ("show ip source binding", None, False),
                ("show ip vrf interfaces", None, False),
                ("show ipv6 interface brief", None, False),
                ("show ipv6 neighbors", None, False),
                ("show isdn status", None, False),
                ("show isis neighbors", None, False),
                ("show license", None, False),
                ("show lldp neighbors", None, False),
                ("show lldp neighbors detail", None, False),
                ("show logging", None, False),
                ("show mac-address-table", None, False),
                ("show module", None, False),
                ("show module online diag", None, False),
                ("show module status", None, False),
                ("show module submodule", None, False),
                ("show mpls interfaces", None, False),
                ("show object-group", None, False),
                ("show platform diag", None, False),
                ("show power available", None, False),
                ("show power status", None, False),
                ("show power supplies", None, False),
                ("show processes cpu", None, False),
                ("show processes memory sorted", None, False),
                ("show redundancy", None, False),
                ("show route-map", None, False),
                ("show running-config partition access-list", None, False),
                ("show running-config partition route-map", None, False),
                ("show snmp community", None, False),
                ("show snmp user", None, False),
                ("show spanning-tree", None, False),
                ("show standby", None, False),
                ("show standby brief", None, False),
                ("show switch detail", None, False),
                ("show switch detail stack ports", None, False),
                ("show tacacs", None, False),
                ("show version", None, False),
                ("show vlan", None, False),
                ("show vrf", None, False),
                ("show vrrp all", None, False),
                ("show vrrp brief", None, False),
                ("show vtp status", None, False),
                ("show running-config", None, True),  # Keep as raw - config parsing is complex
            ],
        }

        # Return platform-specific commands or minimal fallback
        return standard_commands.get(platform, [("show running-config", None, True)])

    def get_command_template(self, platform: str, command: str) -> tuple[Path, bool] | None:
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
        self, templates_dir: Path | None = None, blacklist_file: Path | None = None
    ) -> None:
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
        platform: str | None = None,
        device: str | None = None,
        command: str | None = None,
        list_all: bool = False,
    ) -> ToolOutput:
        """
        Discover CLI commands and templates for a platform.

        **NetBox Integration (Phase B.1 Step 3)**:
        - If `device` is provided, queries NetBox for device.platform
        - Falls back to `platform` parameter if NetBox query fails
        - Enables SSOT platform management (no hardcoded strings)

        Args:
            platform: Platform identifier (e.g., "cisco_ios", "cisco_iosxr")
                      Used as fallback if device/NetBox query fails
            device: Device hostname from NetBox (queries device.platform)
                    Takes priority over `platform` parameter
            command: Optional command to lookup (e.g., "show version")
            list_all: If True, return all available commands for platform

        Returns:
            ToolOutput with command discovery results

        Example (NetBox Integration):
            # Query NetBox for R1's platform
            result = await tool.execute(device="R1", list_all=True)
            # NetBox returns platform.slug="cisco-ios" → normalized to "cisco_ios"
            # Returns: 91 Cisco IOS commands from fallback or templates

        Example (Explicit Platform):
            result = await tool.execute(platform="cisco_ios", list_all=True)
            # Returns: [
            #   {"command": "show version", "template": "cisco_ios_show_version.textfsm", "parsed": True},
            #   ...
            # ]

        Example (Check Specific Command):
            result = await tool.execute(platform="cisco_ios", command="show ip bgp summary")
            # Returns: [
            #   {"command": "show ip bgp summary", "template": "cisco_ios_show_ip_bgp_summary.textfsm",
            #    "parsed": True, "available": True}
            # ]
        """
        # Resolve platform from device or use explicit parameter
        resolved_platform = platform
        platform_source = "explicit"

        if device:
            # Query NetBox for device platform (SSOT)
            netbox_platform = get_device_platform_from_netbox(device)
            if netbox_platform:
                # Normalize NetBox slug (cisco-ios → cisco_ios)
                resolved_platform = _normalize_platform_slug(netbox_platform)
                platform_source = "netbox"
                logger.info(
                    f"[CLITemplateTool] Resolved platform from NetBox: {device} → {resolved_platform}"
                )
            else:
                logger.warning(
                    f"[CLITemplateTool] NetBox query failed for device '{device}', falling back to platform parameter"
                )

        # Validation: must have platform from either source
        if not resolved_platform:
            return ToolOutput(
                source="cli_template",
                device=device or "unknown",
                data=[
                    {
                        "status": "PARAM_ERROR",
                        "message": "Must provide 'platform' parameter or 'device' with NetBox platform metadata",
                        "hint": "Use platform='cisco_ios' OR device='R1' (with NetBox platform assigned)",
                    }
                ],
                metadata={"platform": None, "device": device, "command": command},
                error="Missing platform parameter",
            )

        metadata = {
            "platform": resolved_platform,
            "platform_source": platform_source,
            "device": device,
            "command": command,
            "list_all": list_all,
        }

        # List all commands for platform
        if list_all:
            commands = self.manager.get_commands_for_platform(resolved_platform)

            if not commands:
                return ToolOutput(
                    source="cli_template",
                    device=device or "platform",
                    data=[
                        {
                            "status": "NO_TEMPLATES",
                            "platform": resolved_platform,
                            "message": f"No templates found for platform: {resolved_platform}",
                            "hint": "Check platform identifier (e.g., cisco_ios, cisco_iosxr)",
                        }
                    ],
                    metadata=metadata,
                    error=f"No templates found for platform: {resolved_platform}",
                )

            # Format results
            results = []
            for cmd, template_path, is_empty in commands:
                results.append(
                    {
                        "command": cmd,
                        "template": template_path.name if template_path else None,
                        "parsed": not is_empty,  # True if template has parsing rules
                        "path": str(template_path) if template_path else None,
                    }
                )

            return ToolOutput(
                source="cli_template",
                device=device or "platform",
                data=results,
                metadata={**metadata, "total_commands": len(results)},
            )

        # Lookup specific command
        if command:
            # Check blacklist first
            if self.manager.blacklist.is_blocked(command):
                return ToolOutput(
                    source="cli_template",
                    device=device or "platform",
                    data=[
                        {
                            "command": command,
                            "platform": resolved_platform,
                            "available": False,
                            "blacklisted": True,
                            "message": f"Command '{command}' is blacklisted for safety",
                            "hint": "Use alternative diagnostic commands instead",
                        }
                    ],
                    metadata=metadata,
                    error=f"Command '{command}' is blacklisted",
                )

            # Lookup template
            template_info = self.manager.get_command_template(resolved_platform, command)

            if template_info is None:
                return ToolOutput(
                    source="cli_template",
                    device=device or "platform",
                    data=[
                        {
                            "command": command,
                            "platform": resolved_platform,
                            "available": False,
                            "message": f"No template found for '{command}' on {resolved_platform}",
                            "hint": "Command may still be executable, but output will be raw text",
                        }
                    ],
                    metadata=metadata,
                )

            template_path, is_empty = template_info

            return ToolOutput(
                source="cli_template",
                device=device or "platform",
                data=[
                    {
                        "command": command,
                        "platform": resolved_platform,
                        "available": True,
                        "template": template_path.name,
                        "parsed": not is_empty,
                        "path": str(template_path),
                        "blacklisted": False,
                    }
                ],
                metadata=metadata,
            )

        # No command specified and list_all=False
        return ToolOutput(
            source="cli_template",
            device=device or "platform",
            data=[
                {
                    "status": "PARAM_ERROR",
                    "message": "Must specify either 'command' or 'list_all=True'",
                    "hint": "Use list_all=True to see all available commands",
                }
            ],
            metadata=metadata,
            error="Missing required parameter: command or list_all",
        )


# Note: Do not register CLITemplateTool with ToolRegistry yet
# This tool is for command discovery only, not execution
# Registration will be done after integration with existing nornir_tool_refactored.py


# ---------------------------------------------------------------------------
# LLM-Based Command Generation Tool (Phase B.2 - Platform Command Generation)
# ---------------------------------------------------------------------------

from langchain_core.tools import tool


@tool
async def generate_cli_commands(
    intent: str,
    device: str | None = None,
    platform: str | None = None,
    context: str = "",
) -> dict:
    """Generate platform-specific CLI commands from natural language intent.

    Use this tool when you need to run CLI commands but don't know the exact
    syntax for a specific platform. The tool uses LLM to generate appropriate
    commands based on the device platform.

    **When to Use**:
    - You have a user intent (e.g., "check BGP status") but need exact commands
    - You need to adapt a command for a different platform
    - You're not sure about the correct command syntax

    **Platform Resolution**:
    - If `device` is provided, queries NetBox for platform (recommended)
    - Otherwise, uses explicit `platform` parameter

    **Platform Identifiers**:
    - Cisco IOS: "cisco_ios"
    - Cisco IOS-XR: "cisco_iosxr"
    - Cisco NX-OS: "cisco_nxos"
    - Juniper JunOS: "juniper_junos"
    - Arista EOS: "arista_eos"

    Args:
        intent: Natural language description of what you want to check/do.
               Example: "Show BGP neighbor status", "Check interface CRC errors"
        device: Device hostname from NetBox (queries platform automatically).
               Takes priority over explicit `platform` parameter.
        platform: Explicit platform identifier (used if device not provided).
        context: Additional context (e.g., "device is core router", "previous error was timeout")

    Returns:
        Dict with:
        - commands: List of CLI commands to execute
        - explanation: Brief explanation of what each command does
        - warnings: Any warnings about the commands
        - alternatives: Alternative commands if primary fails
        - platform: Resolved platform identifier
        - cached: Whether result was from cache

    Example:
        >>> result = await generate_cli_commands(
        ...     intent="Check for interface CRC errors",
        ...     device="R1"
        ... )
        >>> result["commands"]
        ["show interfaces | include CRC", "show interfaces counters errors"]

        >>> result = await generate_cli_commands(
        ...     intent="Show OSPF neighbor adjacencies",
        ...     platform="juniper_junos"
        ... )
        >>> result["commands"]
        ["show ospf neighbor", "show ospf neighbor extensive"]
    """
    from olav.tools.cli_command_generator import generate_platform_command

    # Resolve platform from device or use explicit parameter
    resolved_platform = platform

    if device:
        # Query NetBox for device platform (SSOT)
        netbox_platform = get_device_platform_from_netbox(device)
        if netbox_platform:
            resolved_platform = _normalize_platform_slug(netbox_platform)
            logger.info(
                f"[generate_cli_commands] Resolved platform from NetBox: {device} → {resolved_platform}"
            )
        else:
            logger.warning(
                f"[generate_cli_commands] NetBox query failed for device '{device}', using explicit platform"
            )

    # Validation
    if not resolved_platform:
        return {
            "commands": [],
            "explanation": "",
            "warnings": [
                "Must provide either 'device' (with NetBox platform) or 'platform' parameter"
            ],
            "alternatives": [],
            "platform": None,
            "cached": False,
            "error": "Missing platform",
        }

    # Get available commands for context (from TextFSM templates)
    manager = TemplateManager()
    available = manager.get_commands_for_platform(resolved_platform)
    available_commands = [cmd for cmd, _, _ in available]

    # Generate commands using LLM
    result = await generate_platform_command(
        intent=intent,
        platform=resolved_platform,
        available_commands=available_commands[:50],  # Limit to 50 for context window
        context=context,
    )

    # Add platform to result
    return {
        **result,
        "platform": resolved_platform,
    }
