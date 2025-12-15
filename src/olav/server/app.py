"""OLAV FastAPI Server with LangServe Integration.

This module provides the main FastAPI application with:
- LangServe endpoints for remote orchestrator access (/orchestrator/invoke, /orchestrator/stream)
- JWT authentication and RBAC
- Health check and status endpoints
- OpenAPI documentation (Swagger UI, Redoc)
"""

import asyncio
import logging
import os

# Set Windows event loop policy for async compatibility
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config.settings import settings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from olav.server.core.logging import configure_logging
from olav.server.core.lifespan import lifespan
from olav.server.core import state

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)

# ============================================
# Global State
# ============================================
# settings already imported from config.settings
# Global state moved to olav.server.core.state


# ============================================
# Request/Response Models
# ============================================
# Models moved to olav.server.models.*

# ============================================
# Application Lifecycle
# ============================================
# Lifespan moved to olav.server.core.lifespan


# ============================================
# FastAPI Application
# ============================================
def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="OLAV API - Enterprise Network Operations Platform",
        description=(
            "**OLAV** (NetAIChatOps) provides LangServe-based HTTP/WebSocket "
            "endpoints for enterprise network diagnostics, configuration management, and compliance auditing.\n\n"
            "## Features\n"
            "- 🔐 **Token Authentication** (auto-generated on startup)\n"
            "- 🔄 **Streaming Workflows** via Server-Sent Events (SSE)\n"
            "- 🤖 **AI-Powered Diagnostics** using LangGraph orchestrator\n"
            "- 🛡️ **HITL Safety** (Human-in-the-Loop) for write operations\n"
            "- 📊 **Multi-Workflow Support**: Query, Execution, NetBox, Deep Dive\n\n"
            "## Quick Start\n"
            "1. Copy the access token printed on server startup\n"
            "2. Add header: `Authorization: Bearer <token>`\n\n"
            "## Authentication\n"
            "All workflow endpoints require Bearer token:\n"
            "```\n"
            "Authorization: Bearer <token-from-startup>\n"
            "```\n\n"
            "See `/docs` for interactive API testing."
        ),
        version="0.4.0-beta",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "auth",
                "description": "🔐 Authentication and user info",
            },
            {
                "name": "monitoring",
                "description": "📊 Health checks and server status monitoring",
            },
            {
                "name": "orchestrator",
                "description": "🤖 Workflow execution endpoints (query diagnostics, device operations)",
            },
        ],
        contact={
            "name": "OLAV Development Team",
            "email": "network-automation@company.com",
        },
        license_info={
            "name": "Proprietary",
            "url": "https://company.com/license",
        },
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware (configured from settings)
    # Parse comma-separated origins or use "*" for all
    cors_origins = settings.cors_origins
    if cors_origins == "*":
        allow_origins = ["*"]
    else:
        allow_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods.split(",") if settings.cors_allow_methods != "*" else ["*"],
        allow_headers=settings.cors_allow_headers.split(",") if settings.cors_allow_headers != "*" else ["*"],
    )

    # ============================================
    # Monitoring API (Health & Config)
    # ============================================
    from olav.server.routers import monitoring
    app.include_router(monitoring.router)

    # ============================================
    # Autocomplete API
    # ============================================
    from olav.server.routers import autocomplete
    app.include_router(autocomplete.router)











    # ============================================
    # Sessions API (Chat History)
    # ============================================
    from olav.server.routers import sessions
    app.include_router(sessions.router)



    # ============================================
    # Device Inventory API
    # ============================================
    from olav.server.routers import inventory
    app.include_router(inventory.router)

    # ============================================
    # Inspection Reports API
    # ============================================
    from olav.server.routers import inspections
    app.include_router(inspections.router)

    # ============================================
    # Document Management API (RAG)
    # ============================================
    from olav.server.routers import documents
    app.include_router(documents.router)

    # ============================================
    # Authentication API
    # ============================================
    from olav.server.routers import auth
    app.include_router(auth.router)















    # ============================================
    # LangServe Routes
    # ============================================
    # NOTE: LangServe routes now mounted dynamically in lifespan after orchestrator init.
    if not state.orchestrator:
        logger.warning(
            "⚠️ Orchestrator not yet initialized at app creation - routes will be mounted during startup"
        )

    # ============================================
    # Error Handlers
    # ============================================
    from olav.server.core.exceptions import http_exception_handler
    app.add_exception_handler(HTTPException, http_exception_handler)

    # ============================================
    # Simplified Invoke Endpoint (bypasses LangServe validation schema)
    # ============================================
    from olav.server.routers import orchestrator
    app.include_router(orchestrator.router)










    return app


# ============================================
# Application Instance
# ============================================
app = create_app()

# ============================================
# Lazy Initialization
# ============================================
# Orchestrator and Checkpointer are initialized via lifespan startup events.
# Health checks in /health/detailed endpoint are independent and don't require
# full orchestrator initialization, so the /health endpoint works immediately.


# ============================================
# Entry Point for Development
# ============================================
if __name__ == "__main__":
    import uvicorn

    host = settings.server_host
    port = settings.server_port

    logger.info(f"🔥 Starting OLAV API Server on http://{host}:{port}")
    logger.info(f"📖 API Documentation: http://{host}:{port}/docs")

    uvicorn.run(
        "olav.server.app:app",
        host=host,
        port=port,
        reload=True,  # Hot reload for development
        log_level="info",
    )
