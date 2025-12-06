"""NetBox Management Workflow.

Scope:
- Device inventory management (add/update/delete devices)
- IP address assignment and planning
- Site/rack/cable management
- Configuration context management

Tool Chain:
- NetBox API (CRUD operations via netbox_api_call)
- NetBox Schema Search (discover API endpoints)
- OpenSearch (episodic memory for similar operations)

Workflow:
    User Request
    ↓
    [Schema Discovery] → Find API endpoint + required fields
    ↓
    [Operation Planning] → Generate API payload
    ↓
    [HITL Approval] → Human review (for write operations)
    ├─ Approved → [API Execution] → netbox_api_call
    │                    ↓
    │              [Verification] → Confirm operation succeeded
    │                    ↓
    │              [Final Answer]
    │
    └─ Rejected → [Final Answer] (abort)
"""

import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.netbox_tool import netbox_api_call, netbox_schema_search
from olav.tools.opensearch_tool import search_episodic_memory

from .base import BaseWorkflow, BaseWorkflowState
from .registry import WorkflowRegistry


class NetBoxManagementState(BaseWorkflowState):
    """State for NetBox management workflow."""

    api_endpoint: str | None  # API endpoint (e.g., /dcim/devices/)
    operation_plan: dict | None  # API 操作计划（method, payload）
    approval_status: str | None  # pending/approved/rejected
    execution_result: dict | None  # API 执行结果
    verification_result: dict | None  # 验证结果


