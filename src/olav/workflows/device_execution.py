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
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.nornir_tool import cli_tool, netconf_tool
from olav.tools.opensearch_tool import search_episodic_memory, search_openconfig_schema
from olav.tools.suzieq_parquet_tool import suzieq_query

from .base import BaseWorkflow, BaseWorkflowState
from .registry import WorkflowRegistry


class DeviceExecutionState(BaseWorkflowState):
    """State for device execution workflow."""

    config_plan: dict | None  # 变更计划
    approval_status: str | None  # pending/approved/rejected
    execution_result: dict | None  # 执行结果
    validation_result: dict | None  # 验证结果


@WorkflowRegistry.register(
    name="device_execution",
    description="设备配置变更执行（Planning → HITL → Execution → Validation）",
    examples=[
        "修改 R1 的 BGP AS 号为 65001",
        "在 Switch-A 接口 Gi0/1 上配置 VLAN 100",
        "关闭设备 R2 的接口 Ethernet1",
        "设置所有接口 MTU 为 9000",
        "添加静态路由到 10.0.0.0/8",
        "配置 OSPF area 0",
        "修改设备描述信息",
    ],
    triggers=[
        r"修改",
        r"配置",
        r"设置",
        r"添加",
        r"删除",
        r"shutdown",
        r"no shutdown",
        r"change",
        r"configure",
    ],
)
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
            "设备清单",
            "添加设备",
            "ip分配",
            "ip地址",
            "站点",
            "机架",
            "inventory",
            "device list",
            "add device",
            "ip assignment",
            "site",
            "rack",
            "netbox",
        ]
        if any(kw in query_lower for kw in netbox_keywords):
            return False, "NetBox management request, should use netbox_management workflow"

        # Config change keywords (more comprehensive)
        change_keywords = [
            "修改",
            "配置",
            "设置",
            "添加vlan",
            "删除",
            "shutdown",
            "no shutdown",
            "change",
            "modify",
            "set",
            "configure",
            "config",
            "edit",
            "commit",
            "rollback",
            "create",
            "remove",
            "vlan",
            "area",
            "启用",
            "禁用",
        ]

        if any(kw in query_lower for kw in change_keywords):
            return True, "Matches device configuration change scenario"

        return False, "Not a config change request"

    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        """Build device execution workflow graph with proper tool loops."""

        # Define tool nodes for each phase
        # Planning phase tools: Schema search + memory + device discovery for plan generation
        planning_tools = [
            suzieq_query,  # CRITICAL: For device discovery when "all devices" is requested
            search_episodic_memory,
            search_openconfig_schema,
            netconf_tool,  # get-config to retrieve current state
        ]
        planning_tools_node = ToolNode(planning_tools)

        # Execution phase tools: NETCONF/CLI for actual config changes
        execution_tools = [netconf_tool, cli_tool]
        execution_tools_node = ToolNode(execution_tools)

        # Validation phase tools: Verify config was applied
        validation_tools = [suzieq_query, netconf_tool, cli_tool]
        validation_tools_node = ToolNode(validation_tools)

        async def config_planning_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Generate detailed change plan with rollback strategy."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(planning_tools)

            user_query = state["messages"][-1].content
            planning_prompt = prompt_manager.load_prompt(
                "workflows/device_execution", "config_planning", user_query=user_query
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=planning_prompt), *state["messages"]]
            )

            return {
                **state,
                "messages": state["messages"] + [response],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def plan_summary_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Extract structured plan from planning phase for HITL review."""
            # Get the last message from planning phase
            last_message = state["messages"][-1]
            plan_content = last_message.content if hasattr(last_message, "content") else ""

            config_plan = {"plan": plan_content}

            return {
                **state,
                "config_plan": config_plan,
            }

        async def hitl_approval_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """HITL approval - LangGraph interrupt point.

            Uses LangGraph interrupt to pause and wait for user approval.
            When workflow resumes, approval_response contains user decision.
            """
            import logging

            from config.settings import AgentConfig
            from langgraph.types import interrupt

            logger = logging.getLogger(__name__)
            user_approval = state.get("approval_status")

            # YOLO mode: auto-approve
            if AgentConfig.YOLO_MODE and user_approval is None:
                logger.info("[YOLO] Auto-approving device execution...")
                return {
                    **state,
                    "approval_status": "approved",
                }

            # Already processed (resuming after interrupt)
            if user_approval in ("approved", "rejected"):
                return {
                    **state,
                    "approval_status": user_approval,
                }

            # HITL: Request user approval via interrupt
            config_plan = state.get("config_plan", {})

            approval_response = interrupt(
                {
                    "action": "approval_required",
                    "config_plan": config_plan,
                    "message": f"请审批设备配置变更:\n计划: {config_plan}\n\n输入 Y 确认, N 取消:",
                }
            )

            # Process approval response
            if isinstance(approval_response, dict):
                if (
                    approval_response.get("approved")
                    or approval_response.get("user_approval") == "approved"
                ):
                    return {
                        **state,
                        "approval_status": "approved",
                    }
                return {
                    **state,
                    "approval_status": "rejected",
                }
            # String response (Y/N) - treat as approved if truthy
            return {
                **state,
                "approval_status": "approved" if approval_response else "rejected",
            }

        async def config_execution_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Execute configuration changes (NETCONF preferred)."""
            if state.get("approval_status") != "approved":
                return {
                    **state,
                    "execution_result": {
                        "status": "rejected",
                        "message": "User rejected the change",
                    },
                }

            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(execution_tools)

            config_plan = state.get("config_plan", {})
            execution_prompt = prompt_manager.load_prompt(
                "workflows/device_execution", "config_execution", config_plan=str(config_plan)
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=execution_prompt), *state["messages"]]
            )

            return {
                **state,
                "messages": state["messages"] + [response],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def execution_summary_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Extract execution result after tool loop completes."""
            last_message = state["messages"][-1]
            result_content = last_message.content if hasattr(last_message, "content") else ""

            execution_result = {"result": result_content}

            return {
                **state,
                "execution_result": execution_result,
            }

        async def validation_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Validate configuration changes."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(validation_tools)

            config_plan = state.get("config_plan", {})
            execution_result = state.get("execution_result", {})
            validation_prompt = prompt_manager.load_prompt(
                "workflows/device_execution",
                "validation",
                config_plan=str(config_plan),
                execution_result=str(execution_result),
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=validation_prompt), *state["messages"]]
            )

            return {
                **state,
                "messages": state["messages"] + [response],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def validation_summary_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Extract validation result after tool loop completes."""
            last_message = state["messages"][-1]
            result_content = last_message.content if hasattr(last_message, "content") else ""

            validation_result = {"result": result_content}

            return {
                **state,
                "validation_result": validation_result,
            }

        async def final_answer_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Generate final answer with execution summary."""
            llm = LLMFactory.get_chat_model()

            final_prompt = f"""综合执行结果，给出最终答案。

用户请求: {state["messages"][0].content}
变更计划: {state.get("config_plan")}
审批状态: {state.get("approval_status")}
执行结果: {state.get("execution_result")}
验证结果: {state.get("validation_result")}

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

        def route_after_approval(
            state: DeviceExecutionState,
        ) -> Literal["config_execution", "final_answer"]:
            """Route based on approval decision."""
            if state.get("approval_status") == "approved":
                return "config_execution"
            return "final_answer"

        # Build graph with proper tool loops
        workflow = StateGraph(DeviceExecutionState)

        # Add all nodes
        workflow.add_node("config_planning", config_planning_node)
        workflow.add_node("planning_tools", planning_tools_node)
        workflow.add_node("plan_summary", plan_summary_node)
        workflow.add_node("hitl_approval", hitl_approval_node)
        workflow.add_node("config_execution", config_execution_node)
        workflow.add_node("execution_tools", execution_tools_node)
        workflow.add_node("execution_summary", execution_summary_node)
        workflow.add_node("validation", validation_node)
        workflow.add_node("validation_tools", validation_tools_node)
        workflow.add_node("validation_summary", validation_summary_node)
        workflow.add_node("final_answer", final_answer_node)

        # Set entry point
        workflow.set_entry_point("config_planning")

        # Planning phase: Agent Loop (planning <-> planning_tools)
        workflow.add_conditional_edges(
            "config_planning",
            tools_condition,
            {"tools": "planning_tools", "__end__": "plan_summary"},
        )
        workflow.add_edge("planning_tools", "config_planning")

        # After plan summary -> HITL approval
        workflow.add_edge("plan_summary", "hitl_approval")

        # After approval -> route to execution or final answer
        workflow.add_conditional_edges(
            "hitl_approval",
            route_after_approval,
            {
                "config_execution": "config_execution",
                "final_answer": "final_answer",
            },
        )

        # Execution phase: Agent Loop (execution <-> execution_tools)
        workflow.add_conditional_edges(
            "config_execution",
            tools_condition,
            {"tools": "execution_tools", "__end__": "execution_summary"},
        )
        workflow.add_edge("execution_tools", "config_execution")

        # After execution summary -> validation
        workflow.add_edge("execution_summary", "validation")

        # Validation phase: Agent Loop (validation <-> validation_tools)
        workflow.add_conditional_edges(
            "validation",
            tools_condition,
            {"tools": "validation_tools", "__end__": "validation_summary"},
        )
        workflow.add_edge("validation_tools", "validation")

        # After validation summary -> final answer
        workflow.add_edge("validation_summary", "final_answer")

        workflow.add_edge("final_answer", END)

        # Compile with interrupt before approval (only if not YOLO mode)
        from config.settings import AgentConfig

        if AgentConfig.YOLO_MODE:
            # YOLO mode: no interrupts, auto-approve in hitl_approval_node
            return workflow.compile(
                checkpointer=checkpointer,
            )
        # Normal mode: interrupt before approval for user review
        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["hitl_approval"],
        )


__all__ = ["DeviceExecutionState", "DeviceExecutionWorkflow"]
