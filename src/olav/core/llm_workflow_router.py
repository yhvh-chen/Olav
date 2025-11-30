"""
LLM-based Workflow Router.

Replaces hardcoded keyword matching with LLM structured output for
more dynamic, context-aware workflow classification.

This module is part of the "Hardcoded → LLM" migration (Section 23.3.2 in CODE_AUDIT_REPORT.md).
"""

import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)


WorkflowCategory = Literal[
    "query_diagnostic",
    "device_execution",
    "netbox_management",
    "inspection",
    "deep_dive",
]


class WorkflowRouteResult(BaseModel):
    """Structured output for workflow routing decision.

    Attributes:
        workflow: The selected workflow type
        confidence: Confidence score (0.0-1.0)
        reasoning: Explanation for the routing decision
        requires_expert_mode: Whether this query requires expert mode (for deep_dive)
    """

    workflow: WorkflowCategory
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    reasoning: str = Field(description="Explanation for routing decision")
    requires_expert_mode: bool = Field(
        default=False,
        description="True if query requires expert mode (complex audit, batch operations)",
    )


class LLMWorkflowRouter:
    """LLM-based workflow router with structured output.

    Uses Pydantic structured output for reliable classification without
    hardcoded keyword matching.

    Example:
        router = LLMWorkflowRouter(expert_mode=True)
        result = await router.route("审计所有边界路由器的 BGP 配置")
        # result.workflow = "deep_dive"
        # result.confidence = 0.95
        # result.requires_expert_mode = True
    """

    DEFAULT_WORKFLOW = "query_diagnostic"
    DEFAULT_CONFIDENCE = 0.5

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        expert_mode: bool = False,
    ) -> None:
        """Initialize the workflow router.

        Args:
            llm: Language model to use. If None, uses LLMFactory.
            expert_mode: Whether expert mode (deep_dive) is enabled.
        """
        self._llm = llm
        self._structured_llm: BaseChatModel | None = None
        self.expert_mode = expert_mode
        self._prompt: str | None = None

    @property
    def llm(self) -> BaseChatModel:
        """Lazy-load LLM instance."""
        if self._llm is None:
            self._llm = LLMFactory.get_chat_model(json_mode=True)
        return self._llm

    @property
    def structured_llm(self) -> BaseChatModel:
        """LLM with structured output for WorkflowRouteResult."""
        if self._structured_llm is None:
            self._structured_llm = self.llm.with_structured_output(WorkflowRouteResult)
        return self._structured_llm

    @property
    def system_prompt(self) -> str:
        """Load system prompt from prompt manager (cached)."""
        if self._prompt is None:
            try:
                self._prompt = prompt_manager.load_prompt(
                    "core",
                    "workflow_routing",
                    expert_mode_enabled=str(self.expert_mode),
                )
            except Exception as e:
                logger.warning(f"Failed to load workflow routing prompt: {e}, using fallback")
                self._prompt = self._fallback_prompt()
        return self._prompt

    def _fallback_prompt(self) -> str:
        """Fallback prompt when prompt manager fails."""
        expert_section = (
            """
  5. **deep_dive** (仅专家模式): 复杂多步骤任务
     - 场景: 批量审计、跨设备故障排查、配置完整性检查
     - 关键词: 审计所有、批量、为什么无法访问、多台设备
     - 特点: 递归调查、自动任务分解

"""
            if self.expert_mode
            else ""
        )

        return f"""你是 OLAV 工作流编排器。根据用户查询，选择最合适的工作流。

## 工作流类型

  1. **query_diagnostic**: 网络状态查询和故障诊断
     - 场景: BGP/OSPF 状态查询、接口状态、路由表、邻居关系
     - 关键词: 查询、显示、状态、性能分析
     - 工具: SuzieQ (宏观分析)

  2. **device_execution**: 设备配置变更
     - 场景: VLAN 配置、接口启停、路由配置变更
     - 关键词: 配置、修改、添加、删除、shutdown
     - 工具: NETCONF/CLI
     - ⚠️ 需要 HITL 审批

  3. **netbox_management**: NetBox SSOT 管理
     - 场景: 设备清单、IP 分配、站点/机架管理
     - 关键词: 设备清单、添加设备、IP 地址、站点
     - 工具: NetBox API
     - ⚠️ 需要 HITL 审批

  4. **inspection**: 网络巡检和状态同步
     - 场景: NetBox 同步、配置差异检测、健康检查
     - 关键词: 巡检、同步、对比、diff、健康检查
     - 工具: SuzieQ + NetBox 对比
{expert_section}
## 分类规则

- 优先匹配最具体的工作流
- "同步" + "NetBox/网络" = inspection (不是 netbox_management)
- 涉及配置变更 = device_execution
- 纯查询/诊断 = query_diagnostic
- 批量操作/复杂排查 = deep_dive (需专家模式)

## 输出

返回 JSON 包含 workflow、confidence、reasoning、requires_expert_mode。
"""

    async def route(self, query: str) -> WorkflowRouteResult:
        """Route query to appropriate workflow using LLM.

        Args:
            query: User's natural language query

        Returns:
            WorkflowRouteResult with workflow type and confidence
        """
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=query),
            ]

            result = await self.structured_llm.ainvoke(messages)

            # Handle both Pydantic model and dict responses
            if isinstance(result, WorkflowRouteResult):
                route_result = result
            elif isinstance(result, dict):
                route_result = WorkflowRouteResult(**result)
            else:
                logger.warning(f"Unexpected result type: {type(result)}, using fallback")
                return self._fallback_route(query)

            # Validate expert mode requirement
            if route_result.workflow == "deep_dive" and not self.expert_mode:
                logger.info(
                    "Deep dive requested but expert mode disabled, falling back to query_diagnostic"
                )
                return WorkflowRouteResult(
                    workflow="query_diagnostic",
                    confidence=route_result.confidence * 0.7,
                    reasoning=f"Deep dive not available (expert mode disabled): {route_result.reasoning}",
                    requires_expert_mode=True,
                )

            logger.info(
                f"Workflow routed to '{route_result.workflow}' "
                f"(confidence: {route_result.confidence:.2f})"
            )
            return route_result

        except Exception as e:
            logger.warning(f"LLM workflow routing failed: {e}, using fallback")
            return self._fallback_route(query)

    def _fallback_route(self, query: str) -> WorkflowRouteResult:
        """Minimal keyword fallback when LLM fails.

        Uses reduced keyword set for reliability.
        """
        query_lower = query.lower()

        # Priority 1: Deep Dive (expert mode only)
        if self.expert_mode:
            if any(kw in query_lower for kw in ["审计", "audit", "批量", "为什么"]):
                return WorkflowRouteResult(
                    workflow="deep_dive",
                    confidence=0.7,
                    reasoning="Fallback: Deep dive keywords detected",
                    requires_expert_mode=True,
                )

        # Priority 2: Inspection (sync/diff)
        if any(kw in query_lower for kw in ["巡检", "同步", "sync", "对比", "diff"]):
            return WorkflowRouteResult(
                workflow="inspection",
                confidence=0.7,
                reasoning="Fallback: Inspection keywords detected",
            )

        # Priority 3: NetBox management
        if any(kw in query_lower for kw in ["设备清单", "inventory", "netbox", "ip分配"]):
            return WorkflowRouteResult(
                workflow="netbox_management",
                confidence=0.7,
                reasoning="Fallback: NetBox management keywords detected",
            )

        # Priority 4: Device execution (config changes)
        if any(kw in query_lower for kw in ["配置", "修改", "添加", "删除", "shutdown"]):
            return WorkflowRouteResult(
                workflow="device_execution",
                confidence=0.7,
                reasoning="Fallback: Configuration change keywords detected",
            )

        # Default: Query diagnostic
        return WorkflowRouteResult(
            workflow="query_diagnostic",
            confidence=0.5,
            reasoning="Fallback: Default to query/diagnostic",
        )


# Singleton instance
_router: LLMWorkflowRouter | None = None


def get_workflow_router(expert_mode: bool = False) -> LLMWorkflowRouter:
    """Get singleton workflow router instance.

    Args:
        expert_mode: Whether expert mode (deep_dive) is enabled.

    Returns:
        LLMWorkflowRouter instance
    """
    global _router
    if _router is None or _router.expert_mode != expert_mode:
        _router = LLMWorkflowRouter(expert_mode=expert_mode)
    return _router


async def route_workflow(query: str, expert_mode: bool = False) -> WorkflowRouteResult:
    """Convenience function for workflow routing.

    Args:
        query: User's natural language query
        expert_mode: Whether expert mode is enabled

    Returns:
        WorkflowRouteResult with routing decision
    """
    router = get_workflow_router(expert_mode=expert_mode)
    return await router.route(query)