@WorkflowRegistry.register(
    name="netbox_management",
    description="NetBox 管理操作（设备清单/IP/站点/机架）",
    examples=[
        "在 NetBox 中添加新设备 Switch-C",
        "更新设备 R1 的管理 IP 为 192.168.1.10",
        "查询 NetBox 中的所有核心路由器",
        "删除 NetBox 设备记录 Old-Switch",
        "添加新站点 Beijing-IDC",
        "分配 IP 地址给设备接口",
        "更新设备角色为 core",
    ],
    triggers=[r"NetBox", r"清单", r"inventory", r"站点", r"site", r"机架", r"rack", r"IP.*地址"],
)
class NetBoxManagementWorkflow(BaseWorkflow):
    """NetBox inventory and management workflow."""

    @property
    def name(self) -> str:
        return "netbox_management"

    @property
    def description(self) -> str:
        return "NetBox 管理操作（设备清单/IP/站点/机架）"

    @property
    def tools_required(self) -> list[str]:
        return [
            "netbox_schema_search",  # 发现 API 端点
            "netbox_api_call",  # 执行 CRUD 操作
            "search_episodic_memory",  # 历史成功操作
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if request is NetBox management."""
        query_lower = user_query.lower()

        # NetBox 管理关键词
        netbox_keywords = [
            "设备清单",
            "添加设备",
            "ip分配",
            "ip地址",
            "站点",
            "机架",
            "电缆",
            "inventory",
            "device list",
            "add device",
            "ip assignment",
            "site",
            "rack",
            "cable",
            "netbox",
        ]

        if any(kw in query_lower for kw in netbox_keywords):
            return True, "匹配 NetBox 管理场景"

        # 检查是否包含 NetBox 实体类型
        entity_types = [
            "device",
            "interface",
            "ip-address",
            "site",
            "rack",
            "cable",
            "virtual-machine",
        ]
        if any(entity in query_lower for entity in entity_types):
            return True, "Contains NetBox entity type"

        return False, "Not a NetBox management request"

    def build_graph(self, checkpointer: BaseCheckpointSaver) -> StateGraph:
        """Build NetBox management workflow graph."""

        async def schema_discovery_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Discover API endpoint and required fields."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([netbox_schema_search])

            user_query = state["messages"][-1].content
            schema_discovery_prompt = prompt_manager.load_prompt(
                "workflows/netbox_management", "schema_discovery", user_query=user_query
            )
            discovery_prompt = schema_discovery_prompt.format(user_query=user_query)

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=discovery_prompt), *state["messages"]]
            )

            # TODO: Parse API endpoint from response
            api_endpoint = "/dcim/devices/"  # Placeholder

            return {
                **state,
                "api_endpoint": api_endpoint,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def operation_planning_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Generate API operation plan (method + payload)."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([search_episodic_memory, netbox_api_call])

            user_query = state["messages"][0].content
            api_endpoint = state.get("api_endpoint", "")
            plan_prompt = prompt_manager.load_prompt(
                "workflows/netbox_management",
                "operation_planning",
                user_query=user_query,
                api_endpoint=api_endpoint,
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=plan_prompt), *state["messages"]]
            )

            # TODO: Parse operation plan (method, payload)
            operation_plan = {"plan": response.content}

            return {
                **state,
                "operation_plan": operation_plan,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def hitl_approval_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """HITL approval for write operations.

            Uses LangGraph interrupt to pause and wait for user approval.
            When workflow resumes, approval_response contains user decision.
            """
            from config.settings import AgentConfig
            from langgraph.types import interrupt

            user_approval = state.get("approval_status")

            # YOLO mode: auto-approve
            if AgentConfig.YOLO_MODE and user_approval is None:
                logger.info("[YOLO] Auto-approving NetBox operation...")
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
            operation_plan = state.get("operation_plan", {})
            api_endpoint = state.get("api_endpoint", "")

            approval_response = interrupt(
                {
                    "action": "approval_required",
                    "api_endpoint": api_endpoint,
                    "operation_plan": operation_plan,
                    "message": f"Please approve NetBox operation:\nEndpoint: {api_endpoint}\nPlan: {operation_plan}\n\nEnter Y to confirm, N to cancel:",
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

        async def api_execution_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Execute NetBox API operation."""
            if state.get("approval_status") != "approved":
                return {
                    **state,
                    "execution_result": {
                        "status": "rejected",
                        "message": "User rejected the operation",
                    },
                }

            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([netbox_api_call])

            operation_plan = state.get("operation_plan", {})

            execution_prompt = f"""执行 NetBox API 操作。

操作计划: {operation_plan}

使用 netbox_api_call 执行 API 调用。
"""

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=execution_prompt), *state["messages"]]
            )

            execution_result = {"result": response.content}

            return {
                **state,
                "execution_result": execution_result,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def verification_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Verify API operation succeeded."""
            llm = LLMFactory.get_chat_model()
            llm_with_tools = llm.bind_tools([netbox_api_call])

            operation_plan = state.get("operation_plan", {})
            execution_result = state.get("execution_result", {})
            verify_prompt = prompt_manager.load_prompt(
                "workflows/netbox_management",
                "verification",
                operation_plan=str(operation_plan),
                execution_result=str(execution_result),
            )

            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=verify_prompt), *state["messages"]]
            )

            verification_result = {"result": response.content}

            return {
                **state,
                "verification_result": verification_result,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def final_answer_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Generate final answer with operation summary."""
            llm = LLMFactory.get_chat_model()

            final_prompt = f"""Synthesize operation results and provide final answer.

User request: {state["messages"][0].content}
API endpoint: {state.get("api_endpoint")}
Operation plan: {state.get("operation_plan")}
Approval status: {state.get("approval_status")}
Execution result: {state.get("execution_result")}
Verification result: {state.get("verification_result")}

Requirements:
- If rejected, explain reason
- If executed, summarize target objects, API response, verification status
"""

            response = await llm.ainvoke([SystemMessage(content=final_prompt)])

            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response.content)],
            }

        def route_after_planning(
            state: NetBoxManagementState,
        ) -> Literal["hitl_approval", "api_execution"]:
            """Route based on operation type (read vs write)."""
            # TODO: Detect if operation is read-only (GET) vs write (POST/PUT/DELETE)
            # For now, assume all operations need approval
            return "hitl_approval"

        def route_after_approval(
            state: NetBoxManagementState,
        ) -> Literal["api_execution", "final_answer"]:
            """Route based on approval decision."""
            if state.get("approval_status") == "approved":
                return "api_execution"
            return "final_answer"

        # Build graph
        workflow = StateGraph(NetBoxManagementState)

        workflow.add_node("schema_discovery", schema_discovery_node)
        workflow.add_node("operation_planning", operation_planning_node)
        workflow.add_node("hitl_approval", hitl_approval_node)
        workflow.add_node("api_execution", api_execution_node)
        workflow.add_node("verification", verification_node)
        workflow.add_node("final_answer", final_answer_node)

        workflow.set_entry_point("schema_discovery")
        workflow.add_edge("schema_discovery", "operation_planning")
        workflow.add_conditional_edges(
            "operation_planning",
            route_after_planning,
            {
                "hitl_approval": "hitl_approval",
                "api_execution": "api_execution",
            },
        )
        workflow.add_conditional_edges(
            "hitl_approval",
            route_after_approval,
            {
                "api_execution": "api_execution",
                "final_answer": "final_answer",
            },
        )
        workflow.add_edge("api_execution", "verification")
        workflow.add_edge("verification", "final_answer")
        workflow.add_edge("final_answer", END)

        # Compile with checkpointer
        # HITL is handled by interrupt() in hitl_approval_node
        return workflow.compile(
            checkpointer=checkpointer,
        )


__all__ = ["NetBoxManagementState", "NetBoxManagementWorkflow"]
