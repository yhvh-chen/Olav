"""Tool Middleware - Auto-inject tool descriptions into prompts.

Inspired by deepagents Middleware pattern, implementing automatic tool description injection:
1. Keep base prompts concise (focused on responsibilities, <20 lines)
2. Auto-generate tool overview table
3. Load and inject Capability Guides on demand
4. Cross-Workflow reuse ensuring consistency

Phase 4 Extensions:
- HITL (Human-in-the-Loop) support for CLI verification commands
- Command safety classification (read-only vs write operations)
- Pre-execution approval workflow for write operations

Pattern:
    Before (lengthy Prompt):
        60-100 line Prompt with repeated tool descriptions

    After (Middleware injection):
        15-20 line base Prompt + auto-injected tool descriptions
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from olav.core.prompt_manager import prompt_manager

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


# =============================================================================
# HITL Command Classification
# =============================================================================


class CommandSafety(Enum):
    """Safety classification for CLI commands."""
    READ_ONLY = "read_only"  # Safe to execute without approval
    WRITE = "write"  # Requires HITL approval
    DANGEROUS = "dangerous"  # Requires explicit confirmation + HITL


@dataclass
class CommandAnalysis:
    """Result of command safety analysis."""
    command: str
    safety: CommandSafety
    reason: str
    requires_approval: bool
    suggested_verification: str | None = None


class CommandSafetyClassifier:
    """Classify CLI commands by safety level.

    This classifier helps determine which commands require HITL approval.

    Read-Only Commands (no approval needed):
    - show, display, get, list, ping, traceroute

    Write Commands (require approval):
    - configure, set, delete, commit, rollback

    Dangerous Commands (require explicit confirmation):
    - reload, reboot, shutdown, write erase
    """

    # Patterns for read-only commands (safe to execute)
    READ_ONLY_PATTERNS = [
        r"^show\b",
        r"^display\b",
        r"^get\b",
        r"^list\b",
        r"^ping\b",
        r"^traceroute\b",
        r"^tracepath\b",
        r"^mtr\b",
        r"^netstat\b",
        r"^ip\s+(route|addr|link|neigh)\s+show",
        r"^cat\s+/",  # Reading files
        r"^more\s+",
        r"^less\s+",
        r"^head\s+",
        r"^tail\s+",
        r"^run\s+show",  # Juniper
        r"^run\s+ping",
        r"^run\s+traceroute",
    ]

    # Patterns for write commands (require approval)
    WRITE_PATTERNS = [
        r"^configure\b",
        r"^set\b",
        r"^delete\b",
        r"^edit\b",
        r"^commit\b",
        r"^rollback\b",
        r"^no\s+",  # Cisco negation
        r"^ip\s+(route|addr)\s+(add|del)",
        r"^interface\b",
        r"^router\b",
        r"^vlan\b",
        r"^copy\s+running",
        r"^write\s+mem",
    ]

    # Patterns for dangerous commands (require explicit confirmation)
    DANGEROUS_PATTERNS = [
        r"^reload\b",
        r"^reboot\b",
        r"^shutdown\b",
        r"^request\s+system\s+reboot",  # Juniper
        r"^request\s+system\s+halt",
        r"^write\s+erase",
        r"^erase\s+",
        r"^format\s+",
        r"^rm\s+-rf",
        r"^del\s+/force",
    ]

    def __init__(self) -> None:
        """Initialize classifier with compiled patterns."""
        self._read_only_compiled = [re.compile(p, re.IGNORECASE) for p in self.READ_ONLY_PATTERNS]
        self._write_compiled = [re.compile(p, re.IGNORECASE) for p in self.WRITE_PATTERNS]
        self._dangerous_compiled = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]

    def classify(self, command: str) -> CommandAnalysis:
        """Classify a CLI command by safety level.

        Args:
            command: The CLI command to classify

        Returns:
            CommandAnalysis with safety classification
        """
        command = command.strip()

        # Check dangerous first
        for pattern in self._dangerous_compiled:
            if pattern.search(command):
                return CommandAnalysis(
                    command=command,
                    safety=CommandSafety.DANGEROUS,
                    reason="This command can cause system disruption",
                    requires_approval=True,
                    suggested_verification="Are you absolutely sure? This action cannot be undone.",
                )

        # Check write patterns
        for pattern in self._write_compiled:
            if pattern.search(command):
                return CommandAnalysis(
                    command=command,
                    safety=CommandSafety.WRITE,
                    reason="This command modifies device configuration",
                    requires_approval=True,
                    suggested_verification="Please review the command before execution.",
                )

        # Check read-only patterns
        for pattern in self._read_only_compiled:
            if pattern.search(command):
                return CommandAnalysis(
                    command=command,
                    safety=CommandSafety.READ_ONLY,
                    reason="Read-only command",
                    requires_approval=False,
                )

        # Default: treat unknown commands as write (safer)
        return CommandAnalysis(
            command=command,
            safety=CommandSafety.WRITE,
            reason="Unknown command pattern - treating as write operation",
            requires_approval=True,
            suggested_verification="Please verify this command is safe to execute.",
        )


# Global classifier instance
command_classifier = CommandSafetyClassifier()


# =============================================================================
# HITL Approval Workflow
# =============================================================================


@dataclass
class HITLApprovalRequest:
    """Request for human approval of a command."""
    command: str
    device: str
    analysis: CommandAnalysis
    context: str | None = None
    timeout_seconds: int = 300  # 5 minutes default


@dataclass
class HITLApprovalResult:
    """Result of human approval request."""
    approved: bool
    reason: str | None = None
    modified_command: str | None = None  # If human modified the command
    approver: str | None = None
    timestamp: str | None = None


class HITLApprovalHandler:
    """Handler for HITL approval workflow.

    This integrates with LangGraph's interrupt mechanism to pause
    execution and wait for human approval.

    Usage:
        handler = HITLApprovalHandler()

        # Check if command needs approval
        if handler.needs_approval(command):
            # Request approval (triggers LangGraph interrupt)
            result = await handler.request_approval(command, device)
            if not result.approved:
                return "Command rejected by user"
    """

    def __init__(
        self,
        classifier: CommandSafetyClassifier | None = None,
        approval_callback: Callable[[HITLApprovalRequest], HITLApprovalResult] | None = None,
    ) -> None:
        """Initialize HITL handler.

        Args:
            classifier: Command safety classifier (uses global if None)
            approval_callback: Custom approval callback (for testing)
        """
        self.classifier = classifier or command_classifier
        self._approval_callback = approval_callback

    def needs_approval(self, command: str) -> bool:
        """Check if a command requires human approval.

        Args:
            command: The CLI command to check

        Returns:
            True if approval is required
        """
        analysis = self.classifier.classify(command)
        return analysis.requires_approval

    def analyze_command(self, command: str) -> CommandAnalysis:
        """Get detailed safety analysis of a command.

        Args:
            command: The CLI command to analyze

        Returns:
            CommandAnalysis with full details
        """
        return self.classifier.classify(command)

    async def request_approval(
        self,
        command: str,
        device: str,
        context: str | None = None,
    ) -> HITLApprovalResult:
        """Request human approval for a command.

        This method integrates with LangGraph interrupts. In production,
        it will pause the workflow and wait for user input.

        Args:
            command: The command to approve
            device: Target device
            context: Additional context for the user

        Returns:
            HITLApprovalResult with decision
        """
        analysis = self.classifier.classify(command)

        request = HITLApprovalRequest(
            command=command,
            device=device,
            analysis=analysis,
            context=context,
        )

        # If custom callback provided (testing), use it
        if self._approval_callback:
            return self._approval_callback(request)

        # In production, this would trigger a LangGraph interrupt
        # For now, log and return pending
        logger.info(f"HITL approval requested for command: {command} on {device}")
        logger.info(f"Safety: {analysis.safety.value}, Reason: {analysis.reason}")

        # Default: return a pending result that workflows can handle
        return HITLApprovalResult(
            approved=False,
            reason="Approval pending - use LangGraph interrupt",
        )

    def format_approval_request(self, request: HITLApprovalRequest) -> str:
        """Format approval request for display to user.

        Args:
            request: The approval request

        Returns:
            Formatted string for user display
        """
        lines = [
            "## ⚠️ Command Approval Required",
            "",
            f"**Device**: {request.device}",
            f"**Command**: `{request.command}`",
            "",
            f"**Safety Level**: {request.analysis.safety.value.upper()}",
            f"**Reason**: {request.analysis.reason}",
        ]

        if request.analysis.suggested_verification:
            lines.extend([
                "",
                f"**⚡ {request.analysis.suggested_verification}**",
            ])

        if request.context:
            lines.extend([
                "",
                "### Context",
                request.context,
            ])

        lines.extend([
            "",
            "---",
            "Reply with `approve` or `reject` (with optional reason).",
        ])

        return "\n".join(lines)


# Global HITL handler instance
hitl_handler = HITLApprovalHandler()


# =============================================================================
# Tool Middleware (Original + Extensions)
# =============================================================================


class ToolMiddleware:
    """
    Tool description auto-injection Middleware.

    Automatically injects capability_guide into System Prompt, enabling:
    1. Base prompts to remain concise
    2. Tool descriptions maintained in one place
    3. Consistency across Workflows

    Usage:
        middleware = ToolMiddleware()
        enriched_prompt = middleware.enrich_prompt(
            base_prompt="You are a network diagnostics expert...",
            tools=[suzieq_query, netconf_tool, cli_tool]
        )

    Attributes:
        None - tool guide mapping is now derived from ToolRegistry.
    """

    def __init__(self) -> None:
        """Initialize Middleware, set up cache."""
        self._guide_cache: dict[str, str] = {}

    def get_tool_guide(self, tool_name: str) -> str:
        """
        Get capability guide for a tool.

        Uses ToolRegistry._categories to derive the guide prefix,
        replacing the hardcoded TOOL_GUIDE_MAPPING.

        Args:
            tool_name: Tool name (e.g., "suzieq_query")

        Returns:
            capability guide content, or empty string if not found
        """
        if tool_name in self._guide_cache:
            return self._guide_cache[tool_name]

        # Get category from ToolRegistry (replaces TOOL_GUIDE_MAPPING)
        from olav.tools.base import ToolRegistry
        guide_prefix = ToolRegistry._categories.get(tool_name)

        if not guide_prefix:
            # Try resolving alias
            resolved = ToolRegistry._aliases.get(tool_name, tool_name)
            guide_prefix = ToolRegistry._categories.get(resolved)

        if not guide_prefix:
            logger.debug(f"No category for tool: {tool_name}")
            return ""

        guide = prompt_manager.load_tool_capability_guide(guide_prefix)
        self._guide_cache[tool_name] = guide

        if guide:
            logger.debug(f"Loaded capability guide for {tool_name}: {len(guide)} chars")

        return guide

    def enrich_prompt(
        self,
        base_prompt: str,
        tools: list[BaseTool],
        include_guides: bool = True,
        include_tool_table: bool = True,
    ) -> str:
        """
        Auto-inject tool descriptions into Prompt.

        Args:
            base_prompt: Base System Prompt (concise, responsibility-focused)
            tools: List of tools available to current node
            include_guides: Whether to include detailed capability guides
            include_tool_table: Whether to include tool overview table

        Returns:
            Enriched Prompt with tool overview table and capability guides

        Example:
            >>> base = "You are a network diagnostics expert. Analyze user requests."
            >>> enriched = middleware.enrich_prompt(base, [suzieq_query])
            >>> # enriched contains:
            >>> # - Base Prompt
            >>> # - Tool overview table
            >>> # - SuzieQ capability guide
        """
        enriched_parts = [base_prompt]

        # 1. Generate tool overview table
        if include_tool_table and tools:
            tool_table = self._generate_tool_table(tools)
            enriched_parts.append(f"\n## Available Tools\n\n{tool_table}")

        # 2. Collect and deduplicate capability guides
        if include_guides and tools:
            guides = self._collect_guides(tools)
            if guides:
                enriched_parts.append(f"\n## Tool Usage Guide\n\n{guides}")

        return "\n".join(enriched_parts)

    def _generate_tool_table(self, tools: list[BaseTool]) -> str:
        """
        Generate tool overview table.

        Args:
            tools: List of tools

        Returns:
            Markdown formatted tool table
        """
        lines = ["| Tool | Purpose |", "|------|---------|"]
        for tool in tools:
            # Extract first line of docstring as purpose
            desc = "No description"
            if tool.description:
                first_line = tool.description.split("\n")[0].strip()
                # Truncate long descriptions
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
                desc = first_line
            lines.append(f"| `{tool.name}` | {desc} |")
        return "\n".join(lines)

    def _collect_guides(self, tools: list[BaseTool]) -> str:
        """
        Collect and deduplicate capability guides.

        Tools with the same guide_prefix share one guide to avoid duplication.
        Uses ToolRegistry._categories for tool-to-guide mapping.

        Args:
            tools: List of tools

        Returns:
            Merged capability guides
        """
        from olav.tools.base import ToolRegistry

        guides = []
        seen_prefixes: set[str] = set()

        for tool in tools:
            # Get category from ToolRegistry (self-declared by tools)
            guide_prefix = ToolRegistry._categories.get(tool.name)
            if guide_prefix and guide_prefix not in seen_prefixes:
                guide = self.get_tool_guide(tool.name)
                if guide:
                    # Use heading to distinguish different tool guides
                    guides.append(f"### {guide_prefix.upper()} Tools\n\n{guide}")
                    seen_prefixes.add(guide_prefix)

        return "\n\n".join(guides)

    def clear_cache(self) -> None:
        """Clear capability guide cache."""
        self._guide_cache.clear()
        logger.debug("Tool capability guide cache cleared")

    def register_tool_mapping(self, tool_name: str, guide_prefix: str) -> None:
        """
        Dynamically register tool to guide mapping.

        Used for extending support for custom tools.
        Now delegates to ToolRegistry._categories.

        Args:
            tool_name: Tool name
            guide_prefix: capability_guide file prefix (category)
        """
        from olav.tools.base import ToolRegistry

        ToolRegistry._categories[tool_name] = guide_prefix
        logger.debug(f"Registered tool mapping: {tool_name} -> {guide_prefix}")


# Global singleton instance
tool_middleware = ToolMiddleware()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "CommandAnalysis",
    # Command Safety Classification
    "CommandSafety",
    "CommandSafetyClassifier",
    "HITLApprovalHandler",
    # HITL Approval
    "HITLApprovalRequest",
    "HITLApprovalResult",
    # Tool Middleware
    "ToolMiddleware",
    "command_classifier",
    "hitl_handler",
    "tool_middleware",
]
