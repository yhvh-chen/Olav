"""
Strategy Selector - Intelligent routing to optimal execution strategy.

This module implements rule-based strategy selection to route queries
to the most appropriate execution strategy (Fast/Deep/Batch) based on
query characteristics and complexity.

Selection Logic:
1. Batch Path: Multi-device compliance checks ("批量", "all devices", "audit")
2. Deep Path: Complex diagnostics ("why", "troubleshoot", "diagnose")
3. Fast Path: Simple status queries (default for single-device lookups)

Key Benefits:
- Automatic optimization: Fast path = <2s, Deep path = adaptive, Batch = parallel
- No user decision required: Query analysis handles routing
- Graceful degradation: Fast→Deep fallback on complexity detection

Example Routing:
- "查询 R1 BGP 状态" → Fast Path (simple, single device)
- "为什么 R1 BGP 无法建立？" → Deep Path (diagnostic, needs reasoning)
- "批量检查所有路由器 BGP" → Batch Path (multi-device, compliance)
"""

import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from olav.core.json_utils import robust_structured_output
from olav.strategies.batch_path import BatchPathStrategy
from olav.strategies.deep_path import DeepPathStrategy
from olav.strategies.fast_path import FastPathStrategy

logger = logging.getLogger(__name__)


class StrategyDecision(BaseModel):
    """
    Strategy selection decision with reasoning.

    Attributes:
        strategy: Selected strategy name
        confidence: Confidence in selection (0.0-1.0)
        reasoning: Why this strategy was chosen
        fallback: Alternative strategy if primary fails
    """

    strategy: Literal["fast_path", "deep_path", "batch_path"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    fallback: Literal["fast_path", "deep_path", "batch_path"] | None = None


class StrategySelector:
    """
    Intelligent strategy selector for query routing.

    Uses a two-phase approach:
    1. Rule-based filtering (keyword matching)
    2. LLM-based classification (for ambiguous cases)

    This ensures fast routing for clear cases while handling
    edge cases with LLM reasoning.

    Attributes:
        llm: Language model for ambiguous case classification
        use_llm_fallback: Whether to use LLM when rules are uncertain
        confidence_threshold: Minimum confidence for rule-based selection
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        use_llm_fallback: bool = True,
        confidence_threshold: float = 0.8,
    ) -> None:
        """
        Initialize StrategySelector.

        Args:
            llm: Language model for ambiguous cases
            use_llm_fallback: Enable LLM classification fallback
            confidence_threshold: Min confidence for rule-based selection
        """
        self.llm = llm
        self.use_llm_fallback = use_llm_fallback and llm is not None
        self.confidence_threshold = confidence_threshold

    async def select(self, user_query: str) -> StrategyDecision:
        """
        Select optimal strategy for user query.

        Args:
            user_query: User's natural language query

        Returns:
            StrategyDecision with selected strategy and reasoning
        """
        # Phase 1: Rule-based selection (fast path)
        rule_decision = self._rule_based_selection(user_query)

        # If confident, return immediately
        if rule_decision.confidence >= self.confidence_threshold:
            logger.info(
                f"Rule-based selection: {rule_decision.strategy} "
                f"(confidence: {rule_decision.confidence:.2f})"
            )
            return rule_decision

        # Phase 2: LLM-based classification (for ambiguous cases)
        if self.use_llm_fallback:
            logger.info("Rule-based selection uncertain, using LLM classification")
            return await self._llm_based_selection(user_query, rule_decision)

        # No LLM available, return rule-based decision
        logger.warning(f"Low confidence ({rule_decision.confidence:.2f}) but no LLM fallback")
        return rule_decision

    def _rule_based_selection(self, user_query: str) -> StrategyDecision:
        """
        Rule-based strategy selection using keyword matching.

        Priority order:
        1. Batch keywords → Batch Path
        2. Diagnostic keywords → Deep Path
        3. Default → Fast Path

        Args:
            user_query: User query

        Returns:
            StrategyDecision with confidence score
        """
        query_lower = user_query.lower()

        # Check batch keywords (highest priority)
        batch_keywords = [
            "batch",
            "批量",
            "all devices",
            "所有设备",
            "compliance",
            "合规",
            "audit",
            "审计",
            "health check",
            "健康检查",
            "inspect all",
            "检查所有",
            "validate all",
            "验证所有",
            "all routers",
            "所有路由器",
            "all switches",
            "所有交换机",
            "every device",
            "每个设备",
        ]

        batch_matches = sum(1 for kw in batch_keywords if kw in query_lower)
        if batch_matches > 0:
            confidence = min(0.7 + (batch_matches * 0.1), 0.95)
            return StrategyDecision(
                strategy="batch_path",
                confidence=confidence,
                reasoning=f"Detected {batch_matches} batch keywords: multi-device operation",
                fallback="fast_path",  # If batch config missing, fall back to fast
            )

        # Check diagnostic keywords (medium priority)
        diagnostic_keywords = [
            "why",
            "为什么",
            "diagnose",
            "诊断",
            "troubleshoot",
            "排查",
            "analyze",
            "分析",
            "investigate",
            "调查",
            "root cause",
            "根因",
            "explain",
            "解释",
            "debug",
            "调试",
            "trace",
            "追踪",
        ]

        diagnostic_matches = sum(1 for kw in diagnostic_keywords if kw in query_lower)
        if diagnostic_matches > 0:
            confidence = min(0.75 + (diagnostic_matches * 0.1), 0.95)
            return StrategyDecision(
                strategy="deep_path",
                confidence=confidence,
                reasoning=f"Detected {diagnostic_matches} diagnostic keywords: needs reasoning",
                fallback="fast_path",
            )

        # Check fast path indicators (default)
        fast_keywords = [
            "show",
            "显示",
            "list",
            "列出",
            "get",
            "获取",
            "查询",
            "query",
            "check",
            "检查",
            "status",
            "状态",
            "what is",
            "什么是",
            "how many",
            "多少",
        ]

        fast_matches = sum(1 for kw in fast_keywords if kw in query_lower)

        # If no clear indicators, default to fast with low confidence
        if fast_matches == 0:
            return StrategyDecision(
                strategy="fast_path",
                confidence=0.5,
                reasoning="No clear indicators, defaulting to fast path",
                fallback="deep_path",
            )

        # Clear fast path query
        confidence = min(0.6 + (fast_matches * 0.1), 0.9)
        return StrategyDecision(
            strategy="fast_path",
            confidence=confidence,
            reasoning=f"Detected {fast_matches} fast path keywords: simple lookup",
            fallback="deep_path",
        )

    async def _llm_based_selection(
        self, user_query: str, rule_decision: StrategyDecision
    ) -> StrategyDecision:
        """
        LLM-based strategy classification for ambiguous queries.

        Args:
            user_query: User query
            rule_decision: Initial rule-based decision (for context)

        Returns:
            StrategyDecision from LLM analysis
        """
        prompt = f"""你是网络运维策略选择专家。分析用户查询并选择最优执行策略。

## 可选策略

1. **fast_path** (快速路径)
   - 用途: 简单查询、单设备状态检查
   - 特点: <2 秒响应、单次工具调用、确定性结果
   - 示例: "查询 R1 BGP 状态", "显示接口列表", "获取设备 IP"

2. **deep_path** (深度路径)
   - 用途: 复杂诊断、多步推理、根因分析
   - 特点: 迭代推理、假设验证、自适应探索
   - 示例: "为什么 R1 BGP 无法建立？", "诊断丢包原因", "排查路由异常"

3. **batch_path** (批量路径)
   - 用途: 多设备批量检查、合规审计、健康检查
   - 特点: 并行执行、零 LLM 验证、报告生成
   - 示例: "批量检查所有路由器", "审计 BGP 配置", "健康检查所有交换机"

## 用户查询
{user_query}

## 规则初选建议
策略: {rule_decision.strategy}
置信度: {rule_decision.confidence:.2f}
理由: {rule_decision.reasoning}

## 任务
分析查询复杂度、设备范围、预期结果类型，选择最优策略。

返回 JSON：
{{{{
    "strategy": "fast_path|deep_path|batch_path",
    "confidence": 0.95,
    "reasoning": "选择理由（考虑查询类型、复杂度、设备范围）",
    "fallback": "fast_path|deep_path|batch_path"
}}}}
"""

        try:
            # Use robust_structured_output for reliable JSON extraction
            decision = await robust_structured_output(
                llm=self.llm,
                output_class=StrategyDecision,
                prompt=prompt,
            )
            logger.info(
                f"LLM classification: {decision.strategy} (confidence: {decision.confidence:.2f})"
            )
            return decision
        except Exception as e:
            logger.error(f"Failed to parse LLM decision: {e}")
            # Fall back to rule-based decision
            return rule_decision

    @staticmethod
    def get_strategy_class(strategy_name: Literal["fast_path", "deep_path", "batch_path"]) -> type:
        """
        Get strategy class by name.

        Args:
            strategy_name: Strategy identifier

        Returns:
            Strategy class (FastPathStrategy, DeepPathStrategy, or BatchPathStrategy)
        """
        strategy_map = {
            "fast_path": FastPathStrategy,
            "deep_path": DeepPathStrategy,
            "batch_path": BatchPathStrategy,
        }

        return strategy_map[strategy_name]

    def select_sync(self, user_query: str) -> StrategyDecision:
        """
        Synchronous strategy selection (rule-based only).

        Useful when LLM is not available or async execution not needed.

        Args:
            user_query: User query

        Returns:
            StrategyDecision from rule-based selection
        """
        return self._rule_based_selection(user_query)


def create_strategy_selector(
    llm: BaseChatModel | None = None, use_llm_fallback: bool = True
) -> StrategySelector:
    """
    Factory function to create StrategySelector.

    Args:
        llm: Language model for LLM-based classification
        use_llm_fallback: Enable LLM fallback for ambiguous cases

    Returns:
        Configured StrategySelector instance
    """
    return StrategySelector(llm=llm, use_llm_fallback=use_llm_fallback, confidence_threshold=0.8)
