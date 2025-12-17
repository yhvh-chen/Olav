"""Network Relevance Guard - LLM-based pre-filter for non-network queries.

This module provides an LLM-based guard that determines if a user query
is related to network operations. Non-network queries are rejected early to
avoid expensive downstream reasoning cycles.

The guard uses a lightweight LLM call with structured output for fast,
accurate classification.

Usage:
    guard = NetworkRelevanceGuard()

    # Check if query is network-related
    result = await guard.check(user_query)
    if not result.is_relevant:
        return f"Sorry, I am OLAV the network operations assistant, unable to answer this question: {result.reason}"
"""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


class RelevanceResult(BaseModel):
    """Result of network relevance check."""

    is_relevant: bool = Field(description="Whether the query is network-related")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the relevance decision"
    )
    reason: str = Field(
        default="",
        description="Reason for the decision (especially for rejection)"
    )
    method: Literal["llm", "fallback"] = Field(
        default="llm",
        description="Method used for classification"
    )


class LLMRelevanceDecision(BaseModel):
    """Minimal structured output for LLM relevance check.
    
    Simplified to boolean-only to maximize compatibility across LLM providers.
    """

    is_relevant: bool = Field(
        description="True if query is about network/infrastructure operations, False otherwise"
    )


class NetworkRelevanceGuard:
    """
    LLM-based pre-filter to detect non-network queries.

    This guard prevents expensive LLM reasoning on irrelevant queries like
    "1+1=?" or "What's the weather today?".

    Uses a fast, focused LLM call with structured output.
    """

    def __init__(self) -> None:
        """Initialize the guard with LLM."""
        self._llm = None  # Lazy initialization

    @property
    def llm(self):
        """Lazy-load LLM only when needed."""
        if self._llm is None:
            self._llm = LLMFactory.get_chat_model(json_mode=True, reasoning=False)
        return self._llm

    def _get_system_prompt(self) -> str:
        """Load system prompt from config or use fallback."""
        try:
            # Try new prompt system first (overrides/ → _defaults/)
            return prompt_manager.load("network_guard", thinking=False)
        except FileNotFoundError:
            # Fallback to legacy location
            try:
                return prompt_manager.load_prompt("agents", "network_relevance_guard")
            except Exception:
                return self._get_fallback_prompt()

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if config not available."""
        return """You are a network operations assistant pre-filter.

Determine if this query is related to network infrastructure or operations.

When uncertain, return true - it's better to allow than to block.

Return JSON only: {"is_relevant": true} or {"is_relevant": false}"""

    async def check(self, query: str) -> RelevanceResult:
        """
        Check if a query is network-related using LLM.

        Args:
            query: User's natural language query

        Returns:
            RelevanceResult with relevance decision and metadata
        """
        try:
            system_prompt = self._get_system_prompt()
            llm_with_structure = self.llm.with_structured_output(LLMRelevanceDecision)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query),
            ]

            result = await llm_with_structure.ainvoke(messages)

            logger.debug(
                f"Network relevance check: query='{query[:50]}...', "
                f"relevant={result.is_relevant}"
            )

            return RelevanceResult(
                is_relevant=result.is_relevant,
                confidence=1.0,
                reason="LLM classification",
                method="llm"
            )

        except Exception as e:
            logger.error(f"Network relevance check failed: {e}")
            # On failure, default to relevant (allow through) - fail open
            return RelevanceResult(
                is_relevant=True,
                confidence=0.5,
                reason=f"Check failed, defaulting to allow: {str(e)[:50]}",
                method="fallback"
            )


# Singleton instance
_guard: NetworkRelevanceGuard | None = None


def get_network_guard() -> NetworkRelevanceGuard:
    """Get or create the singleton guard instance."""
    global _guard
    if _guard is None:
        _guard = NetworkRelevanceGuard()
    return _guard


# Pre-defined rejection message
REJECTION_MESSAGE = """Sorry, I am OLAV (Network Operations Assistant), specialized in handling network devices and infrastructure related questions.

I can help you with:
🔍 Query network device status (BGP, OSPF, interfaces, etc.)
🔧 Diagnose network faults and troubleshoot issues
⚙️ Configure network devices (requires approval)
📦 Manage device inventory (NetBox)

If you have network-related questions, please rephrase your request."""


__all__ = [
    "REJECTION_MESSAGE",
    "NetworkRelevanceGuard",
    "RelevanceResult",
    "get_network_guard",
]
