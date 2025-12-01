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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Import tools package to ensure ToolRegistry is populated with all tools
# This is required for strategies (fast_path, deep_path) that use ToolRegistry.get_tool()
import olav.tools  # noqa: F401
from olav.agents.dynamic_orchestrator import DynamicIntentRouter
from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.core.settings import settings
from olav.strategies import execute_with_strategy_selection
from olav.workflows.base import WorkflowType
from olav.workflows.deep_dive import DeepDiveWorkflow
from olav.workflows.device_execution import DeviceExecutionWorkflow
from olav.workflows.inspection import InspectionWorkflow
from olav.workflows.netbox_management import NetBoxManagementWorkflow
from olav.workflows.query_diagnostic import QueryDiagnosticWorkflow

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Route user queries to appropriate workflow using Dynamic Intent Router.

    Strategy Integration:
    - For QUERY_DIAGNOSTIC: Uses StrategySelector to choose Fast/Deep/Batch path
    - Fast Path: Simple queries (< 2s response, single tool call)
    - Deep Path: Diagnostic queries (iterative reasoning)
    - Batch Path: Multi-device audits (parallel execution)
    - Inspection: NetBox sync/diff workflow
    - Fallback: Full workflow graph if strategy fails
    """

    def __init__(
        self,
        checkpointer: AsyncPostgresSaver,
        expert_mode: bool = False,
        use_dynamic_router: bool | None = None,
        use_strategy_optimization: bool = True,
    ) -> None:
        """
        Initialize orchestrator with routing strategy.

        Args:
            checkpointer: PostgreSQL checkpointer for workflow state
            expert_mode: Enable Deep Dive workflow for complex tasks
            use_dynamic_router: Use DynamicIntentRouter (default: from env OLAV_USE_DYNAMIC_ROUTER)
            use_strategy_optimization: Use StrategySelector for QUERY_DIAGNOSTIC (default: True)
        """
        self.checkpointer = checkpointer
        self.expert_mode = expert_mode
        self.use_strategy_optimization = use_strategy_optimization

        # Determine routing strategy from settings or parameter
        if use_dynamic_router is None:
            use_dynamic_router = settings.use_dynamic_router

        self.use_dynamic_router = use_dynamic_router

        # Initialize workflows
        self.workflows = {
            WorkflowType.QUERY_DIAGNOSTIC: QueryDiagnosticWorkflow(),
            WorkflowType.DEVICE_EXECUTION: DeviceExecutionWorkflow(),
            WorkflowType.NETBOX_MANAGEMENT: NetBoxManagementWorkflow(),
            WorkflowType.DEEP_DIVE: DeepDiveWorkflow(),
            WorkflowType.INSPECTION: InspectionWorkflow(),
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
                    "inspection": WorkflowType.INSPECTION,
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
        """Legacy classification using LLM Workflow Router.

        This method has been refactored to use LLMWorkflowRouter for more
        dynamic, context-aware classification. The hardcoded keyword patterns
        have been moved to the router as minimal fallback.

        See: olav.core.llm_workflow_router for implementation details.
        """
        from olav.core.llm_workflow_router import LLMWorkflowRouter, WorkflowRouteResult

        # Create router with current expert mode setting
        router = LLMWorkflowRouter(expert_mode=self.expert_mode)

        try:
            result: WorkflowRouteResult = await router.route(user_query)

            # Map workflow name to WorkflowType enum
            workflow_map = {
                "query_diagnostic": WorkflowType.QUERY_DIAGNOSTIC,
                "device_execution": WorkflowType.DEVICE_EXECUTION,
                "netbox_management": WorkflowType.NETBOX_MANAGEMENT,
                "deep_dive": WorkflowType.DEEP_DIVE,
                "inspection": WorkflowType.INSPECTION,
            }

            workflow_type = workflow_map.get(result.workflow, WorkflowType.QUERY_DIAGNOSTIC)

            logger.info(
                f"LLM Workflow Router: {result.workflow} "
                f"(confidence: {result.confidence:.2f}, reason: {result.reasoning[:50]}...)"
            )

            return workflow_type

        except Exception as e:
            logger.warning(f"LLM Workflow Router failed: {e}, using keyword fallback")
            return self._classify_by_keywords(user_query)

    def _classify_by_keywords(self, user_query: str) -> WorkflowType:
        """Minimal keyword fallback when LLM router fails.

        This is a simplified fallback with reduced keyword set (~25 vs ~100).
        For full classification, use LLMWorkflowRouter.
        """
        query_lower = user_query.lower()

        # Priority 1: Deep Dive (expert mode only)
        if self.expert_mode and any(
            kw in query_lower for kw in ["审计", "audit", "批量", "为什么"]
        ):
            logger.info("Fallback: Deep Dive keywords detected")
            return WorkflowType.DEEP_DIVE

        # Priority 2: Inspection (sync/diff)
        if any(kw in query_lower for kw in ["巡检", "同步", "sync", "对比", "diff"]):
            return WorkflowType.INSPECTION

        # Priority 3: NetBox management
        if any(
            kw in query_lower
            for kw in ["设备清单", "inventory", "netbox", "ip分配", "ip地址", "站点", "机架"]
        ):
            return WorkflowType.NETBOX_MANAGEMENT

        # Priority 4: Device execution (config changes)
        if any(kw in query_lower for kw in ["配置", "修改", "添加", "删除", "shutdown"]):
            return WorkflowType.DEVICE_EXECUTION

        # Default: Query diagnostic
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

        # 2.5. Strategy Optimization for QUERY_DIAGNOSTIC
        # Use FastPath/DeepPath/BatchPath for optimized execution
        if workflow_type == WorkflowType.QUERY_DIAGNOSTIC and self.use_strategy_optimization:
            try:
                strategy_result = await self._execute_with_strategy(user_query)
                if strategy_result and strategy_result.get("success"):
                    print(
                        f"[Orchestrator] Strategy optimization succeeded: {strategy_result.get('strategy_used')}"
                    )
                    return {
                        "workflow_type": workflow_type.name,
                        "result": strategy_result,
                        "interrupted": False,
                        "final_message": strategy_result.get("answer"),
                        "strategy_used": strategy_result.get("strategy_used"),
                        "strategy_metadata": strategy_result.get("metadata", {}),
                    }
                print("[Orchestrator] Strategy optimization failed, falling back to workflow graph")
            except Exception as e:
                logger.warning(f"Strategy optimization error: {e}, falling back to workflow graph")

        # 3. Build and execute workflow graph
        # DEEP_DIVE always needs checkpointer for HITL interrupt support
        # Other workflows respect stream_stateless setting for LangServe compatibility
        # NETBOX_MANAGEMENT, DEVICE_EXECUTION and INSPECTION also need HITL support
        if workflow_type in (
            WorkflowType.DEEP_DIVE,
            WorkflowType.NETBOX_MANAGEMENT,
            WorkflowType.DEVICE_EXECUTION,
            WorkflowType.INSPECTION,
        ):
            # These workflows require stateful execution for HITL approval
            use_stateless = False
            print(
                f"[Orchestrator] {workflow_type.name} workflow: forcing stateful mode for HITL support"
            )
        else:
            use_stateless = settings.stream_stateless
        graph = workflow.build_graph(checkpointer=None if use_stateless else self.checkpointer)

        config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "recursion_limit": 100,  # Increased from default 25 for multi-device operations
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

    async def _execute_with_strategy(self, user_query: str) -> dict | None:
        """Execute query using StrategySelector optimization.

        Uses Fast/Deep/Batch path for optimized execution of QUERY_DIAGNOSTIC queries.

        Args:
            user_query: User's natural language query

        Returns:
            Execution result dict or None if strategy optimization is not applicable
        """
        try:
            llm = LLMFactory.get_chat_model()

            # Execute with automatic strategy selection
            result = await execute_with_strategy_selection(
                user_query=user_query,
                llm=llm,
                use_llm_fallback=True,
            )

            if result.success:
                return {
                    "success": True,
                    "answer": result.answer,
                    "strategy_used": result.strategy_used,
                    "reasoning_trace": result.reasoning_trace,
                    "metadata": result.metadata,
                }
            # Strategy failed, return None to trigger workflow fallback
            logger.info(
                f"Strategy {result.strategy_used} failed: {result.error}, "
                f"falling back to workflow graph"
            )
            return None

        except Exception as e:
            logger.warning(f"Strategy execution failed: {e}")
            return None

    async def resume(self, thread_id: str, user_input: str, workflow_type: WorkflowType) -> dict:
        """Resume interrupted workflow with user input (approval/modification).

        Uses LangGraph Command(resume=...) to properly continue from interrupt point.

        Args:
            thread_id: Thread ID of interrupted workflow
            user_input: User's response to plan approval request
            workflow_type: Type of workflow that was interrupted

        Returns:
            Execution result after resumption
        """
        from langgraph.types import Command

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

        # Build resume value for Command
        if user_decision["action"] == "approve":
            resume_value = {"approved": True, "user_approval": "approved"}
        elif user_decision["action"] == "modify":
            # User wants to modify - analyze modification request
            modified_plan = await self._analyze_modification_request(
                user_input=user_input,
                current_plan=current_state.get("execution_plan"),
                todos=current_state.get("todos"),
            )
            resume_value = {
                "approved": True,
                "user_approval": "modified",
                "modified_plan": modified_plan,
                "modification_request": user_input,
            }
        else:
            resume_value = {"approved": True}

        # Resume execution using Command(resume=...)
        # This properly continues from the interrupt point
        result = await graph.ainvoke(Command(resume=resume_value), config=config)

        # Check if interrupted again
        state_snapshot = await graph.aget_state(config)
        if state_snapshot.next:
            return {
                "workflow_type": workflow_type.name,
                "result": result,
                "interrupted": True,
                "next_node": state_snapshot.next[0] if state_snapshot.next else None,
                "execution_plan": result.get("execution_plan")
                or current_state.get("execution_plan"),
                "todos": result.get("todos") or current_state.get("todos", []),
                "final_message": result["messages"][-1].content if result.get("messages") else None,
            }

        return {
            "workflow_type": workflow_type.name,
            "result": result,
            "interrupted": False,
            "execution_plan": result.get("execution_plan") or current_state.get("execution_plan"),
            "todos": result.get("todos") or current_state.get("todos", []),
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

        # Build current plan summary for prompt
        current_plan_summary = (
            f"Feasible tasks ({len(current_plan.get('feasible_tasks', []))}): "
            f"{current_plan.get('feasible_tasks')}\n"
            f"Uncertain tasks ({len(current_plan.get('uncertain_tasks', []))}): "
            f"{current_plan.get('uncertain_tasks')}\n"
            f"Infeasible tasks ({len(current_plan.get('infeasible_tasks', []))}): "
            f"{current_plan.get('infeasible_tasks')}"
        )

        analysis_prompt = prompt_manager.load_prompt(
            "agents",
            "plan_modification",
            current_plan=f"{current_plan_summary}\n\n## Task Details\n{task_details_json}",
            user_request=user_input,
        )

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
        todos: list | None  # HITL: task list for approval display

    from langchain_core.runnables import RunnableConfig

    async def route_to_workflow(state: OrchestratorState, config: RunnableConfig) -> OrchestratorState:
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

        # Get thread_id from config or generate new one
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
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

        # Extract messages from result
        # Strategy results have 'answer' in result['result'], workflow results have 'messages'
        result_data = result.get("result", {})
        if "messages" in result_data:
            output_messages = result_data["messages"]
        elif result.get("final_message"):
            # Strategy path: convert final_message to AIMessage
            output_messages = [*normalized_messages, AIMessage(content=result["final_message"])]
        else:
            output_messages = normalized_messages

        # Return updated state with workflow result (including interrupt info)
        return {
            **state,
            "workflow_type": result.get("workflow_type"),
            "messages": output_messages,
            "interrupted": result.get("interrupted", False),
            "execution_plan": result.get("execution_plan"),
            "todos": result.get("todos", []),  # HITL: pass todos for approval display
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
