"""Base workflow protocol for OLAV agent workflows.

All workflow implementations should inherit from BaseWorkflow to ensure
consistent interface and integration with LangGraph StateGraph.
"""

from abc import ABC, abstractmethod
from typing import Any, TypedDict, Annotated
from enum import Enum

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, add_messages


class WorkflowType(str, Enum):
    """Supported workflow types."""
    QUERY_DIAGNOSTIC = "query_diagnostic"  # 查询/诊断（SuzieQ + NETCONF）
    DEVICE_EXECUTION = "device_execution"  # 设备配置变更（NETCONF/CLI + HITL）
    NETBOX_MANAGEMENT = "netbox_management"  # NetBox 管理（设备清单/IP/站点）
    DEEP_DIVE = "deep_dive"  # Deep Dive（复杂多步任务，需 -e/--expert）


class BaseWorkflowState(TypedDict):
    """Base state shared across all workflows."""
    messages: Annotated[list[BaseMessage], add_messages]
    workflow_type: WorkflowType | None  # 当前工作流类型
    iteration_count: int  # 迭代计数
    error: str | None  # 错误信息（如果有）


class BaseWorkflow(ABC):
    """Abstract base class for all OLAV workflows.
    
    Each workflow defines:
    1. State schema (extending BaseWorkflowState)
    2. Node functions (async callables)
    3. Graph structure (nodes + edges)
    4. Tools used in this workflow
    
    Usage:
        workflow = QueryDiagnosticWorkflow()
        graph = workflow.build_graph(checkpointer)
        result = await graph.ainvoke({"messages": [...]}, config)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Workflow name for logging and identification."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of workflow purpose."""
        pass
    
    @property
    @abstractmethod
    def tools_required(self) -> list[str]:
        """List of tool names required by this workflow.
        
        Returns:
            List of tool identifiers, e.g., ["suzieq_query", "netconf_tool"]
        """
        pass
    
    @abstractmethod
    def build_graph(self, checkpointer: Any) -> StateGraph:
        """Build LangGraph StateGraph for this workflow.
        
        Args:
            checkpointer: PostgreSQL checkpointer for state persistence
            
        Returns:
            Compiled StateGraph ready for execution
        """
        pass
    
    @abstractmethod
    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Validate if user query is suitable for this workflow.
        
        Args:
            user_query: Raw user input
            
        Returns:
            Tuple of (is_valid, reason)
            - is_valid: True if query matches workflow scope
            - reason: Explanation if invalid
        """
        pass


__all__ = ["BaseWorkflow", "BaseWorkflowState", "WorkflowType"]
