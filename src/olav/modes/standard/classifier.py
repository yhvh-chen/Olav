"""Standard Mode Classifier - Unified intent and tool classification.

Combines intent classification and tool selection into a single LLM call.
This is a thin wrapper around UnifiedClassifier for Standard Mode.

Optimization:
- Previous: 2 LLM calls (classify_intent + select_tool)
- Now: 1 LLM call (unified_classify)
"""

import logging
from typing import Any

from olav.core.unified_classifier import (
    UnifiedClassificationResult,
    UnifiedClassifier,
)

logger = logging.getLogger(__name__)


class StandardModeClassifier:
    """Standard Mode classifier - wraps UnifiedClassifier.

    This class provides a clean interface for Standard Mode tool selection.
    It uses a single LLM call to:
    1. Classify intent (suzieq/netbox/cli/netconf/openconfig)
    2. Select appropriate tool
    3. Extract tool parameters

    Usage:
        classifier = StandardModeClassifier()
        result = await classifier.classify("查询 R1 BGP 状态")

        if result.confidence >= 0.7:
            # Execute tool with result.tool and result.parameters
            pass
        else:
            # Route to Expert Mode
            pass
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        enable_cache: bool = True,
    ) -> None:
        """Initialize classifier.

        Args:
            confidence_threshold: Minimum confidence to proceed with Standard Mode.
                                  Below this threshold, route to Expert Mode.
            enable_cache: Whether to cache classification results.
        """
        self.confidence_threshold = confidence_threshold
        self._classifier = UnifiedClassifier(enable_cache=enable_cache)

    async def classify(
        self,
        query: str,
        schema_context: dict[str, Any] | None = None,
    ) -> UnifiedClassificationResult:
        """Classify user query and select tool.

        Args:
            query: User's natural language query.
            schema_context: Optional schema context from discovery.

        Returns:
            UnifiedClassificationResult with intent, tool, and parameters.
        """
        result = await self._classifier.classify(query, schema_context)

        logger.info(
            f"Standard classifier: {result.intent_category}/{result.tool} "
            f"(confidence: {result.confidence:.2f})"
        )

        return result

    def should_escalate_to_expert(self, result: UnifiedClassificationResult) -> bool:
        """Check if query should be escalated to Expert Mode.

        Args:
            result: Classification result.

        Returns:
            True if confidence is below threshold or reasoning suggests complexity.
        """
        if result.confidence < self.confidence_threshold:
            logger.info(
                f"Escalating to Expert Mode: confidence {result.confidence:.2f} "
                f"< threshold {self.confidence_threshold}"
            )
            return True

        # Check for complexity indicators in reasoning
        complexity_keywords = [
            "multi-step",
            "diagnosis",
            "troubleshoot",
            "root cause",
            "故障",
            "排错",
            "诊断",
        ]

        # Handle optional reasoning field (None when omitted for performance)
        if result.reasoning:
            reasoning_lower = result.reasoning.lower()
            if any(kw in reasoning_lower for kw in complexity_keywords):
                logger.info(
                    "Escalating to Expert Mode: complexity detected in reasoning"
                )
                return True

        return False


# Module-level convenience function
async def classify_standard(
    query: str,
    schema_context: dict[str, Any] | None = None,
    confidence_threshold: float = 0.7,
) -> tuple[UnifiedClassificationResult, bool]:
    """Classify query for Standard Mode execution.

    This is the main entry point for Standard Mode classification.

    Args:
        query: User's natural language query.
        schema_context: Optional schema context.
        confidence_threshold: Threshold for Expert Mode escalation.

    Returns:
        Tuple of (result, should_escalate)
    """
    classifier = StandardModeClassifier(confidence_threshold=confidence_threshold)
    result = await classifier.classify(query, schema_context)
    should_escalate = classifier.should_escalate_to_expert(result)

    return result, should_escalate
