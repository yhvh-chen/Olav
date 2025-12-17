"""
Unified Intent and Tool Classifier.

This module combines intent classification and tool selection into a single
LLM call to reduce API calls and improve response time.

Architecture (2-Layer):
1. Keyword Match: Check ToolRegistry.keyword_match() first (instant, from triggers)
2. LLM Fallback: Use LLM for complex queries not matched by keywords

This replaces the previous 3-layer architecture:
- OLD: Fast Path (regex) → LLM → Fallback (keywords)
- NEW: Keyword Match (from ToolRegistry.triggers) → LLM

Benefits:
- Single source of truth: triggers declared at tool registration
- No separate preprocessor.py patterns to maintain
- No fallback keywords that only trigger on LLM failure
"""

import logging
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.base import ToolRegistry

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
    reasoning: str | None = Field(
        default=None, description="Optional brief explanation (omit to reduce latency)"
    )

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
        result = await classifier.classify("Query R1 BGP status")
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
            # Use load_raw to get template without variable substitution
            # (unified_classification template has JSON examples with braces
            #  that would be misinterpreted as variables by PromptTemplate)
            self._prompt = prompt_manager.load_raw("unified_classification")
        return self._prompt

    async def classify(
        self,
        query: str,
        schema_context: dict[str, Any] | None = None,
        skip_keyword_match: bool = False,
    ) -> UnifiedClassificationResult:
        """Classify user query and select tool.

        2-Layer Architecture:
        1. Keyword Match: Check ToolRegistry.keyword_match() (from tool triggers)
        2. LLM Fallback: Use LLM for complex queries

        Args:
            query: User's natural language query.
            schema_context: Optional schema context from discovery (table names, etc.)
            skip_keyword_match: If True, skip keyword matching and always use LLM.

        Returns:
            UnifiedClassificationResult with intent, tool, and parameters.
        """
        import time

        # =================================================================
        # Layer 1: Keyword Match (from ToolRegistry.triggers)
        # =================================================================
        # Keyword match is ONLY used for tools that don't require parameters.
        # Tools like suzieq_query need LLM to extract 'table' parameter.
        PARAM_FREE_TOOLS = {
            "suzieq_schema_search",
            "openconfig_schema_search",
        }
        
        if not skip_keyword_match:
            match = ToolRegistry.keyword_match(query)
            if match is not None:
                tool_name, category, confidence = match
                # Only use keyword match shortcut for parameter-free tools
                if tool_name in PARAM_FREE_TOOLS:
                    logger.info(
                        f"Keyword match hit (param-free): {tool_name} "
                        f"(category: {category}, confidence: {confidence:.2f})"
                    )
                    result = UnifiedClassificationResult(
                        intent_category=category,  # type: ignore
                        tool=tool_name,  # type: ignore
                        parameters={},
                        confidence=confidence,
                        reasoning=f"Keyword match: {tool_name}",
                    )
                    result._llm_time_ms = 0.0
                    result._keyword_match = True
                    return result
                else:
                    # For tools requiring parameters, log the hint but continue to LLM
                    logger.debug(
                        f"Keyword match hint: {tool_name} (requires params, using LLM)"
                    )

        # =================================================================
        # Layer 2: LLM Classification
        # =================================================================
        try:
            # Build enhanced prompt with schema context
            enhanced_prompt = self.prompt
            if schema_context:
                schema_info = "\n".join(
                    [f"- {name}: {info.get('description', '')}" for name, info in schema_context.items()]
                )
                enhanced_prompt += f"\n\n## Discovered Schema\n{schema_info}\n\n⚠️ Use the discovered table names/endpoints above!"

            messages = [
                SystemMessage(content=enhanced_prompt),
                HumanMessage(content=query),
            ]

            llm_start = time.perf_counter()
            result = await self.structured_llm.ainvoke(messages)
            llm_duration_ms = (time.perf_counter() - llm_start) * 1000

            logger.debug(f"LLM classification took {llm_duration_ms:.0f}ms")

            if isinstance(result, UnifiedClassificationResult):
                result._llm_time_ms = llm_duration_ms
                logger.info(
                    f"Unified classifier: {result.intent_category}/{result.tool} "
                    f"(confidence: {result.confidence:.2f}, llm: {llm_duration_ms:.0f}ms)"
                )
                return result

            # Handle dict response
            if isinstance(result, dict):
                classification = UnifiedClassificationResult(**result)
                classification._llm_time_ms = llm_duration_ms
                return classification

            logger.warning(f"Unexpected LLM response type: {type(result)}")
            return self._default_result(query)

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return self._default_result(query)

    def _default_result(self, query: str) -> UnifiedClassificationResult:
        """Default classification when LLM fails.

        Returns SuzieQ as the safest default for network queries.
        """
        return UnifiedClassificationResult(
            intent_category="suzieq",
            tool="suzieq_query",
            parameters={},
            confidence=0.5,
            reasoning="Default: LLM failed, using SuzieQ as fallback",
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
