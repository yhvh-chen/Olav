import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langserve import add_routes

from config.settings import settings
from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
from olav.core.llm import configure_langsmith
from olav.modes.inspection import InspectionScheduler
from olav.server.auth import generate_access_token, is_master_token_from_env
from olav.server.core import state

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle manager."""
    
    logger.info("🚀 Starting OLAV API Server...")

    # Configure LangSmith tracing if enabled
    if configure_langsmith():
        logger.info("🔍 LangSmith tracing enabled")

    # Start Inspection Scheduler
    scheduler = InspectionScheduler()
    scheduler_task = asyncio.create_task(scheduler.start())
    logger.info("⏰ Inspection Scheduler started in background")

    # Initialize Workflow Orchestrator (returns tuple: orchestrator, graph, checkpointer_context)
    try:
        # Feature flags from centralized settings
        _ = settings.use_dynamic_router  # Log for visibility
        expert_mode = settings.expert_mode

        # Initialize orchestrator & underlying Postgres checkpointer (async)
        result = await create_workflow_orchestrator(expert_mode=expert_mode)
        orch_obj, stateful_graph, stateless_graph, checkpointer_manager = (
            result  # (WorkflowOrchestrator, stateful_graph, stateless_graph, context manager)
        )

        # Use stateless graph for LangServe streaming to avoid thread_id requirement
        # Stateless mode doesn't require checkpointer config in every request
        state.orchestrator = stateless_graph
        app.state.orchestrator_obj = orch_obj  # store original orchestrator for stateful ops
        app.state.stateful_graph = stateful_graph  # store stateful graph for stream/events endpoint
        try:
            state.checkpointer = (
                getattr(orch_obj, "checkpointer", None) or checkpointer_manager
            )  # Prefer actual saver
        except Exception:
            state.checkpointer = checkpointer_manager
        # Store checkpointer_manager for cleanup on shutdown
        app.state.checkpointer_manager = checkpointer_manager
        logger.info(
            f"✅ Workflow Orchestrator ready (expert_mode={expert_mode}, sync_fallback={type(state.checkpointer).__name__ != 'AsyncPostgresSaver'})"
        )

        # Wrapper to normalize client payload (role-based) into OrchestratorState
        def _normalize_input(state_dict: dict) -> dict:
            """Normalize input messages to OrchestratorState schema."""
            raw = state_dict.get("messages", [])
            msgs = []
            for m in raw:
                if isinstance(m, dict):
                    role = m.get("role") or m.get("type") or "user"
                    content = m.get("content", "")
                    if role in ("user", "human"):
                        msgs.append(HumanMessage(content=content))
                    else:
                        msgs.append(AIMessage(content=content))
                else:
                    # Already a BaseMessage
                    msgs.append(m)

            # Provide required keys with defaults to satisfy OrchestratorState schema
            return {
                "messages": msgs,
                "workflow_type": None,
                "iteration_count": 0,
                "interrupted": False,
                "execution_plan": None,
            }

        wrapper = RunnableLambda(_normalize_input) | state.orchestrator

        if not state._routes_mounted:
            # Expose streaming endpoints via LangServe (stateless mode - no thread_id requirement)
            add_routes(
                app,
                wrapper,
                path="/orchestrator",
                enabled_endpoints=["stream", "stream_log"],
            )
            state._routes_mounted = True
            logger.info(
                "✅ LangServe streaming routes added (with input normalization): /orchestrator/stream"
            )
        else:
            logger.warning("LangServe routes already mounted, skipping duplicate add_routes call")
    except Exception as e:
        logger.error(f"❌ Failed to initialize orchestrator: {e}")
        state.orchestrator = None
        state.checkpointer = None

    logger.info("🎉 OLAV API Server is ready!")

    # Generate and print access token with URL
    token = generate_access_token()
    host = settings.server_host
    port = settings.server_port
    # Use localhost for display if bound to 0.0.0.0
    display_host = "localhost" if host == "0.0.0.0" else host
    api_base_url = f"http://{display_host}:{port}"
    api_docs_url = f"http://{display_host}:{port}/docs"

    logger.info("=" * 60)
    if is_master_token_from_env():
        logger.info("🔑 MASTER TOKEN (from OLAV_API_TOKEN; rotate by changing env + restart):")
    else:
        max_age_hours = getattr(settings, "token_max_age_hours", 24)
        logger.info(f"🔑 ACCESS TOKEN (auto-generated; valid for {max_age_hours} hours):")

    logger.info(f"   {token}")
    logger.info("")
    logger.info(f"🌐 API Base URL: {api_base_url}")
    logger.info(f"📖 API Docs: {api_docs_url}")
    logger.info("=" * 60)

    yield  # Server running

    # Cleanup on shutdown
    logger.info("🛑 Shutting down OLAV API Server...")

    # Stop scheduler
    if scheduler:
        logger.info("Stopping Inspection Scheduler...")
        await scheduler.stop()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        logger.info("Inspection Scheduler stopped")

    # Cleanup checkpointer connection pool
    cm = getattr(app.state, "checkpointer_manager", None)
    if cm:
        try:
            if hasattr(cm, "__aexit__"):
                await cm.__aexit__(None, None, None)
                logger.info("AsyncPostgresSaver connection pool closed")
            elif hasattr(cm, "__exit__"):
                cm.__exit__(None, None, None)
                logger.info("PostgresSaver connection closed")
        except Exception as e:
            logger.warning(f"Error closing checkpointer: {e}")
