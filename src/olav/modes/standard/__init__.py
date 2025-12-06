"""Standard Mode - Fast single-step query execution.

Components:
    - StandardModeClassifier: LLM-based tool selection (single call)
    - StandardModeExecutor: Direct tool invocation with HITL
    - StandardModeWorkflow: Complete orchestration

Capabilities:
    - SuzieQ query/summarize/unique/aver
    - NetBox read/write (HITL for writes)
    - Schema discovery
    - Nornir config (HITL for writes)

Usage:
    from olav.modes.standard import run_standard_mode

    result = await run_standard_mode(
        query="查询 R1 BGP 状态",
        tool_registry=registry,
    )

    if result.escalated_to_expert:
        # Hand off to Expert Mode
        pass
    elif result.hitl_required:
        # Show approval UI
        pass
    else:
        print(result.answer)
"""

from olav.modes.standard.classifier import (
    StandardModeClassifier,
    classify_standard,
)
from olav.modes.standard.executor import (
    ExecutionResult,
    HITLRequiredError,
    StandardModeExecutor,
)
from olav.modes.standard.workflow import (
    StandardModeResult,
    StandardModeWorkflow,
    run_standard_mode,
)

__all__ = [
    # Executor
    "ExecutionResult",
    "HITLRequiredError",
    # Classifier
    "StandardModeClassifier",
    "StandardModeExecutor",
    # Workflow
    "StandardModeResult",
    "StandardModeWorkflow",
    "classify_standard",
    "run_standard_mode",
]

