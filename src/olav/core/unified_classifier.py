"""
Unified Intent and Tool Classifier.

This module combines intent classification and tool selection into a single
LLM call to reduce API calls and improve response time.

Optimization:
- Previous: 2 LLM calls (classify_intent + select_tool)
- Now: 1 LLM call (unified_classify)

Expected improvement:
- Reduces LLM calls by 1 per request
- Reduces latency by 30-50% for simple queries
"""

import logging
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


class UnifiedClassificationResult(BaseModel):
    """Combined intent classification and tool selection result.

    This replaces both IntentResult and ParameterExtraction with a single
    structured output, reducing LLM calls from 2 to 1.
    """

    # Intent classification
    intent_category: Literal["suzieq", "netbox", "openconfig", "cli", "netconf"] = Field(
        description="Classified intent category"
    )

    # Tool selection
    tool: Literal[
        "suzieq_query",
        "suzieq_schema_search",
        "netbox_api",
        "netbox_api_call",
        "cli_execute",
        "cli_tool",
        "netconf_execute",
        "netconf_tool",
        "openconfig_schema_search",
    ] = Field(description="Selected tool for execution")

    # Tool parameters
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific parameters extracted from query",
    )

    # Confidence and reasoning
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in classification and selection"
    )
    reasoning: str = Field(description="Brief explanation for the classification and tool choice")

    # Optional: fallback suggestions
    fallback_tool: str | None = Field(
        default=None, description="Alternative tool if primary fails"
    )


class UnifiedClassifier:
    """Unified intent and tool classifier using a single LLM call.

    This replaces the two-step process of:
    1. LLMIntentClassifier.classify() - intent classification
    2. FastPathStrategy._extract_parameters() - tool selection

    With a single call that returns both intent and tool selection.

    Usage:
        classifier = UnifiedClassifier()
        result = await classifier.classify("查询 R1 BGP 状态")
        print(result.intent_category)  # "suzieq"
        print(result.tool)  # "suzieq_query"
        print(result.parameters)  # {"table": "bgp", "hostname": "R1"}
    """

    # Default values for fallback
    DEFAULT_CATEGORY = "suzieq"
    DEFAULT_TOOL = "suzieq_query"
    DEFAULT_CONFIDENCE = 0.5

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        enable_cache: bool = True,
    ) -> None:
        """Initialize the classifier.

        Args:
            llm: Language model to use. If None, uses LLMFactory.
            enable_cache: Whether to cache classification results.
        """
        self._llm = llm
        self._structured_llm: BaseChatModel | None = None
        self.enable_cache = enable_cache
        self._prompt: str | None = None

    @property
    def llm(self) -> BaseChatModel:
        """Lazy-load LLM instance."""
        if self._llm is None:
            # Use json_mode for structured output, reasoning=False for concise responses
            # This prevents qwen3/deepseek from generating verbose "thinking" content
            self._llm = LLMFactory.get_chat_model(json_mode=True, reasoning=False)
        return self._llm

    @property
    def structured_llm(self) -> BaseChatModel:
        """Get LLM with structured output binding."""
        if self._structured_llm is None:
            self._structured_llm = self.llm.with_structured_output(UnifiedClassificationResult)
        return self._structured_llm

    @property
    def prompt(self) -> str:
        """Lazy-load prompt template."""
        if self._prompt is None:
            try:
                # Try new prompt system first (overrides/ → _defaults/)
                self._prompt = prompt_manager.load(
                    "unified_classification",
                    thinking=False,  # Classification doesn't need extended thinking
                )
            except FileNotFoundError:
                # Fallback to legacy location
                try:
                    self._prompt = prompt_manager.load_prompt("core", "unified_classification")
                except Exception as e:
                    logger.warning(f"Failed to load unified_classification prompt: {e}")
                    self._prompt = self._get_fallback_prompt()
        return self._prompt

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if template loading fails."""
        return """You are a network operations intent classification and tool selection expert.

Classify user queries and select appropriate tools:

## Intent Categories
- suzieq: Network state query (BGP/OSPF/interface/route status) → use suzieq_query
- netbox: CMDB asset management (device inventory, IP allocation) → use netbox_api_call
- openconfig: YANG schema query → use openconfig_schema_search
- cli: SSH command line execution → use cli_tool
- netconf: NETCONF configuration operations → use netconf_tool

## Tools and Parameters
1. suzieq_query: {table, hostname, namespace, method}
2. suzieq_schema_search: {query}
3. netbox_api_call: {endpoint, filters}
4. cli_tool: {device, command}
5. netconf_tool: {device, xpath}
6. openconfig_schema_search: {intent}

