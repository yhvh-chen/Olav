"""Expert Mode - Multi-step fault diagnosis with L1-L4 funnel debugging.

Architecture:
    Query → Supervisor (Track L1-L4 Confidence) ↔ QuickAnalyzer (ReAct)

Components:
    - ExpertModeSupervisor: Orchestrates diagnosis, tracks layer coverage
    - QuickAnalyzer: ReAct agent for targeted layer investigation
    - ExpertModeWorkflow: Combines Supervisor + QuickAnalyzer

Usage:
    from olav.modes.expert import ExpertModeWorkflow, run_expert_mode

    # Class-based
    workflow = ExpertModeWorkflow(max_rounds=5)
    result = await workflow.run("R1 BGP neighbor down")

    # Convenience function
    result = await run_expert_mode("R1 BGP neighbor down", debug=True)
"""

from olav.modes.expert.quick_analyzer import QuickAnalyzer
from olav.modes.expert.supervisor import (
    LAYER_INFO,
    NETWORK_LAYERS,
    DiagnosisResult,
    DiagnosisTask,
    ExpertModeSupervisor,
    LayerStatus,
    SupervisorState,
)
from olav.modes.expert.workflow import ExpertModeOutput, ExpertModeWorkflow, run_expert_mode

__all__ = [
    "LAYER_INFO",
    "NETWORK_LAYERS",
    "DiagnosisResult",
    "DiagnosisTask",
    "ExpertModeOutput",
    # Supervisor
    "ExpertModeSupervisor",
    # Workflow
    "ExpertModeWorkflow",
    "LayerStatus",
    # Quick Analyzer
    "QuickAnalyzer",
    "SupervisorState",
    "run_expert_mode",
]
