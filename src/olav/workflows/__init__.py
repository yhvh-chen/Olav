"""Workflow module - Modular LangGraph workflows for different operational scenarios.

Architecture:
- BaseWorkflow: Abstract protocol defining workflow interface
- QueryDiagnosticWorkflow: Network queries + root cause analysis (SuzieQ + NETCONF)
- DeviceExecutionWorkflow: Config changes with HITL approval (NETCONF/CLI)
- BatchExecutionWorkflow: Multi-device batch changes with parallel execution
- NetBoxManagementWorkflow: Inventory management with HITL (NetBox API)
- WorkflowOrchestrator: Intent classification + routing

Usage:
    from olav.workflows import create_orchestrator

    orchestrator = await create_orchestrator(postgres_uri)
    result = await orchestrator.route(user_query="BGP为什么down？", thread_id="user-123")
"""

from .base import BaseWorkflow, BaseWorkflowState, WorkflowType
from .batch_execution import (
    BatchExecutionState,
    BatchExecutionWorkflow,
    DeviceResult,
    DeviceTask,
)
from .device_execution import DeviceExecutionState, DeviceExecutionWorkflow
from .inspection import InspectionState, InspectionWorkflow
from .netbox_management import NetBoxManagementState, NetBoxManagementWorkflow
from .query_diagnostic import QueryDiagnosticState, QueryDiagnosticWorkflow
from .registry import WorkflowMetadata, WorkflowRegistry
from .supervisor_driven import (
    LAYER_INFO,
    NETWORK_LAYERS,
    SupervisorDrivenState,
    SupervisorDrivenWorkflow,
    create_supervisor_driven_workflow,
)

__all__ = [
    "BaseWorkflow",
    "BaseWorkflowState",
    "BatchExecutionState",
    "BatchExecutionWorkflow",
    "DeviceExecutionState",
    "DeviceExecutionWorkflow",
    "DeviceResult",
    "DeviceTask",
    "InspectionState",
    "InspectionWorkflow",
    "LAYER_INFO",
    "NETWORK_LAYERS",
    "NetBoxManagementState",
    "NetBoxManagementWorkflow",
    "QueryDiagnosticState",
    "QueryDiagnosticWorkflow",
    "SupervisorDrivenState",
    "SupervisorDrivenWorkflow",
    "WorkflowMetadata",
    "WorkflowRegistry",
    "WorkflowType",
    "create_supervisor_driven_workflow",
]
