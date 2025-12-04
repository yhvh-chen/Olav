"""OLAV CLI Client - Remote and Local Execution.

This module provides a unified client interface for OLAV that supports:
- Remote mode: Connect to LangServe API server via HTTP
- Local mode: Direct local execution (legacy behavior)

Architecture:
    Remote Mode (Default):
        CLI Client (Rich UI) → HTTP/WebSocket → LangServe API → Orchestrator

    Local Mode (-L/--local):
        CLI Client → Direct Orchestrator (in-process)
"""

import asyncio
import logging
import os
import sys
from typing import Any, Literal

import httpx
from langserve import RemoteRunnable
from pydantic import BaseModel
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

# Windows psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
    )

logger = logging.getLogger(__name__)


def _unescape_newlines(text: str) -> str:
    """Unescape literal \\n sequences to actual newlines.

    LLMs sometimes return literal '\\n' strings instead of actual newline
    characters in their JSON output. This function converts them back.

    Args:
        text: Text that may contain literal \\n sequences

    Returns:
        Text with literal \\n converted to actual newlines
    """
    if not text:
        return text
    # Replace literal \n (two characters) with actual newline
    # Also handle \t for tabs
    return text.replace("\\n", "\n").replace("\\t", "\t")


# ============================================
# Data Models
# ============================================
class ServerConfig(BaseModel):
    """Server connection configuration."""

    base_url: str = "http://localhost:8000"
    timeout: int = 300  # 5 minutes for long-running queries
    verify_ssl: bool = True


class ExecutionResult(BaseModel):
    """Result from workflow execution."""

    success: bool
    messages: list[dict[str, Any]]
    thread_id: str
    interrupted: bool = False
    error: str | None = None
    # HITL fields for workflow continuation
    workflow_type: str | None = None
    execution_plan: dict | None = None
    todos: list[dict] | None = None


