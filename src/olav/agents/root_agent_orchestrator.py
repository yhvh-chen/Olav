"""Workflow Orchestrator - Route user queries to appropriate workflow.

Intent Classification:
1. Query/Diagnostic: BGP状态查询、故障诊断、性能分析
2. Device Execution: 配置变更、CLI 执行
3. NetBox Management: 设备清单、IP分配、站点管理
4. Deep Dive: 复杂多步任务、批量审计、递归诊断

Routing Strategy (NEW - Dynamic Intent Router):
- Phase 1: Semantic pre-filtering (vector similarity on workflow examples)
- Phase 2: LLM classification (on Top-3 candidates only)
- Fallback: Keyword-based routing (if semantic index not available)

Legacy Routing Strategy (DEPRECATED):
- LLM-based classification (primary)
- Keyword fallback (secondary)
- Reject if no match

Environment Variables:
- OLAV_USE_DYNAMIC_ROUTER=true: Enable new DynamicIntentRouter (default: true)
- OLAV_USE_DYNAMIC_ROUTER=false: Use legacy classification (for rollback)
"""

import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from olav.agents.dynamic_orchestrator import DynamicIntentRouter
from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.core.settings import settings
from olav.workflows.base import WorkflowType
from olav.workflows.deep_dive import DeepDiveWorkflow
from olav.workflows.device_execution import DeviceExecutionWorkflow
from olav.workflows.netbox_management import NetBoxManagementWorkflow
from olav.workflows.query_diagnostic import QueryDiagnosticWorkflow

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Route user queries to appropriate workflow using Dynamic Intent Router."""

    def __init__(
        self,
        checkpointer: AsyncPostgresSaver,
        expert_mode: bool = False,
        use_dynamic_router: bool | None = None,
    ) -> None:
        """
        Initialize orchestrator with routing strategy.

        Args:
            checkpointer: PostgreSQL checkpointer for workflow state
            expert_mode: Enable Deep Dive workflow for complex tasks
            use_dynamic_router: Use DynamicIntentRouter (default: from env OLAV_USE_DYNAMIC_ROUTER)
        """
        self.checkpointer = checkpointer
        self.expert_mode = expert_mode

        # Determine routing strategy from env or parameter
        if use_dynamic_router is None:
            use_dynamic_router = os.getenv("OLAV_USE_DYNAMIC_ROUTER", "true").lower() == "true"

        self.use_dynamic_router = use_dynamic_router

        # Initialize workflows
        self.workflows = {
            WorkflowType.QUERY_DIAGNOSTIC: QueryDiagnosticWorkflow(),
            WorkflowType.DEVICE_EXECUTION: DeviceExecutionWorkflow(),
            WorkflowType.NETBOX_MANAGEMENT: NetBoxManagementWorkflow(),
            WorkflowType.DEEP_DIVE: DeepDiveWorkflow(),
        }

        # Initialize dynamic router if enabled
        self.dynamic_router: DynamicIntentRouter | None = None
        if self.use_dynamic_router:
            try:
                # Detect OpenRouter key pattern (sk-or- prefix) which is incompatible with OpenAI embeddings
                from olav.core.settings import settings as _env_settings

                key = _env_settings.llm_api_key.strip()
                if key.startswith("sk-or-"):
                    logger.warning(
                        "OpenRouter style key detected; disabling semantic embedding index and using legacy routing"
                    )
                    self.use_dynamic_router = False
                else:
                    llm = LLMFactory.get_chat_model(json_mode=True)
                    embeddings = LLMFactory.get_embedding_model()
                    self.dynamic_router = DynamicIntentRouter(llm=llm, embeddings=embeddings)
                    logger.info("DynamicIntentRouter initialized successfully")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize DynamicIntentRouter: {e}. "
                    f"Falling back to legacy classification."
                )
                self.use_dynamic_router = False
        else:
            logger.info("Using legacy keyword-based classification")

        # LLM for legacy classification
        self.llm = LLMFactory.get_chat_model(json_mode=False)

    async def initialize(self) -> None:
        """
        Initialize router (build semantic index if using dynamic router).

        Should be called once at startup before routing queries.
        """
        if self.dynamic_router:
            try:
                await self.dynamic_router.build_index()
                logger.info("Dynamic router semantic index built successfully")
            except Exception as e:
                logger.error(f"Failed to build semantic index: {e}")
                logger.warning("Falling back to legacy classification")
                self.use_dynamic_router = False
                self.dynamic_router = None

    async def classify_intent(self, user_query: str) -> WorkflowType:
        """Classify user intent using Dynamic Router or legacy classification.

        If expert_mode is enabled and query suggests complex task,
        return DEEP_DIVE workflow type.

        Routing decision hierarchy:
        1. Dynamic Router (if enabled and initialized)
        2. Legacy LLM classification
        3. Keyword fallback
        """

        # Use DynamicIntentRouter if available
        if self.use_dynamic_router and self.dynamic_router:
            try:
                workflow_name = await self.dynamic_router.route(
                    user_query, fallback="query_diagnostic"
                )

                # Map workflow name to WorkflowType enum
                workflow_type_map = {
                    "query_diagnostic": WorkflowType.QUERY_DIAGNOSTIC,
                    "device_execution": WorkflowType.DEVICE_EXECUTION,
                    "netbox_management": WorkflowType.NETBOX_MANAGEMENT,
                    "deep_dive": WorkflowType.DEEP_DIVE,
                }

                if workflow_name in workflow_type_map:
                    logger.info(f"Dynamic router selected: {workflow_name}")
                    return workflow_type_map[workflow_name]
                logger.warning(
                    f"Unknown workflow name from router: {workflow_name}, "
                    f"falling back to legacy classification"
                )
            except Exception as e:
                logger.error(f"Dynamic router failed: {e}, falling back to legacy")

        # Legacy classification (fallback)
        return await self._legacy_classify_intent(user_query)

    async def _legacy_classify_intent(self, user_query: str) -> WorkflowType:
        """Legacy LLM-based classification (for backward compatibility).

        This method preserves the original classification logic.
        """

        # Check for Deep Dive triggers (if expert mode enabled)
        if self.expert_mode:
            deep_dive_keywords = [
                # 审计类 (Audit) - 扩展匹配
                r"审计",
                r"audit",
                r"检查.*完整性",
                r"check.*integrity",
                r"配置.*完整",
                # 批量操作 (Batch)
                r"审计所有",
                r"批量",
                r"全部设备",
                r"所有设备",
                r"所有.*路由器",
                r"all.*router",
                r"多.*设备",
                r"multiple.*device",
                r"多台",
                r"\d+台",
                # 复杂诊断
                r"为什么.*无法访问",
                r"从.*到.*",
                r"跨",
                r"为什么",
                r"why",
                r"深入分析",
                r"详细排查",
                r"彻底检查",
                r"递归",
                r"诊断.*问题",
                r"diagnose.*issue",
                r"排查.*故障",
                r"troubleshoot",
                # 特定协议深度分析
                r"MPLS.*配置",
                r"BGP.*安全",
                r"OSPF.*邻居",
                r"ISIS.*拓扑",
            ]

            import re

            for keyword in deep_dive_keywords:
                if re.search(keyword, user_query, re.IGNORECASE):
                    print(
                        f"[Orchestrator] Expert Mode: Deep Dive trigger detected (pattern: '{keyword}'), using DEEP_DIVE workflow"
                    )
                    return WorkflowType.DEEP_DIVE

        # Strategy 1: LLM-based classification
        llm = LLMFactory.get_chat_model(json_mode=True)

        # Prepare workflow descriptions
        workflows_desc = {
            "query_diagnostic": "网络状态查询、故障诊断、性能分析、BGP/OSPF状态",
            "device_execution": "配置变更、添加VLAN、修改接口、执行CLI命令",
            "netbox_management": "设备清单、IP分配、站点管理、机架管理",
        }

        # Format workflows as string for prompt
        workflows_str = "\n".join([f"- **{k}**: {v}" for k, v in workflows_desc.items()])

        classification_prompt = prompt_manager.load_prompt(
            "workflows/orchestrator",
            "intent_classification",
            workflows=workflows_str,
            user_query=user_query,
        )

        try:
            response = await llm.ainvoke([SystemMessage(content=classification_prompt)])

            # Parse JSON response
            import json

            result = json.loads(response.content)
            workflow_type = result.get("workflow_type")

            if workflow_type in [
                "query_diagnostic",
                "device_execution",
                "netbox_management",
                "deep_dive",
            ]:
                return WorkflowType[workflow_type.upper()]

        except Exception as e:
            print(f"[Orchestrator] LLM classification failed: {e}, falling back to keywords")

        # Strategy 2: Keyword-based fallback
        return self._classify_by_keywords(user_query)

    def _classify_by_keywords(self, user_query: str) -> WorkflowType:
        """Fallback keyword-based classification."""
        query_lower = user_query.lower()

        # Expert Mode: Deep Dive for complex tasks (fallback detection)
        if self.expert_mode:
            complex_keywords = [
                "审计",
                "audit",
                "批量",
                "batch",
                "所有设备",
                "all device",
                "所有路由器",
                "all router",
                "为什么",
                "why",
                "完整性",
                "integrity",
            ]
            if any(kw in query_lower for kw in complex_keywords):
                print(
                    "[Orchestrator] Fallback: Complex task detected in expert mode, using DEEP_DIVE"
                )
                return WorkflowType.DEEP_DIVE

        # NetBox 管理优先（避免与配置变更混淆）
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
            "netbox",
        ]
        if any(kw in query_lower for kw in netbox_keywords):
            return WorkflowType.NETBOX_MANAGEMENT

        # 配置变更
        config_keywords = [
            "配置",
            "修改",
            "添加vlan",
            "删除",
            "shutdown",
            "no shutdown",
            "config",
            "configure",
            "change",
            "edit",
            "commit",
        ]
        if any(kw in query_lower for kw in config_keywords):
            return WorkflowType.DEVICE_EXECUTION

        # 默认：查询/诊断
        return WorkflowType.QUERY_DIAGNOSTIC

    async def route(self, user_query: str, thread_id: str) -> dict:
        """Route query to appropriate workflow and execute.

        Args:
            user_query: User's natural language query
            thread_id: Unique thread ID for state persistence

        Returns:
            Execution result from selected workflow
        """
        # 1. Classify intent
        workflow_type = await self.classify_intent(user_query)
        print(f"[Orchestrator] Classified as: {workflow_type.name}")

        # 2. Validate with workflow
        workflow = self.workflows[workflow_type]
        is_valid, reason = await workflow.validate_input(user_query)

        if not is_valid:
            # Fallback to default (query/diagnostic)
            print(f"[Orchestrator] Validation failed: {reason}, using QueryDiagnostic")
            workflow_type = WorkflowType.QUERY_DIAGNOSTIC
            workflow = self.workflows[workflow_type]

        # 3. Build and execute workflow graph
        # Default to stateless mode for LangServe compatibility (no thread_id requirement)
        # Set OLAV_STREAM_STATELESS=false to enable state persistence (requires client to provide thread_id)
        use_stateless = os.getenv("OLAV_STREAM_STATELESS", "true").lower() == "true"
        graph = workflow.build_graph(checkpointer=None if use_stateless else self.checkpointer)

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        initial_state = {
            "messages": [HumanMessage(content=user_query)],
            "workflow_type": workflow_type,
            "iteration_count": 0,
        }

        # 4. Execute workflow
        result = await graph.ainvoke(initial_state, config=config)

        # 5. Interrupt detection (skip for stateless mode)
        if use_stateless:
            return {
                "workflow_type": workflow_type.name,
                "result": result,
                "interrupted": False,
                "final_message": result["messages"][-1].content if result.get("messages") else None,
            }

        # Stateful mode: check for interrupts
        try:
            state_snapshot = await graph.aget_state(config)
            if state_snapshot.next:  # Has pending nodes (interrupted)
                return {
                    "workflow_type": workflow_type.name,
                    "result": result,
                    "interrupted": True,
                    "next_node": state_snapshot.next[0] if state_snapshot.next else None,
                    "execution_plan": result.get("execution_plan"),
                    "todos": result.get("todos", []),
                    "final_message": result["messages"][-1].content
                    if result.get("messages")
                    else None,
                }
        except Exception as e:
            # Treat errors in state retrieval as non-interrupted (log for debugging)
            print(f"[Orchestrator] State snapshot failed: {e}, assuming non-interrupted")

        return {
            "workflow_type": workflow_type.name,
            "result": result,
            "interrupted": False,
            "final_message": result["messages"][-1].content if result.get("messages") else None,
        }

    async def resume(self, thread_id: str, user_input: str, workflow_type: WorkflowType) -> dict:
        """Resume interrupted workflow with user input (approval/modification).

        Args:
            thread_id: Thread ID of interrupted workflow
            user_input: User's response to plan approval request
            workflow_type: Type of workflow that was interrupted

        Returns:
            Execution result after resumption
        """
        workflow = self.workflows[workflow_type]
        graph = workflow.build_graph(checkpointer=self.checkpointer)

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # Get current state
        state_snapshot = await graph.aget_state(config)
        current_state = state_snapshot.values

        # Debug: Check state snapshot
        logger.debug(f"Resume - Thread ID: {thread_id}")
        logger.debug(f"Resume - State snapshot next: {state_snapshot.next}")
        logger.debug(
            f"Resume - State values keys: {list(current_state.keys()) if current_state else 'None'}"
        )

        # Validate state has required fields
        if not current_state:
            return {
                "workflow_type": workflow_type.name,
                "aborted": True,
                "final_message": "❌ 无法获取当前状态，无法恢复执行。请检查thread_id是否正确。",
            }

        # Process user input
        user_decision = self._process_user_approval(user_input, current_state)

        if user_decision["action"] == "abort":
            # User rejected - terminate workflow
            return {
                "workflow_type": workflow_type.name,
                "aborted": True,
                "final_message": "⛔ 用户已中止执行计划。",
            }

        if user_decision["action"] == "approve":
            # User approved - continue with feasible tasks only
            # Safely get messages or use empty list
            existing_messages = current_state.get("messages", [])
            updated_state = {
                **current_state,
                "user_approval": "approved",
                "messages": [*existing_messages, HumanMessage(content="Y - 批准执行可行任务")],
            }

        elif user_decision["action"] == "modify":
            # User wants to modify - update execution plan based on LLM analysis
            modified_plan = await self._analyze_modification_request(
                user_input=user_input,
                current_plan=current_state.get("execution_plan"),
                todos=current_state.get("todos"),
            )
            existing_messages = current_state.get("messages", [])
            # Re-format plan summary for re-approval
            todos_list = current_state.get("todos", [])
            try:
                plan_summary = self.workflows[workflow_type]._format_execution_plan(
                    todos_list, modified_plan
                )  # type: ignore[attr-defined]
                summary_msg = AIMessage(content=plan_summary)
            except Exception:
                summary_msg = AIMessage(content="执行计划已修改，请重新审批。")
            updated_state = {
                **current_state,
                "execution_plan": modified_plan,
                "user_approval": "modified",
                "todos": current_state.get("todos"),
                "messages": [
                    *existing_messages,
                    HumanMessage(content=f"修改请求: {user_input}"),
                    summary_msg,
                ],
            }

        # Resume execution
        result = await graph.ainvoke(updated_state, config=config)

        # Check if interrupted again
        state_snapshot = await graph.aget_state(config)
        if state_snapshot.next:
            return {
                "workflow_type": workflow_type.name,
                "result": result,
                "interrupted": True,
                "next_node": state_snapshot.next[0] if state_snapshot.next else None,
                "execution_plan": updated_state.get("execution_plan"),
                "todos": updated_state.get("todos", []),
                "final_message": result["messages"][-1].content if result.get("messages") else None,
            }

        return {
            "workflow_type": workflow_type.name,
            "result": result,
            "interrupted": False,
            "execution_plan": updated_state.get("execution_plan"),
            "todos": updated_state.get("todos", []),
            "final_message": result["messages"][-1].content if result.get("messages") else None,
        }

    def _process_user_approval(self, user_input: str, current_state: dict) -> dict:
        """Process user's approval input and determine action.

        Args:
            user_input: Raw user input
            current_state: Current workflow state

        Returns:
            Dict with 'action': 'approve' | 'abort' | 'modify'
        """
        normalized = user_input.strip().upper()

        if normalized in {"Y", "YES", "APPROVE", "确认", "批准", "同意"}:
            return {"action": "approve"}
        if normalized in {"N", "NO", "ABORT", "REJECT", "取消", "中止", "拒绝"}:
            return {"action": "abort"}
        # Any other input treated as modification request
        return {"action": "modify", "content": user_input}

    async def _analyze_modification_request(
        self,
        user_input: str,
        current_plan: dict,
        todos: list[dict],
    ) -> dict:
        """Use LLM to analyze user's modification request and update execution plan.

        Args:
            user_input: User's modification request
            current_plan: Current execution plan
            todos: Current task list

        Returns:
            Modified execution plan
        """
        import json

        from langchain_core.messages import HumanMessage, SystemMessage

        # Prepare task details for LLM
        task_details = [
            {
                "id": t["id"],
                "task": t["task"],
                "feasibility": t.get("feasibility"),
                "recommended_table": t.get("recommended_table"),
            }
            for t in todos
        ]
        task_details_json = json.dumps(task_details, ensure_ascii=False, indent=2)

        analysis_prompt = f"""
