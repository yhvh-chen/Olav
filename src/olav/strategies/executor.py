"""
Strategy Executor - Unified execution interface for all strategies.

This module provides a unified interface for executing different strategies
(Fast/Deep/Batch) based on the StrategySelector's decision.

Integration Flow:
1. StrategySelector.select(query) → StrategyDecision
2. StrategyExecutor.execute(query, decision) → Unified result
3. Fallback handling: If primary fails, try fallback strategy

Example Usage:
```python
from olav.strategies import StrategySelector, StrategyExecutor

selector = StrategySelector(llm=llm)
executor = StrategyExecutor(llm=llm)

decision = await selector.select(user_query)
result = await executor.execute(user_query, decision)

if not result["success"] and result.get("fallback_required"):
    # Retry with fallback strategy
    fallback_decision = StrategyDecision(
        strategy=decision.fallback,
        confidence=0.5,
        reasoning="Fallback from primary strategy failure"
    )
    result = await executor.execute(user_query, fallback_decision)
```
"""

import logging
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from olav.strategies.batch_path import BatchPathStrategy
from olav.strategies.deep_path import DeepPathStrategy
from olav.strategies.fast_path import FastPathStrategy
from olav.strategies.selector import StrategyDecision, StrategySelector

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    """
    Unified execution result from any strategy.

    Normalizes output from Fast/Deep/Batch strategies into a common format.
    """

    success: bool
    strategy_used: Literal["fast_path", "deep_path", "batch_path"]
    answer: str | None = None
    reasoning_trace: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    fallback_required: bool = False
    fallback_strategy: Literal["fast_path", "deep_path", "batch_path"] | None = None