# ============================================
# OLAV Client
# ============================================
class OLAVClient:
    """Unified OLAV client supporting remote and local execution modes."""

    def __init__(
        self,
        mode: Literal["remote", "local"] = "remote",
        server_config: ServerConfig | None = None,
        server_url: str | None = None,
        console: Console | None = None,
        auth_token: str | None = None,
        local_mode: bool | None = None,  # Backward compatibility
    ) -> None:
        """
        Initialize OLAV client.

        Args:
            mode: Execution mode ("remote" or "local")
            server_config: Server configuration (for remote mode)
            server_url: Server URL shortcut (alternative to server_config, for backward compatibility)
            console: Rich console for output (default: create new)
            auth_token: JWT authentication token (optional, will auto-load from ~/.olav/credentials)
            local_mode: Deprecated - use mode="local" instead
        """
        # Backward compatibility: local_mode parameter
        if local_mode is not None:
            logger.warning(
                "⚠️ local_mode parameter is deprecated. Use mode='local' or mode='remote' instead."
            )
            mode = "local" if local_mode else "remote"

        # Backward compatibility: server_url parameter
        if server_url is not None and server_config is None:
            server_config = ServerConfig(base_url=server_url)

        self.mode = mode
        self.server_config = server_config or ServerConfig()
        self.console = console or Console()
        self.remote_runnable: RemoteRunnable | None = None
        self.remote_health: dict[str, Any] | None = None  # Health check result for remote mode
        self.orchestrator: Any = None  # Local orchestrator (stateful for HITL)
        self.orchestrator_instance: Any = None  # WorkflowOrchestrator for resume()
        self.auth_token = auth_token  # JWT token for authenticated requests
        self.auto_fallback = False  # Whether to auto-fallback to local on remote failure
        self.query_mode = "standard"  # Query mode: standard, expert, inspection

    async def connect(self, expert_mode: bool = False, auto_fallback: bool = False) -> None:
        """
        Connect to OLAV backend (remote or local).

        Args:
            expert_mode: Enable Expert Mode (Deep Dive Workflow)
            auto_fallback: Auto-fallback to local mode if remote connection fails
        """
        self.auto_fallback = auto_fallback
        # Store query mode based on expert_mode flag
        self.query_mode = "expert" if expert_mode else "standard"

        if self.mode == "remote":
            # Auto-load credentials if no token provided
            if self.auth_token is None:
                self.auth_token = self._load_stored_token()

            try:
                await self._connect_remote()
            except ConnectionError:
                if auto_fallback:
                    self.console.print(
                        "\n[yellow]⚡ Auto-fallback: Switching to Local Mode...[/yellow]"
                    )
                    self.mode = "local"
                    await self._connect_local(expert_mode)
                else:
                    raise
        else:
            await self._connect_local(expert_mode)

    def _load_stored_token(self) -> str | None:
        """
        Load authentication token from stored credentials.

        Returns:
            JWT token if available and valid, None otherwise
        """
        try:
            from olav.cli.auth import CredentialsManager

            creds_manager = CredentialsManager()
            credentials = creds_manager.load()

            if credentials is None:
                return None

            # Verify server URL matches
            if credentials.server_url != self.server_config.base_url:
                logger.warning(
                    f"Stored credentials are for different server: "
                    f"{credentials.server_url} != {self.server_config.base_url}"
                )
                return None

            return credentials.access_token

        except Exception as e:
            logger.debug(f"Failed to load stored token: {e}")
            return None

    async def _connect_remote(self) -> None:
        """Connect to remote LangServe API server."""
        try:
            # Prepare headers (with authentication if available)
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            # Test server connectivity
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_config.base_url}/health",
                    timeout=5.0,
                    headers=headers if self.auth_token else {},
                )
                response.raise_for_status()
                health = response.json()

            # Store health check result
            self.remote_health = health

            if health["status"] != "healthy":
                self.console.print(
                    f"[yellow]⚠️  Server status: {health['status']} "
                    f"(orchestrator_ready={health['orchestrator_ready']})[/yellow]"
                )

            # Create RemoteRunnable with authentication headers and timeout
            # Note: LangServe RemoteRunnable doesn't support custom headers in constructor
            # So we'll need to use httpx client directly for authenticated requests
            self.remote_runnable = RemoteRunnable(
                f"{self.server_config.base_url}/orchestrator",
                headers=headers if self.auth_token else None,
                timeout=60.0,  # Increased from default 30s to 60s for complex workflows
            )

            self.console.print(
                f"[green]✅ Connected to OLAV API server: {self.server_config.base_url}[/green]"
            )
            self.console.print(f"   Version: {health['version']}")
            self.console.print(f"   Environment: {health['environment']}")

            if self.auth_token:
                self.console.print("   [dim]🔐 Authenticated (using stored credentials)[/dim]")
            else:
                self.console.print(
                    "   [yellow]⚠️  Not authenticated (public endpoints only)[/yellow]"
                )
                self.console.print("   [dim]💡 Run 'olav login' to authenticate[/dim]")

            # Backward compatibility alias
            self.remote_orchestrator = self.remote_runnable

        except httpx.ConnectError:
            self.console.print(
                f"[red]❌ Failed to connect to server: {self.server_config.base_url}[/red]"
            )
            self.console.print("\n💡 Tips:")
            self.console.print("   1. Start server: uv run python src/olav/server/app.py")
            self.console.print("   2. Or use local mode: olav.py -L")
            msg = f"Cannot connect to OLAV server at {self.server_config.base_url}"
            raise ConnectionError(msg)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                self.console.print("[red]❌ Authentication failed (401 Unauthorized)[/red]")
                self.console.print("\n💡 Run 'olav login' to authenticate")
                msg = "Authentication required"
                raise ConnectionError(msg) from e
            raise
        except Exception as e:
            self.console.print(f"[red]❌ Connection error: {e}[/red]")
            raise

    async def _connect_local(self, expert_mode: bool) -> None:
        """Initialize local orchestrator (direct execution with HITL support)."""
        try:
            from olav.agents.root_agent_orchestrator import create_workflow_orchestrator

            self.console.print("[cyan]🔧 Initializing local orchestrator...[/cyan]")

            result = await create_workflow_orchestrator(expert_mode=expert_mode)
            # Unpack tuple: (orchestrator, stateful_graph, stateless_graph, checkpointer_manager)
            orchestrator_instance, stateful_graph, _stateless_graph, checkpointer_mgr = result

            # IMPORTANT: Keep checkpointer_manager reference to prevent connection close
            self.checkpointer_manager = checkpointer_mgr

            # Use STATEFUL graph for HITL support (interrupt/resume)
            # The stateful_graph has checkpointer enabled for workflow interruption
            self.orchestrator = stateful_graph
            self.orchestrator_instance = orchestrator_instance  # For resume() calls

            self.console.print(
                f"[green]✅ Local orchestrator ready (expert_mode={expert_mode}, HITL=enabled)[/green]"
            )

        except Exception as e:
            self.console.print(f"[red]❌ Failed to initialize local orchestrator: {e}[/red]")
            raise

    def set_query_mode(self, mode: str) -> None:
        """Set the query mode for local execution.
        
        User can switch modes in TUI. Workflows are strictly separated:
        - Standard: fast_path strategy (single tool call)
        - Expert: SupervisorDrivenWorkflow (L1-L4 layer analysis)
        
        No automatic escalation between modes - user controls which mode to use.
        
        Args:
            mode: Query mode - "standard" or "expert"
        """
        valid_modes = ["standard", "expert"]
        if mode not in valid_modes:
            self.console.print(f"[yellow]Invalid mode '{mode}'. Valid: {valid_modes}[/yellow]")
            return
        self.query_mode = mode
        self.console.print(f"[green]Query mode set to: {mode}[/green]")

    async def resume(self, thread_id: str, user_input: str, workflow_type: str) -> ExecutionResult:
        """Resume an interrupted workflow with user approval/modification.

        Args:
            thread_id: Thread ID of the interrupted workflow
            user_input: User's decision (Y/N/modification request)
            workflow_type: Type of workflow that was interrupted (e.g., "DEEP_DIVE")

        Returns:
            ExecutionResult with resumed workflow result
        """
        if self.mode == "remote":
            # Remote mode: TODO - implement remote resume via API
            return ExecutionResult(
                success=False,
                messages=[],
                thread_id=thread_id,
                error="Remote resume not yet implemented",
            )

        # Local mode: use orchestrator instance's resume method
        if not self.orchestrator_instance:
            return ExecutionResult(
                success=False,
                messages=[],
                thread_id=thread_id,
                error="Orchestrator not initialized. Call connect() first.",
            )

        try:
            from olav.workflows.base import WorkflowType

            # Convert string to WorkflowType enum
            workflow_enum = WorkflowType[workflow_type.upper()]

            # Call orchestrator's resume method
            result = await self.orchestrator_instance.resume(
                thread_id=thread_id,
                user_input=user_input,
                workflow_type=workflow_enum,
            )

            # Convert result to ExecutionResult
            messages = result.get("result", {}).get("messages", [])
            messages_dict = []
            for msg in messages:
                if hasattr(msg, "type") and hasattr(msg, "content"):
                    messages_dict.append({"type": msg.type, "content": msg.content})

            return ExecutionResult(
                success=not result.get("aborted", False),
                messages=messages_dict,
                thread_id=thread_id,
                interrupted=result.get("interrupted", False),
                workflow_type=result.get("workflow_type"),
                execution_plan=result.get("execution_plan"),
                todos=result.get("todos", []),
            )

        except Exception as e:
            logger.error(f"Resume failed: {e}")
            return ExecutionResult(
                success=False,
                messages=[],
                thread_id=thread_id,
                error=str(e),
            )

    async def execute(self, query: str, thread_id: str, stream: bool = True) -> ExecutionResult:
        """
        Execute query using remote or local backend.

        Args:
            query: User query to execute
            thread_id: Conversation thread ID
            stream: Enable streaming output (default: True)

        Returns:
            ExecutionResult with messages and status
        """
        if self.mode == "remote":
            return await self._execute_remote(query, thread_id, stream)
        return await self._execute_local(query, thread_id, stream)

    async def _execute_remote(self, query: str, thread_id: str, stream: bool) -> ExecutionResult:
        """Execute query via remote API server with retry logic."""
        if not self.remote_runnable:
            msg = "Not connected to remote server. Call connect() first."
            raise RuntimeError(msg)

        # Retry configuration (exponential backoff)
        max_retries = 3
        base_delay = 1.0  # Initial retry delay in seconds

        for attempt in range(max_retries):
            try:
                return await self._execute_remote_attempt(query, thread_id, stream)
            except Exception as e:
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Remote execution failed (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    logger.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    logger.error(f"Remote execution failed after {max_retries} attempts: {e}")
                    return ExecutionResult(
                        success=False, messages=[], thread_id=thread_id, error=str(e)
                    )

        # Should never reach here, but satisfy type checker
        return ExecutionResult(
            success=False, messages=[], thread_id=thread_id, error="Unknown error"
        )

    async def _execute_remote_attempt(
        self, query: str, thread_id: str, stream: bool
    ) -> ExecutionResult:
        """Single attempt to execute query via remote API server."""
        try:
            config = {"configurable": {"thread_id": thread_id}}
            messages_buffer: list[dict] = []
            final_message_content: str = ""

            if stream:
                # Streaming mode with Rich Live display
                with Live(console=self.console, refresh_per_second=4) as live:
                    live.update(Panel("🔄 Waiting for response...", title="OLAV"))

                    async for chunk in self.remote_runnable.astream(
                        {"messages": [{"role": "user", "content": query}]}, config=config
                    ):
                        # Process streaming chunks - LangGraph returns {node_name: {state}}
                        # Extract messages from any node's state
                        for _node_name, node_state in chunk.items():
                            if isinstance(node_state, dict):
                                if "messages" in node_state:
                                    messages_buffer = node_state["messages"]
                                    # Display latest AI message
                                    for msg in reversed(messages_buffer):
                                        msg_type = (
                                            msg.get("type")
                                            if isinstance(msg, dict)
                                            else getattr(msg, "type", None)
                                        )
                                        if msg_type == "ai":
                                            content = (
                                                msg.get("content", "")
                                                if isinstance(msg, dict)
                                                else getattr(msg, "content", "")
                                            )
                                            if content:
                                                final_message_content = content
                                                live.update(Markdown(_unescape_newlines(content)))
                                            break
                                # Also check for final_message in result
                                if node_state.get("final_message"):
                                    final_message_content = node_state["final_message"]
                                    live.update(Markdown(_unescape_newlines(final_message_content)))

            else:
                # Non-streaming mode
                result = await self.remote_runnable.ainvoke(
                    {"messages": [{"role": "user", "content": query}]}, config=config
                )
                messages_buffer = result.get("messages", [])
                final_message_content = result.get("final_message", "")

            # Ensure we have proper AI message in buffer for display
            if final_message_content and not any(
                (m.get("type") if isinstance(m, dict) else getattr(m, "type", None)) == "ai"
                for m in messages_buffer
            ):
                messages_buffer.append({"type": "ai", "content": final_message_content})

            # Convert BaseMessage objects to dicts for Pydantic validation
            def _to_dict(msg) -> dict:
                if isinstance(msg, dict):
                    return msg
                # BaseMessage-like object
                return {
                    "type": getattr(msg, "type", "unknown"),
                    "content": getattr(msg, "content", ""),
                }

            messages_as_dicts = [_to_dict(m) for m in messages_buffer]

            return ExecutionResult(
                success=True,
                messages=messages_as_dicts,
                thread_id=thread_id,
                interrupted=False,
            )

        except Exception:
            # Re-raise to trigger retry logic in _execute_remote
            raise

    async def _execute_local(self, query: str, thread_id: str, stream: bool) -> ExecutionResult:
        """Execute query via local orchestrator.

        Uses orchestrator_instance.route() for proper HITL interrupt detection.
        """
        if not self.orchestrator_instance:
            msg = "Local orchestrator not initialized. Call connect() first."
            raise RuntimeError(msg)

        try:
            # Use orchestrator.route() for proper interrupt handling
            # Pass query_mode for strategy selection (standard/expert/inspection)
            result = await self.orchestrator_instance.route(query, thread_id, mode=self.query_mode)

            # Extract messages from result
            messages_buffer = []
            inner_result = result.get("result", {})
            if inner_result and "messages" in inner_result:
                messages_buffer = inner_result["messages"]

            # Convert BaseMessage to dict
            messages_dict = []
            for msg in messages_buffer:
                if hasattr(msg, "type") and hasattr(msg, "content"):
                    messages_dict.append({"type": msg.type, "content": msg.content})

            # Get final message
            final_message = result.get("final_message", "")
            if final_message:
                final_message = _unescape_newlines(final_message)
            if final_message and not any(m.get("type") == "ai" for m in messages_dict):
                messages_dict.append({"type": "ai", "content": final_message})

            # Display final message if available
            if final_message:
                from rich.markdown import Markdown

                self.console.print(Markdown(final_message))

            # Check for HITL interrupt
            is_interrupted = result.get("interrupted", False)
            workflow_type = result.get("workflow_type")
            execution_plan = inner_result.get("execution_plan") if inner_result else None
            todos = inner_result.get("todos", []) if inner_result else []

            return ExecutionResult(
                success=True,
                messages=messages_dict,
                thread_id=thread_id,
                interrupted=is_interrupted,
                workflow_type=workflow_type,
                execution_plan=execution_plan,
                todos=todos,
            )

        except Exception as e:
            logger.error(f"Local execution failed: {e}")
            return ExecutionResult(success=False, messages=[], thread_id=thread_id, error=str(e))
            return ExecutionResult(success=False, messages=[], thread_id=thread_id, error=str(e))

    async def health_check(self) -> dict[str, Any]:
        """
        Check backend health status.

        Returns:
            Health status dict (remote) or simplified status (local)
        """
        if self.mode == "remote":
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.server_config.base_url}/health", timeout=5.0)
                response.raise_for_status()
                return response.json()
        else:
            return {
                "status": "healthy" if self.orchestrator else "not_initialized",
                "mode": "local",
                "orchestrator_ready": self.orchestrator is not None,
            }

    def display_result(self, result: ExecutionResult) -> None:
        """
        Display execution result using Rich formatting.

        Args:
            result: Execution result to display
        """
        if not result.success:
            self.console.print(f"\n[red]❌ Execution failed: {result.error}[/red]")
            return

        if result.interrupted:
            self.console.print("\n[yellow]⏸️  Execution paused (HITL approval required)[/yellow]")

        # Display messages
        self.console.print("\n" + "=" * 60)
        self.console.print("[bold cyan]📋 Execution Result[/bold cyan]")
        self.console.print("=" * 60)

        for msg in result.messages:
            # Handle both dict and BaseMessage objects
            if isinstance(msg, dict):
                msg_type = msg.get("type", "unknown")
                content = msg.get("content", "")
            else:
                msg_type = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", "")

            # Unescape literal \n sequences from LLM output
            if content:
                content = _unescape_newlines(content)

            if msg_type == "ai":
                self.console.print(Markdown(f"**AI**: {content}"))
            elif msg_type in ("human", "user"):
                self.console.print(f"[bold green]Human[/bold green]: {content}")
            elif msg_type == "tool":
                content_str = str(content) if content else ""
                self.console.print(f"[dim]Tool output: {content_str[:200]}...[/dim]")

        self.console.print("=" * 60)
        self.console.print(f"[dim]Thread ID: {result.thread_id}[/dim]")


# ============================================
# Convenience Functions
# ============================================
async def create_client(
    mode: Literal["remote", "local"] = "remote",
    server_url: str | None = None,
    expert_mode: bool = False,
    auto_fallback: bool = False,
) -> OLAVClient:
    """
    Create and connect OLAV client.

    Args:
        mode: Execution mode ("remote" or "local")
        server_url: API server URL (default: from env or http://localhost:8000)
        expert_mode: Enable Expert Mode (for local mode)
        auto_fallback: Auto-fallback to local mode if remote connection fails

    Returns:
        Connected OLAVClient instance
    """
    if server_url is None:
        server_url = os.getenv("OLAV_SERVER_URL", "http://localhost:8000")

    # Construct ServerConfig from server_url parameter
    server_config = ServerConfig(base_url=server_url)

    client = OLAVClient(mode=mode, server_config=server_config)
    await client.connect(expert_mode=expert_mode, auto_fallback=auto_fallback)
    return client