## Output Format
Return JSON:
{
  "intent_category": "suzieq|netbox|openconfig|cli|netconf",
  "tool": "tool_name",
  "parameters": {...},
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "fallback_tool": "..." (optional)
}

## Examples
Query: "Query R1 BGP status"
→ intent_category: "suzieq", tool: "suzieq_query", parameters: {"table": "bgp", "hostname": "R1"}

Query: "Find device R1 in NetBox"
→ intent_category: "netbox", tool: "netbox_api_call", parameters: {"endpoint": "/dcim/devices/", "filters": {"name": "R1"}}
"""

    async def classify(
        self,
        query: str,
        schema_context: dict[str, Any] | None = None,
    ) -> UnifiedClassificationResult:
        """Classify user query and select tool in a single LLM call.

        Args:
            query: User's natural language query.
            schema_context: Optional schema context from discovery (table names, etc.)

        Returns:
            UnifiedClassificationResult with intent, tool, and parameters.
        """
        try:
            # Build enhanced prompt with schema context
            enhanced_prompt = self.prompt
            if schema_context:
                schema_info = "\n".join(
                    [f"- {name}: {info.get('description', '')}" for name, info in schema_context.items()]
                )
                enhanced_prompt += f"\n\n## 已发现的 Schema\n{schema_info}\n\n⚠️ 使用上述发现的表名/端点！"

            messages = [
                SystemMessage(content=enhanced_prompt),
                HumanMessage(content=query),
            ]

            result = await self.structured_llm.ainvoke(messages)

            if isinstance(result, UnifiedClassificationResult):
                logger.info(
                    f"Unified classifier: {result.intent_category}/{result.tool} "
                    f"(confidence: {result.confidence:.2f})"
                )
                return result

            # Handle dict response
            if isinstance(result, dict):
                return UnifiedClassificationResult(**result)

            logger.warning(f"Unexpected LLM response type: {type(result)}")
            return self._fallback_classify(query)

        except Exception as e:
            logger.warning(f"Unified classification failed: {e}")
            return self._fallback_classify(query)

    def _fallback_classify(self, query: str) -> UnifiedClassificationResult:
        """Keyword-based fallback classification.

        Uses minimal keyword matching as a safety net when LLM fails.
        """
        query_lower = query.lower()

        # NetBox keywords
        if any(kw in query_lower for kw in ["netbox", "cmdb", "资产", "设备清单", "inventory"]):
            return UnifiedClassificationResult(
                intent_category="netbox",
                tool="netbox_api_call",
                parameters={"endpoint": "/dcim/devices/"},
                confidence=0.6,
                reasoning="Keyword fallback: netbox/cmdb",
            )

        # NETCONF keywords
        if any(kw in query_lower for kw in ["netconf", "rpc", "edit-config"]):
            return UnifiedClassificationResult(
                intent_category="netconf",
                tool="netconf_tool",
                parameters={},
                confidence=0.6,
                reasoning="Keyword fallback: netconf",
            )

        # OpenConfig keywords
        if any(kw in query_lower for kw in ["openconfig", "yang", "xpath"]):
            return UnifiedClassificationResult(
                intent_category="openconfig",
                tool="openconfig_schema_search",
                parameters={"intent": query},
                confidence=0.6,
                reasoning="Keyword fallback: openconfig/yang",
            )

        # CLI keywords
        if any(kw in query_lower for kw in ["cli", "ssh", "命令行", "show run"]):
            return UnifiedClassificationResult(
                intent_category="cli",
                tool="cli_tool",
                parameters={},
                confidence=0.6,
                reasoning="Keyword fallback: cli/ssh",
            )

        # Default to SuzieQ for network state queries
        return UnifiedClassificationResult(
            intent_category="suzieq",
            tool="suzieq_query",
            parameters={},
            confidence=0.5,
            reasoning="Default: network state query via SuzieQ",
            fallback_tool="cli_tool",
        )


# Singleton instance
_unified_classifier: UnifiedClassifier | None = None


def get_unified_classifier() -> UnifiedClassifier:
    """Get singleton classifier instance."""
    global _unified_classifier
    if _unified_classifier is None:
        _unified_classifier = UnifiedClassifier()
    return _unified_classifier


async def unified_classify(
    query: str,
    schema_context: dict[str, Any] | None = None,
) -> UnifiedClassificationResult:
    """Classify intent and select tool in a single LLM call.

    This is the main entry point for unified classification.

    Args:
        query: User's natural language query.
        schema_context: Optional schema context for better tool selection.

    Returns:
        UnifiedClassificationResult with intent, tool, and parameters.
    """
    classifier = get_unified_classifier()
    return await classifier.classify(query, schema_context)
