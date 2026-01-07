"""Network Relevance Guard - LLM-based pre-filter for non-network queries.

Determines if a user query is related to network operations.
Non-network queries are rejected early to avoid expensive downstream processing.
"""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.olav.core.llm import LLMFactory

logger = logging.getLogger(__name__)


class RelevanceResult(BaseModel):
    """Result of network relevance check."""

    is_relevant: bool = Field(description="Whether the query is network-related")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1",
    )
    reason: str = Field(
        default="",
        description="Reason for the decision",
    )
    method: Literal["llm", "fallback"] = Field(
        default="llm",
        description="Classification method used",
    )


class NetworkRelevanceGuard:
    """LLM-based guard for network query relevance."""

    def __init__(self) -> None:
        """Initialize the guard with LLM."""
        self.llm = LLMFactory.get_chat_model()

    async def check(self, query: str) -> RelevanceResult:
        """Check if a query is network-related.

        Args:
            query: User's natural language query

        Returns:
            RelevanceResult with relevance decision
        """
        system_prompt = """You are a network relevance classifier.
Determine if a user query is related to network operations, infrastructure, or devices.

Network queries include:
- BGP, OSPF, routing protocols
- Network device status, interfaces, configuration
- Network troubleshooting, diagnosis, performance
- Network inventory, topology
- Firewall, VPN, security

Non-network queries:
- General knowledge, math, coding
- Business operations, HR, finance
- Personal assistance, chat

Return JSON: {"is_relevant": true/false}"""

        try:
            llm_with_json = self.llm.with_structured_output(dict)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query),
            ]

            result = await llm_with_json.ainvoke(messages)

            is_relevant = result.get("is_relevant", True)
            logger.debug(
                f"Network relevance check: query='{query[:50]}...', relevant={is_relevant}"
            )

            return RelevanceResult(
                is_relevant=is_relevant,
                confidence=1.0,
                reason="LLM classification",
                method="llm",
            )

        except Exception as e:
            logger.error(f"Network relevance check failed: {e}")
            # Fail open - allow through on error
            return RelevanceResult(
                is_relevant=True,
                confidence=0.5,
                reason=f"Check failed, defaulting to allow: {str(e)[:50]}",
                method="fallback",
            )


# Singleton instance
_guard: NetworkRelevanceGuard | None = None


def get_network_guard() -> NetworkRelevanceGuard:
    """Get or create the singleton guard instance."""
    global _guard
    if _guard is None:
        _guard = NetworkRelevanceGuard()
    return _guard


REJECTION_MESSAGE = """I am OLAV, a Network Operations AI Assistant.

I specialize in network infrastructure management:
🔍 Query network device status (BGP, OSPF, interfaces)
🔧 Troubleshoot network faults and performance issues
⚙️ Manage network device configuration (requires approval)
📦 Manage device inventory (NetBox)

Please ask me about network-related topics."""


__all__ = [
    "NetworkRelevanceGuard",
    "RelevanceResult",
    "get_network_guard",
    "REJECTION_MESSAGE",
]
