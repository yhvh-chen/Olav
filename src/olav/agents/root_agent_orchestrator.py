"""Workflow Orchestrator - Route user queries to appropriate workflow.

Intent Classification:
1. Query/Diagnostic: BGP status queries, fault diagnosis, performance analysis
2. Device Execution: Configuration changes, CLI execution
3. NetBox Management: Device inventory, IP allocation, site management
4. Deep Dive: Complex multi-step tasks, batch audits, recursive diagnosis

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

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Import tools package to ensure ToolRegistry is populated with all tools
# This is required for modes (standard, expert, inspection) that use ToolRegistry.get_tool()
import olav.tools  # noqa: F401
from olav.agents.dynamic_orchestrator import DynamicIntentRouter
from olav.agents.network_relevance_guard import (
    REJECTION_MESSAGE,
    get_network_guard,
)
from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from config.settings import settings
from olav.workflows.base import WorkflowType
from olav.workflows.deep_dive import DeepDiveWorkflow
from olav.workflows.device_execution import DeviceExecutionWorkflow
from olav.workflows.inspection import InspectionWorkflow
from olav.workflows.netbox_management import NetBoxManagementWorkflow
from olav.workflows.query_diagnostic import QueryDiagnosticWorkflow

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Route user queries to appropriate workflow using Dynamic Intent Router.

    Mode Architecture:
    - Standard Mode (-S): Fast single-tool responses via StandardModeWorkflow
    - Expert Mode (-E): L1-L4 layer analysis via SupervisorDrivenWorkflow
    - Inspection Mode: YAML-driven batch audits via InspectionWorkflow
    - Fallback: Full workflow graph if mode execution fails
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
            use_strategy_optimization: Use Standard Mode for QUERY_DIAGNOSTIC (default: True)
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
                from config.settings import settings as _env_settings

                key = _env_settings.llm_api_key.strip()
                if key.startswith("sk-or-"):
                    logger.warning(
                        "OpenRouter style key detected; disabling semantic embedding index and using legacy routing"
                    )
                    self.use_dynamic_router = False
                else:
                    # Use json_mode for structured output, reasoning=False to avoid verbose thinking
                    llm = LLMFactory.get_chat_model(json_mode=True, reasoning=False)
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

        # Network relevance guard (LLM-based pre-filter for non-network queries)
        self.network_guard = get_network_guard()

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
        """Legacy classification using keyword matching.

        Used as fallback when Dynamic Router is not available.
        Simple keyword-based classification for workflow selection.
        """
        return self._classify_by_keywords(user_query)

    def _classify_by_keywords(self, user_query: str) -> WorkflowType:
        """Keyword-based workflow classification.

        Simple but reliable keyword matching for workflow selection.
        """
        query_lower = user_query.lower()

        config_verbs = (
            "configure",
            "config",
            "modify",
            "change",
            "add",
            "create",
            "delete",
            "remove",
            "shutdown",
            "no shutdown",
            "enable",
            "disable",
            "set",
        )

        # Network configuration objects (signals user wants to change device config)
        device_config_objects = (
            "loopback",
            "interface",
            "vlan",
            "bgp",
            "ospf",
            "route",
            "static route",
            "neighbor",
            "prefix-list",
            "route-map",
            "access-list",
        )

        # Strong NetBox / IPAM signals
        netbox_markers = (
            "netbox",
            "inventory",
            "cmdb",
            "ipam",
            "dcim",
            "site",
            "rack",
            "prefix",
            "available ip",
            "allocate",
            "allocation",
            "/dcim/",
            "/ipam/",
            "ip-addresses",
        )

        # Priority 1: Deep Dive (expert mode only)
        if self.expert_mode and any(
            kw in query_lower for kw in ["audit", "batch", "why"]
        ):
            logger.info("Fallback: Deep Dive keywords detected")
            return WorkflowType.DEEP_DIVE

        # Priority 2: Inspection (sync/diff)
        if any(kw in query_lower for kw in ["inspect", "sync", "diff", "compare"]):
            return WorkflowType.INSPECTION

        # Priority 3: Device execution (config changes)
        # IMPORTANT: Prefer device_execution for config verbs + network config objects,
        # even if the query mentions "ip address" (common in interface config requests).
        if any(v in query_lower for v in config_verbs) and any(
            obj in query_lower for obj in device_config_objects
        ):
            return WorkflowType.DEVICE_EXECUTION

        # Priority 4: NetBox management (CMDB/IPAM)
        if any(marker in query_lower for marker in netbox_markers):
            return WorkflowType.NETBOX_MANAGEMENT

        # Priority 5: Device execution (generic config verbs)
        if any(v in query_lower for v in config_verbs):
            return WorkflowType.DEVICE_EXECUTION

        # Default: Query diagnostic
        return WorkflowType.QUERY_DIAGNOSTIC

    async def _load_conversation_history(
        self,
        thread_id: str,
        max_messages: int = 50,
        max_tokens: int = 16000,
        enable_summary: bool = True,
    ) -> list[BaseMessage]:
        """Load conversation history from checkpointer with optional summarization.

        This enables LLM to use prior context (e.g., interface lists from previous queries)
        to resolve abbreviations like 'lo16' -> 'Loopback16'.

        When history exceeds max_tokens, older messages are summarized to save tokens
        while preserving important context.

        Args:
            thread_id: Unique conversation thread ID
            max_messages: Maximum number of historical messages to load (default: 50)
            max_tokens: Maximum tokens for history (default: 16000)
            enable_summary: Enable LLM summarization for long histories (default: True)

        Returns:
            List of BaseMessage objects (HumanMessage/AIMessage), potentially with
            a SystemMessage summary of older context prepended
        """
        if not self.checkpointer:
            logger.debug("No checkpointer configured, skipping history load")
            return []

        try:
            # Use aget_tuple to retrieve the latest checkpoint state
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint_tuple = await self.checkpointer.aget_tuple(config)

            if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                logger.debug(f"No checkpoint found for thread_id={thread_id}")
                return []

            # Extract messages from checkpoint channel_values
            channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])

            if not messages:
                logger.debug(f"No messages in checkpoint for thread_id={thread_id}")
                return []

            # Convert to BaseMessage objects if needed and apply limit
            history: list[BaseMessage] = []
            for msg in messages[-max_messages:]:
                if isinstance(msg, BaseMessage):
                    history.append(msg)
                elif isinstance(msg, dict):
                    role = msg.get("role", msg.get("type", ""))
                    content = msg.get("content", "")
                    if role in ("human", "user"):
                        history.append(HumanMessage(content=content))
                    elif role in ("ai", "assistant"):
                        history.append(AIMessage(content=content))

            # Estimate token count (rough: 4 chars ≈ 1 token)
            total_chars = sum(len(m.content) for m in history if hasattr(m, "content"))
            estimated_tokens = total_chars // 4

            # If within token limit, return as-is
            if estimated_tokens <= max_tokens or not enable_summary:
                logger.info(
                    f"Loaded {len(history)} messages (~{estimated_tokens} tokens) "
                    f"for thread_id={thread_id}"
                )
                return history

            # Summarize older messages to fit within token limit
            logger.info(
                f"History exceeds {max_tokens} tokens (~{estimated_tokens}), "
                f"summarizing older messages"
            )
            return await self._summarize_history(history, max_tokens)

        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
            return []

    async def _summarize_history(
        self,
        messages: list[BaseMessage],
        max_tokens: int,
        recent_count: int = 10,
    ) -> list[BaseMessage]:
        """Summarize older messages while keeping recent ones intact.

        Uses ConversationSummaryBufferMemory pattern:
        - Keep last `recent_count` messages as-is (for detailed context)
        - Summarize older messages into a single SystemMessage

        Args:
            messages: Full message history
            max_tokens: Token budget for history
            recent_count: Number of recent messages to preserve verbatim

        Returns:
            [SystemMessage(summary)] + recent_messages
        """
        if len(messages) <= recent_count:
            return messages

        # Split into old (to summarize) and recent (to keep)
        old_messages = messages[:-recent_count]
        recent_messages = messages[-recent_count:]

        try:
            # Build summary prompt
            old_content = "\n".join(
                f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content[:500]}"
                for m in old_messages
                if hasattr(m, "content")
            )

            # Load prompt from config
            summary_prompt = prompt_manager.load_prompt(
                "agents",
                "conversation_summary",
                old_content=old_content,
            )

            # Use a lightweight LLM call for summarization
            llm = LLMFactory.get_chat_model(json_mode=False, reasoning=False)
            response = await llm.ainvoke([HumanMessage(content=summary_prompt)])

            summary_text = f"[Previous conversation summary]\n{response.content}"
            summary_message = SystemMessage(content=summary_text)

            logger.info(
                f"Summarized {len(old_messages)} old messages, "
                f"keeping {len(recent_messages)} recent messages"
            )

            return [summary_message] + recent_messages

        except Exception as e:
            logger.warning(f"Summary generation failed: {e}, using truncation fallback")
            # Fallback: just return recent messages without summary
            return recent_messages

    async def _save_messages_to_checkpointer(
        self,
        thread_id: str,
        user_query: str,
        assistant_response: str,
    ) -> None:
        """Save conversation messages to checkpointer for context continuity.

        This ensures Standard Mode queries (like "check interfaces on R1")
        are available as context for subsequent requests (like "delete lo11").

        Args:
            thread_id: Conversation thread ID
            user_query: User's query
            assistant_response: Assistant's response
        """
        if not self.checkpointer:
            return

        try:
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

            # Load existing messages or start fresh
            existing_messages: list[BaseMessage] = []
            try:
                checkpoint_tuple = await self.checkpointer.aget_tuple(config)
                if checkpoint_tuple and checkpoint_tuple.checkpoint:
                    channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                    existing_messages = channel_values.get("messages", [])
            except Exception:
                pass  # Start fresh if no existing checkpoint

            # Append new messages
            new_messages = existing_messages + [
                HumanMessage(content=user_query),
                AIMessage(content=assistant_response),
            ]

            # Save updated checkpoint
            checkpoint = {
                "v": 1,
                "id": f"checkpoint-{thread_id}",
                "ts": None,
                "channel_values": {
                    "messages": new_messages,
                },
                "channel_versions": {},
                "versions_seen": {},
                "pending_sends": [],
            }

            await self.checkpointer.aput(
                config=config,
                checkpoint=checkpoint,
                metadata={"source": "standard_mode", "step": len(new_messages) // 2},
                new_versions={},
            )

            print(f"[Orchestrator] ✅ Saved {len(new_messages)} messages to checkpointer for thread_id={thread_id}")
            logger.debug(
                f"Saved {len(new_messages)} messages to checkpointer for thread_id={thread_id}"
            )

        except Exception as e:
            print(f"[Orchestrator] ❌ Failed to save messages: {e}")
            logger.warning(f"Failed to save messages to checkpointer: {e}")

    async def route(self, user_query: str, thread_id: str, mode: str = "standard") -> dict:
        """Route query to appropriate workflow and execute.

        STRICT MODE SEPARATION:
        - standard (-S): Uses fast_path strategy with single tool calls
        - expert (-E): Uses SupervisorDrivenWorkflow with L1-L4 layer analysis

        No automatic switching between modes. User explicitly controls via CLI flags.

        Args:
            user_query: User's natural language query
            thread_id: Unique thread ID for state persistence
            mode: Execution mode from CLI (standard/expert)
                  - standard: Fast path (single tool call, optimized for speed)
                  - expert: Supervisor-Driven deep dive (L1-L4 layer analysis)

        Returns:
            Execution result from selected workflow
        """
        # ===== GUARD: Check if query is network-related (opt-in security feature) =====
        if settings.enable_guard_mode:
            relevance = await self.network_guard.check(user_query)
            if not relevance.is_relevant:
                logger.info(f"Query rejected by network guard: {relevance.reason}")
                print(f"[Orchestrator] Non-network query rejected ({relevance.method})")
                return {
                    "workflow_type": "REJECTED",
                    "result": {"success": False, "rejected": True},
                    "interrupted": False,
                    "final_message": REJECTION_MESSAGE,
                    "mode": mode,
                }
        else:
            logger.debug("Network guard disabled (ENABLE_GUARD_MODE=false)")

        # ===== EXPERT MODE: Direct to SupervisorDrivenWorkflow =====
        if mode == "expert":
            print("[Orchestrator] Expert mode (-E): Using SupervisorDrivenWorkflow")
            return await self._execute_expert_mode(user_query, thread_id)

        # ===== STANDARD MODE: Intent classification + fast_path =====
        # 1. Classify intent for workflow selection
        workflow_type = await self.classify_intent(user_query)
        print(f"[Orchestrator] Standard mode (-S): Classified as {workflow_type.name}")

        # 2. Validate with workflow
        workflow = self.workflows[workflow_type]
        is_valid, reason = await workflow.validate_input(user_query)

        if not is_valid:
            print(f"[Orchestrator] Validation failed: {reason}, using QueryDiagnostic")
            workflow_type = WorkflowType.QUERY_DIAGNOSTIC
            workflow = self.workflows[workflow_type]

        # 3. For QUERY_DIAGNOSTIC, use fast_path strategy (standard mode)
        if workflow_type == WorkflowType.QUERY_DIAGNOSTIC and self.use_strategy_optimization:
            try:
                strategy_result = await self._execute_standard_mode(user_query)
                if strategy_result:
                    # Check for HITL requirement first
                    if strategy_result.get("hitl_required"):
                        print("[Orchestrator] HITL required, returning approval prompt")
                        return {
                            "workflow_type": workflow_type.name,
                            "result": strategy_result,
                            "interrupted": True,  # Treat as interrupted for HITL
                            "hitl_required": True,
                            "final_message": strategy_result.get("answer"),
                            "strategy_used": "fast_path",
                            "mode": "standard",
                        }
                    # Check for success
                    if strategy_result.get("success"):
                        print("[Orchestrator] fast_path succeeded")
                        # Save query and response to checkpointer for conversation continuity
                        # This enables subsequent requests (like "delete lo11") to access
                        # prior context (interface list from "check interfaces on R1")
                        await self._save_messages_to_checkpointer(
                            thread_id=thread_id,
                            user_query=user_query,
                            assistant_response=strategy_result.get("answer", ""),
                        )
                        return {
                            "workflow_type": workflow_type.name,
                            "result": strategy_result,
                            "interrupted": False,
                            "final_message": strategy_result.get("answer"),
                            "strategy_used": "fast_path",
                            "mode": "standard",
                        }
                print("[Orchestrator] fast_path failed, falling back to workflow graph")
            except Exception as e:
                logger.warning(f"fast_path error: {e}, falling back to workflow graph")

        # 4. Build and execute workflow graph (for non-QUERY_DIAGNOSTIC or fallback)
        if workflow_type in (
            WorkflowType.DEEP_DIVE,
            WorkflowType.NETBOX_MANAGEMENT,
            WorkflowType.DEVICE_EXECUTION,
            WorkflowType.INSPECTION,
        ):
            use_stateless = False
            print(f"[Orchestrator] {workflow_type.name}: stateful mode for HITL")
        else:
            use_stateless = settings.stream_stateless
        graph = workflow.build_graph(checkpointer=None if use_stateless else self.checkpointer)

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100,
        }

        # Load conversation history for context-aware processing
        # This enables LLM to resolve interface abbreviations (lo16 -> Loopback16)
        # by referencing previously queried interface lists
        history_messages = await self._load_conversation_history(thread_id)
        
        # Debug: Print history status
        if history_messages:
            print(f"[Orchestrator] Loaded {len(history_messages)} history messages for context")
            # Show brief preview of last message content (truncated)
            last_msg = history_messages[-1] if history_messages else None
            if last_msg and hasattr(last_msg, 'content'):
                preview = last_msg.content[:200].replace('\n', ' ')
                print(f"[Orchestrator] Last history message preview: {preview}...")
        else:
            print(f"[Orchestrator] WARNING: No history messages found for thread_id={thread_id}")
        
        # Combine history with current query
        all_messages = history_messages + [HumanMessage(content=user_query)]

        initial_state = {
            "messages": all_messages,
            "workflow_type": workflow_type,
            "iteration_count": 0,
        }

        result = await graph.ainvoke(initial_state, config=config)

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
            if state_snapshot.next:
                # Extract execution plan from result (device_execution uses config_plan)
                execution_plan = result.get("execution_plan") or result.get("config_plan")
                
                return {
                    "workflow_type": workflow_type.name,
                    "result": result,
                    "interrupted": True,
                    "next_node": state_snapshot.next[0] if state_snapshot.next else None,
                    "execution_plan": execution_plan,
                    "config_plan": result.get("config_plan"),  # Include config_plan for device_execution
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

    def _format_hitl_prompt(self, result) -> str:
        """Format HITL approval prompt for user display.

        Args:
            result: StandardModeResult with hitl_required=True

        Returns:
            Formatted message asking for user approval
        """
        tool_name = result.tool_name or "unknown"
        operation = result.hitl_operation or "configuration change"
        params = result.hitl_parameters or {}

        # Extract key info for display
        device = params.get("device", params.get("hostname", "unknown"))
        command = params.get("command", "")

        lines = [
            "## ⚠️ HITL Approval Required",
            "",
            f"**Tool**: `{tool_name}`",
            f"**Device**: `{device}`",
            f"**Operation**: {operation}",
            "",
        ]

        if command:
            lines.extend([
                "**Command to execute**:",
                "```",
                command,
                "```",
                "",
            ])

        lines.extend([
            "---",
            "**This operation will modify device configuration.**",
            "",
            "Please review and approve or reject this action.",
        ])

        return "\n".join(lines)

    async def _execute_standard_mode(self, user_query: str) -> dict | None:
        """Execute query using Standard Mode workflow.

        Standard mode (-S): Optimized for quick single-tool responses.
        Uses StandardModeWorkflow from modes/standard/.

        Args:
            user_query: User's natural language query

        Returns:
            Execution result dict or None if mode execution fails
        """
        try:
            from config.settings import settings

            from olav.modes.standard import run_standard_mode
            from olav.tools.base import ToolRegistry

            result = await run_standard_mode(
                query=user_query,
                tool_registry=ToolRegistry(),
                yolo_mode=settings.yolo_mode,  # Use global HITL config
            )

            if result.success:
                return {
                    "success": True,
                    "answer": result.answer,
                    "strategy_used": "standard_mode",
                    "reasoning_trace": [],
                    "metadata": result.metadata,
                    "mode": "standard",
                }

            # Check for HITL requirement (write operation needs approval)
            if result.hitl_required:
                logger.info(f"HITL required for {result.tool_name}: {result.hitl_operation}")
                return {
                    "success": False,
                    "hitl_required": True,
                    "hitl_operation": result.hitl_operation,
                    "hitl_parameters": result.hitl_parameters,
                    "tool_name": result.tool_name,
                    "answer": self._format_hitl_prompt(result),
                    "strategy_used": "standard_mode",
                    "reasoning_trace": [],
                    "metadata": result.metadata or {},
                    "mode": "standard",
                }

            # Check for escalation to Expert Mode
            if result.escalated_to_expert:
                logger.info(
                    f"Standard mode escalated to Expert: {result.escalation_reason}"
                )
                return None
            # Mode execution failed
            logger.info(
                f"Standard mode failed: {result.error}, falling back to workflow graph"
            )
            return None

        except Exception as e:
            logger.warning(f"Standard mode execution failed: {e}")
            return None

    async def _execute_expert_mode(self, user_query: str, thread_id: str) -> dict:
        """Execute query using SupervisorDrivenWorkflow (Expert mode).

        Expert mode (-E): L1-L4 layer-based network analysis with Supervisor coordination.
        Uses SupervisorDrivenWorkflow for complex multi-step diagnostics.

        The Supervisor:
        1. Creates a diagnostic plan based on L1-L4 layer methodology
        2. Dispatches work to specialized layer analyzers
        3. Tracks confidence levels and iteration progress
        4. Synthesizes findings into actionable conclusions

        Args:
            user_query: User's natural language query
            thread_id: Thread ID for state persistence

        Returns:
            Execution result from SupervisorDrivenWorkflow
        """
        try:
            from olav.workflows.supervisor_driven import SupervisorDrivenWorkflow

            # Build SupervisorDrivenWorkflow with checkpointer for state persistence
            workflow = SupervisorDrivenWorkflow()
            graph = workflow.build_graph(checkpointer=self.checkpointer)

            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 100,  # Complex diagnostics may need more iterations
            }

            initial_state = {
                "messages": [HumanMessage(content=user_query)],
                "workflow_type": WorkflowType.DEEP_DIVE,
                "iteration_count": 0,
            }

            # Execute workflow
            result = await graph.ainvoke(initial_state, config=config)

            # Check for HITL interrupts
            try:
                state_snapshot = await graph.aget_state(config)
                if state_snapshot.next:
                    return {
                        "workflow_type": "SUPERVISOR_DRIVEN_DEEP_DIVE",
                        "result": result,
                        "interrupted": True,
                        "pending_nodes": list(state_snapshot.next),
                        "final_message": result["messages"][-1].content
                        if result.get("messages")
                        else None,
                        "mode": "expert",
                        "confidence_level": result.get("confidence_level", 0.0),
                    }
            except Exception as e:
                logger.debug(f"State snapshot check failed: {e}")

            return {
                "workflow_type": "SUPERVISOR_DRIVEN_DEEP_DIVE",
                "result": result,
                "interrupted": False,
                "final_message": result["messages"][-1].content
                if result.get("messages")
                else None,
                "mode": "expert",
                "confidence_level": result.get("confidence_level", 0.0),
                "iteration_count": result.get("iteration_count", 0),
            }

        except Exception as e:
            logger.error(f"Expert mode (SupervisorDrivenWorkflow) failed: {e}")
            return {
                "workflow_type": "SUPERVISOR_DRIVEN_DEEP_DIVE",
                "result": None,
                "interrupted": False,
                "final_message": f"❌ Expert mode execution failed: {e}",
                "mode": "expert",
                "error": str(e),
            }


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
                "final_message": "❌ Unable to get current state, cannot resume execution. Please check if thread_id is correct.",
            }

        # Process user input
        user_decision = self._process_user_approval(user_input, current_state)

        if user_decision["action"] == "abort":
            # User rejected - terminate workflow
            return {
                "workflow_type": workflow_type.name,
                "aborted": True,
                "final_message": "⛔ User has aborted the execution plan.",
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

        if normalized in {"Y", "YES", "APPROVE", "OK", "CONFIRM"}:
            return {"action": "approve"}
        if normalized in {"N", "NO", "ABORT", "REJECT", "CANCEL"}:
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
        # HITL additional info for CLI display
        hitl_required: bool | None
        tool_name: str | None
        hitl_operation: str | None
        hitl_parameters: dict | None
        hitl_message: str | None

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
                "messages": [AIMessage(content="No user query detected")],
            }

        # Get thread_id from config or generate new one
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            import time
            thread_id = f"workflow-{int(time.time())}"

        # Get mode from config (CLI passes this via configurable)
        mode = config.get("configurable", {}).get("mode", "standard")

        # Ensure required defaults if omitted
        if "iteration_count" not in state:
            state["iteration_count"] = 0  # type: ignore[index]
        if "workflow_type" not in state:
            state["workflow_type"] = None  # type: ignore[index]
        if "interrupted" not in state:
            state["interrupted"] = False  # type: ignore[index]
        if "execution_plan" not in state:
            state["execution_plan"] = None  # type: ignore[index]

        # Route to appropriate workflow with mode parameter
        result = await orchestrator.route(user_message, thread_id, mode=mode)

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
        output_state = {
            **state,
            "workflow_type": result.get("workflow_type"),
            "messages": output_messages,
            "interrupted": result.get("interrupted", False),
            "execution_plan": result.get("execution_plan"),
            "todos": result.get("todos", []),  # HITL: pass todos for approval display
        }

        # Include HITL info if present (for CLI to display approval prompt)
        if result.get("hitl_required") or result_data.get("hitl_required"):
            output_state["hitl_required"] = True
            output_state["tool_name"] = result_data.get("tool_name")
            output_state["hitl_operation"] = result_data.get("hitl_operation")
            output_state["hitl_parameters"] = result_data.get("hitl_parameters")
            output_state["hitl_message"] = result.get("final_message") or result_data.get("answer")

        return output_state

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
