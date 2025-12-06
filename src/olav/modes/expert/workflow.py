"""Expert Mode Workflow - Combines Supervisor + QuickAnalyzer.

The workflow:
1. Initialize Supervisor state
2. Round 0: KB + Syslog context enrichment
3. Rounds 1-N: Iterative layer investigation
4. Generate final diagnosis report

Usage:
    workflow = ExpertModeWorkflow()
    result = await workflow.run("R1 无法与 R2 建立 BGP", path_devices=["R1", "R2"])
    print(result.final_report)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from olav.modes.expert.supervisor import (
    ExpertModeSupervisor,
    SupervisorState,
    DiagnosisResult,
)
from olav.modes.expert.quick_analyzer import QuickAnalyzer
from olav.modes.shared.debug import DebugContext, DebugOutput

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow State
# =============================================================================


@dataclass
class ExpertModeOutput:
    """Output from Expert Mode workflow."""
    
    success: bool
    query: str
    root_cause_found: bool
    root_cause: str | None
    final_report: str
    layer_coverage: dict[str, Any]
    rounds_executed: int
    
    # Debug information
    debug_output: DebugOutput | None = None
    
    # Timing
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None
    
    @property
    def duration_seconds(self) -> float:
        """Calculate execution duration."""
        if not self.completed_at:
            return 0.0
        
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.completed_at)
        return (end - start).total_seconds()


# =============================================================================
# Expert Mode Workflow
# =============================================================================


class ExpertModeWorkflow:
    """Orchestrates multi-step fault diagnosis.
    
    Combines:
    - Supervisor: Plans tasks, tracks L1-L4 coverage
    - QuickAnalyzer: Executes tasks using ReAct + SuzieQ
    
    The workflow iterates until:
    - Root cause is found
    - Max rounds reached
    - All layers have sufficient confidence
    
    Usage:
        workflow = ExpertModeWorkflow(max_rounds=5)
        
        # Without debug
        result = await workflow.run("R1 BGP neighbor down")
        
        # With debug context
        async with DebugContext() as ctx:
            result = await workflow.run("R1 BGP neighbor down", debug_context=ctx)
            debug_output = ctx.output
    """
    
    def __init__(self, max_rounds: int = 5, max_analyzer_iterations: int = 5):
        """Initialize Expert Mode workflow.
        
        Args:
            max_rounds: Maximum investigation rounds (Supervisor).
            max_analyzer_iterations: Maximum ReAct iterations per task (QuickAnalyzer).
        """
        self.max_rounds = max_rounds
        self.max_analyzer_iterations = max_analyzer_iterations
    
    async def run(
        self,
        query: str,
        path_devices: list[str] | None = None,
        debug_context: DebugContext | None = None,
    ) -> ExpertModeOutput:
        """Run Expert Mode fault diagnosis.
        
        Args:
            query: User query or alert message.
            path_devices: Optional list of devices to investigate.
            debug_context: Optional debug context for instrumentation.
        
        Returns:
            ExpertModeOutput with diagnosis results.
        """
        started_at = datetime.now().isoformat()
        
        # Initialize components
        supervisor = ExpertModeSupervisor(max_rounds=self.max_rounds)
        analyzer = QuickAnalyzer(
            max_iterations=self.max_analyzer_iterations,
            debug_context=debug_context,
        )
        
        # Create initial state
        state = supervisor.create_initial_state(
            query=query,
            path_devices=path_devices,
        )
        
        logger.info(f"Expert Mode started: {query}")
        
        # Record initial state
        if debug_context:
            debug_context.log_graph_state(
                node="ExpertMode.init",
                state={
                    "query": query,
                    "path_devices": path_devices,
                    "max_rounds": self.max_rounds,
                },
            )
        
        try:
            # Round 0: KB + Syslog context
            state = await supervisor.round_zero_context(state)
            
            if debug_context:
                debug_context.log_graph_state(
                    node="ExpertMode.round_zero",
                    state={
                        "similar_cases": len(state.similar_cases),
                        "syslog_events": len(state.syslog_events),
                        "priority_layer": state.priority_layer,
                    },
                )
            
            logger.info(
                f"Round 0 complete: {len(state.similar_cases)} similar cases, "
                f"{len(state.syslog_events)} syslog events, "
                f"priority layer: {state.priority_layer}"
            )
            
            # Rounds 1-N: Iterative investigation
            while state.should_continue():
                # Plan next task
                task = await supervisor.plan_next_task(state)
                if not task:
                    break
                
                logger.info(
                    f"Round {state.current_round + 1}: "
                    f"Investigating {task.layer} ({task.description})"
                )
                
                if debug_context:
                    debug_context.log_graph_state(
                        node=f"ExpertMode.round_{state.current_round + 1}.plan",
                        state={
                            "task_id": task.task_id,
                            "layer": task.layer,
                            "suggested_tables": task.suggested_tables,
                        },
                    )
                
                # Execute task
                result = await analyzer.execute(task)
                
                if debug_context:
                    debug_context.log_graph_state(
                        node=f"ExpertMode.round_{state.current_round + 1}.result",
                        state={
                            "success": result.success,
                            "confidence": result.confidence,
                            "findings_count": len(result.findings),
                        },
                    )
                
                # Update state
                state = supervisor.update_state(state, result)
                
                logger.info(
                    f"Round {state.current_round} complete: "
                    f"confidence={result.confidence:.2f}, "
                    f"{len(result.findings)} findings"
                )
            
            # Generate report
            final_report = supervisor.generate_report(state)
            
            if debug_context:
                debug_context.log_graph_state(
                    node="ExpertMode.complete",
                    state={
                        "root_cause_found": state.root_cause_found,
                        "rounds_executed": state.current_round,
                    },
                )
            
            logger.info(
                f"Expert Mode complete: root_cause_found={state.root_cause_found}, "
                f"rounds={state.current_round}"
            )
            
            return ExpertModeOutput(
                success=True,
                query=query,
                root_cause_found=state.root_cause_found,
                root_cause=state.root_cause,
                final_report=final_report,
                layer_coverage={
                    layer: {
                        "checked": status.checked,
                        "confidence": status.confidence,
                        "findings": status.findings,
                    }
                    for layer, status in state.layer_coverage.items()
                },
                rounds_executed=state.current_round,
                debug_output=debug_context.output if debug_context else None,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )
        
        except Exception as e:
            logger.error(f"Expert Mode failed: {e}")
            
            return ExpertModeOutput(
                success=False,
                query=query,
                root_cause_found=False,
                root_cause=None,
                final_report=f"Error: {e}",
                layer_coverage={},
                rounds_executed=state.current_round if state else 0,
                debug_output=debug_context.output if debug_context else None,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )


# =============================================================================
# Convenience Functions
# =============================================================================


async def run_expert_mode(
    query: str,
    path_devices: list[str] | None = None,
    max_rounds: int = 5,
    debug: bool = False,
) -> ExpertModeOutput:
    """Run Expert Mode fault diagnosis.
    
    Convenience function for running Expert Mode without instantiating the class.
    
    Args:
        query: User query or alert message.
        path_devices: Optional list of devices to investigate.
        max_rounds: Maximum investigation rounds.
        debug: Whether to enable debug instrumentation.
    
    Returns:
        ExpertModeOutput with diagnosis results.
    
    Example:
        result = await run_expert_mode(
            "R1 BGP neighbor down",
            path_devices=["R1", "R2"],
            max_rounds=5,
            debug=True,
        )
        print(result.final_report)
    """
    workflow = ExpertModeWorkflow(max_rounds=max_rounds)
    
    if debug:
        async with DebugContext() as ctx:
            return await workflow.run(query, path_devices, ctx)
    else:
        return await workflow.run(query, path_devices)
