"""Standard Mode Workflow - Complete Standard Mode orchestration.

This is the main entry point for Standard Mode.
Combines classifier, executor, and response formatting.
"""

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from olav.modes.standard.classifier import StandardModeClassifier
from olav.modes.standard.executor import (
    ExecutionResult,
    HITLRequiredError,
    StandardModeExecutor,
)
from olav.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class StandardModeResult(BaseModel):
    """Complete result of Standard Mode execution."""

    # Success/failure
    success: bool

    # Human-readable answer
    answer: str = ""

    # Escalation to Expert Mode
    escalated_to_expert: bool = False
    escalation_reason: str = ""

    # HITL information
    hitl_required: bool = False
    hitl_operation: str = ""
    hitl_parameters: dict[str, Any] = Field(default_factory=dict)

    # Execution details
    tool_name: str = ""
    tool_output: Any = None
    execution_time_ms: float = 0.0

    # Classification details
    intent_category: str = ""
    confidence: float = 0.0

    # Error information
    error: str | None = None

    # Debug metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class StandardModeWorkflow:
    """Standard Mode workflow - fast single-step query execution.

    This workflow:
    1. Classifies user query (single LLM call)
    2. Checks confidence threshold
    3. Executes tool (with HITL check)
    4. Formats response

    Usage:
        workflow = StandardModeWorkflow(tool_registry)
        result = await workflow.run("查询 R1 BGP 状态")

        if result.escalated_to_expert:
            # Hand off to Expert Mode
            pass
        elif result.hitl_required:
            # Show approval UI
            pass
        else:
            print(result.answer)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        confidence_threshold: float = 0.7,
        yolo_mode: bool = False,
    ) -> None:
        """Initialize Standard Mode workflow.

        Args:
            tool_registry: Registry of available tools.
            confidence_threshold: Threshold for Expert Mode escalation.
            yolo_mode: Skip HITL approval (for testing).
        """
        self.classifier = StandardModeClassifier(
            confidence_threshold=confidence_threshold,
        )
        self.executor = StandardModeExecutor(
            tool_registry=tool_registry,
            yolo_mode=yolo_mode,
        )
        self.tool_registry = tool_registry
        self.confidence_threshold = confidence_threshold

    async def run(
        self,
        query: str,
        schema_context: dict[str, Any] | None = None,
        approval_callback: Any = None,
    ) -> StandardModeResult:
        """Execute Standard Mode workflow.

        Args:
            query: User's natural language query.
            schema_context: Optional schema context from discovery.
            approval_callback: Optional callback for HITL approval.

        Returns:
            StandardModeResult with answer or escalation/HITL info.
        """
        start_time = time.perf_counter()

        try:
            # Step 1: Classify query
            classify_start = time.perf_counter()
            classification = await self.classifier.classify(query, schema_context)
            classify_time_ms = (time.perf_counter() - classify_start) * 1000

            # Get LLM time from classification result if available
            llm_time_ms = getattr(classification, "_llm_time_ms", classify_time_ms)

            # Step 2: Check for Expert Mode escalation
            if self.classifier.should_escalate_to_expert(classification):
                elapsed = (time.perf_counter() - start_time) * 1000
                return StandardModeResult(
                    success=False,
                    escalated_to_expert=True,
                    escalation_reason=(
                        f"Confidence {classification.confidence:.2f} "
                        f"below threshold {self.confidence_threshold}"
                    ),
                    intent_category=classification.intent_category,
                    confidence=classification.confidence,
                    execution_time_ms=elapsed,
                    metadata={
                        "classification": classification.model_dump(),
                    },
                )

            # Step 3: Execute tool
            if approval_callback:
                exec_result = await self.executor.execute_with_approval(
                    classification, query, approval_callback
                )
            else:
                try:
                    exec_result = await self.executor.execute(classification, query)
                except HITLRequiredError as e:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    return StandardModeResult(
                        success=False,
                        hitl_required=True,
                        hitl_operation=e.operation,
                        hitl_parameters=e.parameters,
                        tool_name=e.tool_name,
                        intent_category=classification.intent_category,
                        confidence=classification.confidence,
                        execution_time_ms=elapsed,
                        metadata={
                            "classification": classification.model_dump(),
                            "hitl_reason": e.reason,
                        },
                    )

            # Step 4: Format response
            elapsed = (time.perf_counter() - start_time) * 1000

            if not exec_result.success:
                return StandardModeResult(
                    success=False,
                    error=exec_result.error,
                    tool_name=exec_result.tool_name,
                    tool_output=exec_result.tool_output,
                    intent_category=classification.intent_category,
                    confidence=classification.confidence,
                    execution_time_ms=elapsed,
                    hitl_required=exec_result.hitl_triggered,
                    metadata={
                        "classification": classification.model_dump(),
                    },
                )

            # Format answer from tool output
            answer = self._format_answer(query, exec_result)

            return StandardModeResult(
                success=True,
                answer=answer,
                tool_name=exec_result.tool_name,
                tool_output=exec_result.tool_output,
                intent_category=classification.intent_category,
                confidence=classification.confidence,
                execution_time_ms=elapsed,
                metadata={
                    "classification": classification.model_dump(),
                    "tool_execution_ms": exec_result.execution_time_ms,
                    "llm_time_ms": llm_time_ms,
                    "classify_time_ms": classify_time_ms,
                },
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception(f"Standard Mode workflow failed: {e}")
            return StandardModeResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )

    def _format_answer(self, query: str, result: ExecutionResult) -> str:
        """Format tool output into human-readable answer.

        For now, this is a simple formatting. In production, this could
        use an LLM for more natural responses.
        """
        if not result.tool_output:
            return "No data returned from tool."

        output = result.tool_output

        # Handle different output formats
        if hasattr(output, "data") and output.data:
            data = output.data

            # DataFrame-like output
            if hasattr(data, "to_string"):
                return f"Query result:\n\n{data.to_string()}"

            # List of dicts
            if isinstance(data, list):
                if len(data) == 0:
                    return "No matching data found."

                # Format as simple table
                lines = [f"Found {len(data)} results:"]
                for i, item in enumerate(data[:10], 1):  # Limit to 10 items
                    if isinstance(item, dict):
                        summary = ", ".join(f"{k}={v}" for k, v in list(item.items())[:5])
                        lines.append(f"  {i}. {summary}")
                    else:
                        lines.append(f"  {i}. {item}")

                if len(data) > 10:
                    lines.append(f"  ... and {len(data) - 10} more")

                return "\n".join(lines)

            # Dict output
            if isinstance(data, dict):
                lines = ["Result:"]
                for k, v in list(data.items())[:10]:
                    lines.append(f"  {k}: {v}")
                return "\n".join(lines)

            # String output
            return str(data)

        # Raw message
        if hasattr(output, "message") and output.message:
            return output.message

        return str(output)


# Module-level convenience function
async def run_standard_mode(
    query: str,
    tool_registry: ToolRegistry,
    confidence_threshold: float = 0.7,
    yolo_mode: bool = False,
    schema_context: dict[str, Any] | None = None,
    approval_callback: Any = None,
) -> StandardModeResult:
    """Run Standard Mode workflow.

    This is the main entry point for Standard Mode execution.

    Args:
        query: User's natural language query.
        tool_registry: Registry of available tools.
        confidence_threshold: Threshold for Expert Mode escalation.
        yolo_mode: Skip HITL approval (for testing).
        schema_context: Optional schema context.
        approval_callback: Optional HITL approval callback.

    Returns:
        StandardModeResult with answer or escalation/HITL info.
    """
    workflow = StandardModeWorkflow(
        tool_registry=tool_registry,
        confidence_threshold=confidence_threshold,
        yolo_mode=yolo_mode,
    )
    return await workflow.run(query, schema_context, approval_callback)
