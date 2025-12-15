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

import json
import logging
import re
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
    api_method: str | None  # HTTP method (GET/POST/PUT/PATCH/DELETE)
    operation_plan: dict | None  # API operation plan (method, payload)
    approval_status: str | None  # pending/approved/rejected
    execution_result: dict | None  # API execution result
    verification_result: dict | None  # Verification result


_READ_ONLY_METHODS: set[str] = {"GET", "HEAD", "OPTIONS"}


def _extract_json_object_from_text(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from LLM text.

    The NetBox workflow prompts ask the model to output a JSON object inside a ```json code fence.
    We extract the *last* such object to reduce the chance of capturing an example block.
    """

    if not text:
        return None

    # Prefer fenced ```json blocks
    fenced = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[str] = []
    if fenced:
        candidates.extend(fenced)

    # Fallback: any fenced block
    if not candidates:
        any_fenced = re.findall(r"```\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        candidates.extend(any_fenced)

    # Last resort: first object-like span
    if not candidates:
        span = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if span:
            candidates.append(span.group(1))

    for blob in reversed(candidates):
        try:
            parsed = json.loads(blob)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


@WorkflowRegistry.register(
    name="netbox_management",
    description="NetBox management operations (device inventory/IP/site/rack)",
    examples=[
        "Add new device Switch-C in NetBox",
        "Update device R1 management IP to 192.168.1.10",
        "Query all core routers in NetBox",
        "Delete NetBox device record Old-Switch",
        "Add new site Beijing-IDC",
        "Assign IP address to device interface",
        "Update device role to core",
    ],
    triggers=[
        # English patterns - LLM handles multilingual intent classification
        r"NetBox",
        r"inventory",
        r"site",
        r"rack",
        r"IP.*address",
        r"device.*list",
        r"add.*device",
    ],
)
class NetBoxManagementWorkflow(BaseWorkflow):
    """NetBox inventory and management workflow."""

    @property
    def name(self) -> str:
        return "netbox_management"

    @property
    def description(self) -> str:
        return "NetBox management operations (device inventory/IP/site/rack)"

    @property
    def tools_required(self) -> list[str]:
        return [
            "netbox_schema_search",  # Discover API endpoints
            "netbox_api_call",  # Execute CRUD operations
            "search_episodic_memory",  # Historical success operations
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Check if request is NetBox management."""
        query_lower = user_query.lower()

        # NetBox management keywords
        netbox_keywords = [
            # English keywords for NetBox operations
            "inventory",
            "device list",
            "add device",
            "ip assignment",
            "ip address",
            "site",
            "rack",
            "cable",
            "netbox",
        ]

        if any(kw in query_lower for kw in netbox_keywords):
            return True, "Matched NetBox management scenario"

        # Check for NetBox entity types
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

            parsed_plan = _extract_json_object_from_text(response.content)
            operation_plan: dict
            api_method: str | None = None
            api_endpoint_override: str | None = None

            if isinstance(parsed_plan, dict):
                operation_plan = parsed_plan
                method_val = parsed_plan.get("method")
                if isinstance(method_val, str) and method_val.strip():
                    api_method = method_val.strip().upper()
                endpoint_val = parsed_plan.get("endpoint") or parsed_plan.get("api_endpoint")
                if isinstance(endpoint_val, str) and endpoint_val.strip():
                    api_endpoint_override = endpoint_val.strip()
            else:
                operation_plan = {"plan": response.content}

            # Read-only operations should not require HITL.
            approval_status = state.get("approval_status")
            if api_method in _READ_ONLY_METHODS and approval_status is None:
                approval_status = "approved"

            return {
                **state,
                "operation_plan": operation_plan,
                "api_method": api_method,
                "api_endpoint": api_endpoint_override or state.get("api_endpoint"),
                "approval_status": approval_status,
                "messages": state["messages"] + [AIMessage(content=response.content)],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def hitl_approval_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """HITL approval for write operations.

            Uses LangGraph interrupt to pause and wait for user approval.
            When workflow resumes, approval_response contains user decision.
            """
            from config.settings import settings
            from langgraph.types import interrupt

            user_approval = state.get("approval_status")

            # Safety: never interrupt for read-only API calls.
            api_method = (state.get("api_method") or "").upper() if state.get("api_method") else None
            if api_method is None:
                plan = state.get("operation_plan") or {}
                if isinstance(plan, dict):
                    method_val = plan.get("method")
                    if isinstance(method_val, str) and method_val.strip():
                        api_method = method_val.strip().upper()
            if api_method in _READ_ONLY_METHODS:
                return {**state, "approval_status": "approved"}

            # YOLO mode: auto-approve
            if settings.yolo_mode and user_approval is None:
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

            operation_plan = state.get("operation_plan") or {}
            if not isinstance(operation_plan, dict):
                operation_plan = {"plan": operation_plan}

            # Prefer parsed method/path from state, fall back to plan.
            method = (state.get("api_method") or operation_plan.get("method") or "GET")
            if isinstance(method, str):
                method = method.strip().upper()
            else:
                method = "GET"

            # Support both historical name "endpoint" and correct name "path".
            path = (
                operation_plan.get("path")
                or operation_plan.get("endpoint")
                or operation_plan.get("api_endpoint")
                or state.get("api_endpoint")
                or ""
            )

            payload = operation_plan.get("payload") or operation_plan.get("data")
            params = operation_plan.get("params") or operation_plan.get("filters")

            if not isinstance(path, str) or not path.strip():
                execution_result = {
                    "success": False,
                    "error": "Missing NetBox API path in operation_plan (expected: path/endpoint)",
                    "data": [],
                    "metadata": {"operation_plan": operation_plan},
                }
            else:
                # Execute the API call deterministically so we can't 'hallucinate success'.
                execution_result = await netbox_api_call(
                    path=path.strip(),
                    method=method,
                    data=payload if isinstance(payload, dict) else None,
                    params=params if isinstance(params, dict) else None,
                    device=None,
                )

            return {
                **state,
                "execution_result": execution_result,
                "messages": state["messages"]
                + [
                    AIMessage(
                        content=(
                            f"[NetBox Execution] method={method} path={path} "
                            f"success={execution_result.get('success', False)}"
                        )
                    )
                ],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def verification_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Verify API operation succeeded."""
            execution_result = state.get("execution_result") or {}
            if isinstance(execution_result, dict) and execution_result.get("success") is False:
                verification_result = {
                    "status": "failed",
                    "error": execution_result.get("error") or "NetBox API call failed",
                    "metadata": execution_result.get("metadata"),
                }
            else:
                verification_result = {
                    "status": "skipped",
                    "reason": "Execution result already reflects NetBox API response",
                }

            return {
                **state,
                "verification_result": verification_result,
                "messages": state["messages"]
                + [AIMessage(content=f"[NetBox Verification] {verification_result}")],
                "iteration_count": state.get("iteration_count", 0) + 1,
            }

        async def final_answer_node(state: NetBoxManagementState) -> NetBoxManagementState:
            """Generate final answer with operation summary."""
            llm = LLMFactory.get_chat_model()

            final_prompt = f"""Synthesize operation results and provide final answer.

IMPORTANT SAFETY NOTE:
- This workflow ONLY interacts with NetBox (SSOT) via NetBox API.
- Do NOT claim that a network device configuration has been changed.
- If the user's request sounds like a device config change (e.g., add Loopback, configure interface), explicitly say: "NetBox was updated, but the device was not configured" and advise using the device execution workflow.

User request: {state["messages"][0].content}
API endpoint: {state.get("api_endpoint")}
API method: {state.get("api_method")}
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
            method = state.get("api_method")
            if method and method.upper() in _READ_ONLY_METHODS:
                return "api_execution"
            # Default: require HITL for anything else / unknown
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
