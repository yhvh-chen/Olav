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
from olav.tools.nornir_tool import device_config
from olav.tools.opensearch_tool import search_episodic_memory, search_openconfig_schema
from olav.tools.suzieq_parquet_tool import suzieq_query

from .base import BaseWorkflow, BaseWorkflowState
from .registry import WorkflowRegistry


class DeviceExecutionState(BaseWorkflowState):
    """State for device execution workflow."""

    config_plan: dict | None  # Change plan
    approval_status: str | None  # pending/approved/rejected
    execution_result: dict | None  # Execution result
    validation_result: dict | None  # Validation result


@WorkflowRegistry.register(
    name="device_execution",
    description="Device configuration change execution (Planning → HITL → Execution → Validation)",
    examples=[
        "Modify R1 BGP AS number to 65001",
        "Configure VLAN 100 on Switch-A interface Gi0/1",
        "Shutdown interface Ethernet1 on device R2",
        "Set MTU to 9000 on all interfaces",
        "Add static route to 10.0.0.0/8",
        "Configure OSPF area 0",
        "Modify device description",
    ],
    triggers=[
        # English patterns - LLM handles multilingual intent classification
        r"modify",
        r"configure",
        r"set",
        r"add",
        r"delete",
        r"shutdown",
        r"no shutdown",
        r"change",
        r"remove",
    ],
)
class DeviceExecutionWorkflow(BaseWorkflow):
    """Device configuration change workflow with HITL approval."""

    @property
    def name(self) -> str:
        return "device_execution"

    @property
    def description(self) -> str:
        return "Device configuration change execution (Planning → HITL → Execution → Validation)"

    @property
    def tools_required(self) -> list[str]:
        return [
            "search_episodic_memory",  # Historical success cases
            "search_openconfig_schema",  # XPath confirmation
            "device_config",  # Unified config tool (auto-routes to NETCONF/CLI)
            "suzieq_query",  # Post-change validation
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if request is a configuration change."""
        query_lower = user_query.lower()

        # Exclude NetBox management keywords (higher priority)
        netbox_keywords = [
            # English keywords for NetBox operations
            "inventory",
            "device list",
            "add device",
            "ip assignment",
            "ip address",
            "site",
            "rack",
            "netbox",
        ]
        if any(kw in query_lower for kw in netbox_keywords):
            return False, "NetBox management request, should use netbox_management workflow"

        # Config change keywords (comprehensive)
        change_keywords = [
            # English keywords for config changes
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
            "delete",  # Added: delete operations
            "add",     # Added: add operations
            "remove",
            "vlan",
            "area",
            "enable",
            "disable",
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
        ]
        planning_tools_node = ToolNode(planning_tools)

        # Execution phase tools: Unified device_config (auto-routes to NETCONF/CLI)
        execution_tools = [device_config]
        execution_tools_node = ToolNode(execution_tools)

        # Validation phase tools: Verify config was applied
        validation_tools = [suzieq_query]
        validation_tools_node = ToolNode(validation_tools)

        async def config_planning_node(state: DeviceExecutionState) -> DeviceExecutionState:
            """Generate detailed change plan with rollback strategy."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools(planning_tools)

            # Debug: Show how many messages are in state
            msg_count = len(state["messages"])
            print(f"[config_planning_node] Received {msg_count} messages in state")
            for i, msg in enumerate(state["messages"]):
                msg_type = type(msg).__name__
                content_preview = msg.content[:100].replace('\n', ' ') if hasattr(msg, 'content') else "N/A"
                print(f"  [{i}] {msg_type}: {content_preview}...")

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

            from config.settings import settings
            from langgraph.types import interrupt

            logger = logging.getLogger(__name__)
            user_approval = state.get("approval_status")

            # YOLO mode: auto-approve
            if settings.yolo_mode and user_approval is None:
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
                    "message": f"Please approve device configuration change:\nPlan: {config_plan}\n\nEnter Y to confirm, N to cancel:",
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

            final_prompt = f"""Summarize the execution results and provide a final answer.

User Request: {state["messages"][0].content}
Change Plan: {state.get("config_plan")}
Approval Status: {state.get("approval_status")}
Execution Result: {state.get("execution_result")}
Validation Result: {state.get("validation_result")}

Requirements:
- If rejected, explain the reason
- If executed, summarize affected devices, configuration items, and validation status
- If validation failed, provide rollback recommendations
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
        from config.settings import settings

        if settings.yolo_mode:
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
