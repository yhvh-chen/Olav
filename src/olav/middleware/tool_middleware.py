"""Tool Middleware - 自动注入工具说明到 Prompt。

借鉴 deepagents 的 Middleware 模式，实现工具说明的自动注入：
1. 基础 Prompt 保持简短（职责聚焦，<20 行）
2. 工具概览表自动生成
3. Capability Guide 按需加载并注入
4. 跨 Workflow 复用，保证一致性

Phase 4 Extensions:
- HITL (Human-in-the-Loop) support for CLI verification commands
- Command safety classification (read-only vs write operations)
- Pre-execution approval workflow for write operations

Pattern:
    Before (冗长 Prompt):
        60-100 行 Prompt，包含重复的工具说明
    
    After (Middleware 注入):
        15-20 行基础 Prompt + 自动注入的工具说明
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

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
    工具说明自动注入 Middleware。
    
    自动将 capability_guide 注入到 System Prompt，使得：
    1. 基础 Prompt 可以保持简短
    2. 工具说明只需维护一处
    3. 跨 Workflow 保持一致
    
    Usage:
        middleware = ToolMiddleware()
        enriched_prompt = middleware.enrich_prompt(
            base_prompt="你是网络诊断专家...",
            tools=[suzieq_query, netconf_tool, cli_tool]
        )
    
    Attributes:
        TOOL_GUIDE_MAPPING: 工具名到 capability_guide 前缀的映射
    """
    
    # 工具名到 capability_guide 前缀的映射
    # capability_guide 文件位于 config/prompts/tools/{prefix}_capability_guide.yaml
    TOOL_GUIDE_MAPPING: dict[str, str] = {
        # SuzieQ 工具
        "suzieq_query": "suzieq",
        "suzieq_schema_search": "suzieq",
        "suzieq_summarize": "suzieq",
        # NETCONF 工具
        "netconf_get": "netconf",
        "netconf_edit": "netconf",
        "netconf_tool": "netconf",
        # CLI 工具
        "cli_execute": "cli",
        "cli_tool": "cli",
        # NetBox 工具
        "netbox_api_call": "netbox",
        "netbox_schema_search": "netbox",
        "netbox_query": "netbox",
        "netbox_create": "netbox",
        "netbox_update": "netbox",
    }
    
    def __init__(self) -> None:
        """初始化 Middleware，设置缓存。"""
        self._guide_cache: dict[str, str] = {}
    
    def get_tool_guide(self, tool_name: str) -> str:
        """
        获取工具的 capability guide。
        
        Args:
            tool_name: 工具名称（如 "suzieq_query"）
        
        Returns:
            capability guide 内容，如果不存在则返回空字符串
        """
        if tool_name in self._guide_cache:
            return self._guide_cache[tool_name]
        
        guide_prefix = self.TOOL_GUIDE_MAPPING.get(tool_name)
        if not guide_prefix:
            logger.debug(f"No capability guide mapping for tool: {tool_name}")
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
        自动注入工具说明到 Prompt。
        
        Args:
            base_prompt: 基础 System Prompt（简短，职责聚焦）
            tools: 当前节点可用的工具列表
            include_guides: 是否包含详细 capability guide
            include_tool_table: 是否包含工具概览表
        
        Returns:
            增强后的 Prompt，包含工具概览表和 capability guide
        
        Example:
            >>> base = "你是网络诊断专家。分析用户请求。"
            >>> enriched = middleware.enrich_prompt(base, [suzieq_query])
            >>> # enriched 包含:
            >>> # - 基础 Prompt
            >>> # - 工具概览表
            >>> # - SuzieQ capability guide
        """
        enriched_parts = [base_prompt]
        
        # 1. 生成工具概览表
        if include_tool_table and tools:
            tool_table = self._generate_tool_table(tools)
            enriched_parts.append(f"\n## 可用工具\n\n{tool_table}")
        
        # 2. 收集并去重 capability guides
        if include_guides and tools:
            guides = self._collect_guides(tools)
            if guides:
                enriched_parts.append(f"\n## 工具使用指南\n\n{guides}")
        
        return "\n".join(enriched_parts)
    
    def _generate_tool_table(self, tools: list[BaseTool]) -> str:
        """
        生成工具概览表。
        
        Args:
            tools: 工具列表
        
        Returns:
            Markdown 格式的工具表格
        """
        lines = ["| 工具 | 用途 |", "|------|------|"]
        for tool in tools:
            # 提取 docstring 第一行作为用途
            desc = "无描述"
            if tool.description:
                first_line = tool.description.split("\n")[0].strip()
                # 截断过长的描述
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
                desc = first_line
            lines.append(f"| `{tool.name}` | {desc} |")
        return "\n".join(lines)
    
    def _collect_guides(self, tools: list[BaseTool]) -> str:
        """
        收集并去重 capability guides。
        
        同一个 guide_prefix 的工具共享一个 guide，避免重复。
        
        Args:
            tools: 工具列表
        
        Returns:
            合并后的 capability guides
        """
        guides = []
        seen_prefixes: set[str] = set()
        
        for tool in tools:
            guide_prefix = self.TOOL_GUIDE_MAPPING.get(tool.name)
            if guide_prefix and guide_prefix not in seen_prefixes:
                guide = self.get_tool_guide(tool.name)
                if guide:
                    # 使用标题区分不同工具的指南
                    guides.append(f"### {guide_prefix.upper()} 工具\n\n{guide}")
                    seen_prefixes.add(guide_prefix)
        
        return "\n\n".join(guides)
    
    def clear_cache(self) -> None:
        """清空 capability guide 缓存。"""
        self._guide_cache.clear()
        logger.debug("Tool capability guide cache cleared")
    
    def register_tool_mapping(self, tool_name: str, guide_prefix: str) -> None:
        """
        动态注册工具到 guide 的映射。
        
        用于扩展支持自定义工具。
        
        Args:
            tool_name: 工具名称
            guide_prefix: capability_guide 文件前缀
        """
        self.TOOL_GUIDE_MAPPING[tool_name] = guide_prefix
        logger.debug(f"Registered tool mapping: {tool_name} -> {guide_prefix}")


# 全局单例实例
tool_middleware = ToolMiddleware()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Command Safety Classification
    "CommandSafety",
    "CommandAnalysis",
    "CommandSafetyClassifier",
    "command_classifier",
    # HITL Approval
    "HITLApprovalRequest",
    "HITLApprovalResult",
    "HITLApprovalHandler",
    "hitl_handler",
    # Tool Middleware
    "ToolMiddleware",
    "tool_middleware",
]
