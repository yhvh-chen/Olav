"""Workflow module - Modular LangGraph workflows for different operational scenarios.

Architecture:
- BaseWorkflow: Abstract protocol defining workflow interface
- QueryDiagnosticWorkflow: Network queries + root cause analysis (SuzieQ + NETCONF)
- DeviceExecutionWorkflow: Config changes with HITL approval (NETCONF/CLI)
- NetBoxManagementWorkflow: Inventory management with HITL (NetBox API)
- WorkflowOrchestrator: Intent classification + routing

Usage:
    from olav.workflows import create_orchestrator
    
    orchestrator = await create_orchestrator(postgres_uri)
    result = await orchestrator.route(user_query="BGP为什么down？", thread_id="user-123")
"""

from .base import BaseWorkflow, BaseWorkflowState, WorkflowType
from .query_diagnostic import QueryDiagnosticWorkflow, QueryDiagnosticState
from .device_execution import DeviceExecutionWorkflow, DeviceExecutionState
from .netbox_management import NetBoxManagementWorkflow, NetBoxManagementState

__all__ = [
    "BaseWorkflow",
    "BaseWorkflowState",
    "WorkflowType",
    "QueryDiagnosticWorkflow",
    "QueryDiagnosticState",
    "DeviceExecutionWorkflow",
    "DeviceExecutionState",
    "NetBoxManagementWorkflow",
    "NetBoxManagementState",
]
