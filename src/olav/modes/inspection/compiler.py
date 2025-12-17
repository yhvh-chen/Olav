"""Intent Compiler - LLM-driven intent to query plan compilation.

This module implements the IntentCompiler that translates natural language
inspection intents into structured SuzieQ query plans.

Key Features:
- LLM-driven intent compilation with structured output
- Schema-aware: uses suzieq-schema index for context
- Caching: avoids redundant LLM calls for same intents
- Fallback: graceful degradation when LLM fails

Example:
    compiler = IntentCompiler()

    # Compile intent to query plan
    plan = await compiler.compile(
        intent="Check if BGP neighbors are Established",
        severity="critical"
    )

    # Result:
    # QueryPlan(
    #     table="bgp",
    #     method="get",
    #     filters={"state": "Established"},
    #     validation=ValidationRule(field="state", operator="!=", expected="Established")
    # )
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class ValidationRule(BaseModel):
    """Validation rule for threshold checking."""

    field: str = Field(description="Field to validate")
    operator: Literal["==", "!=", ">", "<", ">=", "<=", "in", "not_in"] = Field(
        default="!=", description="Comparison operator"
    )
    expected: Any = Field(description="Expected/threshold value")
    on_match: Literal["report_violation", "report_ok"] = Field(
        default="report_violation",
        description="Action when condition matches"
    )


class QueryPlan(BaseModel):
    """Compiled query plan from intent."""

    table: str = Field(description="SuzieQ table name (e.g., bgp, ospf, interfaces)")
    method: Literal["get", "summarize", "unique", "aver"] = Field(
        default="get", description="Query method"
    )
    filters: dict[str, Any] = Field(
        default_factory=dict, description="Query filters"
    )
    columns: list[str] = Field(
        default_factory=list, description="Columns to return (empty = all)"
    )
    validation: ValidationRule | None = Field(
        default=None, description="Threshold validation rule"
    )

    # Data source control (for multi-source fallback)
    source: Literal["suzieq", "openconfig", "cli", "unknown"] = Field(
        default="suzieq", description="Data source for execution"
    )
    fallback_tool: str | None = Field(
        default=None, description="Tool to use for fallback (netconf_get or cli_show)"
    )
    fallback_params: dict[str, Any] | None = Field(
        default=None, description="Parameters for fallback tool"
    )
    read_only: bool = Field(
        default=True, description="Whether this is a read-only operation (always True for inspection)"
    )

    # Metadata
    compiled_from_intent: str = Field(default="", description="Original intent")
    confidence: float = Field(default=0.8, description="Compilation confidence")


class LLMCompilationResult(BaseModel):
    """LLM structured output for intent compilation."""

    table: str = Field(description="SuzieQ table name")
    method: Literal["get", "summarize", "unique", "aver"] = Field(default="get")
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)

    # Validation
    validation_field: str | None = Field(default=None)
    validation_operator: str = Field(default="!=")
    validation_expected: Any = Field(default=None)

    reasoning: str = Field(default="", description="Reasoning for the compilation")


# =============================================================================
# Intent Compiler
# =============================================================================

# SuzieQ supported tables (commonly available with data)
SUZIEQ_TABLES: set[str] = {
    "bgp", "ospf", "interfaces", "routes", "macs", "arpnd",
    "device", "lldp", "vlan", "evpnVni", "fs", "ifCounters",
    "inventory", "mlag", "network", "path", "sqpoller", "time",
    "topcpu", "topmem", "topology", "vrf",
}

# Checks that need real-time data (SuzieQ parquet may be stale)
REALTIME_TABLES: set[str] = {
    "topcpu", "topmem",  # CPU/memory need fresh data
}

# Show command templates for common checks
SHOW_COMMAND_TEMPLATES: dict[str, str] = {
    "cpu": "show processes cpu",
    "memory": "show memory",
    "temperature": "show environment temperature",
    "power": "show environment power",
    "version": "show version",
    "logging": "show logging",
    "config": "show running-config",
}


class IntentCompiler:
    """LLM-driven intent to query plan compiler.

    Compiles natural language inspection intents into structured SuzieQ
    query plans with validation rules.

    Features:
    - Schema-aware compilation using suzieq-schema context
    - Caching to avoid redundant LLM calls
    - Fallback to default plan on LLM failure

    Usage:
        compiler = IntentCompiler()
        plan = await compiler.compile(
            intent="Check BGP neighbor status",
            severity="critical"
        )
    """

    def __init__(
        self,
        cache_dir: Path | str = "data/cache/inspection_plans",
        enable_cache: bool = True,
    ) -> None:
        """Initialize compiler.

        Args:
            cache_dir: Directory to cache compiled plans.
            enable_cache: Whether to enable caching.
        """
        self.cache_dir = Path(cache_dir)
        self.enable_cache = enable_cache

        if enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load prompt from config
        intent_prompt_template = prompt_manager.load_prompt(
            "inspection",
            "intent_compiler",
            check_name="{check_name}",
            intent="{intent}",
            severity="{severity}",
        )
        self.prompt = ChatPromptTemplate.from_template(intent_prompt_template)
        self._llm: BaseChatModel | None = None

    def _get_llm(self) -> BaseChatModel:
        """Lazy-load LLM with structured output."""
        if self._llm is None:
            from olav.core.llm import LLMFactory

            base_llm = LLMFactory.get_chat_model(json_mode=True)
            self._llm = base_llm.with_structured_output(LLMCompilationResult)
        return self._llm

    def _get_cache_key(self, intent: str, check_name: str, severity: str) -> str:
        """Generate cache key from intent parameters."""
        data = json.dumps({
            "intent": intent,
            "check_name": check_name,
            "severity": severity,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _load_from_cache(self, cache_key: str) -> QueryPlan | None:
        """Load compiled plan from cache."""
        if not self.enable_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return QueryPlan(**data)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return None

    def _save_to_cache(self, cache_key: str, plan: QueryPlan) -> None:
        """Save compiled plan to cache."""
        if not self.enable_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            cache_file.write_text(
                plan.model_dump_json(indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    async def compile(
        self,
        intent: str,
        check_name: str = "",
        severity: str = "warning",
    ) -> QueryPlan:
        """Compile intent to query plan.

        Args:
            intent: Natural language inspection intent.
            check_name: Name of the check (for context).
            severity: Severity level (critical, warning, info).

        Returns:
            QueryPlan with table, filters, and validation rules.
        """
        # Check cache first
        cache_key = self._get_cache_key(intent, check_name, severity)
        cached = self._load_from_cache(cache_key)
        if cached:
            logger.info(f"[IntentCompiler] Cache hit: {check_name}")
            return cached

        logger.info(f"[IntentCompiler] Compiling: {intent[:50]}...")

        try:
            # Call LLM
            llm = self._get_llm()
            messages = self.prompt.format_messages(
                check_name=check_name or "unnamed",
                intent=intent,
                severity=severity,
            )

            result: LLMCompilationResult = await llm.ainvoke(messages)

            # Build QueryPlan
            validation = None
            if result.validation_field and result.validation_expected is not None:
                validation = ValidationRule(
                    field=result.validation_field,
                    operator=result.validation_operator,  # type: ignore
                    expected=result.validation_expected,
                )

            plan = QueryPlan(
                table=result.table,
                method=result.method,
                filters=result.filters,
                columns=result.columns,
                validation=validation,
                compiled_from_intent=intent,
                confidence=0.8,
                read_only=True,  # Always read-only for inspection
            )

            # Check if SuzieQ supports this table
            plan = await self._apply_fallback_if_needed(plan, intent)

            # Cache result
            self._save_to_cache(cache_key, plan)

            logger.info(
                f"[IntentCompiler] Compiled: table={plan.table}, "
                f"method={plan.method}, source={plan.source}, "
                f"validation={plan.validation}"
            )

            return plan

        except Exception as e:
            logger.error(f"[IntentCompiler] Compilation failed: {e}")

            # Fallback: try to infer from intent keywords
            return self._fallback_compile(intent, check_name, severity)

    def compile_sync(
        self,
        intent: str,
        check_name: str = "",
        severity: str = "warning",
    ) -> QueryPlan:
        """Synchronous version of compile."""
        import asyncio
        return asyncio.run(self.compile(intent, check_name, severity))

    def _fallback_compile(
        self,
        intent: str,
        check_name: str,
        severity: str,
    ) -> QueryPlan:
        """Fallback compilation using keyword matching."""
        intent_lower = intent.lower()

        # Keyword to table mapping
        table_keywords = {
            "bgp": ["bgp", "neighbor", "peer", "as"],
            "ospf": ["ospf", "ospf neighbor", "area"],
            "interfaces": ["interface", "port", "error"],
            "routes": ["route", "routing table"],
            "device": ["device", "cpu", "memory", "uptime"],
            "macs": ["mac", "mac address"],
            "lldp": ["lldp", "cdp", "topology"],
            "vlan": ["vlan"],
        }

        # Find best matching table
        table = "device"  # default
        for tbl, keywords in table_keywords.items():
            if any(kw in intent_lower for kw in keywords):
                table = tbl
                break

        logger.warning(
            f"[IntentCompiler] Using fallback: table={table} for intent={intent[:30]}"
        )

        return QueryPlan(
            table=table,
            method="summarize",
            filters={},
            validation=None,
            compiled_from_intent=intent,
            confidence=0.3,  # Low confidence for fallback
            read_only=True,
        )

    async def _apply_fallback_if_needed(
        self,
        plan: QueryPlan,
        intent: str,
    ) -> QueryPlan:
        """Check if SuzieQ supports the table and apply fallback if needed.

        Args:
            plan: The compiled query plan.
            intent: Original intent for fallback compilation.

        Returns:
            Updated QueryPlan with source and fallback_tool if needed.
        """
        # Check if table is supported by SuzieQ
        if plan.table in SUZIEQ_TABLES and plan.table not in REALTIME_TABLES:
            # SuzieQ can handle this
            plan.source = "suzieq"
            return plan

        # Need fallback - try to compile CLI show command
        logger.info(
            f"[IntentCompiler] Table '{plan.table}' needs fallback, "
            f"compiling CLI show command..."
        )

        show_command = await self._compile_show_command(intent, plan.table)

        if show_command:
            plan.source = "cli"
            plan.fallback_tool = "cli_show"
            plan.fallback_params = {"command": show_command}
            plan.confidence = 0.7  # Slightly lower confidence for CLI
            logger.info(f"[IntentCompiler] Fallback to CLI: {show_command}")
        else:
            # Keep SuzieQ as source but log warning
            logger.warning(
                f"[IntentCompiler] Could not compile fallback for '{plan.table}', "
                f"keeping SuzieQ (may fail)"
            )
            plan.source = "suzieq"

        return plan

    async def _compile_show_command(
        self,
        intent: str,
        table: str,
    ) -> str | None:
        """Compile intent to CLI show command.

        Args:
            intent: Natural language intent.
            table: Target table name.

        Returns:
            Show command string, or None if compilation fails.
        """
        # First check if we have a template
        intent_lower = intent.lower()

        for keyword, template in SHOW_COMMAND_TEMPLATES.items():
            if keyword in intent_lower:
                logger.info(
                    f"[IntentCompiler] Using show command template: {template}"
                )
                return template

        # Try LLM compilation for show command
        try:
            from olav.core.llm import LLMFactory

            llm = LLMFactory.get_chat_model()

            # Load prompt from config
            prompt = prompt_manager.load_prompt(
                "inspection",
                "show_command",
                intent=intent,
                table=table,
            )

            response = await llm.ainvoke(prompt)
            command = response.content.strip()

            # Validate: must start with "show "
            if not self._validate_show_command(command):
                logger.warning(
                    f"[IntentCompiler] Invalid command generated: {command}"
                )
                return None

            return command

        except Exception as e:
            logger.error(f"[IntentCompiler] Show command compilation failed: {e}")
            return None

    def _validate_show_command(self, command: str) -> bool:
        """Validate that command is a safe show command.

        Args:
            command: The command to validate.

        Returns:
            True if command is safe (show only), False otherwise.
        """
        if not command:
            return False

        cmd_lower = command.strip().lower()

        # Must start with "show"
        if not cmd_lower.startswith("show "):
            return False

        # Blacklist dangerous patterns
        dangerous_patterns = [
            "configure", "config", "set ", "delete", "no ",
            "write", "copy", "reload", "shutdown", "erase",
            "|", ";", "&&", "||",  # Command injection
        ]

        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                logger.warning(
                    f"[IntentCompiler] Dangerous pattern '{pattern}' in command"
                )
                return False

        return True

    def clear_cache(self) -> int:
        """Clear all cached plans.

        Returns:
            Number of cache files deleted.
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1

        logger.info(f"[IntentCompiler] Cleared {count} cached plans")
        return count