你是 OLAV 执行计划分析专家。用户对当前计划提出了修改请求，请分析并更新执行计划。

## 当前执行计划
可行任务 ({len(current_plan.get("feasible_tasks", []))} 个): {current_plan.get("feasible_tasks")}
不确定任务 ({len(current_plan.get("uncertain_tasks", []))} 个): {current_plan.get("uncertain_tasks")}
无法执行任务 ({len(current_plan.get("infeasible_tasks", []))} 个): {current_plan.get("infeasible_tasks")}

## 任务详情
{task_details_json}

## 用户修改请求
{user_input}

## 分析要求
1. 理解用户意图（例如：跳过某些任务、修改查询表、添加过滤条件等）
2. 更新任务的 feasibility 状态
3. 修改 recommended_table（如果用户指定了）
4. 更新 feasible_tasks / uncertain_tasks / infeasible_tasks 列表

返回 JSON 格式的新执行计划：
{{{{
    "feasible_tasks": [任务ID列表],
    "uncertain_tasks": [任务ID列表],
    "infeasible_tasks": [任务ID列表],
    "recommendations": {{{{"任务ID": "建议"}}}},
    "user_approval_required": false,
    "modification_summary": "对用户请求的理解和执行的修改摘要"
}}}}
"""

        response = await self.llm.ainvoke(
            [
                SystemMessage(content="You are an execution plan analyzer."),
                HumanMessage(content=analysis_prompt),
            ]
        )

        try:
            import json

            return json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback: keep original plan
            import logging

            logging.getLogger(__name__).warning(
                "Failed to parse LLM modification response, keeping original plan"
            )
            return current_plan


async def create_orchestrator(postgres_uri: str) -> WorkflowOrchestrator:
    """Factory function to create orchestrator with checkpointer."""
    checkpointer = AsyncPostgresSaver.from_conn_string(postgres_uri)
    return WorkflowOrchestrator(checkpointer=checkpointer)


async def create_workflow_orchestrator(expert_mode: bool = False):
    """Create Workflow Orchestrator with PostgreSQL checkpointer and a stateless stream graph.

    Args:
        expert_mode: Enable Expert Mode (Deep Dive Workflow)

    Returns:
        Tuple of (orchestrator, graph, checkpointer_manager)
        - orchestrator: WorkflowOrchestrator instance (for resume)
        - graph: Compiled LangGraph (for streaming)
        - checkpointer_manager: Context manager for cleanup

    Architecture:
        Workflow Orchestrator Graph
        ├── Intent Classification (LLM + keyword fallback)
        ├── Query/Diagnostic Workflow (SuzieQ + NETCONF)
        ├── Device Execution Workflow (Config changes with HITL)
        ├── NetBox Management Workflow (Inventory with HITL)
        └── Deep Dive Workflow (Multi-step tasks, only if expert_mode=True)
    """
    from typing import TypedDict

    from langchain_core.messages import BaseMessage
    from langgraph.graph import END, StateGraph

    # Attempt async checkpointer; fallback to sync if Windows Proactor loop incompatibility encountered
    try:
        checkpointer_manager = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
        checkpointer = await checkpointer_manager.__aenter__()
        await checkpointer.setup()
        async_mode = True
    except Exception as e:
        if "ProactorEventLoop" in str(e) or "Proactor" in str(e):
            logger.warning(
                "AsyncPostgresSaver failed due to ProactorEventLoop; falling back to synchronous PostgresSaver"
            )
            from langgraph.checkpoint.postgres import PostgresSaver  # Local import

            # PostgresSaver.from_conn_string returns a context manager; manually enter
            pg_cm = PostgresSaver.from_conn_string(settings.postgres_uri)
            checkpointer = pg_cm.__enter__()
            checkpointer.setup()
            checkpointer_manager = pg_cm  # context manager for uniform return
            async_mode = False
        else:
            raise

    # Create orchestrator with expert mode flag
    orchestrator = WorkflowOrchestrator(checkpointer=checkpointer, expert_mode=expert_mode)

    # Initialize dynamic router (build semantic index)
    await orchestrator.initialize()

    # Define state for orchestrator graph
    # Make non-critical fields optional so external clients (LangServe RemoteRunnable,
    # simplified test payloads) can omit them without triggering 422 validation errors.
    # Only 'messages' is required; others will be defaulted during processing.
    class OrchestratorState(TypedDict, total=False):
        # Accept raw dict messages (role/content) from external clients; will be
        # normalized to LangChain message objects inside route_to_workflow.
        messages: list
        workflow_type: str | None
        iteration_count: int
        interrupted: bool | None  # HITL interrupt flag
        execution_plan: dict | None  # Plan from schema investigation

    async def route_to_workflow(state: OrchestratorState) -> OrchestratorState:
        """Route user query to appropriate workflow."""
        # Normalize inbound messages: convert dicts to HumanMessage/AIMessage/SystemMessage
        normalized_messages: list[BaseMessage] = []
        for m in state.get("messages", []):
            try:
                if isinstance(m, dict) and "role" in m and "content" in m:
                    role = m["role"].lower()
                    content = m["content"]
                    if role in {"user", "human"}:
                        normalized_messages.append(HumanMessage(content=content))
                    elif role in {"assistant", "ai"}:
                        normalized_messages.append(AIMessage(content=content))
                    elif role == "system":
                        normalized_messages.append(SystemMessage(content=content))
                    else:
                        normalized_messages.append(HumanMessage(content=content))
                elif isinstance(m, (HumanMessage, AIMessage, SystemMessage)):
                    normalized_messages.append(m)
            except Exception:
                continue
        if not normalized_messages:
            normalized_messages = [HumanMessage(content="")]  # placeholder to avoid empty list

        # Get latest human message content
        user_message = None
        for msg in reversed(normalized_messages):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

        if not user_message:
            return {
                **state,
                "messages": [AIMessage(content="未检测到用户查询")],
            }

        # Generate thread_id from state or create new one
        import time

        thread_id = f"workflow-{int(time.time())}"

        # Ensure required defaults if omitted
        if "iteration_count" not in state:
            state["iteration_count"] = 0  # type: ignore[index]
        if "workflow_type" not in state:
            state["workflow_type"] = None  # type: ignore[index]
        if "interrupted" not in state:
            state["interrupted"] = False  # type: ignore[index]
        if "execution_plan" not in state:
            state["execution_plan"] = None  # type: ignore[index]

        # Route to appropriate workflow
        result = await orchestrator.route(user_message, thread_id)

        # Return updated state with workflow result (including interrupt info)
        return {
            **state,
            "workflow_type": result.get("workflow_type"),
            "messages": result["result"].get("messages", normalized_messages),
            "interrupted": result.get("interrupted", False),
            "execution_plan": result.get("execution_plan"),
        }

    # Build orchestrator graph
    graph_builder = StateGraph(OrchestratorState)
    graph_builder.add_node("route_to_workflow", route_to_workflow)
    graph_builder.set_entry_point("route_to_workflow")
    graph_builder.add_edge("route_to_workflow", END)

    # Stateful graph (persists checkpoints)
    stateful_graph = graph_builder.compile(checkpointer=checkpointer)
    if not async_mode:
        logger.info("Compiled orchestrator graph with synchronous PostgresSaver (fallback mode)")

    # Stateless graph (no checkpoint requirements) for streaming endpoints without thread_id/config
    stateless_graph = graph_builder.compile()
    logger.info("Compiled additional stateless orchestrator graph for stream endpoint")

    return orchestrator, stateful_graph, stateless_graph, checkpointer_manager


__all__ = ["WorkflowOrchestrator", "create_orchestrator", "create_workflow_orchestrator"]
