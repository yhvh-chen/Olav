"""
LLM-based Intent Classifier.

Replaces hardcoded keyword matching with LLM structured output
for more dynamic and adaptive intent classification.

This module provides:
- IntentResult: Pydantic model for structured output
- LLMIntentClassifier: Main classifier class
- classify_intent_with_llm: Convenience function
"""

import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    """LLM structured output model for intent classification."""

    category: Literal["suzieq", "netbox", "openconfig", "cli", "netconf"] = Field(
        description="Classified intent category"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Brief explanation for the classification")


class LLMIntentClassifier:
    """LLM-based intent classifier using structured output.

    Replaces the hardcoded INTENT_PATTERNS dictionary in fast_path.py
    with dynamic LLM classification.

    Features:
    - Uses LLM structured output (json_mode)
    - Loads prompt from config/prompts/core/intent_classification.yaml
    - Falls back to keyword-based classification on failure
    - Caches classification results (via Redis if available)

    Usage:
        classifier = LLMIntentClassifier()
        result = await classifier.classify("查询 R1 BGP 状态")
        print(result.category)  # "suzieq"
        print(result.confidence)  # 0.95
    """

    # Default category when classification fails
    DEFAULT_CATEGORY = "suzieq"
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
            self._llm = LLMFactory.get_chat_model(json_mode=True)
        return self._llm

    @property
    def structured_llm(self) -> BaseChatModel:
        """Get LLM with structured output binding."""
        if self._structured_llm is None:
            self._structured_llm = self.llm.with_structured_output(IntentResult)
        return self._structured_llm

    @property
    def prompt(self) -> str:
        """Lazy-load prompt template."""
        if self._prompt is None:
            try:
                self._prompt = prompt_manager.load_prompt("core", "intent_classification")
            except Exception as e:
                logger.warning(f"Failed to load prompt template: {e}")
                self._prompt = self._get_fallback_prompt()
        return self._prompt

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if template loading fails."""
        return """你是网络运维意图分类专家。将用户查询分类到以下类别：
- suzieq: 网络状态查询（BGP/OSPF/接口状态）
- netbox: CMDB 资产管理（设备清单、IP 分配）
- openconfig: YANG/NETCONF 结构化配置
- cli: SSH 命令行执行
- netconf: NETCONF RPC 操作

返回 JSON: {"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}"""

    async def classify(self, query: str) -> IntentResult:
        """Classify user query intent using LLM.

        Args:
            query: User's natural language query.

        Returns:
            IntentResult with category, confidence, and reasoning.
        """
        try:
            messages = [
                SystemMessage(content=self.prompt),
                HumanMessage(content=query),
            ]

            result = await self.structured_llm.ainvoke(messages)

            if isinstance(result, IntentResult):
                logger.debug(
                    f"LLM classified '{query[:50]}...' as {result.category} "
                    f"(confidence: {result.confidence:.2f})"
                )
                return result

            # Handle dict response (some LLMs return dict instead of model)
            if isinstance(result, dict):
                return IntentResult(**result)

            logger.warning(f"Unexpected LLM response type: {type(result)}")
            return self._fallback_classify(query)

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return self._fallback_classify(query)

    def _fallback_classify(self, query: str) -> IntentResult:
        """Keyword-based fallback classification.

        Uses minimal keyword matching as a safety net.
        """
        query_lower = query.lower()

        # Simple keyword matching (much smaller than original)
        if any(kw in query_lower for kw in ["netbox", "cmdb", "资产", "设备清单"]):
            return IntentResult(
                category="netbox",
                confidence=0.6,
                reasoning="Keyword match: netbox/cmdb/资产",
            )

        if any(kw in query_lower for kw in ["netconf", "rpc", "edit-config"]):
            return IntentResult(
                category="netconf",
                confidence=0.6,
                reasoning="Keyword match: netconf/rpc",
            )

        if any(kw in query_lower for kw in ["openconfig", "yang", "xpath"]):
            return IntentResult(
                category="openconfig",
                confidence=0.6,
                reasoning="Keyword match: openconfig/yang",
            )

        if any(kw in query_lower for kw in ["cli", "ssh", "命令行"]):
            return IntentResult(
                category="cli",
                confidence=0.6,
                reasoning="Keyword match: cli/ssh",
            )

        # Default to suzieq for network queries
        return IntentResult(
            category="suzieq",
            confidence=0.5,
            reasoning="Default: network state query",
        )


# Convenience function for direct use
_classifier: LLMIntentClassifier | None = None


def get_classifier() -> LLMIntentClassifier:
    """Get singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = LLMIntentClassifier()
    return _classifier


async def classify_intent_with_llm(query: str) -> tuple[str, float]:
    """Classify intent using LLM.

    Drop-in replacement for the original classify_intent() function.

    Args:
        query: User's natural language query.

    Returns:
        Tuple of (category, confidence) matching the original API.
    """
    classifier = get_classifier()
    result = await classifier.classify(query)
    return (result.category, result.confidence)
