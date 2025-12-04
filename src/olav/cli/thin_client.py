"""OLAV CLI Thin Client - Pure HTTP Client.

This module provides a lightweight client that ONLY communicates via HTTP.
NO local orchestrator, NO LangGraph imports, NO heavy dependencies.

Design Principles:
    - Zero server-side dependencies
    - Pure httpx for all communication
    - SSE parsing for streaming responses
    - Pydantic for data validation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)


# ============================================
# Event Types (SSE Streaming Protocol)
# ============================================
class StreamEventType(str, Enum):
    """Types of events in the streaming response.
    
    Matches server-side StreamEventType in /orchestrator/stream/events endpoint.
    """
    
    # Content events
    TOKEN = "token"              # Final response token
    MESSAGE = "message"          # Complete message (fallback)
    
    # Process events (from server's thinking process)
    THINKING = "thinking"        # LLM reasoning process
    TOOL_START = "tool_start"    # Tool invocation started
    TOOL_END = "tool_end"        # Tool invocation completed
    
    # Legacy aliases for backward compatibility
    TOOL_CALL = "tool_start"     # Alias
    TOOL_RESULT = "tool_end"     # Alias
    
    # Control events
    INTERRUPT = "interrupt"      # HITL approval required
    HITL_INTERRUPT = "interrupt" # Alias for backward compatibility  
    ERROR = "error"              # Error occurred
    DONE = "done"                # Stream completed


@dataclass
class StreamEvent:
    """A single event from the SSE stream."""
    
    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass 
class ToolCall:
    """Tool invocation record."""
    
    id: str
    name: str
    args: dict[str, Any]
    result: str | None = None
    success: bool = True
    duration_ms: float | None = None


@dataclass
class HITLRequest:
    """HITL approval request from server."""
    
    plan_id: str
    workflow_type: str
    operation: str
    target_device: str
    commands: list[str]
    risk_level: str  # "low", "medium", "high"
    reasoning: str
    execution_plan: dict[str, Any] | None = None
    todos: list[dict] | None = None


# ============================================
# Response Models
# ============================================
class ExecutionResult(BaseModel):
    """Result from workflow execution."""
    
    success: bool
    content: str = ""
    thread_id: str
    interrupted: bool = False
    error: str | None = None
    
    # Tool tracking
    tools_used: list[str] = []
    tool_calls: list[dict] = []
    
    # HITL fields
    hitl_request: dict | None = None
    workflow_type: str | None = None
    execution_plan: dict | None = None
    todos: list[dict] = []


class HealthStatus(BaseModel):
    """Server health status."""
    
    status: str
    version: str
    environment: str
    orchestrator_ready: bool


# ============================================
# Configuration
# ============================================
@dataclass
class ClientConfig:
    """Client configuration."""
    
    server_url: str = "http://localhost:8000"
    timeout: float = 360.0  # 6 minutes for complex queries (deep path)
    connect_timeout: float = 5.0
    
    @classmethod
    def from_env(cls) -> "ClientConfig":
        """Load config from environment variables."""
        return cls(
            server_url=os.getenv("OLAV_SERVER_URL", "http://localhost:8000"),
            timeout=float(os.getenv("OLAV_TIMEOUT", "300")),
        )
    
    @classmethod
    def from_file(cls, path: Path | None = None) -> "ClientConfig":
        """Load config from TOML file."""
        if path is None:
            path = Path.home() / ".olav" / "config.toml"
        
        if not path.exists():
            return cls.from_env()
        
        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            server = data.get("server", {})
            return cls(
                server_url=server.get("url", "http://localhost:8000"),
                timeout=server.get("timeout", 300),
            )
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            return cls.from_env()


# ============================================
# SSE Parser
# ============================================
class SSEParser:
    """Parse Server-Sent Events from HTTP stream."""
    
    def __init__(self):
        self.buffer = ""
    
    def parse_line(self, line: str) -> StreamEvent | None:
        """Parse a single SSE line.
        
        SSE format:
            event: token
            data: {"content": "hello"}
            
        Returns:
            StreamEvent if complete event parsed, None otherwise
        """
        line = line.strip()
        
        if not line:
            # Empty line = end of event, but we parse incrementally
            return None
        
        if line.startswith("event:"):
            self.buffer = line[6:].strip()
            return None
        
        if line.startswith("data:"):
            data_str = line[5:].strip()
            event_type_str = self.buffer or "message"
            
            try:
                # Parse event type
                try:
                    event_type = StreamEventType(event_type_str)
                except ValueError:
                    event_type = StreamEventType.MESSAGE
                
                # Parse data
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        data = {"raw": data_str}
                else:
                    data = {}
                
                return StreamEvent(type=event_type, data=data)
                
            finally:
                self.buffer = ""
        
        return None


# ============================================
# Thin Client
# ============================================
class OlavThinClient:
    """Pure HTTP client for OLAV API.
    
    This client has NO dependencies on server-side code.
    All communication is via HTTP/SSE.
    """
    
    def __init__(
        self, 
        config: ClientConfig | None = None,
        auth_token: str | None = None,
    ):
        """Initialize thin client.
        
        Args:
            config: Client configuration
            auth_token: JWT authentication token (optional for now)
        """
        self.config = config or ClientConfig.from_file()
        self.auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
    
    @property
    def headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers
    
    async def __aenter__(self) -> "OlavThinClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.config.server_url,
            timeout=httpx.Timeout(
                connect=self.config.connect_timeout,
                read=self.config.timeout,
                write=30.0,
                pool=5.0,
            ),
            headers=self.headers,
            http2=True,
        )
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # ------------------------------------------
    # Health & Status
    # ------------------------------------------
    async def health(self) -> HealthStatus:
        """Check server health."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get("/health")
        response.raise_for_status()
        return HealthStatus(**response.json())
    
    # ------------------------------------------
    # Chat / Query
    # ------------------------------------------
    async def chat(
        self,
        message: str,
        thread_id: str,
        mode: str = "standard",  # "standard" or "expert" (set via CLI -S or -E)
    ) -> ExecutionResult:
        """Execute a chat query (non-streaming).
        
        Args:
            message: User message
            thread_id: Conversation thread ID
            mode: Query mode ("standard" or "expert", set at startup via CLI flags)
            
        Returns:
            ExecutionResult with response
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        payload = {
            "input": {
                "messages": [{"role": "user", "content": message}],
            },
            "config": {
                "configurable": {
                    "thread_id": thread_id,
                    "mode": mode,
                }
            },
        }
        
        response = await self._client.post("/orchestrator/invoke", json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract final message from response
        content = ""
        output = result.get("output", {})
        if isinstance(output, dict):
            messages = output.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("type") == "ai":
                    content = msg.get("content", "")
                    break
        
        return ExecutionResult(
            success=True,
            content=content,
            thread_id=thread_id,
        )
    
    async def chat_stream(
        self,
        message: str,
        thread_id: str,
        mode: str = "standard",
    ) -> AsyncIterator[StreamEvent]:
        """Execute a chat query with streaming response.
        
        Uses /orchestrator/stream/events endpoint for structured events.
        
        Args:
            message: User message
            thread_id: Conversation thread ID
            mode: Query mode
            
        Yields:
            StreamEvent objects as they arrive
            
        Event types from server:
            - thinking: {"step": "reasoning", "content": "..."}
            - tool_start: {"id": "...", "name": "...", "display_name": "...", "args": {...}}
            - tool_end: {"id": "...", "name": "...", "duration_ms": 123, "success": true}
            - token: {"content": "..."}
            - interrupt: {"execution_plan": {...}}
            - error: {"code": "...", "message": "..."}
            - done: {}
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        payload = {
            "input": {
                "messages": [{"role": "user", "content": message}],
            },
            "config": {
                "configurable": {
                    "thread_id": thread_id,
                    "mode": mode,
                }
            },
        }
        
        # Use enhanced streaming endpoint with structured events
        async with self._client.stream(
            "POST",
            "/orchestrator/stream/events",
            json=payload,
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                
                data_str = line[5:].strip()  # Remove "data: " prefix
                if not data_str:
                    continue
                
                try:
                    data = json.loads(data_str)
                    event_type_str = data.get("type", "message")
                    
                    # Map server event type to enum
                    try:
                        event_type = StreamEventType(event_type_str)
                    except ValueError:
                        event_type = StreamEventType.MESSAGE
                    
                    # Create event with appropriate data
                    event = StreamEvent(type=event_type, data=data)
                    yield event
                    
                    # Check for terminal events
                    if event_type in (StreamEventType.DONE, StreamEventType.ERROR):
                        break
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse SSE data: {e}")
                    continue
    
    # ------------------------------------------
    # HITL Resume
    # ------------------------------------------
    async def resume(
        self,
        thread_id: str,
        decision: str,  # "Y", "N", or modification text
        workflow_type: str,
    ) -> ExecutionResult:
        """Resume an interrupted workflow.
        
        Args:
            thread_id: Thread ID of interrupted workflow
            decision: User's decision (Y/N/modification)
            workflow_type: Type of interrupted workflow
            
        Returns:
            ExecutionResult with resumed workflow result
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        payload = {
            "thread_id": thread_id,
            "user_input": decision,
            "workflow_type": workflow_type,
        }
        
        response = await self._client.post("/orchestrator/resume", json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        return ExecutionResult(
            success=not result.get("aborted", False),
            content=result.get("final_message", ""),
            thread_id=thread_id,
            interrupted=result.get("interrupted", False),
            workflow_type=result.get("workflow_type"),
            execution_plan=result.get("execution_plan"),
            todos=result.get("todos", []),
        )
    
    # ------------------------------------------
    # Inspection
    # ------------------------------------------
    async def list_inspection_profiles(self) -> list[dict]:
        """List available inspection profiles."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get("/inspection/profiles")
        response.raise_for_status()
        return response.json().get("profiles", [])
    
    async def run_inspection(
        self,
        profile: str,
        scope: str = "all",
    ) -> AsyncIterator[StreamEvent]:
        """Run an inspection with streaming progress.
        
        Args:
            profile: Inspection profile name
            scope: Target scope ("all", "core", "edge", etc.)
            
        Yields:
            StreamEvent objects for progress updates
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        payload = {"profile": profile, "scope": scope}
        parser = SSEParser()
        
        async with self._client.stream(
            "POST",
            "/inspection/run",
            json=payload,
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                event = parser.parse_line(line)
                if event:
                    yield event
    
    async def get_inspection_report(self, report_id: str) -> dict:
        """Get inspection report by ID."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get(f"/inspection/reports/{report_id}")
        response.raise_for_status()
        return response.json()
    
    # ------------------------------------------
    # Documents (RAG)
    # ------------------------------------------
    async def list_documents(self) -> list[dict]:
        """List indexed documents."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get("/documents")
        response.raise_for_status()
        return response.json().get("documents", [])
    
    async def upload_document(
        self,
        file_path: Path,
        on_progress: callable | None = None,
    ) -> dict:
        """Upload a document for RAG indexing with progress tracking.
        
        Args:
            file_path: Path to document file
            on_progress: Optional callback(bytes_sent: int) for progress updates
            
        Returns:
            Upload result with document ID
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        
        # Create a wrapper to track upload progress
        class ProgressFileWrapper:
            def __init__(self, file, callback, total_size):
                self._file = file
                self._callback = callback
                self._bytes_read = 0
                self._total_size = total_size
            
            def read(self, size=-1):
                data = self._file.read(size)
                if data:
                    self._bytes_read += len(data)
                    if self._callback:
                        self._callback(self._bytes_read)
                return data
            
            def seek(self, *args, **kwargs):
                return self._file.seek(*args, **kwargs)
            
            def tell(self):
                return self._file.tell()
        
        with open(file_path, "rb") as f:
            if on_progress:
                wrapped_file = ProgressFileWrapper(f, on_progress, file_size)
                files = {"file": (file_path.name, wrapped_file, "application/octet-stream")}
            else:
                files = {"file": (file_path.name, f, "application/octet-stream")}
            
            response = await self._client.post("/documents/upload", files=files)
        
        response.raise_for_status()
        return response.json()
    
    async def search_documents(self, query: str, limit: int = 5) -> list[dict]:
        """Search indexed documents.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching document chunks with scores
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get(
            "/documents/search",
            params={"q": query, "limit": limit},
        )
        response.raise_for_status()
        return response.json().get("results", [])
    
    # ------------------------------------------
    # Sessions
    # ------------------------------------------
    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """List conversation sessions."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get("/sessions", params={"limit": limit})
        response.raise_for_status()
        return response.json().get("sessions", [])
    
    async def get_session(self, session_id: str) -> dict:
        """Get session details including messages."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.get(f"/sessions/{session_id}")
        response.raise_for_status()
        return response.json()
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        response = await self._client.delete(f"/sessions/{session_id}")
        return response.status_code == 200
    
    # ------------------------------------------
    # Autocomplete
    # ------------------------------------------
    async def get_device_names(self) -> list[str]:
        """Get device names for autocomplete.
        
        Returns:
            List of device names from NetBox
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        try:
            response = await self._client.get("/autocomplete/devices")
            response.raise_for_status()
            data = response.json()
            return data.get("devices", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Endpoint not available - silently ignore
                logger.debug("Autocomplete endpoint not available (404)")
            else:
                logger.debug(f"Failed to fetch device names: {e}")
            return []
        except Exception as e:
            logger.debug(f"Failed to fetch device names: {e}")
            return []
    
    async def get_suzieq_tables(self) -> list[str]:
        """Get SuzieQ table names for autocomplete.
        
        Returns:
            List of SuzieQ table names
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        
        try:
            response = await self._client.get("/autocomplete/tables")
            response.raise_for_status()
            data = response.json()
            return data.get("tables", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Endpoint not available - silently ignore
                logger.debug("Autocomplete endpoint not available (404)")
            else:
                logger.debug(f"Failed to fetch SuzieQ tables: {e}")
            return []
        except Exception as e:
            logger.debug(f"Failed to fetch SuzieQ tables: {e}")
            return []


# ============================================
# Factory Function
# ============================================
async def create_thin_client(
    server_url: str | None = None,
    auth_token: str | None = None,
) -> OlavThinClient:
    """Create a connected thin client.
    
    Args:
        server_url: Server URL (default: from config/env)
        auth_token: JWT token (optional)
        
    Returns:
        Connected OlavThinClient
        
    Example:
        async with await create_thin_client() as client:
            health = await client.health()
            print(health)
    """
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    return OlavThinClient(config=config, auth_token=auth_token)
