import asyncio
import logging
from typing import Any

from fastapi import FastAPI
from langchain_core.runnables import Runnable
from langgraph.checkpoint.postgres import PostgresSaver
from langserve import add_routes

from config.settings import settings
from olav.agents.root_agent_orchestrator import create_workflow_orchestrator

logger = logging.getLogger(__name__)

# ============================================
# Global State
# ============================================
orchestrator: Runnable | None = None
checkpointer: PostgresSaver | None = None
_orchestrator_lock = asyncio.Lock()
_routes_mounted = False


async def ensure_orchestrator_initialized(app: FastAPI) -> None:
    """Lazy initialization of orchestrator for cases where startup lifecycle races tests.

    This allows /health to self-heal in environments (Windows CI) where the FastAPI
    lifespan startup may not complete before the first health probe.
    Idempotent: guarded by an asyncio.Lock and _routes_mounted flag.
    """
    global orchestrator, checkpointer, _routes_mounted
    if orchestrator and checkpointer:
        logger.debug("Lazy init skipped: orchestrator & checkpointer already set")
        return
    async with _orchestrator_lock:
        if orchestrator and checkpointer:  # double-check inside lock
            logger.debug("Lazy init double-check: already initialized inside lock")
            return
        try:
            logger.info(
                "[LazyInit] Starting orchestrator initialization (expert_mode/env flags)..."
            )
            expert_mode = settings.expert_mode
            result = await create_workflow_orchestrator(expert_mode=expert_mode)
            orch_obj, _stateful_graph, stateless_graph, checkpointer_manager = result
            # Use stateless graph for LangServe streaming (no thread_id requirement)
            # For stateful operations, use app.state.orchestrator_obj directly
            orchestrator = stateless_graph
            try:
                checkpointer = getattr(orch_obj, "checkpointer", None) or checkpointer_manager
            except Exception:
                checkpointer = checkpointer_manager
            if not _routes_mounted:
                add_routes(
                    app,
                    orchestrator,
                    path="/orchestrator",
                    enabled_endpoints=["invoke", "stream", "stream_log"],
                )
                _routes_mounted = True
                logger.info("✅ LangServe routes added: /orchestrator/invoke, /orchestrator/stream")
            else:
                logger.warning(
                    "LangServe routes already mounted, skipping duplicate add_routes call"
                )
            logger.info(
                f"✅ LazyInit success: graph={type(orchestrator).__name__}, checkpointer={type(checkpointer).__name__}, expert_mode={expert_mode}"
            )
        except Exception as e:  # pragma: no cover - diagnostic branch
            logger.exception(f"❌ Lazy orchestrator initialization failed: {e}")
