"""
Execution Strategies Package.

This package implements different execution strategies for OLAV workflows:

- FastPathStrategy: Single-shot function calling for simple queries (no agent loop)
- DeepPathStrategy: Hypothesis-driven loop for complex diagnostics (iterative reasoning)
- BatchPathStrategy: YAML-driven inspection with parallel execution (deterministic validation)
- StrategySelector: Rule-based routing to optimal strategy
- StrategyExecutor: Unified execution interface with fallback handling

Each strategy optimizes for different query characteristics:
- Fast: Low latency, high certainty (SuzieQ table lookup)
- Deep: High complexity, root cause analysis (multi-source validation)
- Batch: High volume, compliance checks (zero-hallucination logic)

Usage:
```python
from olav.strategies import execute_with_mode

result = await execute_with_mode(
    user_query="查询 R1 BGP 状态",
    llm=LLMFactory.get_chat_model(),
    mode="standard",
)
```
"""

from .batch_path import BatchPathStrategy
from .deep_path import DeepPathStrategy
from .executor import (
    ExecutionResult,
    StrategyExecutor,
    execute_with_mode,
)
from .fast_path import FastPathStrategy
from .selector import StrategyDecision, StrategySelector, create_strategy_selector

__all__ = [
    "BatchPathStrategy",
    "DeepPathStrategy",
    "ExecutionResult",
    "FastPathStrategy",
    "StrategyDecision",
    "StrategyExecutor",
    "StrategySelector",
    "create_strategy_selector",
    "execute_with_mode",
]
