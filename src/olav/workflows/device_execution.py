"""Device Execution Workflow (Configuration Changes).

Scope:
- Network device configuration changes (BGP AS, interface config, routing policy, etc.)
- NETCONF/CLI write operations with HITL approval
- Post-change validation

Tool Chain:
- OpenSearch (schema/memory for change plan)
- NETCONF (preferred, atomic commit)
- CLI (fallback, no atomic rollback)
- SuzieQ (post-change validation)

Workflow:
    User Request
    ↓
    [Config Planning] → Generate change plan + rollback strategy
    ↓
    [HITL Approval] → Human review (interrupt point)
    ├─ Approved → [Config Execution] → NETCONF/CLI edit-config
    │                    ↓
    │              [Validation] → Verify config applied
    │                    ↓
    │              [Final Answer]
    │
    └─ Rejected → [Final Answer] (abort)
"""

import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Literal
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.suzieq_parquet_tool import suzieq_query
from olav.tools.opensearch_tool import search_episodic_memory, search_openconfig_schema
from olav.tools.nornir_tool import cli_tool, netconf_tool

from .base import BaseWorkflow, BaseWorkflowState


class DeviceExecutionState(BaseWorkflowState):
    """State for device execution workflow."""
    config_plan: dict | None  # 变更计划
    approval_status: str | None  # pending/approved/rejected
    execution_result: dict | None  # 执行结果
    validation_result: dict | None  # 验证结果


class DeviceExecutionWorkflow(BaseWorkflow):
    """Device configuration change workflow with HITL approval."""
    
    @property
    def name(self) -> str:
        return "device_execution"
    
    @property
    def description(self) -> str:
        return "设备配置变更执行（Planning → HITL → Execution → Validation）"
    
    @property
    def tools_required(self) -> list[str]:
        return [
            "search_episodic_memory",  # 历史成功案例
            "search_openconfig_schema",  # XPath 确认
            "netconf_tool",  # 主要执行方式（带 commit confirmed）
            "cli_tool",  # 降级方式（警告无自动回滚）
            "suzieq_query",  # 变更后验证
        ]
    
    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if request is a configuration change."""
        query_lower = user_query.lower()
        
        # 排除 NetBox 管理关键词（优先级高）
        netbox_keywords = [
            "设备清单", "添加设备", "ip分配", "ip地址", "站点", "机架",
            "inventory", "device list", "add device", "ip assignment",
            "site", "rack", "netbox"
        ]
        if any(kw in query_lower for kw in netbox_keywords):
            return False, "NetBox 管理请求，应使用 netbox_management workflow"
        
        # 配置变更关键词（更全面）
        change_keywords = [
            "修改", "配置", "设置", "添加vlan", "删除", "shutdown", "no shutdown",
            "change", "modify", "set", "configure", "config", "edit",
            "commit", "rollback", "create", "remove", "vlan", "area", "启用", "禁用"
        ]
        
        if any(kw in query_lower for kw in change_keywords):
            return True, "匹配设备配置变更场景"
        
        return False, "非配置变更请求"
    
    def build_graph(self, checkpointer) -> StateGraph:
        """Build device execution workflow graph."""
        
        async def config_planning_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Generate detailed change plan with rollback strategy."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([
                search_episodic_memory,
                search_openconfig_schema,
                netconf_tool,  # get-config to retrieve current state
            ])
            
            user_query = state["messages"][-1].content
            planning_prompt = prompt_manager.load_prompt(
                "workflows/device_execution",
                "config_planning",
                user_query=user_query
            )
            
            response = await llm_with_tools.ainvoke([
                SystemMessage(content=planning_prompt),
                *state["messages"]
            ])
            
            # TODO: Parse structured plan from response
            config_plan = {"plan": response.content}
            
            return {
                **state,
                "config_plan": config_plan,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }
        
        async def hitl_approval_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """HITL approval - LangGraph interrupt point."""
            # When resumed, approval_status should be set by user via state update
            approval_status = state.get("approval_status", "pending")
            
            return {
                **state,
                "approval_status": approval_status,
            }
        
        async def config_execution_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Execute configuration changes (NETCONF preferred)."""
            if state.get("approval_status") != "approved":
                return {
                    **state,
                    "execution_result": {
                        "status": "rejected",
                        "message": "User rejected the change"
                    },
                }
            
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([netconf_tool, cli_tool])
            
            config_plan = state.get("config_plan", {})
            execution_prompt = prompt_manager.load_prompt(
                "workflows/device_execution",
                "config_execution",
                config_plan=str(config_plan)
            )
            
            response = await llm_with_tools.ainvoke([
                SystemMessage(content=execution_prompt),
                *state["messages"]
            ])
            
            execution_result = {"result": response.content}
            
            return {
                **state,
                "execution_result": execution_result,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }
        
        async def validation_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Validate configuration changes."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([suzieq_query, netconf_tool, cli_tool])
            
            config_plan = state.get("config_plan", {})
            execution_result = state.get("execution_result", {})
            validation_prompt = prompt_manager.load_prompt(
                "workflows/device_execution",
                "validation",
                config_plan=str(config_plan),
                execution_result=str(execution_result)
            )
            
            response = await llm_with_tools.ainvoke([
                SystemMessage(content=validation_prompt),
                *state["messages"]
            ])
            
            validation_result = {"result": response.content}
            
            return {
                **state,
                "validation_result": validation_result,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }
        
        async def final_answer_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Generate final answer with execution summary."""
            llm = LLMFactory.get_chat_model()
            
            final_prompt = f"""综合执行结果，给出最终答案。

用户请求: {state['messages'][0].content}
变更计划: {state.get('config_plan')}
审批状态: {state.get('approval_status')}
执行结果: {state.get('execution_result')}
验证结果: {state.get('validation_result')}

要求：
- 如果被拒绝，说明原因
- 如果已执行，汇总影响设备、配置项、验证状态
- 如果验证失败，提供回滚建议
"""
            
            response = await llm.ainvoke([SystemMessage(content=final_prompt)])
            
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response.content)],
            }
        
        def route_after_approval(state: DeviceExecutionState) -> Literal["config_execution", "final_answer"]:
            """Route based on approval decision."""
            if state.get("approval_status") == "approved":
                return "config_execution"
            return "final_answer"
        
        # Build graph
        workflow = StateGraph(DeviceExecutionState)
        
        workflow.add_node("config_planning", config_planning_node)
        workflow.add_node("hitl_approval", hitl_approval_node)
        workflow.add_node("config_execution", config_execution_node)
        workflow.add_node("validation", validation_node)
        workflow.add_node("final_answer", final_answer_node)
        
        workflow.set_entry_point("config_planning")
        workflow.add_edge("config_planning", "hitl_approval")
        workflow.add_conditional_edges(
            "hitl_approval",
            route_after_approval,
            {
                "config_execution": "config_execution",
                "final_answer": "final_answer",
            }
        )
        workflow.add_edge("config_execution", "validation")
        workflow.add_edge("validation", "final_answer")
        workflow.add_edge("final_answer", END)
        
        # Compile with interrupt before approval
        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["hitl_approval"],
        )


__all__ = ["DeviceExecutionWorkflow", "DeviceExecutionState"]
