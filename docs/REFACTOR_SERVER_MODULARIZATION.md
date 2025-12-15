# Server Modularization Refactor Plan

## Overview

The current `src/olav/server/app.py` file has grown to over 3300 lines, making it difficult to maintain, test, and navigate. This document outlines the design for refactoring the monolithic application file into a modular structure based on FastAPI best practices.

## Proposed Directory Structure

We will reorganize `src/olav/server/` into the following structure:

```text
src/olav/server/
├── __init__.py
├── app.py                  # Entry point (App factory, Middleware, Router assembly)
├── core/                   # Core infrastructure components
│   ├── __init__.py
│   ├── config.py           # Server-specific configuration
│   ├── exceptions.py       # Global exception handlers
│   ├── lifespan.py         # Startup/Shutdown logic
│   ├── logging.py          # Logging configuration (HealthCheckFilter)
│   └── state.py            # Global state management (orchestrator, checkpointer)
├── models/                 # Pydantic Data Models (Request/Response schemas)
│   ├── __init__.py
│   ├── auth.py             # Authentication models
│   ├── common.py           # Shared models (HealthResponse, etc.)
│   ├── document.py         # RAG Document models
│   ├── inspection.py       # Inspection & Report models
│   ├── inventory.py        # Device Inventory models
│   ├── orchestrator.py     # Workflow invocation models
│   └── session.py          # Chat Session models
└── routers/                # API Route Handlers
    ├── __init__.py
    ├── auth.py             # /auth, /me, /status
    ├── autocomplete.py     # /autocomplete
    ├── documents.py        # /documents
    ├── inspections.py      # /inspections, /reports
    ├── inventory.py        # /inventory
    ├── monitoring.py       # /health, /config
    ├── orchestrator.py     # /orchestrator (Invoke/Stream)
    └── sessions.py         # /sessions
```

## Module Responsibilities

### 1. Models Layer (`models/`)
Extracts all `pydantic.BaseModel` definitions from `app.py`.
- **Goal**: Decouple data validation schemas from route logic.
- **Files**:
    - `common.py`: `HealthResponse`, `StatusResponse`, `PublicConfigResponse`
    - `inspection.py`: `InspectionConfig`, `ReportDetail`, `JobStatusResponse`
    - `orchestrator.py`: `InvokeInput`, `StreamEventType`

### 2. Core Layer (`core/`)
Handles infrastructure concerns and global state to avoid circular dependencies.
- **`state.py`**: Holds global variables like `orchestrator` and `checkpointer`. Includes `ensure_orchestrator_initialized`.
- **`lifespan.py`**: Contains the `lifespan` context manager. It initializes components defined in `state.py`.
- **`logging.py`**: Contains `HealthCheckFilter` and logger setup.

### 3. Routers Layer (`routers/`)
Contains the actual API endpoint logic, using `APIRouter`.
- **Goal**: Group related endpoints.
- **Example (`routers/monitoring.py`)**:
    ```python
    from fastapi import APIRouter
    from olav.server.models.common import HealthResponse
    
    router = APIRouter(tags=["monitoring"])
    
    @router.get("/health", response_model=HealthResponse)
    async def health_check(): ...
    ```

### 4. Application Entry (`app.py`)
Becomes a lightweight assembly file.
- **Responsibilities**:
    - Initialize `FastAPI` app.
    - Configure CORS and Middleware.
    - Include routers: `app.include_router(monitoring.router)`.
    - Register exception handlers.

## Refactoring Strategy

To ensure stability, the refactor will be executed in phases:

### Phase 1: Models Extraction
- Create `src/olav/server/models/` directory.
- Move Pydantic classes from `app.py` to respective files in `models/`.
- Update `app.py` to import models from the new locations.

### Phase 2: Core Extraction
- Create `src/olav/server/core/`.
- Move `HealthCheckFilter` to `core/logging.py`.
- Move global state variables and initialization logic to `core/state.py`.
- Move `lifespan` function to `core/lifespan.py`.

### Phase 3: Routers Extraction
- Create `src/olav/server/routers/`.
- For each functional group (Auth, Monitoring, Inspections, etc.):
    - Create a router file.
    - Move endpoint functions to the router.
    - Replace `@app.get` with `@router.get`.
    - Update `app.py` to `include_router`.

### Phase 4: Cleanup
- Remove unused imports from `app.py`.
- Verify all tests pass.
- Verify `uv run olav status` and API functionality.
