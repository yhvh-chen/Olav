"""Expert Mode Workflow - Two-phase diagnosis: Quick + Deep.

The workflow:
0. Guard: Two-layer filtering (relevance + sufficiency)
1. Initialize Supervisor state
2. Round 0: KB + Syslog context enrichment
3. Phase 1 (Rounds 1-N): Quick Analyzer with SuzieQ (historical data)
4. Phase 2 (if needed): Deep Analyzer with OpenConfig/CLI (realtime data)
5. Generate final diagnosis report + index to Episodic Memory

Two-Phase Architecture:
- Phase 1 (Quick): SuzieQ historical data, max 60% confidence
- Phase 2 (Deep): OpenConfig/CLI realtime data, up to 95% confidence

Usage:
    workflow = ExpertModeWorkflow()
    result = await workflow.run("R1 无法与 R2 建立 BGP", path_devices=["R1", "R2"])
    print(result.final_report)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from olav.modes.expert.deep_analyzer import DeepAnalyzer
from olav.modes.expert.guard import (
    DiagnosisContext,
    ExpertModeGuard,
    ExpertModeGuardResult,
)
from olav.modes.expert.quick_analyzer import QuickAnalyzer
from olav.modes.expert.report import ReportGenerator
from olav.modes.expert.supervisor import (
    ExpertModeSupervisor,
)
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

    # Phase tracking
    phase2_executed: bool = False
    phase2_findings: list[str] = field(default_factory=list)

    # Guard result (if guard was enabled)
    guard_result: ExpertModeGuardResult | None = None
    diagnosis_context: DiagnosisContext | None = None

    # Redirect info (if query was redirected)
    redirected: bool = False
    redirect_mode: str | None = None
    redirect_message: str | None = None

    # Clarification needed (if info insufficient)
    clarification_needed: bool = False
    clarification_prompt: str | None = None
    missing_info: list[str] = field(default_factory=list)

    # Agentic loop - indexed to episodic memory
    indexed_to_memory: bool = False

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
    """Orchestrates two-phase fault diagnosis.

    Two-Phase Architecture:
    - Phase 1 (Quick Analyzer): SuzieQ historical data, max 60% confidence
    - Phase 2 (Deep Analyzer): OpenConfig/CLI realtime data, up to 95% confidence

    Combines:
    - Supervisor: Plans tasks, tracks L1-L4 coverage, triggers Phase 2
    - QuickAnalyzer: Phase 1 - SuzieQ ReAct agent
    - DeepAnalyzer: Phase 2 - OpenConfig/CLI verification
    - ReportGenerator: Final report + Agentic memory indexing

    The workflow iterates until:
    - Root cause is found with sufficient confidence
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

    def __init__(
        self,
        max_rounds: int = 5,
        max_analyzer_iterations: int = 5,
        enable_phase2: bool = True,
        enable_guard: bool = True,
        index_to_memory: bool = True,
    ) -> None:
        """Initialize Expert Mode workflow.

        Args:
            max_rounds: Maximum investigation rounds (Supervisor).
            max_analyzer_iterations: Maximum ReAct iterations per task.
            enable_phase2: Whether to enable Phase 2 (Deep Analyzer).
            enable_guard: Whether to enable Guard (two-layer filtering).
            index_to_memory: Whether to index successful diagnoses to memory.
        """
        self.max_rounds = max_rounds
        self.max_analyzer_iterations = max_analyzer_iterations
        self.enable_phase2 = enable_phase2
        self.enable_guard = enable_guard
        self.index_to_memory = index_to_memory

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
        quick_analyzer = QuickAnalyzer(
            max_iterations=self.max_analyzer_iterations,
            debug_context=debug_context,
        )
        deep_analyzer = DeepAnalyzer(
            max_iterations=self.max_analyzer_iterations,
            debug_context=debug_context,
        )
        report_generator = ReportGenerator()

        logger.info(f"Expert Mode started: {query}")

        # =================================================================
        # Step 0: Guard - Two-layer filtering
        # =================================================================
        guard_result: ExpertModeGuardResult | None = None
        diagnosis_context: DiagnosisContext | None = None

        if self.enable_guard:
            from olav.core.llm import LLMFactory

            guard_llm = LLMFactory.get_chat_model(json_mode=True)
            guard = ExpertModeGuard(llm=guard_llm)
            guard_result = await guard.check(query)

            if debug_context:
                debug_context.log_graph_state(
                    node="ExpertMode.guard",
                    state={
                        "query_type": guard_result.query_type.value,
                        "is_fault_diagnosis": guard_result.is_fault_diagnosis,
                        "is_sufficient": guard_result.is_sufficient,
                        "missing_info": guard_result.missing_info,
                    },
                )

            logger.info(
                f"Guard result: type={guard_result.query_type.value}, "
                f"is_diagnosis={guard_result.is_fault_diagnosis}, "
                f"sufficient={guard_result.is_sufficient}"
            )

            # Layer 1: Not a fault diagnosis → redirect
            if not guard_result.is_fault_diagnosis:
                redirect_msg = ExpertModeGuard.get_redirect_message(guard_result.query_type)
                logger.info(f"Guard: Redirecting to {guard_result.redirect_mode}: {redirect_msg}")

                return ExpertModeOutput(
                    success=False,
                    query=query,
                    root_cause_found=False,
                    root_cause=None,
                    final_report=redirect_msg,
                    layer_coverage={},
                    rounds_executed=0,
                    guard_result=guard_result,
                    redirected=True,
                    redirect_mode=guard_result.redirect_mode,
                    redirect_message=redirect_msg,
                    started_at=started_at,
                    completed_at=datetime.now().isoformat(),
                )

            # Layer 2: Info not sufficient → ask for clarification
            if not guard_result.is_sufficient:
                clarification_msg = (
                    guard_result.clarification_prompt
                    or f"请补充以下信息: {', '.join(guard_result.missing_info)}"
                )
                logger.info(f"Guard: Clarification needed: {clarification_msg}")

                return ExpertModeOutput(
                    success=False,
                    query=query,
                    root_cause_found=False,
                    root_cause=None,
                    final_report=clarification_msg,
                    layer_coverage={},
                    rounds_executed=0,
                    guard_result=guard_result,
                    diagnosis_context=guard_result.context,
                    clarification_needed=True,
                    clarification_prompt=clarification_msg,
                    missing_info=guard_result.missing_info,
                    started_at=started_at,
                    completed_at=datetime.now().isoformat(),
                )

            # Guard passed: extract diagnosis context
            diagnosis_context = guard_result.context
            logger.info(
                f"Guard passed: symptom={diagnosis_context.symptom if diagnosis_context else 'N/A'}, "
                f"source={diagnosis_context.source_device if diagnosis_context else 'N/A'}, "
                f"target={diagnosis_context.target_device if diagnosis_context else 'N/A'}"
            )

        # Create initial state (with enriched context from Guard if available)
        state = supervisor.create_initial_state(
            query=query,
            path_devices=path_devices,
        )

        # Record initial state
        if debug_context:
            debug_context.log_graph_state(
                node="ExpertMode.init",
                state={
                    "query": query,
                    "path_devices": path_devices,
                    "max_rounds": self.max_rounds,
                    "guard_enabled": self.enable_guard,
                    "guard_passed": guard_result.is_fault_diagnosis if guard_result else "N/A",
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

                # Execute task (Phase 1 - Quick Analyzer with SuzieQ)
                result = await quick_analyzer.execute(task)

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

            # =================================================================
            # Phase 2: Deep Analyzer (if needed)
            # =================================================================
            phase2_executed = False
            phase2_findings: list[str] = []

            if supervisor.should_trigger_phase2(state):
                logger.info("Phase 2 triggered: Running Deep Analyzer for realtime verification")

                if debug_context:
                    debug_context.log_graph_state(
                        node="ExpertMode.phase2_start",
                        state={
                            "trigger_reason": "confidence < 0.6 or root_cause not found",
                            "current_confidence": max(
                                (s.confidence for s in state.layer_coverage.values()),
                                default=0.0
                            ),
                        },
                    )

                # Collect hypotheses from Phase 1 findings for Deep Analyzer
                phase1_hypotheses: list[str] = []
                for layer, status in state.layer_coverage.items():
                    for finding in status.findings:
                        phase1_hypotheses.append(f"[{layer}] {finding}")

                # Execute Phase 2 with realtime tools
                deep_result = await deep_analyzer.execute_from_workflow(
                    query=query,
                    target_devices=path_devices or [],
                    hypotheses=phase1_hypotheses,
                )

                phase2_executed = True
                phase2_findings = deep_result.findings

                # Update state with Phase 2 results
                if deep_result.root_cause_found and deep_result.root_cause:
                    state.root_cause_found = True
                    state.root_cause = deep_result.root_cause

                # Mark phase 2 executed
                state.phase2_executed = True
                state.phase2_findings = phase2_findings

                if debug_context:
                    debug_context.log_graph_state(
                        node="ExpertMode.phase2_complete",
                        state={
                            "root_cause_found": deep_result.root_cause_found,
                            "findings_count": len(phase2_findings),
                            "confidence": deep_result.confidence,
                        },
                    )

                logger.info(
                    f"Phase 2 complete: root_cause_found={deep_result.root_cause_found}, "
                    f"{len(phase2_findings)} findings"
                )

            # =================================================================
            # Generate Report and Index to Episodic Memory
            # =================================================================
            final_report = report_generator.generate(
                query=query,
                state=state,
                phase2_executed=phase2_executed,
                phase2_findings=phase2_findings,
            )

            # Index successful diagnosis to Episodic Memory for future retrieval
            if state.root_cause_found:
                await report_generator.index_to_episodic_memory(
                    query=query,
                    root_cause=state.root_cause or "",
                    findings=[
                        finding
                        for status in state.layer_coverage.values()
                        for finding in status.findings
                    ] + phase2_findings,
                    phase2_executed=phase2_executed,
                )

            if debug_context:
                debug_context.log_graph_state(
                    node="ExpertMode.complete",
                    state={
                        "root_cause_found": state.root_cause_found,
                        "rounds_executed": state.current_round,
                        "phase2_executed": phase2_executed,
                    },
                )

            logger.info(
                f"Expert Mode complete: root_cause_found={state.root_cause_found}, "
                f"rounds={state.current_round}, phase2={phase2_executed}"
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
                phase2_executed=phase2_executed,
                phase2_findings=phase2_findings,
                guard_result=guard_result,
                diagnosis_context=diagnosis_context,
                indexed_to_memory=state.root_cause_found,
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
                phase2_executed=False,
                phase2_findings=[],
                guard_result=guard_result,
                diagnosis_context=diagnosis_context,
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