class StrategyExecutor:
    """
    Unified strategy executor with automatic fallback handling.

    Provides a single interface for executing any strategy and handles
    fallback logic when primary strategy fails.

    Attributes:
        llm: Language model for strategy execution
        fast_path: FastPathStrategy instance (lazy initialized)
        deep_path: DeepPathStrategy instance (lazy initialized)
        batch_path: BatchPathStrategy instance (lazy initialized)
        auto_fallback: Whether to automatically try fallback on failure
    """

    def __init__(
        self,
        llm: BaseChatModel,
        auto_fallback: bool = True,
        fast_path_config: dict[str, Any] | None = None,
        deep_path_config: dict[str, Any] | None = None,
        batch_path_config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize StrategyExecutor with all strategies.

        Args:
            llm: Language model for strategy execution
            auto_fallback: Enable automatic fallback on failure
            fast_path_config: FastPathStrategy configuration
            deep_path_config: DeepPathStrategy configuration
            batch_path_config: BatchPathStrategy configuration
        """
        self.llm = llm
        self.auto_fallback = auto_fallback

        # Store configs for lazy initialization
        self._fast_config = fast_path_config or {}
        self._deep_config = deep_path_config or {}
        self._batch_config = batch_path_config or {}

        # Lazy-initialized strategies
        self._fast_path: FastPathStrategy | None = None
        self._deep_path: DeepPathStrategy | None = None
        self._batch_path: BatchPathStrategy | None = None

        logger.info(
            f"StrategyExecutor initialized with auto_fallback={auto_fallback}, "
            f"strategies: [fast_path, deep_path, batch_path] (lazy init)"
        )

    def _get_fast_path(self) -> FastPathStrategy:
        """Lazily initialize FastPathStrategy with ToolRegistry."""
        if self._fast_path is None:
            from olav.tools.base import ToolRegistry

            # Import tools package to trigger self-registration
            if not ToolRegistry.list_tools():
                import olav.tools  # noqa: F401 - triggers tool registration

            self._fast_path = FastPathStrategy(
                llm=self.llm, tool_registry=ToolRegistry, **self._fast_config
            )
        return self._fast_path

    def _get_deep_path(self) -> DeepPathStrategy:
        """Lazily initialize DeepPathStrategy."""
        if self._deep_path is None:
            from olav.tools.base import ToolRegistry

            # Import tools package to trigger self-registration
            if not ToolRegistry.list_tools():
                import olav.tools  # noqa: F401 - triggers tool registration

            self._deep_path = DeepPathStrategy(
                llm=self.llm, tool_registry=ToolRegistry, **self._deep_config
            )
        return self._deep_path

    def _get_batch_path(self) -> BatchPathStrategy:
        """Lazily initialize BatchPathStrategy."""
        if self._batch_path is None:
            self._batch_path = BatchPathStrategy(llm=self.llm, **self._batch_config)
        return self._batch_path

    async def execute(
        self,
        user_query: str,
        decision: StrategyDecision,
        context: dict[str, Any] | None = None,
        batch_config_path: str | None = None,
    ) -> ExecutionResult:
        """
        Execute the selected strategy.

        Args:
            user_query: User's natural language query
            decision: StrategyDecision from selector
            context: Optional execution context
            batch_config_path: Path to batch config (for batch_path only)

        Returns:
            ExecutionResult with normalized output
        """
        logger.info(
            f"Executing strategy: {decision.strategy} "
            f"(confidence: {decision.confidence:.2f}, fallback: {decision.fallback})"
        )

        try:
            result = await self._execute_strategy(
                user_query=user_query,
                strategy=decision.strategy,
                context=context,
                batch_config_path=batch_config_path,
            )

            # Check if fallback is needed
            if (
                not result.success
                and result.fallback_required
                and self.auto_fallback
                and decision.fallback
            ):
                logger.info(
                    f"Primary strategy {decision.strategy} failed, "
                    f"attempting fallback: {decision.fallback}"
                )
                result = await self._execute_strategy(
                    user_query=user_query,
                    strategy=decision.fallback,
                    context=context,
                    batch_config_path=batch_config_path,
                )
                result.metadata["fallback_from"] = decision.strategy

            return result

        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            return ExecutionResult(
                success=False,
                strategy_used=decision.strategy,
                error=str(e),
                fallback_required=True,
                fallback_strategy=decision.fallback,
            )

    async def _execute_strategy(
        self,
        user_query: str,
        strategy: Literal["fast_path", "deep_path", "batch_path"],
        context: dict[str, Any] | None = None,
        batch_config_path: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a specific strategy and normalize result.

        Args:
            user_query: User's query
            strategy: Strategy name
            context: Execution context
            batch_config_path: Batch config path (for batch_path)

        Returns:
            Normalized ExecutionResult
        """
        if strategy == "fast_path":
            return await self._execute_fast_path(user_query, context)
        if strategy == "deep_path":
            return await self._execute_deep_path(user_query, context)
        if strategy == "batch_path":
            return await self._execute_batch_path(batch_config_path, context)
        msg = f"Unknown strategy: {strategy}"
        raise ValueError(msg)

    async def _execute_fast_path(
        self, user_query: str, context: dict[str, Any] | None
    ) -> ExecutionResult:
        """Execute Fast Path strategy."""
        fast_path = self._get_fast_path()
        result = await fast_path.execute(user_query, context)

        if not result.get("success", False):
            return ExecutionResult(
                success=False,
                strategy_used="fast_path",
                error=result.get("reason", "Unknown error"),
                fallback_required=result.get("fallback_required", True),
                fallback_strategy="deep_path",
                metadata={"confidence": result.get("confidence", 0)},
            )

        # Extract tool_output - may be ToolOutput object or dict
        tool_output = result.get("tool_output")
        tool_name = None
        if tool_output:
            if hasattr(tool_output, "source"):
                # ToolOutput object
                tool_name = tool_output.source
            elif isinstance(tool_output, dict):
                tool_name = tool_output.get("tool_name")

        return ExecutionResult(
            success=True,
            strategy_used="fast_path",
            answer=result.get("answer"),
            metadata={
                "tool_used": tool_name,
                "execution_time_ms": result.get("metadata", {}).get("execution_time_ms"),
                "confidence": result.get("metadata", {}).get("confidence"),
                "cache_hit": result.get("metadata", {}).get("cache_hit", False),
            },
        )

    async def _execute_deep_path(
        self, user_query: str, context: dict[str, Any] | None
    ) -> ExecutionResult:
        """Execute Deep Path strategy."""
        deep_path = self._get_deep_path()
        result = await deep_path.execute(user_query, context)

        if not result.get("success", False):
            return ExecutionResult(
                success=False,
                strategy_used="deep_path",
                error=result.get("reason", "Unknown error"),
                fallback_required=True,
                fallback_strategy="fast_path",
            )

        return ExecutionResult(
            success=True,
            strategy_used="deep_path",
            answer=result.get("conclusion"),
            reasoning_trace=result.get("reasoning_trace"),
            metadata={
                "iterations": result.get("metadata", {}).get("iterations"),
                "hypotheses_tested": result.get("hypotheses_tested"),
                "confidence": result.get("confidence"),
            },
        )

    async def _execute_batch_path(
        self, config_path: str | None, context: dict[str, Any] | None
    ) -> ExecutionResult:
        """Execute Batch Path strategy."""
        if not config_path:
            # Try to infer config from context
            config_path = context.get("batch_config_path") if context else None

        if not config_path:
            return ExecutionResult(
                success=False,
                strategy_used="batch_path",
                error="Batch path requires config_path",
                fallback_required=True,
                fallback_strategy="fast_path",
            )

        batch_path = self._get_batch_path()
        result = await batch_path.execute(config_path=config_path)

        return ExecutionResult(
            success=True,
            strategy_used="batch_path",
            answer=result.summary.summary_text
            if hasattr(result.summary, "summary_text")
            else str(result.summary),
            metadata={
                "config_name": result.config_name,
                "devices_checked": result.summary.total_devices
                if hasattr(result.summary, "total_devices")
                else None,
                "checks_passed": result.summary.passed
                if hasattr(result.summary, "passed")
                else None,
                "checks_failed": result.summary.failed
                if hasattr(result.summary, "failed")
                else None,
                "violations": result.violations,
            },
        )


async def execute_with_mode(
    user_query: str,
    llm: BaseChatModel,
    mode: Literal["standard", "expert", "inspection"] = "standard",
    context: dict[str, Any] | None = None,
    batch_config_path: str | None = None,
) -> ExecutionResult:
    """
    Execute query using mode-based strategy selection (no LLM for routing).

    This is an optimized version that skips StrategySelector's LLM call by
    directly mapping CLI mode to execution strategy:
    - standard → fast_path (single tool call, optimized for speed)
    - expert → deep_path (iterative reasoning for complex diagnostics)
    - inspection → batch_path (parallel execution with YAML config)

    Benefits:
    - Reduces LLM API calls by 1 (no StrategySelector.select())
    - User explicitly controls execution mode via CLI
    - Faster response time (~10-20% improvement)

    Args:
        user_query: User's natural language query
        llm: Language model for execution (not routing)
        mode: Execution mode from CLI (standard/expert/inspection)
        context: Optional execution context
        batch_config_path: Path to batch config (for inspection mode, use inspect subcommand)

    Returns:
        ExecutionResult with strategy output

    Example:
        ```python
        from olav.strategies.executor import execute_with_mode

        # Standard mode: fast path (single tool call)
        result = await execute_with_mode(
            user_query="查询 R1 BGP 状态",
            llm=LLMFactory.get_chat_model(),
            mode="standard",
        )

        # NOTE: Expert mode now uses SupervisorDrivenWorkflow directly
        # via root_agent_orchestrator._execute_expert_mode(), not this function.
        # This function is only used for standard mode fast_path.
        ```
    """
    # Direct mode-to-strategy mapping (no LLM call)
    # NOTE: Expert mode is handled by SupervisorDrivenWorkflow, not here
    mode_strategy_map: dict[str, Literal["fast_path", "deep_path", "batch_path"]] = {
        "standard": "fast_path",
        "expert": "deep_path",  # Legacy fallback only, prefer SupervisorDrivenWorkflow
        "inspection": "batch_path",  # Use inspect subcommand instead
    }

    strategy = mode_strategy_map.get(mode, "fast_path")

    logger.info(f"Mode-based strategy: {strategy} (mode={mode}, no fallback)")

    # Create decision without LLM (100% confidence since user explicitly chose mode)
    # NO FALLBACK: User explicitly selected this mode, respect their choice
    decision = StrategyDecision(
        strategy=strategy,
        confidence=1.0,  # User explicitly selected this mode
        reasoning=f"User selected {mode} mode via CLI",
        fallback=None,  # No automatic fallback - user controls mode
    )

    # Execute with selected strategy - disable auto_fallback
    # User explicitly chose mode via CLI, don't override their decision
    # Lower confidence_threshold to 0.5 to allow more queries to use fast_path (and its Redis cache)
    executor = StrategyExecutor(
        llm=llm,
        auto_fallback=False,
        fast_path_config={"confidence_threshold": 0.5},
    )
    result = await executor.execute(
        user_query=user_query,
        decision=decision,
        context=context,
        batch_config_path=batch_config_path,
    )

    # Add mode info to metadata
    result.metadata["mode"] = mode
    result.metadata["selection"] = {
        "strategy": strategy,
        "confidence": 1.0,
        "reasoning": f"User selected {mode} mode",
        "fallback": None,  # No fallback - user controls mode
    }

    return result


__all__ = [
    "ExecutionResult",
    "StrategyExecutor",
    "execute_with_mode",
]
