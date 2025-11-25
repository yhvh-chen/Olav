"""
Execution Strategies Package.

This package implements different execution strategies for OLAV workflows:

- FastPathStrategy: Single-shot function calling for simple queries (no agent loop)
- DeepPathStrategy: Hypothesis-driven loop for complex diagnostics (iterative reasoning)
- BatchPathStrategy: YAML-driven inspection with parallel execution (deterministic validation)

Each strategy optimizes for different query characteristics:
- Fast: Low latency, high certainty (SuzieQ table lookup)
- Deep: High complexity, root cause analysis (multi-source validation)
- Batch: High volume, compliance checks (zero-hallucination logic)
"""

from .batch_path import BatchPathStrategy
from .deep_path import DeepPathStrategy
from .fast_path import FastPathStrategy
from .selector import StrategyDecision, StrategySelector, create_strategy_selector

__all__ = [
    "BatchPathStrategy",
    "DeepPathStrategy",
    "FastPathStrategy",
    "StrategyDecision",
    "StrategySelector",
    "create_strategy_selector",
]
