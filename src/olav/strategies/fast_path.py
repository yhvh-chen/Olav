"""
Fast Path Strategy - Single-shot function calling for simple queries.

This strategy bypasses agent loops and multi-step reasoning for queries
that can be answered with a single tool invocation. Optimizes for:
- Low latency (< 2 seconds)
- High accuracy (no iterative hallucination)
- Simple queries (status checks, single-device lookups)

Execution Flow:
1. Parameter Extraction: LLM extracts structured params from query
2. Tool Selection: Priority queue (SuzieQ > NetBox > CLI)
3. Single Invocation: Call tool once, no loops (with optional caching)
4. Strict Formatting: Force LLM to use tool output only (no speculation)

Example Queries (these are illustrative, actual table names discovered via Schema):
- "查询 R1 的 BGP 邻居状态" → suzieq_query(table=<discovered>, hostname="R1")
- "Switch-A 的管理 IP 是什么？" → netbox_api_call(endpoint="/dcim/devices/", name="Switch-A")
- "检查接口 eth0 状态" → suzieq_query(table="interfaces", ifname="eth0")

Key Difference from Agent Loop:
- Agent: Query → Think → Tool → Think → Tool → Think → Answer (slow, may drift)
- Fast Path: Query → Extract Params → Tool → Format Answer (fast, deterministic)

Caching (Phase B.2):
- Tool results cached using FilesystemMiddleware
- Cache key: SHA256 hash of (tool_name + parameters)
- Reduces duplicate LLM calls by 10-20%
- Cache TTL: 300 seconds (configurable)

Resilience (LangChain 1.10):
- ToolRetryMiddleware: Automatic retry for transient network errors
- Exponential backoff with jitter to prevent thundering herd

Refactored: Uses LangChain with_structured_output() - no fallback parsing needed.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Literal

import numpy as np
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from olav.core.json_utils import robust_structured_output
from olav.core.llm_intent_classifier import classify_intent_with_llm
from olav.core.prompt_manager import prompt_manager
from olav.core.memory_writer import MemoryWriter
from olav.core.middleware import FilesystemMiddleware
from olav.tools.base import ToolOutput, ToolRegistry
from olav.tools.opensearch_tool import EpisodicMemoryTool

logger = logging.getLogger(__name__)


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs: Any) -> str:
    """JSON dumps with numpy support."""
    return json.dumps(obj, cls=NumpyEncoder, **kwargs)


class ParameterExtraction(BaseModel):
    """
    Structured parameters extracted from user query.

    LLM converts natural language to tool-compatible parameters.
    """

    tool: Literal[
        "suzieq_query",
        "netbox_api",
        "netbox_api_call",
        "cli_execute",
        "cli_tool",
        "netconf_execute",
        "netconf_tool",
        "openconfig_schema_search",
        "netbox_schema_search",
        "suzieq_schema_search",
    ]
    parameters: dict[str, Any] = Field(description="Tool-specific parameters")
    confidence: float = Field(
        description="Confidence that Fast Path is appropriate (0.0-1.0)", ge=0.0, le=1.0
    )
    reasoning: str = Field(description="Why this tool and parameters were chosen")


# Intent classification - use LLM-based classifier with keyword fallback
# The LLMIntentClassifier provides more dynamic classification while
# keeping minimal keyword patterns as a fast fallback.
# See: olav.core.llm_intent_classifier (imported at top)

# Minimal keyword patterns for fast fallback (reduced from ~50 to ~15 keywords)
# Extended with CLI-specific keywords for config queries that SuzieQ doesn't cover
INTENT_PATTERNS_FALLBACK: dict[str, list[str]] = {
    "netbox": ["netbox", "cmdb", "资产", "设备清单", "inventory"],
    "openconfig": ["openconfig", "yang", "xpath"],
    "cli": [
        "cli",
        "ssh",
        "命令行",
        "show run",
        "running-config",
        # Config items NOT collected by SuzieQ - need CLI/NETCONF
        "syslog",
        "logging",
        "日志服务",
        "日志配置",
        "ntp",
        "时间同步",
        "clock",
        "snmp",
        "snmp-server",
        "监控配置",
        "aaa",
        "tacacs",
        "radius",
        "认证",
        "授权",
        "banner",
        "motd",
        "登录提示",
        "username",
        "用户",
        "密码",
        "acl",
        "access-list",
        "访问控制",
        "line vty",
        "console",
        "终端配置",
    ],
    "netconf": ["netconf", "rpc", "edit-config"],
    "suzieq": ["bgp", "ospf", "interface", "route", "状态", "status"],
}

# Fallback tool chain when primary schema has no match
# Maps intent category to ordered list of fallback tools
FALLBACK_TOOL_CHAIN: dict[str, list[str]] = {
    "suzieq": ["cli_tool", "netconf_tool"],  # SuzieQ no data → try CLI/NETCONF
    "netbox": ["suzieq_query", "cli_tool"],  # NetBox no match → try SuzieQ/CLI
    "openconfig": ["cli_tool", "netconf_tool"],  # OpenConfig no path → try CLI
    "cli": [],  # CLI is already fallback
    "netconf": ["cli_tool"],  # NETCONF fails → try CLI
}


def classify_intent(query: str) -> tuple[str, float]:
    """
    Classify user query intent to determine tool category.

    DEPRECATED: This is a synchronous fallback using keyword matching.
    For async context, use classify_intent_async() which uses LLM for
    more accurate, context-aware classification.

    Args:
        query: User's natural language query

    Returns:
        Tuple of (tool_category, confidence)
        Categories: "netbox", "openconfig", "cli", "netconf", "suzieq"
    """
    query_lower = query.lower()

    # Count matches for each category
    scores: dict[str, int] = {}
    for category, patterns in INTENT_PATTERNS_FALLBACK.items():
        score = sum(1 for p in patterns if p.lower() in query_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        # Default to SuzieQ for general network queries
        return ("suzieq", 0.5)

    # Get highest scoring category
    best_category = max(scores, key=lambda k: scores[k])
    best_score = scores[best_category]

    # Calculate confidence based on score and uniqueness
    total_matches = sum(scores.values())
    if total_matches > 0:
        # Higher confidence if matches are concentrated in one category
        confidence = min(0.95, 0.5 + (best_score / total_matches) * 0.4 + (best_score * 0.05))
    else:
        confidence = 0.5

    return (best_category, confidence)


async def classify_intent_async(query: str) -> tuple[str, float]:
    """
    Async intent classification using LLM with keyword fallback.

    Uses LLMIntentClassifier for dynamic, context-aware classification.
    Falls back to keyword matching if LLM call fails.

    Args:
        query: User's natural language query

    Returns:
        Tuple of (tool_category, confidence)
        Categories: "netbox", "openconfig", "cli", "netconf", "suzieq"
    """
    try:
        result = await classify_intent_with_llm(query)
        return (result.category, result.confidence)
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}, using keyword fallback")
        return classify_intent(query)


class FormattedAnswer(BaseModel):
    """
    Structured answer based strictly on tool output.

    LLM formats tool data into human-readable response without speculation.
    """

    answer: str = Field(description="Human-readable answer derived from tool data")
    data_used: list[str] = Field(description="List of fields from tool output used in answer")
    confidence: float = Field(description="Confidence in answer accuracy (0.0-1.0)", ge=0.0, le=1.0)


class FastPathStrategy:
    """
    Fast Path execution strategy for simple, single-tool queries.

    Implements a three-step process:
    1. Extract parameters from natural language
    2. Execute single tool call (priority: SuzieQ > NetBox > CLI) with caching
    3. Format answer in strict mode (no hallucination beyond tool data)

    Attributes:
        llm: Language model for parameter extraction and formatting
        tool_registry: Registry of available tools
        priority_order: Default tool selection priority
        confidence_threshold: Minimum confidence to use Fast Path (default: 0.7)
        filesystem: FilesystemMiddleware for tool result caching (optional)
        cache_ttl: Cache time-to-live in seconds (default: 300)
        enable_cache: Whether to enable tool result caching (default: True)
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tool_registry: "ToolRegistry",
        confidence_threshold: float = 0.7,
        memory_writer: MemoryWriter | None = None,
        enable_memory_rag: bool = True,
        episodic_memory_tool: EpisodicMemoryTool | None = None,
        filesystem: FilesystemMiddleware | None = None,
        enable_cache: bool = True,
        cache_ttl: int = 300,
    ) -> None:
        """
        Initialize Fast Path strategy.

        Args:
            llm: Language model (should support JSON mode)
            tool_registry: ToolRegistry instance (required for tool discovery)
            confidence_threshold: Min confidence to proceed (default: 0.7)
            memory_writer: MemoryWriter for capturing successes (optional)
            enable_memory_rag: Enable episodic memory RAG optimization (default: True)
            episodic_memory_tool: Tool for searching historical patterns (optional)
            filesystem: FilesystemMiddleware for caching (optional, auto-created if None)
            enable_cache: Enable tool result caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 300)
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.confidence_threshold = confidence_threshold
        self.memory_writer = memory_writer or MemoryWriter()
        self.enable_memory_rag = enable_memory_rag
        self.episodic_memory_tool = episodic_memory_tool or EpisodicMemoryTool()
        self.priority_order = ["suzieq_query", "netbox_api_call", "cli_tool", "netconf_tool"]

        # Caching configuration (Phase B.2)
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.filesystem = filesystem  # Will be created on-demand if None

        # Load tool capability guides (cached at init)
        self._tool_guides = self._load_tool_capability_guides()

        # Validate tool registry
        if not self.tool_registry:
            msg = "ToolRegistry is required for FastPathStrategy"
            raise ValueError(msg)

        logger.info(
            f"FastPathStrategy initialized with confidence threshold: {confidence_threshold}, "
            f"available tools: {len(self.tool_registry.list_tools())}, "
            f"caching: {enable_cache} (TTL: {cache_ttl}s)"
        )

    def _load_tool_capability_guides(self) -> dict[str, str]:
        """Load tool capability guides from config/prompts/tools/.

        Returns:
            Dict mapping tool prefix to capability guide content
        """
        from olav.core.prompt_manager import prompt_manager

        guides = {}
        # Load guides for main tool categories
        for tool_prefix in ["suzieq", "netbox", "cli", "netconf"]:
            guide = prompt_manager.load_tool_capability_guide(tool_prefix)
            if guide:
                guides[tool_prefix] = guide
                logger.debug(f"Loaded capability guide for: {tool_prefix}")

        return guides

    def _get_tool_category(self, tool_name: str) -> str:
        """Map tool name to intent category.

        Args:
            tool_name: Name of the tool (e.g., "suzieq_query", "netbox_api")

        Returns:
            Intent category: "suzieq", "netbox", "openconfig", "cli", "netconf"
        """
        # Tool name to category mapping
        tool_category_map = {
            "suzieq_query": "suzieq",
            "suzieq_schema_search": "suzieq",
            "netbox_api": "netbox",
            "netbox_api_call": "netbox",
            "netbox_schema_search": "netbox",
            "openconfig_schema_search": "openconfig",
            "cli_execute": "cli",
            "cli_tool": "cli",
            "netconf_execute": "netconf",
            "netconf_tool": "netconf",
        }

        return tool_category_map.get(tool_name, "suzieq")

    async def _discover_schema_for_intent(
        self, query: str, intent_category: str
    ) -> dict[str, Any] | None:
        """Discover schema based on intent category.

        Different schema sources for different intents:
        - suzieq: SuzieQ schema (tables like bgp, ospf, interfaces)
        - netbox: NetBox schema (endpoints like /dcim/devices/)
        - openconfig: OpenConfig YANG paths

        Args:
            query: User query for semantic search
            intent_category: Classified intent category

        Returns:
            Schema context dict or None if discovery fails
        """
        try:
            if intent_category == "suzieq":
                # Use existing SuzieQ schema discovery
                return await self._discover_schema(query)

            if intent_category == "netbox":
                # Search NetBox schema for relevant endpoints
                from olav.tools.netbox_tool import NetBoxSchemaSearchTool

                netbox_tool = NetBoxSchemaSearchTool()
                result = await netbox_tool.execute(query=query)

                if result and not result.error and result.data:
                    endpoints = result.data if isinstance(result.data, list) else []
                    return {ep.get("path", ""): ep for ep in endpoints[:5]}
                return None

            if intent_category == "openconfig":
                # Search OpenConfig schema for XPaths
                from olav.tools.opensearch_tool import OpenConfigSchemaTool

                oc_tool = OpenConfigSchemaTool()
                result = await oc_tool.execute(intent=query)

                if result and not result.error and result.data:
                    paths = result.data if isinstance(result.data, list) else []
                    return {p.get("xpath", ""): p for p in paths[:10]}
                return None

            # CLI/NETCONF don't need schema discovery
            return None

        except Exception as e:
            logger.warning(f"Schema discovery failed for {intent_category}: {e}")
            return None

    async def execute(
        self, user_query: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Execute Fast Path strategy for a user query.

        Improved tool selection flow:
        1. Intent Classification: Keyword-based pre-classification
        2. Schema Discovery: Find correct tables/endpoints for the classified category
        3. Episodic Memory: Only use if tool category matches intent
        4. Parameter Extraction: LLM extracts params with schema context
        5. Tool Execution: Execute with caching

        Args:
            user_query: Natural language query
            context: Optional context (device list, network topology, etc.)

        Returns:
            Dict with 'success', 'answer', 'tool_output', 'metadata'
        """
        try:
            # Step 0: Intent Classification using LLM (with keyword fallback)
            intent_category, intent_confidence = await classify_intent_async(user_query)
            logger.info(
                f"Intent classified as '{intent_category}' (confidence: {intent_confidence:.2f})"
            )

            # Step 1: Schema Discovery based on intent category
            schema_context = await self._discover_schema_for_intent(user_query, intent_category)
            if schema_context:
                logger.info(
                    f"Schema-Aware: discovered {len(schema_context)} entries for {intent_category}"
                )

            # Step 1.5: Check schema relevance (Fallback Chain)
            # If discovered schema doesn't match query semantically, use fallback tool
            use_fallback = False
            fallback_reason = None
            if intent_category in ("suzieq", "openconfig"):
                is_relevant, fallback_reason = self._check_schema_relevance(
                    user_query, schema_context, intent_category
                )
                if not is_relevant:
                    logger.warning(
                        f"Schema mismatch detected: {fallback_reason}. Triggering fallback."
                    )
                    use_fallback = True

            if use_fallback:
                # Direct fallback execution (bypass LLM parameter extraction)
                fallback_tool, fallback_params = self._get_fallback_tool(
                    intent_category, user_query
                )
                logger.info(f"Fallback: using {fallback_tool} instead of {intent_category} tools")

                # Check if this is an "all devices" query that needs batch execution
                device_param = fallback_params.get("device", "")
                if device_param == "__ALL_DEVICES__" or fallback_params.get("batch_mode"):
                    logger.info(
                        "Fallback detected 'all devices' query - signaling for batch workflow"
                    )
                    return {
                        "success": False,
                        "reason": "batch_execution_required",
                        "fallback_required": True,
                        "batch_hint": {
                            "tool": fallback_tool,
                            "command": fallback_params.get("command"),
                            "xpath": fallback_params.get("xpath"),
                            "all_devices": True,
                        },
                        "message": "Query requires execution on all devices - use batch workflow",
                    }

                # Check for unknown device
                if device_param == "__UNKNOWN__":
                    logger.warning("Fallback could not determine device from query")
                    return {
                        "success": False,
                        "reason": "device_not_specified",
                        "fallback_required": True,
                        "message": "Could not determine which device to query. Please specify a device name.",
                    }

                # Execute fallback tool directly
                tool_output = await self._execute_tool(fallback_tool, fallback_params)

                if tool_output.error:
                    logger.error(f"Fallback tool execution failed: {tool_output.error}")
                    return {
                        "success": False,
                        "reason": "fallback_tool_error",
                        "error": tool_output.error,
                        "tool_output": tool_output,
                        "fallback_info": {
                            "original_category": intent_category,
                            "fallback_tool": fallback_tool,
                            "fallback_reason": fallback_reason,
                        },
                    }

                # Format answer for fallback result
                fallback_extraction = ParameterExtraction(
                    tool=fallback_tool,
                    parameters=fallback_params,
                    confidence=0.7,  # Lower confidence for fallback
                    reasoning=f"Fallback from {intent_category}: {fallback_reason}",
                )
                formatted = await self._format_answer(user_query, tool_output, fallback_extraction)

                return {
                    "success": True,
                    "answer": formatted.answer,
                    "tool_output": tool_output,
                    "metadata": {
                        "strategy": "fast_path_fallback",
                        "original_category": intent_category,
                        "fallback_tool": fallback_tool,
                        "fallback_reason": fallback_reason,
                        "confidence": 0.7,
                        "data_fields_used": formatted.data_used,
                        "answer_confidence": formatted.confidence,
                    },
                }

            # Step 2: Search episodic memory (RAG optimization)
            # Only use if tool category matches intent classification
            memory_pattern = None
            if self.enable_memory_rag:
                memory_pattern = await self._search_episodic_memory(user_query)

                if memory_pattern:
                    memory_tool = memory_pattern.get("tool", "")
                    memory_category = self._get_tool_category(memory_tool)

                    # Validate memory pattern against intent classification
                    if memory_category != intent_category:
                        logger.warning(
                            f"Episodic memory suggests '{memory_tool}' ({memory_category}) but "
                            f"intent classified as '{intent_category}'. Ignoring memory."
                        )
                        memory_pattern = None
                    elif schema_context:
                        # Also validate against schema if available
                        memory_table = memory_pattern.get("parameters", {}).get("table")
                        if (
                            memory_table
                            and intent_category == "suzieq"
                            and memory_table not in schema_context
                        ):
                            logger.warning(
                                f"Episodic memory suggests table '{memory_table}' but schema "
                                f"suggests {list(schema_context.keys())}. Ignoring memory."
                            )
                            memory_pattern = None

            # Step 3: Extract parameters (use memory pattern if valid, else LLM with schema)
            if memory_pattern and memory_pattern.get("confidence", 0) > 0.8:
                # Use historical pattern directly
                extraction = ParameterExtraction(
                    tool=memory_pattern["tool"],
                    parameters=memory_pattern["parameters"],
                    confidence=memory_pattern["confidence"],
                    reasoning=f"From episodic memory: {memory_pattern.get('intent', 'historical pattern')}",
                )
                logger.info(
                    f"Using episodic memory pattern: {memory_pattern['tool']} "
                    f"(confidence: {memory_pattern['confidence']:.2f})"
                )
            else:
                # LLM parameter extraction WITH schema context and intent hint
                extraction = await self._extract_parameters(
                    user_query, context, schema_context, intent_category
                )

            # Check confidence threshold
            if extraction.confidence < self.confidence_threshold:
                logger.info(
                    f"Fast Path confidence {extraction.confidence:.2f} below threshold "
                    f"{self.confidence_threshold}, falling back to standard workflow"
                )
                return {
                    "success": False,
                    "reason": "low_confidence",
                    "confidence": extraction.confidence,
                    "fallback_required": True,
                }

            logger.info(
                f"Fast Path selected tool: {extraction.tool} "
                f"(confidence: {extraction.confidence:.2f})"
            )

            # Step 2: Check for "all devices" before execution
            # CLI and NETCONF tools don't support "all" - need batch workflow
            device_param = extraction.parameters.get("device", "")
            if extraction.tool in ("cli_tool", "netconf_tool") and device_param in (
                "all",
                "__ALL_DEVICES__",
            ):
                # Check if query implies all devices
                all_devices_patterns = [
                    "所有设备",
                    "全部设备",
                    "all device",
                    "每个设备",
                    "各设备",
                    "所有路由器",
                    "所有交换机",
                    "all router",
                    "all switch",
                ]
                query_lower = user_query.lower()
                is_all_devices = any(p in query_lower for p in all_devices_patterns)

                if is_all_devices:
                    logger.info(
                        "Fast Path detected 'all devices' for CLI/NETCONF - signaling batch workflow"
                    )
                    return {
                        "success": False,
                        "reason": "batch_execution_required",
                        "fallback_required": True,
                        "batch_hint": {
                            "tool": extraction.tool,
                            "command": extraction.parameters.get("command"),
                            "xpath": extraction.parameters.get("xpath"),
                            "all_devices": True,
                        },
                        "message": "Query requires execution on all devices - use batch workflow",
                    }

            # Step 3: Execute tool
            tool_output = await self._execute_tool(extraction.tool, extraction.parameters)

            if tool_output.error:
                logger.error(f"Tool execution failed: {tool_output.error}")
                return {
                    "success": False,
                    "reason": "tool_error",
                    "error": tool_output.error,
                    "tool_output": tool_output,
                }

            # Step 3: Format answer (strict mode)
            formatted = await self._format_answer(user_query, tool_output, extraction)

            # Step 4: Capture success to episodic memory
            execution_time_ms = tool_output.metadata.get("elapsed_ms", 0)
            await self.memory_writer.capture_success(
                intent=user_query,
                tool_used=extraction.tool,
                parameters=extraction.parameters,
                tool_output=tool_output,
                strategy_used="fast_path",
                execution_time_ms=execution_time_ms,
            )

            return {
                "success": True,
                "answer": formatted.answer,
                "tool_output": tool_output,
                "metadata": {
                    "strategy": "fast_path",
                    "tool": extraction.tool,
                    "confidence": extraction.confidence,
                    "data_fields_used": formatted.data_used,
                    "answer_confidence": formatted.confidence,
                },
            }

        except Exception as e:
            logger.exception(f"Fast Path execution failed: {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
                "fallback_required": True,
            }

    async def _discover_schema(self, user_query: str) -> dict[str, Any] | None:
        """
        Schema-Aware discovery: search schema to find correct tables/fields.

        This is CRITICAL for avoiding table name guessing errors like
        using 'ospf' instead of 'ospfNbr'.

        Args:
            user_query: User's natural language query

        Returns:
            Dict mapping table names to their schema info, or None if not applicable
        """
        try:
            # Get the schema search tool
            schema_tool = self.tool_registry.get_tool("suzieq_schema_search")
            if not schema_tool:
                logger.debug("suzieq_schema_search tool not available, skipping schema discovery")
                return None

            # Execute schema search
            from olav.tools.base import ToolOutput

            result = await schema_tool.execute(query=user_query)

            if isinstance(result, ToolOutput) and result.data:
                # Extract relevant tables from schema search result
                schema_context = {}
                data = result.data

                # Handle different response formats
                if isinstance(data, dict):
                    # Format: {'tables': [...], 'table1': {...}, ...}
                    tables = data.get("tables", [])
                    for table in tables:
                        if table in data:
                            schema_context[table] = data[table]
                elif isinstance(data, list):
                    # Format: [{'table': 'name', 'fields': [...], ...}, ...]
                    for item in data:
                        if isinstance(item, dict) and "table" in item:
                            schema_context[item["table"]] = item

                if schema_context:
                    logger.info(f"Schema discovery found tables: {list(schema_context.keys())}")
                    return schema_context

            return None

        except Exception as e:
            logger.warning(f"Schema discovery failed: {e}")
            return None

    def _check_schema_relevance(
        self,
        user_query: str,
        schema_context: dict[str, Any] | None,
        intent_category: str,
    ) -> tuple[bool, str | None]:
        """
        Check if discovered schema is relevant to user query.

        This prevents using SuzieQ tables like 'bgp' or 'interfaces' when
        the user is asking about 'syslog' which SuzieQ doesn't collect.

        Args:
            user_query: Original user query
            schema_context: Discovered schema (tables/endpoints/paths)
            intent_category: Classified intent category

        Returns:
            Tuple of (is_relevant, fallback_reason)
            - is_relevant: True if schema matches query semantically
            - fallback_reason: Explanation if not relevant (for logging)
        """
        if not schema_context:
            return False, "No schema discovered"

        query_lower = user_query.lower()

        # Extract key terms from query for matching
        # These are the terms we expect to find in schema results
        query_terms = set()
        for word in query_lower.split():
            # Skip common stop words
            if len(word) > 2 and word not in {
                "the",
                "all",
                "for",
                "and",
                "查询",
                "检查",
                "显示",
                "配置",
            }:
                query_terms.add(word)

        # Check if any schema table/endpoint name matches query terms
        schema_names = set(schema_context.keys())
        schema_names_lower = {name.lower() for name in schema_names}

        # Direct match: query term appears in schema name
        direct_matches = query_terms & schema_names_lower
        if direct_matches:
            logger.debug(f"Schema relevance: direct match found {direct_matches}")
            return True, None

        # Semantic mapping for common network concepts
        semantic_map = {
            # Query terms → Expected schema tables
            "syslog": ["syslog", "logging"],
            "logging": ["syslog", "logging"],
            "日志": ["syslog", "logging"],
            "ntp": ["ntp", "clock", "time"],
            "时间": ["ntp", "clock", "time"],
            "snmp": ["snmp"],
            "监控": ["snmp"],
            "aaa": ["aaa", "tacacs", "radius"],
            "认证": ["aaa", "tacacs", "radius"],
            "acl": ["acl", "access-list", "firewall"],
            "访问控制": ["acl", "access-list"],
            "bgp": ["bgp"],
            "ospf": ["ospf", "ospfNbr", "ospfIf"],
            "interface": ["interfaces", "interface"],
            "接口": ["interfaces", "interface"],
            "route": ["routes", "route"],
            "路由": ["routes", "route"],
            "vlan": ["vlan", "vlans"],
        }

        # Check semantic relevance
        for term in query_terms:
            expected_schemas = semantic_map.get(term, [])
            if expected_schemas:
                # Check if any expected schema is in discovered schema
                for expected in expected_schemas:
                    if any(expected in name.lower() for name in schema_names):
                        logger.debug(f"Schema relevance: semantic match {term} → {expected}")
                        return True, None

                # Expected schema not found - this is a mismatch
                logger.info(
                    f"Schema mismatch: query term '{term}' expects {expected_schemas}, "
                    f"but schema has {list(schema_names)}"
                )
                return False, f"Query requires '{term}' but schema has {list(schema_names)[:3]}"

        # Default: if no specific term matched, trust the schema discovery
        # This handles generic queries like "check R1 status"
        return True, None

    def _get_fallback_tool(
        self,
        intent_category: str,
        user_query: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        Get fallback tool and parameters when primary schema has no match.

        Uses FALLBACK_TOOL_CHAIN to determine next tool to try.
        Extracts basic parameters (device names) from query.

        Args:
            intent_category: Original intent category
            user_query: User query for parameter extraction

        Returns:
            Tuple of (tool_name, parameters)
        """
        fallback_chain = FALLBACK_TOOL_CHAIN.get(intent_category, ["cli_tool"])
        fallback_tool = fallback_chain[0] if fallback_chain else "cli_tool"

        # Extract device names from query (simple regex)
        import re

        device_pattern = r"\b([A-Z][A-Za-z0-9_-]*\d+|R\d+|SW\d+|Switch-?\w+|Router-?\w+)\b"
        devices = re.findall(device_pattern, user_query)

        # Check if query implies "all devices" operation
        all_devices_patterns = [
            "所有设备",
            "全部设备",
            "all device",
            "每个设备",
            "各设备",
            "所有路由器",
            "所有交换机",
            "all router",
            "all switch",
        ]
        query_lower = user_query.lower()
        is_all_devices = any(p in query_lower for p in all_devices_patterns)

        # If "all devices" and no specific device mentioned, get device list from tool registry
        device_param = devices[0] if devices else None
        if not device_param and is_all_devices:
            # Try to get device list from NetBox/inventory
            try:
                # Use tool registry to get available devices
                if hasattr(self.tool_registry, "get_device_list"):
                    device_list = self.tool_registry.get_device_list()
                    if device_list:
                        device_param = device_list  # Pass as list for batch execution
            except Exception as e:
                logger.warning(f"Failed to get device list for fallback: {e}")

        # Build parameters based on fallback tool
        if fallback_tool == "cli_tool":
            # Determine CLI command based on query keywords
            if "syslog" in query_lower or "logging" in query_lower or "日志" in query_lower:
                command = "show logging"
            elif "ntp" in query_lower or "时间" in query_lower:
                command = "show ntp status"
            elif "snmp" in query_lower:
                command = "show snmp"
            elif "aaa" in query_lower or "认证" in query_lower:
                command = "show aaa"
            elif "acl" in query_lower or "访问" in query_lower:
                command = "show access-lists"
            else:
                command = "show running-config"

            # If still no device and it's an "all devices" query, signal that
            # the query needs batch execution (return special marker)
            if device_param is None and is_all_devices:
                # For "all devices" queries without explicit device list,
                # return a special marker that indicates batch execution needed
                params = {
                    "device": "__ALL_DEVICES__",  # Special marker
                    "command": command,
                    "batch_mode": True,
                }
            else:
                params = {
                    "device": device_param if device_param else "__UNKNOWN__",
                    "command": command,
                }
        elif fallback_tool == "netconf_tool":
            # Use generic system xpath for config queries
            params = {
                "device": device_param if device_param else "__ALL_DEVICES__",
                "xpath": "/system",
            }
        else:
            params = {}

        logger.info(f"Fallback to {fallback_tool} with params: {params}")
        return fallback_tool, params

    async def _extract_parameters(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        schema_context: dict[str, Any] | None = None,
        intent_category: str | None = None,
    ) -> ParameterExtraction:
        """
        Extract structured parameters from natural language query.

        Uses Schema-Aware pattern with Intent-Guided tool selection:
        1. Intent category guides which tool family to prefer
        2. Schema context provides exact table/endpoint names
        3. LLM extracts parameters for the chosen tool

        Args:
            user_query: User's query
            context: Optional context for parameter extraction
            schema_context: Schema info from _discover_schema (table names and fields)
            intent_category: Pre-classified intent category (suzieq, netbox, openconfig, cli, netconf)

        Returns:
            ParameterExtraction with tool and parameters
        """
        # Map intent to preferred tool
        intent_tool_map = {
            "suzieq": "suzieq_query",
            "netbox": "netbox_api_call",
            "openconfig": "openconfig_schema_search",
            "cli": "cli_tool",
            "netconf": "netconf_tool",
        }
        preferred_tool = intent_tool_map.get(intent_category or "suzieq", "suzieq_query")

        # Build intent-aware schema section
        if schema_context:
            if intent_category == "netbox":
                # NetBox endpoint format
                schema_items = "\n".join(
                    [
                        f"    - {endpoint}: {info.get('description', '')}"
                        for endpoint, info in list(schema_context.items())[:5]
                    ]
                )
                schema_section = f"""
## 🎯 NetBox Schema Discovery 结果
意图分类：**NetBox 设备/IP查询**（优先使用 netbox_api_call）
以下是相关的 NetBox API 端点：
{schema_items}

⚠️ 重要：使用 netbox_api_call 工具和上述端点！
"""
            elif intent_category == "openconfig":
                # OpenConfig XPath format
                schema_items = "\n".join(
                    [
                        f"    - {xpath}: {info.get('description', '')}"
                        for xpath, info in list(schema_context.items())[:10]
                    ]
                )
                schema_section = f"""
## 🎯 OpenConfig Schema Discovery 结果
意图分类：**OpenConfig 配置路径查询**（使用 openconfig_schema_search 或 netconf_tool）
以下是相关的 XPath：
{schema_items}

⚠️ 重要：如果需要查询设备配置，使用 netconf_tool！
"""
            else:
                # SuzieQ table format (default)
                schema_tables = "\n".join(
                    [
                        f"    - {table}: {info.get('description', '')} (fields: {', '.join(info.get('fields', [])[:5])}...)"
                        for table, info in schema_context.items()
                    ]
                )
                schema_section = f"""
## 🎯 SuzieQ Schema Discovery 结果
意图分类：**网络状态查询**（优先使用 suzieq_query）
以下是根据你的查询从 Schema 中发现的相关表：
{schema_tables}

⚠️ 重要：使用上述发现的表名，不要猜测！
"""
        else:
            # No schema - guide based on intent
            intent_hints = {
                "netbox": "意图是 NetBox 查询，使用 netbox_api_call。常用端点：/dcim/devices/, /ipam/ip-addresses/, /dcim/sites/",
                "openconfig": "意图是 OpenConfig 路径查询，使用 openconfig_schema_search 或 netconf_tool",
                "cli": "意图是 CLI 命令执行，使用 cli_tool。需要 device 和 command 参数",
                "netconf": "意图是 NETCONF 配置，使用 netconf_tool。需要 device 和 xpath 参数",
                "suzieq": "意图是网络状态查询，使用 suzieq_query。先用 suzieq_schema_search 查找正确表名",
            }
            hint = intent_hints.get(intent_category or "suzieq", "")
            schema_section = f"""
## ⚠️ 意图分类结果
{hint}
"""

        # Build tool capability guide section
        capability_guide = ""
        guide_key = intent_category if intent_category in self._tool_guides else "suzieq"
        if self._tool_guides.get(guide_key):
            capability_guide = f"""
## 工具能力指南
{self._tool_guides[guide_key]}
"""

        # Tool descriptions with intent-specific ordering
        all_tools = {
            "suzieq_query": "Query SuzieQ Parquet database. Parameters: table, hostname, namespace, method, max_age_hours.",
            "netbox_api_call": "Query NetBox SSOT (device inventory, IPs, sites, racks). Parameters: endpoint, filters.",
            "cli_tool": "Execute CLI command on device (fallback, slower). Parameters: device, command.",
            "netconf_tool": "Execute NETCONF get-config (OpenConfig paths). Parameters: device, xpath.",
            "openconfig_schema_search": "Search OpenConfig YANG schema for XPaths. Parameters: intent (natural language), device_type (optional, e.g. 'interfaces', 'bgp').",
        }

        # Reorder based on intent
        if intent_category == "netbox":
            tool_order = ["netbox_api_call", "suzieq_query", "cli_tool", "netconf_tool"]
        elif intent_category == "openconfig":
            tool_order = ["openconfig_schema_search", "netconf_tool", "suzieq_query", "cli_tool"]
        elif intent_category == "cli":
            tool_order = ["cli_tool", "suzieq_query", "netbox_api_call", "netconf_tool"]
        elif intent_category == "netconf":
            tool_order = ["netconf_tool", "openconfig_schema_search", "suzieq_query", "cli_tool"]
        else:
            tool_order = ["suzieq_query", "netbox_api_call", "cli_tool", "netconf_tool"]

        tools_desc = "\n".join(
            [
                f"- **{t}** {'(recommended)' if t == preferred_tool else ''}: {all_tools.get(t, '')}"
                for t in tool_order
                if t in all_tools
            ]
        )

        context_section = ""
        if context:
            context_section = f"\n\n## Available Context\n{context}"

        try:
            prompt = prompt_manager.load_prompt(
                "strategies/fast_path",
                "parameter_extraction",
                user_query=user_query,
                context_section=context_section,
                schema_section=schema_section,
                capability_guide=capability_guide,
                tools_desc=tools_desc,
                preferred_tool=preferred_tool,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load parameter_extraction prompt: {e}, using fallback")
            prompt = f"Extract parameters for query: {user_query}"

        try:
            # Use robust_structured_output for reliable JSON parsing
            # Handles markdown-wrapped JSON and multiple fallback strategies
            extraction = await robust_structured_output(
                llm=self.llm,
                output_class=ParameterExtraction,
                prompt=prompt,
            )
        except Exception as e:
            logger.error(f"Failed to extract parameters: {e}")
            extraction = ParameterExtraction(
                tool="suzieq_query",
                parameters={},
                confidence=0.3,
                reasoning=f"Parse error: {e}",
            )

        logger.debug(f"Extracted: {extraction.tool} with params {extraction.parameters}")
        return extraction

    async def _execute_tool(self, tool_name: str, parameters: dict[str, Any]) -> ToolOutput:
        """
        Execute the selected tool with extracted parameters.

        Implements:
        1. Tool retry with exponential backoff (LangChain 1.10 pattern)
        2. Caching layer (Phase B.2)

        Retry Configuration:
        - max_retries: 3 attempts total
        - retry_on: ConnectionError, TimeoutError, OSError
        - backoff: exponential (1s, 2s, 4s) with jitter

        Args:
            tool_name: Tool identifier (must be registered in ToolRegistry)
            parameters: Tool parameters

        Returns:
            ToolOutput from tool execution or cache
        """
        # Tool name normalization (LLM may use different names)
        tool_name_map = {
            "netbox_api_call": "netbox_api",
            "cli_tool": "cli_execute",
            "netconf_tool": "netconf_execute",
        }
        tool_name = tool_name_map.get(tool_name, tool_name)

        # Parameter normalization for specific tools
        # This handles cases where LLM uses different parameter names
        if tool_name == "openconfig_schema_search":
            if "query" in parameters and "intent" not in parameters:
                parameters["intent"] = parameters.pop("query")
        elif tool_name == "netbox_api":
            # Map 'endpoint' to 'path' (NetBoxAPITool uses 'path')
            if "endpoint" in parameters and "path" not in parameters:
                parameters["path"] = parameters.pop("endpoint")
            # Ensure path starts with /api/ or /
            if "path" in parameters:
                path = parameters["path"]
                if not path.startswith("/"):
                    path = "/" + path
                if not path.startswith("/api/"):
                    path = "/api" + path
                parameters["path"] = path
            if "filters" in parameters and isinstance(parameters["filters"], dict):
                # Flatten filters into params
                if "params" not in parameters:
                    parameters["params"] = {}
                parameters["params"].update(parameters.pop("filters"))

        # Step 1: Check cache (if enabled)
        if self.enable_cache:
            cache_result = await self._check_cache(tool_name, parameters)
            if cache_result:
                logger.info(f"Cache HIT for {tool_name} (params: {parameters})")
                return cache_result
            logger.debug(f"Cache MISS for {tool_name} (params: {parameters})")

        # Step 2: Validate tool registry
        if not self.tool_registry:
            logger.error("ToolRegistry not configured in FastPathStrategy")
            return ToolOutput(
                source=tool_name,
                device="unknown",
                data=[],
                error="ToolRegistry not configured - cannot execute tools",
            )

        # Step 3: Get tool from registry
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Tool '{tool_name}' not found in ToolRegistry")
            available_tools = [t.name for t in self.tool_registry.list_tools()]
            return ToolOutput(
                source=tool_name,
                device="unknown",
                data=[],
                error=f"Tool '{tool_name}' not registered. Available: {', '.join(available_tools)}",
            )

        # Step 4: Execute tool with retry logic (LangChain 1.10 pattern)
        logger.debug(f"Executing tool '{tool_name}' with parameters: {parameters}")
        start_time = time.time()

        tool_output = await self._execute_with_retry(tool, tool_name, parameters)

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Add execution time to metadata
        if tool_output.metadata is None:
            tool_output.metadata = {}
        tool_output.metadata["elapsed_ms"] = elapsed_ms

        # Step 5: Cache result (if enabled and successful)
        if self.enable_cache and not tool_output.error:
            await self._write_cache(tool_name, parameters, tool_output)

        return tool_output

    async def _execute_with_retry(
        self,
        tool: Any,
        tool_name: str,
        parameters: dict[str, Any],
        max_retries: int | None = None,
        initial_delay: float | None = None,
        backoff_factor: float | None = None,
        jitter: bool | None = None,
    ) -> ToolOutput:
        """
        Execute tool with exponential backoff retry.

        Implements the same retry pattern as LangChain 1.10's ToolRetryMiddleware
        but at the strategy level for tools not using the agent framework.
        Default values are loaded from config/settings.py ToolRetryConfig.

        Args:
            tool: Tool instance to execute
            tool_name: Tool name for logging
            parameters: Tool parameters
            max_retries: Maximum retry attempts (default: ToolRetryConfig.MAX_RETRIES)
            initial_delay: Initial delay in seconds (default: ToolRetryConfig.INITIAL_DELAY)
            backoff_factor: Multiplier for exponential backoff (default: ToolRetryConfig.BACKOFF_FACTOR)
            jitter: Add randomness to delay (default: ToolRetryConfig.JITTER)

        Returns:
            ToolOutput from successful execution or last error
        """
        import random

        from config.settings import ToolRetryConfig

        # Use config defaults if not specified
        _max_retries = max_retries if max_retries is not None else ToolRetryConfig.MAX_RETRIES
        _initial_delay = initial_delay if initial_delay is not None else ToolRetryConfig.INITIAL_DELAY
        _backoff_factor = backoff_factor if backoff_factor is not None else ToolRetryConfig.BACKOFF_FACTOR
        _jitter = jitter if jitter is not None else ToolRetryConfig.JITTER

        # Exceptions that should trigger retry (network/transient errors)
        retryable_exceptions = (
            ConnectionError,
            TimeoutError,
            OSError,
        )

        last_error: Exception | None = None
        delay = _initial_delay

        for attempt in range(_max_retries):
            try:
                return await tool.execute(**parameters)
            except retryable_exceptions as e:
                last_error = e
                if attempt < _max_retries - 1:
                    # Calculate delay with optional jitter
                    actual_delay = delay
                    if _jitter:
                        actual_delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Tool '{tool_name}' failed (attempt {attempt + 1}/{_max_retries}): {e}. "
                        f"Retrying in {actual_delay:.1f}s..."
                    )
                    await asyncio.sleep(actual_delay)
                    delay *= _backoff_factor
                else:
                    logger.error(
                        f"Tool '{tool_name}' failed after {_max_retries} attempts: {e}"
                    )
            except Exception as e:
                # Non-retryable exception - fail immediately
                logger.error(f"Tool '{tool_name}' failed with non-retryable error: {e}")
                return ToolOutput(
                    source=tool_name,
                    device=parameters.get("device", "unknown"),
                    data=[],
                    error=f"Tool execution failed: {e}",
                )

        # All retries exhausted
        return ToolOutput(
            source=tool_name,
            device=parameters.get("device", "unknown"),
            data=[],
            error=f"Tool '{tool_name}' failed after {max_retries} retries: {last_error}",
        )

    def _get_cache_key(self, tool_name: str, parameters: dict[str, Any]) -> str:
        """
        Generate cache key from tool name and parameters.

        Uses SHA256 hash of canonical JSON representation for consistency.

        Args:
            tool_name: Tool identifier
            parameters: Tool parameters (will be sorted for consistency)

        Returns:
            Cache key (e.g., "tool_results/suzieq_query_abc123def456.json")

        Examples:
            >>> strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1"})
            "tool_results/suzieq_query_3f2a1b9c8d7e6f5a.json"
        """
        # Create canonical JSON (sorted keys)
        canonical = safe_json_dumps(
            {"tool": tool_name, "params": parameters}, sort_keys=True, ensure_ascii=False
        )

        # Hash to get cache key
        hash_obj = hashlib.sha256(canonical.encode("utf-8"))
        cache_hash = hash_obj.hexdigest()[:16]  # First 16 chars

        return f"tool_results/{tool_name}_{cache_hash}.json"

    async def _check_cache(self, tool_name: str, parameters: dict[str, Any]) -> ToolOutput | None:
        """
        Check cache for existing tool result.

        Args:
            tool_name: Tool identifier
            parameters: Tool parameters

        Returns:
            Cached ToolOutput if exists and not expired, None otherwise
        """
        try:
            # Lazy-initialize filesystem if needed
            if self.filesystem is None:
                from langgraph.checkpoint.memory import MemorySaver

                checkpointer = MemorySaver()
                self.filesystem = FilesystemMiddleware(
                    checkpointer=checkpointer,
                    workspace_root="./data/cache",
                    audit_enabled=False,
                    hitl_enabled=False,
                )

            cache_key = self._get_cache_key(tool_name, parameters)

            # Read from cache
            cached_content = await self.filesystem.read_file(cache_key)
            if (
                not cached_content
                or cached_content == "System reminder: File exists but has empty contents"
            ):
                return None

            # Deserialize cached result
            cached_data = json.loads(cached_content)

            # Check cache expiration (TTL)
            cache_time = cached_data.get("cached_at", 0)
            age_seconds = time.time() - cache_time

            if age_seconds > self.cache_ttl:
                logger.debug(
                    f"Cache expired for {tool_name} (age: {age_seconds:.1f}s > TTL: {self.cache_ttl}s)"
                )
                # Clean up expired cache
                await self.filesystem.delete_file(cache_key)
                return None

            # Deserialize ToolOutput
            tool_output_data = cached_data.get("tool_output", {})
            tool_output = ToolOutput(
                source=tool_output_data.get("source", tool_name),
                device=tool_output_data.get("device", "unknown"),
                data=tool_output_data.get("data", []),
                error=tool_output_data.get("error"),
                metadata=tool_output_data.get("metadata", {}),
            )

            # Add cache metadata
            tool_output.metadata["cache_hit"] = True
            tool_output.metadata["cache_age_seconds"] = age_seconds

            return tool_output

        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Cache read error for {tool_name}: {e}")
            return None

    async def _write_cache(
        self, tool_name: str, parameters: dict[str, Any], tool_output: ToolOutput
    ) -> None:
        """
        Write tool result to cache.

        Args:
            tool_name: Tool identifier
            parameters: Tool parameters
            tool_output: Tool execution result
        """
        try:
            # Lazy-initialize filesystem if needed
            if self.filesystem is None:
                from langgraph.checkpoint.memory import MemorySaver

                checkpointer = MemorySaver()
                self.filesystem = FilesystemMiddleware(
                    checkpointer=checkpointer,
                    workspace_root="./data/cache",
                    audit_enabled=False,
                    hitl_enabled=False,
                )

            cache_key = self._get_cache_key(tool_name, parameters)

            # Serialize ToolOutput
            cache_data = {
                "tool": tool_name,
                "parameters": parameters,
                "cached_at": time.time(),
                "cache_ttl": self.cache_ttl,
                "tool_output": {
                    "source": tool_output.source,
                    "device": tool_output.device,
                    "data": tool_output.data,
                    "error": tool_output.error,
                    "metadata": tool_output.metadata,
                },
            }

            # Write to cache
            await self.filesystem.write_file(
                cache_key, safe_json_dumps(cache_data, ensure_ascii=False, indent=2)
            )

            logger.debug(
                f"Cached result for {tool_name} (key: {cache_key}, TTL: {self.cache_ttl}s)"
            )

        except Exception as e:
            logger.warning(f"Cache write error for {tool_name}: {e}")

    async def _format_answer(
        self, user_query: str, tool_output: ToolOutput, extraction: ParameterExtraction
    ) -> FormattedAnswer:
        """
        Format tool output into human-readable answer (strict mode).

        LLM is forced to only use data from tool_output, no speculation.

        Args:
            user_query: Original user query
            tool_output: Tool execution result
            extraction: Parameter extraction context

        Returns:
            FormattedAnswer with human-readable text
        """
        # Serialize tool data for LLM (use safe encoder for numpy types)
        data_json = safe_json_dumps(tool_output.data, ensure_ascii=False, indent=2)

        try:
            prompt = prompt_manager.load_prompt(
                "strategies/fast_path",
                "answer_formatting",
                user_query=user_query,
                tool_source=tool_output.source,
                tool_device=tool_output.device,
                data_json=data_json,
                tool_metadata=str(tool_output.metadata),
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load answer_formatting prompt: {e}, using fallback")
            prompt = f"Format answer for: {user_query}\nData: {data_json}"

        try:
            # Use robust_structured_output for reliable JSON parsing
            formatted = await robust_structured_output(
                llm=self.llm,
                output_class=FormattedAnswer,
                prompt=prompt,
            )
        except Exception as e:
            logger.error(f"Failed to parse formatted answer: {e}")
            # Fallback formatting
            formatted = FormattedAnswer(
                answer=f"Tool returned {len(tool_output.data)} records.", data_used=[], confidence=0.5
            )

        return formatted

    def is_suitable(self, user_query: str) -> bool:
        """
        Quick heuristic to check if query is suitable for Fast Path.

        Args:
            user_query: User's query

        Returns:
            True if likely suitable, False otherwise
        """
        # Fast Path suitable for:
        # - Single device queries
        # - Status checks
        # - Simple lookups

        # Not suitable for:
        # - "为什么" (why) questions
        # - Multi-step diagnostics
        # - Batch operations

        unsuitable_patterns = [
            "为什么",
            "why",
            "诊断",
            "diagnose",
            "排查",
            "troubleshoot",
            "所有设备",
            "all device",
            "批量",
            "batch",
            "审计",
            "audit",
        ]

        query_lower = user_query.lower()
        return all(pattern not in query_lower for pattern in unsuitable_patterns)

    async def _search_episodic_memory(
        self,
        user_query: str,
        max_results: int = 3,
        confidence_threshold: float = 0.8,
    ) -> dict[str, Any] | None:
        """
        Search episodic memory for historical success patterns.

        This implements RAG optimization: if we've successfully handled
        a similar query before, reuse the same tool + parameters.

        Args:
            user_query: User's natural language query
            max_results: Max historical patterns to retrieve
            confidence_threshold: Min confidence to use memory pattern

        Returns:
            Dict with tool, parameters, confidence if match found, else None

        Example:
            >>> pattern = await strategy._search_episodic_memory("查询 R1 BGP 状态")
            >>> pattern
            {
                "tool": "suzieq_query",
                "parameters": {"table": "bgp", "hostname": "R1", "method": "get"},
                "confidence": 0.95,
                "intent": "查询 R1 BGP 状态"
            }
        """
        try:
            # Search episodic memory
            result = await self.episodic_memory_tool.execute(
                intent=user_query,
                max_results=max_results,
                only_successful=True,
            )

            if result.error or not result.data:
                logger.debug(f"No episodic memory patterns found for: {user_query}")
                return None

            # Get best match (first result, highest relevance)
            best_match = result.data[0]

            # Calculate semantic similarity confidence (simple heuristic)
            # In production, use embedding similarity
            historical_intent = best_match.get("intent", "")
            query_words = set(user_query.lower().split())
            historical_words = set(historical_intent.lower().split())

            # Jaccard similarity
            if query_words and historical_words:
                intersection = query_words & historical_words
                union = query_words | historical_words
                similarity = len(intersection) / len(union)
            else:
                similarity = 0.0

            # Boost confidence if exact match
            if user_query.lower() == historical_intent.lower():
                similarity = 1.0

            logger.info(
                f"Found episodic memory pattern: '{historical_intent}' "
                f"(similarity: {similarity:.2f})"
            )

            # Only use if confidence above threshold
            if similarity < confidence_threshold:
                logger.debug(
                    f"Similarity {similarity:.2f} below threshold {confidence_threshold}, "
                    "falling back to LLM extraction"
                )
                return None

            # Extract tool and parameters from memory
            tool_used = best_match.get("tool_used")
            parameters = best_match.get("parameters", {})

            if not tool_used or not parameters:
                logger.warning("Episodic memory pattern missing tool or parameters")
                return None

            return {
                "tool": tool_used,
                "parameters": parameters,
                "confidence": similarity,
                "intent": historical_intent,
                "execution_time_ms": best_match.get("execution_time_ms", 0),
            }

        except Exception as e:
            logger.error(f"Episodic memory search failed: {e}")
            return None
