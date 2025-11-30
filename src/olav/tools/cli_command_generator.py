"""
CLI Command Generator - LLM-based platform-specific command generation.

This module uses LLM to generate platform-appropriate CLI commands based on:
- User intent (natural language description)
- Target platform (from NetBox SSOT)
- Available commands (from TextFSM templates)

The generator bridges the gap between user intent and platform-specific syntax:
- Cisco IOS: "show ip interface brief"
- Juniper JunOS: "show interfaces terse"
- Arista EOS: "show interfaces status"

Architecture:
- Uses PromptManager to load cli_command_generator.yaml template
- Queries TemplateManager for available commands (used as context)
- Caches generated commands in Redis (reduces LLM calls)
- Returns structured JSON with commands, explanation, and alternatives

Author: OLAV Development Team
Date: 2025-11-27
"""

import hashlib
import json
import logging
from typing import TypedDict

from olav.core.cache import get_cache_manager
from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


class CommandGeneratorResult(TypedDict):
    """Structured result from command generator."""

    commands: list[str]
    explanation: str
    warnings: list[str]
    alternatives: list[str]
    cached: bool


class CLICommandGenerator:
    """
    LLM-based CLI command generator with caching.

    Generates platform-specific CLI commands from natural language intent.
    Uses Redis caching to reduce LLM calls for repeated queries.

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
    """

    CACHE_NAMESPACE = "cli_cmd"
    DEFAULT_TTL = 3600  # 1 hour

    def __init__(self, cache_ttl: int | None = None) -> None:
        """
        Initialize command generator.

        Args:
            cache_ttl: Cache TTL in seconds (default: 3600)
        """
        self.cache_ttl = cache_ttl or self.DEFAULT_TTL
        self._llm = None

    @property
    def llm(self):
        """Lazy-load LLM instance."""
        if self._llm is None:
            self._llm = LLMFactory.get_chat_model(json_mode=True)
        return self._llm

    def _generate_cache_key(self, intent: str, platform: str, context: str) -> str:
        """
        Generate cache key from intent, platform, and context.

        Args:
            intent: User intent
            platform: Target platform
            context: Additional context

        Returns:
            Hash-based cache key
        """
        content = f"{intent}|{platform}|{context}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _get_from_cache(self, cache_key: str) -> CommandGeneratorResult | None:
        """
        Try to get cached result.

        Args:
            cache_key: Cache key

        Returns:
            Cached result or None
        """
        try:
            cache = get_cache_manager()
            cached = await cache.get(f"{self.CACHE_NAMESPACE}:{cache_key}")
            if cached:
                result = json.loads(cached)
                result["cached"] = True
                logger.info(f"[CLICommandGenerator] Cache hit for key: {cache_key[:8]}...")
                return result
        except Exception as e:
            logger.warning(f"[CLICommandGenerator] Cache get failed: {e}")
        return None

    async def _set_to_cache(self, cache_key: str, result: CommandGeneratorResult) -> None:
        """
        Cache the result.

        Args:
            cache_key: Cache key
            result: Result to cache
        """
        try:
            cache = get_cache_manager()
            # Remove cached flag before storing
            to_cache = {k: v for k, v in result.items() if k != "cached"}
            await cache.set(
                f"{self.CACHE_NAMESPACE}:{cache_key}",
                json.dumps(to_cache),
                ttl=self.cache_ttl,
            )
            logger.debug(f"[CLICommandGenerator] Cached result for key: {cache_key[:8]}...")
        except Exception as e:
            logger.warning(f"[CLICommandGenerator] Cache set failed: {e}")

    async def generate(
        self,
        intent: str,
        platform: str,
        available_commands: list[str] | None = None,
        context: str = "",
        use_cache: bool = True,
    ) -> CommandGeneratorResult:
        """
        Generate platform-specific CLI commands from intent.

        Args:
            intent: Natural language description of what to check/do
                   Example: "Check BGP neighbor status", "Show interface errors"
            platform: Target platform identifier
                     Examples: "cisco_ios", "cisco_iosxr", "arista_eos", "juniper_junos"
            available_commands: List of commands available from TextFSM templates
                               If None, no filtering is applied
            context: Additional context (e.g., device info, previous errors)
            use_cache: Whether to use Redis cache (default: True)

        Returns:
            CommandGeneratorResult with:
            - commands: List of CLI commands to execute
            - explanation: Brief explanation of what each command does
            - warnings: Any warnings about the commands
            - alternatives: Alternative commands if primary fails
            - cached: Whether result was from cache

        Example:
            >>> generator = CLICommandGenerator()
            >>> result = await generator.generate(
            ...     intent="Show BGP neighbor status",
            ...     platform="cisco_ios",
            ...     available_commands=["show ip bgp summary", "show ip bgp neighbors"]
            ... )
            >>> print(result["commands"])
            ["show ip bgp summary", "show ip bgp neighbors"]
        """
        # Format available commands for prompt
        commands_str = (
            "\n".join(f"- {cmd}" for cmd in available_commands)
            if available_commands
            else "No specific template list available"
        )

        # Check cache first
        cache_key = self._generate_cache_key(intent, platform, context)
        if use_cache:
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

        # Load prompt template
        try:
            prompt = prompt_manager.load_prompt(
                category="tools",
                name="cli_command_generator",
                intent=intent,
                platform=platform,
                available_commands=commands_str,
                context=context or "No additional context",
            )
        except FileNotFoundError:
            logger.error("[CLICommandGenerator] Prompt template not found")
            return CommandGeneratorResult(
                commands=[],
                explanation="Prompt template not found",
                warnings=["CLI command generator prompt template missing"],
                alternatives=[],
                cached=False,
            )

        # Call LLM
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            # Parse JSON response
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                else:
                    raise

            # Normalize result
            normalized: CommandGeneratorResult = {
                "commands": result.get("commands", []),
                "explanation": result.get("explanation", ""),
                "warnings": result.get("warnings", []),
                "alternatives": result.get("alternatives", []),
                "cached": False,
            }

            # Cache result
            if use_cache:
                await self._set_to_cache(cache_key, normalized)

            logger.info(
                f"[CLICommandGenerator] Generated {len(normalized['commands'])} commands "
                f"for platform={platform}, intent='{intent[:50]}...'"
            )
            return normalized

        except Exception as e:
            logger.exception(f"[CLICommandGenerator] LLM generation failed: {e}")
            return CommandGeneratorResult(
                commands=[],
                explanation="",
                warnings=[f"Command generation failed: {e}"],
                alternatives=[],
                cached=False,
            )


# Global instance
_generator: CLICommandGenerator | None = None


def get_command_generator() -> CLICommandGenerator:
    """Get global command generator instance."""
    global _generator
    if _generator is None:
        _generator = CLICommandGenerator()
    return _generator


async def generate_platform_command(
    intent: str,
    platform: str,
    available_commands: list[str] | None = None,
    context: str = "",
) -> CommandGeneratorResult:
    """
    Convenience function to generate platform-specific CLI commands.

    This is the main entry point for other modules to use.

    Args:
        intent: Natural language description
        platform: Target platform (cisco_ios, arista_eos, etc.)
        available_commands: Available TextFSM template commands
        context: Additional context

    Returns:
        CommandGeneratorResult with commands and metadata

    Example:
        >>> from olav.tools.cli_command_generator import generate_platform_command
        >>> result = await generate_platform_command(
        ...     intent="Check for interface CRC errors",
        ...     platform="cisco_ios"
        ... )
        >>> result["commands"]
        ["show interfaces | include CRC", "show interfaces counters errors"]
    """
    generator = get_command_generator()
    return await generator.generate(
        intent=intent,
        platform=platform,
        available_commands=available_commands,
        context=context,
    )
