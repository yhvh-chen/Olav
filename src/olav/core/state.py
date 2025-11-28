"""Agent state definitions using TypedDict.

NOTE: The primary workflow states are now defined in olav.workflows.base.BaseWorkflowState
and workflow-specific state classes (InspectionState, QueryDiagnosticState, etc.).

This module provides legacy AgentState for compatibility and reference.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Root agent state shared across all SubAgents.
    
    NOTE: Current architecture uses BaseWorkflowState from olav.workflows.base.
    This class is retained for compatibility and potential future use.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    device: str | None
    topology_context: dict[str, Any] | None
    current_user: str
    session_id: str


# Legacy state classes removed (2025-11-28)
# - SuzieQState: Replaced by QueryDiagnosticState
# - RAGState: Replaced by OpenSearch schema search
# - NetConfState: Replaced by DeviceExecutionState
