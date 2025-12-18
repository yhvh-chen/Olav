"""OLAV CLI v2 - Main Entry Point.

A professional-grade CLI for OLAV Network Operations Platform.

Usage:
    olav                          # Interactive REPL
    olav query "check BGP state"  # Single query
    olav init all                 # Initialize all infrastructure
    olav init schema              # Initialize schema indexes only
    olav init netbox              # Import NetBox inventory
    olav inspect run daily-check  # Run inspection
    olav doc search "BGP config"  # Search documents
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

# Ensure project root is in sys.path for config module import
# This allows importing 'config.settings' from src/olav/core/llm.py
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import typer
from rich.console import Console

if TYPE_CHECKING:
    from olav.cli.thin_client import ClientConfig

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ============================================
# App Definition
# ============================================
app = typer.Typer(
    name="olav",
    help="OLAV (NetAIChatOps)",
    add_completion=True,
    no_args_is_help=False,
)

console = Console()


# ============================================
# Helper: Load .env file
# ============================================
def _load_env_file() -> dict[str, str]:
    """Load .env file from current directory and return as dict."""
    env_path = Path.cwd() / ".env"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def _load_credentials_file() -> dict[str, str]:
    """Load credentials from ~/.olav/credentials file."""
    credentials_path = Path.home() / ".olav" / "credentials"
    credentials: dict[str, str] = {}
    if credentials_path.exists():
        with open(credentials_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    credentials[key.strip()] = value.strip()
    return credentials


def _get_config_from_env(server_url: str | None = None) -> tuple[ClientConfig, str | None]:
    """Get ClientConfig and auth_token from environment/.env/credentials files.

    Token lookup priority:
        1. OLAV_API_TOKEN environment variable
        2. OLAV_API_TOKEN from .env file
        3. OLAV_SESSION_TOKEN from ~/.olav/credentials (session token from register)

    Args:
        server_url: Optional server URL override from CLI

    Returns:
        Tuple of (ClientConfig, auth_token)
    """
    import os

    from olav.cli.thin_client import ClientConfig

    env_vars = _load_env_file()
    credentials = _load_credentials_file()

    # Get server URL: CLI arg > env var > .env file > derived from port > default
    if not server_url:
        server_url = os.getenv("OLAV_SERVER_URL") or env_vars.get("OLAV_SERVER_URL")

    # If OLAV_SERVER_URL isn't set, but the project provides OLAV_SERVER_PORT (common in Docker setups),
    # derive the base URL so `uv run olav` works out of the box.
    if not server_url:
        server_port = os.getenv("OLAV_SERVER_PORT") or env_vars.get("OLAV_SERVER_PORT")
        if server_port and str(server_port).strip():
            server_url = f"http://127.0.0.1:{str(server_port).strip()}"

    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url

    # Get auth token with priority:
    # 1. Environment variable (explicit override)
    # 2. .env file (project-level config)
    # 3. ~/.olav/credentials session token (registered client)
    auth_token = (
        os.getenv("OLAV_API_TOKEN")
        or env_vars.get("OLAV_API_TOKEN")
        or credentials.get("OLAV_SESSION_TOKEN")
    )

    return config, auth_token


def _persist_server_url_to_config(server_url: str) -> None:
    """Persist the server URL to ~/.olav/config.toml.

    This enables running subsequent commands without passing --server,
    as ClientConfig.from_file() will pick it up.
    """
    config_path = Path.home() / ".olav" / "config.toml"
    config_path.parent.mkdir(exist_ok=True)

    timeout_value: int | None = None
    if config_path.exists():
        try:
            import tomllib

            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            server = data.get("server", {})
            timeout_value = server.get("timeout")
        except Exception:
            # If the file is unreadable, overwrite with a minimal config.
            timeout_value = None

    with open(config_path, "w", encoding="utf-8") as f:
        f.write("[server]\n")
        f.write(f'url = "{server_url}"\n')
        if timeout_value is not None:
            f.write(f"timeout = {timeout_value}\n")


# ============================================
# Shared Options
# ============================================
ServerOption = Annotated[
    str | None,
    typer.Option(
        "--server",
        help="API server URL (defaults to OLAV_SERVER_URL or ~/.olav/config.toml; fallback: http://localhost:8000)",
        envvar="OLAV_SERVER_URL",
    ),
]

# Mode options: -S (standard) and -e (expert) are mutually exclusive
StandardModeOption = Annotated[
    bool,
    typer.Option(
        "--standard", "-S",
        help="Standard mode: fast path with single tool calls (default)",
    ),
]

ExpertModeOption = Annotated[
    str | None,
    typer.Option(
        "--expert", "-e",
        help="Expert mode: Supervisor-Driven deep dive with L1-L4 layer analysis. Optionally accepts a query string.",
    ),
]

VerboseOption = Annotated[
    bool,
    typer.Option(
        "--verbose", "-v",
        help="Show detailed output",
    ),
]

YoloOption = Annotated[
    bool,
    typer.Option(
        "--yolo", "-y",
        help="Skip HITL approval prompts (auto-approve all write operations)",
    ),
]

JsonOption = Annotated[
    bool,
    typer.Option(
        "--json", "-j",
        help="Output as JSON",
    ),
]

# Debug Option
DebugOption = Annotated[
    bool,
    typer.Option(
        "--debug", "-D",
        help="Enable debug mode: show LLM calls, tool invocations, and graph states",
    ),
]

# Init Options (deprecated - use 'olav init' subcommands instead)
InitOption = Annotated[
    bool,
    typer.Option(
        "--init",
        help="[DEPRECATED] Use 'olav init all' instead",
        hidden=True,
    ),
]

InitNetBoxOption = Annotated[
    bool,
    typer.Option(
        "--init-netbox",
        help="[DEPRECATED] Use 'olav init netbox' instead",
        hidden=True,
    ),
]

InitStatusOption = Annotated[
    bool,
    typer.Option(
        "--init-status",
        help="[DEPRECATED] Use 'olav init status' instead",
        hidden=True,
    ),
]


def _resolve_mode(standard: bool, expert: str | None) -> str:
    """Resolve mode from mutually exclusive flags.

    Args:
        standard: -S/--standard flag
        expert: -e/--expert flag (can be bool-like or contain query string)

    Returns:
        Mode string: "standard" or "expert"

    Raises:
        typer.BadParameter: If both flags are set
    """
    # expert can be a string (query) or None
    expert_enabled = expert is not None
    
    if standard and expert_enabled:
        msg = "Cannot use both --standard and --expert. Choose one."
        raise typer.BadParameter(msg)

    if expert_enabled:
        return "expert"

    # Default to standard
    return "standard"


# ============================================
# CLI Query Argument - NOTE: Cannot use Annotated for variadic args
# ============================================

CliOption = Annotated[
    bool,
    typer.Option(
        "--cli",
        help="Single-shot CLI mode: execute query and exit (requires -q/--query argument)",
    ),
]

QueryOption = Annotated[
    str | None,
    typer.Option(
        "--query", "-q",
        help="Query text for single-shot mode (use with --cli or alone)",
    ),
]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    query: QueryOption = None,
    server: ServerOption = None,
    standard: StandardModeOption = False,
    expert: ExpertModeOption = None,
    verbose: VerboseOption = False,
    debug: DebugOption = False,
    json_output: JsonOption = False,
    yolo: YoloOption = False,
    init: InitOption = False,
    init_netbox: InitNetBoxOption = False,
    init_status: InitStatusOption = False,
    cli: CliOption = False,
) -> None:
    """OLAV (NetAIChatOps).

    Run without arguments to launch interactive dashboard.
    Use -q/--query or -e/--expert with query for single-shot queries.

    Examples:
        olav                        # Interactive dashboard
        olav -q "check BGP"         # Single query (standard mode)
        olav -e "diagnose OSPF"     # Single query (expert mode)
        olav -q "check BGP" -v      # Verbose with ThinkingTree
        olav -q "check BGP" -D      # With debug timing info
        olav -q "check BGP" -j      # JSON output for scripting
    """
    # Configure LangSmith tracing if enabled
    from olav.core.llm import configure_langsmith
    if configure_langsmith():
        if not json_output:
            console.print("[dim]🔍 LangSmith tracing enabled[/dim]")

    # Handle deprecated --init flags (redirect to new subcommands)
    if init or init_status:
        console.print("[yellow]⚠ --init/--init-status are deprecated. Use 'olav init all' or 'olav init status' instead.[/yellow]")
        if init_status:
            _show_init_status()
        else:
            _init_infrastructure(components=["postgres", "schema", "rag"], force=True)
        raise typer.Exit()

    # Handle deprecated --init-netbox (redirect to new subcommand)
    if init_netbox:
        console.print("[yellow]⚠ --init-netbox is deprecated. Use 'olav init netbox' instead.[/yellow]")
        _init_netbox_inventory(force=False)
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        # Resolve mode from flags
        mode = _resolve_mode(standard, expert)

        # query_text priority: -e "query" > -q "query"
        # If expert contains a query string, use it; otherwise use -q
        query_text = query
        if expert is not None and expert:
            # -e was given with a query string
            query_text = expert

        if cli or query_text:
            # Single-shot execution mode using Dashboard batch
            if cli and not query_text:
                console.print("[red]Error: --cli requires a query argument[/red]")
                console.print('[dim]Usage: olav --cli -q "Query BGP status"[/dim]')
                raise typer.Exit(code=1)

            # Use Dashboard batch mode for single query (unified path)
            asyncio.run(_run_single_query_via_dashboard(
                query_text, server, mode,
                verbose=verbose,
                debug=debug,
                json_output=json_output,
                yolo=yolo,
            ))
        else:
            # Default: launch full-screen TUI dashboard
            asyncio.run(_run_dashboard(server, mode, verbose))


async def _run_single_query_via_dashboard(
    query_text: str,
    server_url: str | None,
    mode: str,
    verbose: bool = False,
    debug: bool = False,
    json_output: bool = False,
    yolo: bool = False,
) -> None:
    """Execute a single query using Dashboard batch mode (unified code path).

    This replaces the legacy _single_query function with Dashboard-based execution,
    ensuring consistent behavior between interactive and single-shot modes.
    """
    from olav.cli.display import Dashboard
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        # Single-shot mode should be clean and script-friendly: no big banner.
        dash = Dashboard(client, console, mode=mode, show_banner=False)

        # Show query in non-JSON mode
        if not json_output:
            console.print(f"[bold green]You[/bold green]: {query_text}")
            console.print()

        # Run as single-item batch
        await dash.run_batch(
            [query_text],
            yolo=yolo,
            verbose=verbose,
            debug=debug,
            json_output=json_output,
        )


def _get_project_root():
    """Get project root directory."""
    from pathlib import Path
    # Look for pyproject.toml to find project root
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


async def _run_dashboard(
    server_url: str | None,
    mode: str,
    verbose: bool,
) -> None:
    """Run full-screen TUI dashboard.

    Args:
        server_url: Optional API server URL override
        mode: "standard" or "expert"
        verbose: Show verbose output
    """
    from olav.cli.display import Dashboard
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        dash = Dashboard(client, console, mode=mode)
        try:
            await dash.run()
        except KeyboardInterrupt:
            dash.stop()
            console.print("\n[yellow]Dashboard closed.[/yellow]")


async def _show_status(server_url: str | None) -> None:
    """Show system status information.

    Args:
        server_url: Optional API server URL override
    """
    from rich.panel import Panel

    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    console.print()
    console.print(Panel.fit(
        "[bold cyan]OLAV System Status[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    async with OlavThinClient(config, auth_token=auth_token) as client:
        # Server health
        console.print("[bold]📊 Server Status[/bold]")
        try:
            health = await client.health()
            status_icon = "🟢" if health.status == "healthy" else "🔴"
            console.print(f"  Status:       {status_icon} {health.status}")
            console.print(f"  Version:      {health.version}")
            console.print(f"  Environment:  {health.environment}")
            orchestrator = "✅ Ready" if health.orchestrator_ready else "❌ Not ready"
            console.print(f"  Orchestrator: {orchestrator}")
        except Exception as e:
            console.print(f"  [red]❌ Cannot connect to server: {e}[/red]")
            return

        console.print()

        # Devices
        console.print("[bold]📡 Devices[/bold]")
        try:
            devices = await client.get_device_names()
            console.print(f"  Total: {len(devices)} devices")
            if devices and len(devices) <= 10:
                for device in devices:
                    console.print(f"    • {device}")
            elif devices:
                for device in devices[:5]:
                    console.print(f"    • {device}")
                console.print(f"    ... and {len(devices) - 5} more")
        except Exception as e:
            console.print(f"  [yellow]⚠ Cannot fetch devices: {e}[/yellow]")

        console.print()

        # SuzieQ tables
        console.print("[bold]📊 SuzieQ Tables[/bold]")
        try:
            tables = await client.get_suzieq_tables()
            console.print(f"  Total: {len(tables)} tables")
            if tables and len(tables) <= 10:
                console.print(f"  Tables: {', '.join(tables)}")
            elif tables:
                console.print(f"  Tables: {', '.join(tables[:10])}, ...")
        except Exception as e:
            console.print(f"  [yellow]⚠ Cannot fetch tables: {e}[/yellow]")

    console.print()


async def _interactive_session(
    server_url: str | None,
    mode: str,
    verbose: bool,
) -> None:
    """Run interactive REPL session with prompt_toolkit."""
    from olav.cli.display import HITLPanel, ResultRenderer, ThinkingTree
    from olav.cli.repl import REPLSession, handle_slash_command
    from olav.cli.thin_client import (
        OlavThinClient,
        StreamEventType,
    )

    # Setup - get config and auth token from env/credentials
    config, auth_token = _get_config_from_env(server_url)

    renderer = ResultRenderer(console)
    hitl_panel = HITLPanel(console)

    # Show banner
    console.print()
    console.print("[bold blue]╔═══════════════════════════════════════════════════════════╗[/bold blue]")
    console.print("[bold blue]║[/bold blue]  [bold cyan]OLAV[/bold cyan] - Enterprise Network Operations ChatOps Platform  [bold blue]║[/bold blue]")
    console.print("[bold blue]╚═══════════════════════════════════════════════════════════╝[/bold blue]")
    console.print()
    console.print(f"[dim]Server: {config.server_url}[/dim]")
    console.print(f"[dim]Mode: {mode}[/dim]")
    console.print("[dim]Type /help for commands, Ctrl+R for history search[/dim]")
    console.print()

    async with OlavThinClient(config, auth_token=auth_token) as client:
        # Check server health
        try:
            health = await client.health()
            console.print(f"[green]✅ Connected[/green] (v{health.version})")
            console.print()
        except Exception as e:
            console.print(f"[red]❌ Cannot connect to server: {e}[/red]")
            console.print("[dim]💡 Start server: docker-compose up -d olav-server[/dim]")
            return

        # Create REPL session with prompt_toolkit
        async with REPLSession(client, console, mode) as repl:
            pending_hitl = None

            while True:
                try:
                    # Get input with prompt_toolkit
                    user_input = await repl.prompt(hitl_pending=bool(pending_hitl))

                    if user_input is None:
                        # Ctrl+C or Ctrl+D
                        console.print("\n[yellow]Goodbye! 👋[/yellow]")
                        break

                    if not user_input:
                        continue

                    # Handle slash commands
                    if user_input.startswith("/"):
                        should_exit = handle_slash_command(repl, user_input)
                        if should_exit:
                            break
                        continue

                    # Handle HITL response
                    if pending_hitl:
                        from olav.cli.thin_client import HITLRequest

                        # Parse user decision
                        if user_input.lower() in ("y", "yes", "approve"):
                            decision = "Y"
                        elif user_input.lower() in ("n", "no", "reject", "abort"):
                            decision = "N"
                        else:
                            decision = user_input

                        result = await client.resume(
                            thread_id=repl.thread_id,
                            decision=decision,
                            workflow_type=pending_hitl["workflow_type"],
                        )

                        if result.interrupted:
                            # Still interrupted (plan modified, needs re-approval)
                            console.print("[yellow]⏸️ Plan modified, requires re-approval[/yellow]")
                            pending_hitl = {
                                "workflow_type": result.workflow_type,
                                "execution_plan": result.execution_plan,
                                "todos": result.todos,
                            }
                            hitl_panel.display_execution_plan(
                                HITLRequest(
                                    plan_id="",
                                    workflow_type=result.workflow_type or "",
                                    operation="",
                                    target_device="",
                                    commands=[],
                                    risk_level="medium",
                                    reasoning="",
                                    execution_plan=result.execution_plan,
                                    todos=result.todos,
                                )
                            )
                        else:
                            pending_hitl = None
                            if result.content:
                                renderer.render_message(result.content)

                        continue

                    # Normal query execution with streaming
                    console.print()

                    with ThinkingTree(console) as tree:
                        content_buffer = ""
                        thinking_started = False

                        async for event in client.chat_stream(user_input, repl.thread_id, repl.mode):
                            event_type = event.type
                            data = event.data

                            if event_type == StreamEventType.THINKING:
                                thinking = data.get("thinking", {})
                                tree.add_thinking(thinking.get("content", ""))
                                thinking_started = True

                            elif event_type == StreamEventType.TOOL_START:
                                # Finalize thinking before tool calls
                                if thinking_started:
                                    tree.finalize_thinking()
                                    thinking_started = False
                                tool_info = data.get("tool", {})
                                tree.add_tool_call(
                                    tool_info.get("display_name") or tool_info.get("name", "unknown"),
                                    tool_info.get("args", {}),
                                )

                            elif event_type == StreamEventType.TOOL_END:
                                tool_info = data.get("tool", {})
                                tree.mark_tool_complete(
                                    tool_info.get("name", "unknown"),
                                    success=tool_info.get("success", True),
                                )

                            elif event_type == StreamEventType.TOKEN:
                                # Finalize thinking before tokens (response started)
                                if thinking_started:
                                    tree.finalize_thinking()
                                    thinking_started = False
                                content_buffer += data.get("content", "")

                            elif event_type == StreamEventType.MESSAGE:
                                content_buffer = data.get("content", content_buffer)

                            elif event_type == StreamEventType.INTERRUPT:
                                # HITL interrupt
                                from olav.cli.thin_client import HITLRequest

                                pending_hitl = {
                                    "workflow_type": data.get("workflow_type"),
                                    "execution_plan": data.get("execution_plan"),
                                    "todos": data.get("todos"),
                                }

                                hitl_panel.display(
                                    HITLRequest(
                                        plan_id=data.get("plan_id", ""),
                                        workflow_type=data.get("workflow_type", ""),
                                        operation=data.get("operation", ""),
                                        target_device=data.get("target_device", ""),
                                        commands=data.get("commands", []),
                                        risk_level=data.get("risk_level", "medium"),
                                        reasoning=data.get("reasoning", ""),
                                        execution_plan=data.get("execution_plan"),
                                        todos=data.get("todos"),
                                    )
                                )
                                console.print()
                                console.print("[yellow]⚠️ Your approval is needed (Y/N/modification):[/yellow]")
                                break

                            elif event_type == StreamEventType.ERROR:
                                error_info = data.get("error", {})
                                error_msg = error_info.get("message") if isinstance(error_info, dict) else str(error_info)
                                renderer.render_error(error_msg or "Unknown error")
                                break

                    # Display final response if not interrupted
                    if not pending_hitl and content_buffer:
                        renderer.render_message(content_buffer)
                        console.print()

                except KeyboardInterrupt:
                    console.print("\n[dim]Use /exit to quit or Ctrl+D[/dim]")
                    continue


# ============================================
# Register Command (Client Registration)
# ============================================
@app.command()
def register(
    name: Annotated[
        str,
        typer.Option(
            "--name", "-n",
            help="Client name for identification (e.g., 'alice-laptop', 'ci-runner-1')",
        ),
    ],
    token: Annotated[
        str | None,
        typer.Option(
            "--token", "-t",
            help="Master token (from server startup). If not provided, uses OLAV_API_TOKEN env var.",
        ),
    ] = None,
    server: ServerOption = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save/--no-save",
            help="Save session token to ~/.olav/credentials (default: save)",
        ),
    ] = True,
) -> None:
    """Register this client with the OLAV server and get a session token.

    This command:
    1. Connects to the OLAV server
    2. Authenticates with the master token
    3. Receives a unique session token for this client
    4. Optionally saves the session token to ~/.olav/credentials

    Example:
        olav register --name "my-laptop" --token "abc123..."
        olav register -n ci-runner --server http://server:8000
    """
    asyncio.run(_register_client(name, token, server, save))


async def _register_client(
    client_name: str,
    master_token: str | None,
    server_url: str | None,
    save_credentials: bool,
) -> None:
    """Execute client registration."""
    from pathlib import Path

    from olav.cli.thin_client import OlavThinClient

    # Get config and token
    config, env_token = _get_config_from_env(server_url)

    # Use provided token or fall back to env
    token = master_token or env_token
    if not token:
        console.print("[red]Error: No master token provided.[/red]")
        console.print("Provide --token or set OLAV_API_TOKEN environment variable.")
        raise typer.Exit(1)

    console.print(f"[bold]Registering client '{client_name}'...[/bold]")
    console.print(f"Server: {config.server_url}")

    try:
        async with OlavThinClient(config, auth_token=None) as client:
            # First check server health
            try:
                health = await client.health()
                if health.status != "healthy":
                    console.print(f"[yellow]Warning: Server status is '{health.status}'[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: Cannot connect to server: {e}[/red]")
                raise typer.Exit(1)

            # Register client
            result = await client.register(client_name, token)

            session_token = result["session_token"]
            client_id = result["client_id"]
            expires_at = result["expires_at"]

            console.print()
            console.print("[green]✅ Registration successful![/green]")
            console.print(f"   Client ID: {client_id}")
            console.print(f"   Client Name: {client_name}")
            console.print(f"   Expires: {expires_at}")
            console.print()

            # Persist server URL so subsequent commands can omit --server.
            # Do this only when a server URL was explicitly provided/resolved for registration.
            if server_url:
                _persist_server_url_to_config(config.server_url)
                console.print(f"[dim]Server URL saved to {Path.home() / '.olav' / 'config.toml'}[/dim]")

            if save_credentials:
                # Save to ~/.olav/credentials
                credentials_dir = Path.home() / ".olav"
                credentials_dir.mkdir(exist_ok=True)
                credentials_file = credentials_dir / "credentials"

                # Load existing or create new
                credentials: dict[str, str] = {}
                if credentials_file.exists():
                    with open(credentials_file) as f:
                        for line in f:
                            line = line.strip()
                            if line and "=" in line and not line.startswith("#"):
                                k, _, v = line.partition("=")
                                credentials[k.strip()] = v.strip()

                # Update with session token
                credentials["OLAV_SESSION_TOKEN"] = session_token
                credentials["OLAV_CLIENT_ID"] = client_id
                credentials["OLAV_CLIENT_NAME"] = client_name

                # Write back
                with open(credentials_file, "w") as f:
                    f.write("# OLAV Client Credentials\n")
                    f.write("# Auto-generated by 'olav register'\n\n")
                    for k, v in credentials.items():
                        f.write(f"{k}={v}\n")

                console.print(f"[dim]Credentials saved to {credentials_file}[/dim]")
                console.print()
                console.print("[bold]To use the session token:[/bold]")
                console.print(f"  export OLAV_API_TOKEN={session_token}")
                console.print("  # Or the CLI will auto-load from ~/.olav/credentials")

    except Exception as e:
        if "401" in str(e):
            console.print("[red]Error: Invalid master token.[/red]")
        else:
            console.print(f"[red]Error: Registration failed: {e}[/red]")
        raise typer.Exit(1)


# ============================================
# Status Command - System Health Check
# ============================================
@app.command()
def status(
    server: ServerOption = None,
    verbose: VerboseOption = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Check system health and infrastructure status.

    Queries the server's /health/detailed API endpoint to get comprehensive
    status of all infrastructure components:
    
    - Server connectivity and authentication
    - PostgreSQL (LangGraph checkpointer)
    - OpenSearch (vector search, schema index)
    - Redis (optional, session cache)
    - NetBox (optional, SSOT)
    - LLM provider connectivity
    - SuzieQ parquet data availability

    Example:
        olav status
        olav status -v          # verbose output
        olav status --json      # JSON output for scripting
    """
    asyncio.run(_run_doctor(server, verbose, json_output))


@app.command(hidden=True)
def doctor(
    server: ServerOption = None,
    verbose: VerboseOption = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """[Deprecated] Use 'olav status' instead.
    
    This command is deprecated and will be removed in a future version.
    Please use 'olav status' for system health checks.
    """
    console.print("[yellow]⚠️  Warning: 'doctor' command is deprecated. Use 'olav status' instead.[/yellow]")
    asyncio.run(_run_doctor(server, verbose, json_output))


async def _run_doctor(
    server_url: str | None,
    verbose: bool,
    json_output: bool = False,
) -> None:
    """Run comprehensive system health check via Server API."""
    import json as json_lib

    import httpx

    from rich.panel import Panel
    from rich.table import Table

    from olav.cli.thin_client import OlavThinClient

    if not json_output:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]🩺 OLAV System Health Check[/bold cyan]",
            border_style="cyan",
        ))
        console.print()

    try:
        config, auth_token = _get_config_from_env(server_url)
        credentials = _load_credentials_file()

        if not json_output:
            console.print(f"[dim]Server URL: {config.server_url}[/dim]")

        async with OlavThinClient(config, auth_token=auth_token) as client:
            # Get comprehensive health status from Server API
            try:
                if not json_output:
                    console.print("[dim]Requesting /health/detailed endpoint...[/dim]")
                response = await client._client.get("/health/detailed")
                if response.status_code == 200:
                    health_data = response.json()
                else:
                    console.print(f"[red]Server returned error: HTTP {response.status_code}[/red]")
                    if verbose:
                        console.print(f"[dim]Response: {response.text}[/dim]")
                    raise typer.Exit(1)
            except httpx.HTTPError as he:
                console.print(f"[red]Cannot connect to server: {he}[/red]")
                console.print("[yellow]💡 Tip: Make sure the server is running:[/yellow]")
                console.print("   docker-compose up -d olav-server")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                if verbose:
                    import traceback
                    console.print(traceback.format_exc())
                raise typer.Exit(1)

            # Get auth status
            user_info = None
            auth_status_code = None
            if auth_token:
                try:
                    auth_response = await client._client.get("/me")
                    auth_status_code = auth_response.status_code
                    if auth_response.status_code == 200:
                        user_info = auth_response.json()
                except Exception:
                    pass

            # JSON output mode
            if json_output:
                output_data = {
                    "server": {
                        "url": config.server_url,
                        "status": health_data.get("status"),
                        "version": health_data.get("version"),
                    },
                    "auth": {
                        "authenticated": user_info is not None,
                        "user": user_info,
                        "client_id": credentials.get("OLAV_CLIENT_ID"),
                    },
                    "components": health_data.get("components", {}),
                }
                console.print(json_lib.dumps(output_data, indent=2))
                return

            # Build results table from server response
            results: list[tuple[str, str, str]] = []
            components = health_data.get("components", {})

            # Server status
            server_comp = components.get("server", {})
            server_status = "✅ Connected" if health_data.get("status") == "healthy" else "⚠️ Degraded"
            orch_ready = "ready" if server_comp.get("orchestrator_ready") else "not ready"
            results.append(("OLAV Server", server_status, f"v{health_data.get('version')} ({orch_ready})"))

            # Auth status
            if user_info:
                auth_detail = f"{user_info.get('username', 'unknown')} ({user_info.get('role', '?')})"
                results.append(("Authentication", "✅ Authenticated", auth_detail))
            elif auth_token:
                if auth_status_code in (401, 404, 405):
                    results.append(("Authentication", "ℹ️ Auth Disabled", f"Server response: {auth_status_code}"))
                else:
                    results.append(("Authentication", "⚠️ Token Invalid", f"Token provided but not valid (HTTP {auth_status_code})"))
            else:
                results.append(("Authentication", "⏭️ Not Configured", "Run 'olav register'"))

            # PostgreSQL
            pg_comp = components.get("postgresql", {})
            pg_status = pg_comp.get("status", "unknown")
            if pg_status == "connected":
                pg_version = pg_comp.get("version", "")[:50]
                results.append(("PostgreSQL", "✅ Connected", pg_version))
            elif pg_status == "not_initialized":
                results.append(("PostgreSQL", "⚠️ Not Initialized", "Run 'olav init postgres'"))
            else:
                results.append(("PostgreSQL", "❌ Failed", pg_comp.get("error", "Unknown error")[:60]))

            # OpenSearch
            os_comp = components.get("opensearch", {})
            os_status = os_comp.get("status", "unknown")
            if os_status in ("green", "yellow"):
                nodes = os_comp.get("nodes", 0)
                results.append(("OpenSearch", f"✅ {os_status.upper()}", f"{nodes} node(s)"))
            elif os_status == "red":
                results.append(("OpenSearch", "⚠️ RED", "Cluster unhealthy"))
            elif os_status == "auth_failed":
                results.append(("OpenSearch", "❌ Auth Failed", "Check credentials"))
            else:
                results.append(("OpenSearch", "❌ Failed", os_comp.get("error", "Unknown")[:60]))

            # Redis (optional)
            redis_comp = components.get("redis", {})
            redis_status = redis_comp.get("status", "unknown")
            if redis_status == "connected":
                results.append(("Redis (optional)", "✅ Connected", "Distributed cache enabled"))
            elif redis_status == "not_configured":
                results.append(("Redis (optional)", "⏭️ Not Configured", redis_comp.get("note", "Using in-memory cache")))
            else:
                results.append(("Redis (optional)", "⏭️ Not Available", redis_comp.get("fallback", "Using memory cache")))

            # NetBox (optional)
            nb_comp = components.get("netbox", {})
            nb_status = nb_comp.get("status", "unknown")
            if nb_status == "connected":
                results.append(("NetBox", "✅ Connected", nb_comp.get("url", "")))
            elif nb_status == "not_configured":
                results.append(("NetBox", "⏭️ Not Configured", "Set NETBOX_URL and NETBOX_TOKEN"))
            elif nb_status == "auth_failed":
                results.append(("NetBox", "⚠️ Auth Failed", f"HTTP {nb_comp.get('http_code', '?')}"))
            else:
                results.append(("NetBox", "❌ Failed", nb_comp.get("error", "Unknown")[:60]))

            # LLM Provider
            llm_comp = components.get("llm", {})
            llm_status = llm_comp.get("status", "unknown")
            provider = llm_comp.get("provider", "unknown")
            if llm_status == "connected":
                if provider == "ollama":
                    models = llm_comp.get("models", [])
                    results.append(("LLM (Ollama)", "✅ Connected", f"Models: {', '.join(models)}"))
                else:
                    model = llm_comp.get("model", "")
                    results.append((f"LLM ({provider.title()})", "✅ Connected", f"Model: {model}"))
            elif llm_status == "configured":
                model = llm_comp.get("model", "")
                results.append((f"LLM ({provider.title()})", "✅ Configured", f"Model: {model}"))
            elif llm_status == "no_key":
                results.append((f"LLM ({provider.title()})", "⚠️ No API Key", "Set LLM_API_KEY"))
            else:
                results.append(("LLM", "❌ Failed", llm_comp.get("error", "Unknown")[:60]))

            # SuzieQ Data
            sq_comp = components.get("suzieq", {})
            sq_status = sq_comp.get("status", "unknown")

            # Newer server schema: {status: healthy|degraded|failed, gui: {...}, data: {...}}
            if sq_status in ("healthy", "available"):
                data = sq_comp.get("data", {}) if isinstance(sq_comp, dict) else {}
                data_status = data.get("status", "unknown")
                age_seconds = data.get("age_seconds")
                details = f"data={data_status}"
                if age_seconds is not None:
                    details += f" age={age_seconds}s"
                results.append(("SuzieQ Data", "✅ Healthy", details))
            elif sq_status == "degraded":
                gui = sq_comp.get("gui", {}) if isinstance(sq_comp, dict) else {}
                data = sq_comp.get("data", {}) if isinstance(sq_comp, dict) else {}
                gui_status = gui.get("status", "unknown")
                data_status = data.get("status", "unknown")
                age_seconds = data.get("age_seconds")
                details = f"gui={gui_status} data={data_status}"
                if age_seconds is not None:
                    details += f" age={age_seconds}s"
                results.append(("SuzieQ Data", "⚠️ Degraded", details))
            elif sq_status == "failed":
                results.append(("SuzieQ Data", "❌ Error", sq_comp.get("error", "Unknown")[:60]))
            else:
                # Backward compatible fallback
                results.append(("SuzieQ Data", "❌ Error", sq_comp.get("error", "Unknown")[:60]))

            # Display results table
            console.print()
            table = Table(title="System Components", show_header=True, header_style="bold")
            table.add_column("Component", style="cyan")
            table.add_column("Status")
            table.add_column("Details", style="dim")

            all_ok = True
            for name, status, details in results:
                if "❌" in status:
                    all_ok = False
                    status_style = "red"
                elif "⚠️" in status:
                    status_style = "yellow"
                elif "⏭️" in status:
                    status_style = "dim"
                else:
                    status_style = "green"

                if verbose or "❌" in status or "⚠️" in status:
                    table.add_row(name, f"[{status_style}]{status}[/{status_style}]", details)
                else:
                    table.add_row(name, f"[{status_style}]{status}[/{status_style}]", "")

            console.print(table)
            console.print()

            # Verbose SuzieQ details (what data was detected)
            if verbose:
                sq_comp = components.get("suzieq", {})
                if isinstance(sq_comp, dict):
                    gui = sq_comp.get("gui", {}) if isinstance(sq_comp.get("gui"), dict) else {}
                    data = sq_comp.get("data", {}) if isinstance(sq_comp.get("data"), dict) else {}

                    def _fmt_list(values: list[str] | None) -> str:
                        if not values:
                            return "(none)"
                        return ", ".join(values)

                    details_lines = [
                        f"status: {sq_comp.get('status', 'unknown')}",
                        f"gui: {gui.get('status', 'unknown')} ({gui.get('url', '')})",
                        f"parquet_dir: {data.get('parquet_dir', '')}",
                        f"data: {data.get('status', 'unknown')} age={data.get('age_seconds', 'n/a')}s max={data.get('max_age_seconds', 'n/a')}s",
                        f"host_dirs: {data.get('host_dirs', data.get('parquet_files', 0))}",
                        f"namespaces_sample: {_fmt_list(data.get('namespaces_sample'))}",
                        f"hostnames_sample: {_fmt_list(data.get('hostnames_sample'))}",
                    ]
                    if data.get("newest_parquet_utc"):
                        details_lines.insert(4, f"newest_parquet_utc: {data.get('newest_parquet_utc')}")
                    if data.get("newest_host_parquet_files") is not None:
                        details_lines.append(f"newest_host_parquet_files: {data.get('newest_host_parquet_files')}")

                    console.print(Panel.fit(
                        "\n".join(details_lines),
                        title="SuzieQ details",
                        border_style="cyan",
                    ))
                    console.print()

            if all_ok:
                console.print("[green]✅ All systems operational![/green]")
            else:
                console.print("[yellow]⚠️ Some issues detected. Use -v for details.[/yellow]")
            console.print()

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error during health check: {e}[/red]")
        raise typer.Exit(1)


# ============================================
# Init Commands (Subcommand Group)
# ============================================
init_app = typer.Typer(
    name="init",
    help="Initialize OLAV infrastructure and indexes",
)
app.add_typer(init_app, name="init")


@init_app.command("all")
def init_all_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force reset all indexes"),
    ] = False,
) -> None:
    """Initialize all infrastructure components.

    Initializes PostgreSQL, all schema indexes, and RAG indexes.
    Use --force to delete and recreate existing indexes.

    Examples:
        olav init all           # Initialize (skip existing)
        olav init all --force   # Force reset all
    """
    _init_infrastructure(components=["postgres", "schema", "rag"], force=force)


@init_app.command("schema")
def init_schema_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force reset schema indexes"),
    ] = False,
) -> None:
    """Initialize schema indexes only.

    Initializes SuzieQ, OpenConfig, and NetBox schema indexes.
    Preserves RAG indexes (episodic-memory, docs).

    Examples:
        olav init schema           # Initialize schema indexes
        olav init schema --force   # Force reset schema indexes
    """
    _init_infrastructure(components=["schema"], force=force)


@init_app.command("rag")
def init_rag_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force reset RAG indexes"),
    ] = False,
) -> None:
    """Initialize RAG indexes only.

    Initializes episodic memory and document indexes.
    Preserves schema indexes.

    Examples:
        olav init rag           # Initialize RAG indexes
        olav init rag --force   # Force reset RAG indexes
    """
    _init_infrastructure(components=["rag"], force=force)


@init_app.command("postgres")
def init_postgres_cmd() -> None:
    """Initialize PostgreSQL Checkpointer tables.

    Creates or verifies LangGraph Checkpointer tables in PostgreSQL.

    Examples:
        olav init postgres
    """
    _init_infrastructure(components=["postgres"], force=False)


@init_app.command("netbox")
def init_netbox_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force import even if devices exist"),
    ] = False,
    csv: Annotated[
        str,
        typer.Option("--csv", help="Path to CSV inventory file (default: config/inventory.csv)"),
    ] = "config/inventory.csv",
) -> None:
    """Initialize NetBox inventory and device configs.

    1. Checks NetBox connectivity
    2. Imports devices from CSV file (default: config/inventory.csv)
    3. Generates device configurations

    Use --force to import even if NetBox already has devices.
    Use --csv to specify a custom inventory file path.

    Examples:
        olav init netbox                                    # Import from default CSV
        olav init netbox --force                            # Force import
        olav init netbox --csv /data/custom_devices.csv     # Custom CSV path
        olav init netbox --csv /data/custom.csv --force     # Custom CSV with force
    """
    _init_netbox_inventory(force=force, csv_path=csv)


@init_app.command("status")
def init_status_cmd() -> None:
    """Show current index status.

    Displays document counts for all OLAV indexes.

    Examples:
        olav init status
    """
    _show_init_status()


def _init_infrastructure(components: list[str], force: bool = False) -> None:
    """Run infrastructure initialization for specified components.

    Args:
        components: List of components to initialize ("postgres", "schema", "rag")
        force: Force reset indexes
    """
    from rich.panel import Panel

    console.print()
    console.print(Panel.fit(
        "[bold cyan]OLAV Infrastructure Initialization[/bold cyan]",
        border_style="blue",
    ))
    console.print()

    import sys as _sys
    original_argv = _sys.argv.copy()

    # Build command line arguments based on components
    args = ["olav.etl.init_all"]

    if "postgres" in components and "schema" not in components and "rag" not in components:
        args.append("--postgres")
    elif "schema" in components and "rag" not in components:
        args.extend(["--suzieq", "--openconfig", "--netbox"])
    elif "rag" in components and "schema" not in components:
        args.extend(["--episodic", "--syslog"])
        # Also init docs
        try:
            from olav.etl.init_docs import main as init_docs_main
            console.print("[dim]Initializing document RAG index...[/dim]")
            init_docs_main(force=force)
            console.print("[green]  ✓ Document RAG index ready[/green]")
        except Exception as e:
            console.print(f"[yellow]  ⚠ Document index init failed: {e}[/yellow]")

    if force:
        args.append("--force")

    _sys.argv = args

    try:
        from olav.etl.init_all import main as init_main
        init_main()
    except SystemExit as e:
        if e.code != 0:
            console.print()
            console.print("[red]❌ Initialization failed[/red]")
            raise typer.Exit(code=1)
    finally:
        _sys.argv = original_argv

    console.print()
    console.print("[green]✅ Initialization complete[/green]")


def _init_netbox_inventory(force: bool = False, csv_path: str = "config/inventory.csv") -> None:
    """Initialize NetBox inventory (import devices + generate configs).

    Args:
        force: Force import even if NetBox already has devices
        csv_path: Path to CSV file (relative to project root or absolute)
    """
    import os
    import subprocess

    from rich.panel import Panel

    console.print()
    console.print(Panel.fit(
        "[bold cyan]OLAV NetBox Initialization[/bold cyan]",
        border_style="blue",
    ))
    console.print()

    # Resolve CSV path
    if os.path.isabs(csv_path):
        csv_full_path = csv_path
    else:
        csv_full_path = os.path.join(str(_get_project_root()), csv_path)

    # Verify CSV exists
    if not os.path.exists(csv_full_path):
        console.print(f"[red]❌ CSV file not found: {csv_path}[/red]")
        console.print(f"[dim]Full path: {csv_full_path}[/dim]")
        raise typer.Exit(code=1)

    # 1. Check NetBox connectivity
    console.print("[dim]Checking NetBox connectivity...[/dim]")
    uv_path = shutil.which("uv") or "uv"
    try:
        result = subprocess.run(
            [uv_path, "run", "python", "scripts/check_netbox.py", "--autocreate"],
            check=False, capture_output=True,
            text=True,
            cwd=str(_get_project_root()),
        )
        if result.returncode != 0:
            console.print("[red]❌ NetBox connectivity check failed[/red]")
            console.print(f"[dim]{result.stderr or result.stdout}[/dim]")
            raise typer.Exit(code=1)
        console.print("[green]  ✓ NetBox connectivity OK[/green]")
    except FileNotFoundError:
        console.print("[yellow]  ⚠ NetBox check script not found, skipping[/yellow]")

    # 2. Import inventory to NetBox
    console.print("[dim]Importing inventory to NetBox...[/dim]")
    try:
        env = os.environ.copy()
        env["NETBOX_CSV_PATH"] = csv_full_path
        if force:
            env["NETBOX_INGEST_FORCE"] = "true"

        result = subprocess.run(
            [uv_path, "run", "python", "-m", "olav.etl.netbox_ingest"],
            check=False, capture_output=True,
            text=True,
            cwd=str(_get_project_root()),
            env=env,
        )
        if result.returncode == 0:
            console.print("[green]  ✓ NetBox inventory imported[/green]")
        elif result.returncode == 99:
            if force:
                console.print("[green]  ✓ NetBox inventory force imported[/green]")
            else:
                console.print("[dim]  ✓ NetBox already has devices, skipped (use --force to override)[/dim]")
        else:
            console.print("[red]❌ NetBox inventory import failed[/red]")
            console.print(f"[dim]{result.stderr or result.stdout}[/dim]")
            raise typer.Exit(code=1)
    except FileNotFoundError:
        console.print("[yellow]  ⚠ NetBox ingest script not found, skipping[/yellow]")

    # 3. Generate device configs
    console.print("[dim]Generating device configs...[/dim]")
    try:
        from olav.etl.generate_configs import main as generate_configs_main
        generate_configs_main()
        console.print("[green]  ✓ Device configs generated[/green]")
    except Exception as e:
        console.print(f"[yellow]  ⚠ Config generation failed: {e}[/yellow]")

    console.print()
    console.print("[green]✅ NetBox initialization complete[/green]")


def _show_init_status() -> None:
    """Show current index status."""
    from rich.panel import Panel

    console.print()
    console.print(Panel.fit(
        "[bold cyan]OLAV Index Status[/bold cyan]",
        border_style="blue",
    ))
    console.print()

    import sys as _sys
    original_argv = _sys.argv.copy()
    _sys.argv = ["olav.etl.init_all", "--status"]

    try:
        from olav.etl.init_all import main as init_main
        init_main()
    except SystemExit:
        pass  # Status doesn't fail
    finally:
        _sys.argv = original_argv


# ============================================
# Session Commands (Subcommand Group)
# ============================================
session_app = typer.Typer(
    name="session",
    help="Manage auth sessions and conversation threads",
)
app.add_typer(session_app, name="session")


@session_app.command("clients")
def session_clients(
    server: ServerOption = None,
) -> None:
    """List active client sessions (admin only).

    Shows all registered clients currently connected to the server.
    Requires master token (admin only).
    """
    asyncio.run(_session_clients(server))


async def _session_clients(server_url: str | None) -> None:
    """List active client sessions."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    if not auth_token:
        console.print("[red]Error: No authentication token found.[/red]")
        raise typer.Exit(1)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get("/auth/sessions")
            response.raise_for_status()
            data = response.json()

            sessions = data.get("sessions", [])
            total = data.get("total", len(sessions))

            if not sessions:
                console.print("[dim]No active sessions[/dim]")
                return

            console.print(f"[bold]Active Client Sessions ({total})[/bold]")
            console.print()

            for s in sessions:
                console.print(f"  • {s['client_name']}")
                console.print(f"    ID: {s['client_id']}")
                console.print(f"    Created: {s['created_at']}")
                console.print(f"    Expires: {s['expires_at']}")
                console.print()

        except Exception as e:
            if "401" in str(e) or "403" in str(e):
                console.print("[red]Error: Admin access required (use master token)[/red]")
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


@session_app.command("logout")
def session_logout(
    server: ServerOption = None,
) -> None:
    """Logout and revoke current session.

    This will:
    - Revoke the current session token on the server
    - Remove credentials from ~/.olav/credentials
    """
    asyncio.run(_session_logout(server))


async def _session_logout(server_url: str | None) -> None:
    """Logout and revoke session."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)
    credentials = _load_credentials_file()

    session_token = credentials.get("OLAV_SESSION_TOKEN")

    if not session_token:
        console.print("[yellow]No session token found. Already logged out.[/yellow]")
        return

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            # Revoke session on server
            response = await client._client.post(f"/auth/revoke/{session_token}")

            if response.status_code == 200:
                console.print("[green]✅ Session revoked on server[/green]")
            elif response.status_code == 404:
                console.print("[yellow]Session already expired or revoked[/yellow]")
            else:
                console.print(f"[yellow]Server returned: {response.status_code}[/yellow]")

        except Exception as e:
            console.print(f"[yellow]Warning: Could not contact server: {e}[/yellow]")

    # Remove local credentials
    credentials_file = Path.home() / ".olav" / "credentials"
    if credentials_file.exists():
        # Remove session-related keys
        with open(credentials_file) as f:
            lines = f.readlines()

        with open(credentials_file, "w") as f:
            for line in lines:
                if not any(key in line for key in ["OLAV_SESSION_TOKEN", "OLAV_CLIENT_ID", "OLAV_CLIENT_NAME"]):
                    f.write(line)

        console.print(f"[dim]Credentials removed from {credentials_file}[/dim]")

    console.print()
    console.print("Logged out successfully. Run 'olav register' to authenticate again.")


@session_app.command("threads")
def session_threads(
    limit: Annotated[int, typer.Option(help="Max threads to show")] = 20,
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """List conversation threads (chat sessions)."""
    asyncio.run(_session_threads(limit, server, json_output))


async def _session_threads(limit: int, server_url: str | None, json_output: bool) -> None:
    """List conversation threads."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            sessions = await client.list_sessions(limit)

            if json_output:
                import json
                print(json.dumps(sessions, indent=2))
            else:
                console.print("[bold]Conversation Threads:[/bold]")
                console.print()
                for s in sessions:
                    sid = s.get("thread_id", "unknown")
                    preview = s.get("first_message", "")[:50]
                    updated = s.get("updated_at", "")
                    console.print(f"  [cyan]{sid}[/cyan]")
                    console.print(f"    {preview}...")
                    console.print(f"    [dim]{updated}[/dim]")
                    console.print()

        except Exception as e:
            console.print(f"[red]Failed to list threads: {e}[/red]")
            raise typer.Exit(1)


# ============================================
# Inspect Commands
# ============================================
inspect_app = typer.Typer(help="Network inspection commands")
app.add_typer(inspect_app, name="inspect")


@inspect_app.command("list")
def inspect_list(
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """List available inspection profiles."""
    asyncio.run(_inspect_list(server, json_output))


async def _inspect_list(server_url: str | None, json_output: bool) -> None:
    """List inspection profiles."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            profiles = await client.list_inspection_profiles()

            if json_output:
                import json
                print(json.dumps(profiles, indent=2))
            else:
                console.print("[bold]Available Inspection Profiles:[/bold]")
                console.print()
                for p in profiles:
                    name = p.get("name", "unknown")
                    desc = p.get("description", "")
                    console.print(f"  [cyan]{name}[/cyan]")
                    if desc:
                        console.print(f"    {desc}")

        except Exception as e:
            console.print(f"[red]Failed to list profiles: {e}[/red]")
            raise typer.Exit(1)


@inspect_app.command("run")
def inspect_run(
    profile: Annotated[str, typer.Argument(help="Profile name to run")],
    scope: Annotated[str, typer.Option(help="Target scope")] = "all",
    server: ServerOption = None,
    wait: Annotated[bool, typer.Option("--wait", "-w", help="Wait for completion")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Run an inspection profile (async).

    By default, returns immediately with a job ID.
    Use --wait to block until completion.

    Example:
        olav inspect run bgp_peer_audit
        olav inspect run bgp_peer_audit --wait
    """
    asyncio.run(_inspect_run(profile, scope, server, wait, verbose))


async def _inspect_run(
    profile: str,
    scope: str,
    server_url: str | None,
    wait: bool,
    verbose: bool,
) -> None:
    """Run inspection (async mode)."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    console.print(f"[bold]Running Inspection: {profile}[/bold]")
    console.print()

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            # Trigger inspection
            response = await client._client.post(
                f"/inspections/{profile}/run",
                json={}
            )

            if response.status_code == 404:
                console.print(f"[red]Error: Inspection '{profile}' not found[/red]")
                raise typer.Exit(1)

            response.raise_for_status()
            data = response.json()

            job_id = data.get("job_id")
            data.get("status")
            message = data.get("message")

            console.print(f"[green]✅ {message}[/green]")
            console.print(f"   Job ID: {job_id}")
            console.print()

            if not wait:
                console.print("[dim]Use 'olav inspect status <job_id>' to check progress[/dim]")
                console.print("[dim]Use 'olav report list' to view completed reports[/dim]")
                return

            # Wait mode: poll for completion
            console.print("[dim]Waiting for completion...[/dim]")

            while True:
                await asyncio.sleep(2)

                status_response = await client._client.get(f"/inspections/jobs/{job_id}")
                if status_response.status_code != 200:
                    console.print("[red]Error: Failed to get job status[/red]")
                    break

                job_data = status_response.json()
                job_status = job_data.get("status")
                progress = job_data.get("progress", 0)
                current_device = job_data.get("current_device", "")

                if verbose:
                    console.print(f"  [{progress}%] {current_device}", end="\r")

                if job_status == "completed":
                    report_id = job_data.get("report_id")
                    console.print()
                    console.print("[bold green]✅ Inspection Complete[/bold green]")
                    console.print(f"   Pass: {job_data.get('pass_count', 0)}")
                    console.print(f"   Fail: {job_data.get('fail_count', 0)}")
                    if report_id:
                        console.print(f"   Report: {report_id}")
                    break

                if job_status == "failed":
                    error = job_data.get("error", "Unknown error")
                    console.print()
                    console.print(f"[bold red]❌ Inspection Failed: {error}[/bold red]")
                    raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


@inspect_app.command("status")
def inspect_status(
    job_id: Annotated[str, typer.Argument(help="Job ID to check")],
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """Check the status of an inspection job.

    Example:
        olav inspect status 550e8400-e29b-41d4-a716-446655440000
    """
    asyncio.run(_inspect_status(job_id, server, json_output))


async def _inspect_status(job_id: str, server_url: str | None, json_output: bool) -> None:
    """Check job status."""
    import json as json_lib

    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get(f"/inspections/jobs/{job_id}")

            if response.status_code == 404:
                console.print(f"[red]Error: Job '{job_id}' not found[/red]")
                raise typer.Exit(1)

            response.raise_for_status()
            data = response.json()

            if json_output:
                console.print(json_lib.dumps(data, indent=2))
                return

            status = data.get("status", "unknown")
            status_color = {
                "pending": "yellow",
                "running": "cyan",
                "completed": "green",
                "failed": "red",
            }.get(status, "white")

            console.print("[bold]Job Status[/bold]")
            console.print()
            console.print(f"  Job ID:      {data.get('job_id')}")
            console.print(f"  Inspection:  {data.get('inspection_id')}")
            console.print(f"  Status:      [{status_color}]{status}[/{status_color}]")
            console.print(f"  Progress:    {data.get('progress', 0)}%")

            if data.get("current_device"):
                console.print(f"  Current:     {data.get('current_device')}")

            console.print()
            console.print(f"  Created:     {data.get('created_at')}")
            if data.get("started_at"):
                console.print(f"  Started:     {data.get('started_at')}")
            if data.get("completed_at"):
                console.print(f"  Completed:   {data.get('completed_at')}")

            if status == "completed":
                console.print()
                console.print(f"  ✅ Pass: {data.get('pass_count', 0)}")
                console.print(f"  ❌ Fail: {data.get('fail_count', 0)}")
                if data.get("report_id"):
                    console.print(f"  📋 Report: {data.get('report_id')}")

            if status == "failed" and data.get("error"):
                console.print()
                console.print(f"  [red]Error: {data.get('error')}[/red]")

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


@inspect_app.command("jobs")
def inspect_jobs(
    server: ServerOption = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max jobs to show")] = 20,
    json_output: JsonOption = False,
) -> None:
    """List recent inspection jobs.

    Example:
        olav inspect jobs
        olav inspect jobs --limit 10
    """
    asyncio.run(_inspect_jobs(server, limit, json_output))


async def _inspect_jobs(server_url: str | None, limit: int, json_output: bool) -> None:
    """List inspection jobs."""
    import json as json_lib

    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get(
                "/inspections/jobs",
                params={"limit": limit}
            )
            response.raise_for_status()
            data = response.json()

            jobs = data.get("jobs", [])

            if json_output:
                console.print(json_lib.dumps(data, indent=2))
                return

            if not jobs:
                console.print("[dim]No inspection jobs found[/dim]")
                return

            console.print(f"[bold]Recent Inspection Jobs ({len(jobs)})[/bold]")
            console.print()

            for j in jobs:
                status = j.get("status", "unknown")
                status_icon = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                }.get(status, "❓")

                console.print(f"  {status_icon} [bold]{j.get('job_id')[:8]}...[/bold]")
                console.print(f"     Inspection: {j.get('inspection_id')}")
                console.print(f"     Status: {status} ({j.get('progress', 0)}%)")
                console.print(f"     Created: {j.get('created_at')}")
                console.print()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


# ============================================
# Report Commands
# ============================================
report_app = typer.Typer(
    name="report",
    help="View inspection reports",
)
app.add_typer(report_app, name="report")


@report_app.command("list")
def report_list(
    server: ServerOption = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max reports to show")] = 20,
    json_output: JsonOption = False,
) -> None:
    """List inspection reports.

    Shows recent inspection reports ordered by execution time.

    Example:
        olav report list
        olav report list --limit 10
        olav report list --json
    """
    asyncio.run(_report_list(server, limit, json_output))


async def _report_list(server_url: str | None, limit: int, json_output: bool) -> None:
    """List inspection reports."""
    import json as json_lib

    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get(
                "/reports",
                params={"limit": limit}
            )
            response.raise_for_status()
            data = response.json()

            reports = data.get("reports", [])
            total = data.get("total", len(reports))

            if json_output:
                console.print(json_lib.dumps(data, indent=2, ensure_ascii=False))
                return

            if not reports:
                console.print("[dim]No inspection reports found[/dim]")
                return

            console.print(f"[bold]Inspection Reports ({len(reports)}/{total})[/bold]")
            console.print()

            for r in reports:
                status = r.get("status", "unknown")
                status_color = "green" if status == "all passed" else "yellow" if "attention" in status else "red"

                console.print(f"  [{status_color}]●[/{status_color}] [bold]{r.get('id', 'unknown')}[/bold]")
                console.print(f"    📋 {r.get('title', 'Untitled')}")
                console.print(f"    🕐 {r.get('executed_at', 'unknown')}")
                console.print(f"    📊 Devices: {r.get('device_count', 0)} | Checks: {r.get('check_count', 0)}")
                console.print(f"    ✅ Pass: {r.get('pass_count', 0)} | ❌ Fail: {r.get('fail_count', 0)}")
                console.print()

        except Exception as e:
            console.print(f"[red]Error: Failed to list reports: {e}[/red]")
            raise typer.Exit(1)


@report_app.command("show")
def report_show(
    report_id: Annotated[str, typer.Argument(help="Report ID to show")],
    server: ServerOption = None,
    raw: Annotated[bool, typer.Option("--raw", help="Show raw markdown")] = False,
) -> None:
    """Show inspection report details.

    Displays the full content of an inspection report.

    Example:
        olav report show inspection_bgp_peer_audit_20251127_231051
        olav report show <report_id> --raw
    """
    asyncio.run(_report_show(report_id, server, raw))


async def _report_show(report_id: str, server_url: str | None, raw: bool) -> None:
    """Show inspection report."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get(f"/reports/{report_id}")

            if response.status_code == 404:
                console.print(f"[red]Error: Report '{report_id}' not found[/red]")
                raise typer.Exit(1)

            response.raise_for_status()
            data = response.json()

            if raw:
                # Print raw markdown content
                console.print(data.get("content", ""))
            else:
                # Pretty print
                from rich.markdown import Markdown
                from rich.panel import Panel

                # Header
                console.print(Panel(
                    f"[bold]{data.get('title', 'Inspection Report')}[/bold]\n\n"
                    f"Config: {data.get('config_name', 'unknown')}\n"
                    f"Executed: {data.get('executed_at', 'unknown')}\n"
                    f"Duration: {data.get('duration', 'unknown')}",
                    title=f"📋 {report_id}",
                ))

                # Summary stats
                console.print()
                console.print("[bold]Summary[/bold]")
                console.print(f"  Devices: {data.get('device_count', 0)}")
                console.print(f"  Checks:  {data.get('check_count', 0)}")
                console.print(f"  ✅ Pass: {data.get('pass_count', 0)} ({data.get('pass_rate', '0%')})")
                console.print(f"  ❌ Fail: {data.get('fail_count', 0)}")
                console.print(f"  Status: {data.get('status', 'unknown')}")

                # Warnings
                warnings = data.get("warnings", [])
                if warnings:
                    console.print()
                    console.print("[bold yellow]Warnings[/bold yellow]")
                    for w in warnings:
                        console.print(f"  ⚠️  {w}")

                # Full content
                console.print()
                console.print("[bold]Full Report[/bold]")
                console.print()
                md = Markdown(data.get("content", ""))
                console.print(md)

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error: Failed to show report: {e}[/red]")
            raise typer.Exit(1)


@report_app.command("download")
def report_download(
    report_id: Annotated[str, typer.Argument(help="Report ID to download")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path"),
    ] = None,
    server: ServerOption = None,
) -> None:
    """Download inspection report to a file.

    Saves the report markdown to a local file.

    Example:
        olav report download <report_id>
        olav report download <report_id> -o ./my_report.md
    """
    asyncio.run(_report_download(report_id, output, server))


async def _report_download(report_id: str, output: Path | None, server_url: str | None) -> None:
    """Download inspection report."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            response = await client._client.get(f"/reports/{report_id}")

            if response.status_code == 404:
                console.print(f"[red]Error: Report '{report_id}' not found[/red]")
                raise typer.Exit(1)

            response.raise_for_status()
            data = response.json()

            content = data.get("content", "")

            # Determine output path
            if output is None:
                output = Path(f"{report_id}.md")

            output.write_text(content, encoding="utf-8")
            console.print(f"[green]✅ Report saved to {output}[/green]")

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error: Failed to download report: {e}[/red]")
            raise typer.Exit(1)


# ============================================
# Document Commands
# ============================================
doc_app = typer.Typer(help="RAG document management")
app.add_typer(doc_app, name="doc")


@doc_app.command("list")
def doc_list(
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """List indexed documents."""
    asyncio.run(_doc_list(server, json_output))


async def _doc_list(server_url: str | None, json_output: bool) -> None:
    """List documents."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            docs = await client.list_documents()

            if json_output:
                import json
                print(json.dumps(docs, indent=2))
            else:
                console.print("[bold]Indexed Documents:[/bold]")
                console.print()
                for d in docs:
                    name = d.get("name", "unknown")
                    size = d.get("size", 0)
                    console.print(f"  📄 {name} ({size} bytes)")

        except Exception as e:
            console.print(f"[red]Failed to list documents: {e}[/red]")
            raise typer.Exit(1)

@doc_app.command("search")
def doc_search(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option(help="Max results")] = 5,
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """Search indexed documents."""
    asyncio.run(_doc_search(query, limit, server, json_output))


async def _doc_search(
    query: str,
    limit: int,
    server_url: str | None,
    json_output: bool,
) -> None:
    """Search documents."""
    from olav.cli.thin_client import OlavThinClient

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            results = await client.search_documents(query, limit)

            if json_output:
                import json
                print(json.dumps(results, indent=2))
            else:
                console.print(f"[bold]Search Results for: {query}[/bold]")
                console.print()

                if not results:
                    console.print("[dim]No results found[/dim]")
                else:
                    for i, r in enumerate(results, 1):
                        score = r.get("score", 0)
                        content = r.get("content", "")[:200]
                        source = r.get("source", "unknown")

                        console.print(f"[cyan]{i}. {source}[/cyan] (score: {score:.2f})")
                        console.print(f"   {content}...")
                        console.print()

        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            raise typer.Exit(1)


@doc_app.command("upload")
def doc_upload(
    file_path: Annotated[str, typer.Argument(help="File to upload")],
    server: ServerOption = None,
) -> None:
    """Upload a document for RAG indexing."""
    asyncio.run(_doc_upload(file_path, server))


async def _doc_upload(file_path: str, server_url: str | None) -> None:
    """Upload document with progress bar."""
    from pathlib import Path

    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    from olav.cli.thin_client import OlavThinClient

    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    file_size = path.stat().st_size

    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config, auth_token=auth_token) as client:
        try:
            # Use rich progress bar for file upload
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                upload_task = progress.add_task(
                    f"Uploading {path.name}",
                    total=file_size,
                )

                # Progress callback
                def on_progress(bytes_sent: int):
                    progress.update(upload_task, completed=bytes_sent)

                result = await client.upload_document(path, on_progress=on_progress)

                # Mark complete
                progress.update(upload_task, completed=file_size)

            console.print()
            console.print(f"[green]✅ Uploaded: {path.name}[/green]")
            console.print(f"[dim]Document ID: {result.get('id', 'unknown')}[/dim]")

            # Show indexing status if available
            if result.get("indexed"):
                console.print(f"[dim]Chunks indexed: {result.get('chunks', 'N/A')}[/dim]")

        except Exception as e:
            console.print(f"[red]Upload failed: {e}[/red]")
            raise typer.Exit(1)


# ============================================
# Config Command
# ============================================
@app.command()
def config(
    show: Annotated[bool, typer.Option("--show", help="Show current config")] = False,
    set_server: Annotated[str | None, typer.Option("--server", help="Set server URL")] = None,
) -> None:
    """Manage CLI configuration."""
    from pathlib import Path

    config_path = Path.home() / ".olav" / "config.toml"

    if show or (not set_server):
        # Show config
        if config_path.exists():
            console.print(f"[bold]Config file: {config_path}[/bold]")
            console.print()
            with open(config_path) as f:
                console.print(f.read())
        else:
            console.print("[dim]No config file found. Using defaults.[/dim]")
            console.print(f"[dim]Config path: {config_path}[/dim]")

    if set_server:
        # Update server URL
        import tomllib

        config_path.parent.mkdir(exist_ok=True)

        # Load existing or create new
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        else:
            data = {}

        # Update
        if "server" not in data:
            data["server"] = {}
        data["server"]["url"] = set_server

        # Write back (simple format since tomllib is read-only)
        with open(config_path, "w") as f:
            f.write("[server]\n")
            f.write(f'url = "{set_server}"\n')
            if "timeout" in data.get("server", {}):
                f.write(f'timeout = {data["server"]["timeout"]}\n')

        console.print(f"[green]✅ Server URL set to: {set_server}[/green]")


# ============================================
# Version Command (includes banner)
# ============================================
@app.command()
def version(
    banner: Annotated[
        bool,
        typer.Option("--banner", "-b", help="Show full ASCII art banner"),
    ] = False,
) -> None:
    """Show version information and optional banner.

    Example:
        olav version         # Show version info
        olav version --banner  # Show full ASCII banner
    """
    from olav import __version__

    if banner:
        from olav.cli.display import show_welcome_banner
        show_welcome_banner(console)
    else:
        # Compact version display with mini logo
        console.print()
        console.print("[bold cyan]❄ OLAV[/bold cyan] [dim](NetAIChatOps)[/dim]")
        console.print(f"  Version: [bold]{__version__}[/bold]")
        console.print("  Enterprise Network Operations ChatOps Platform")
        console.print()


# ============================================
# Dashboard Command (TUI Mode)
# ============================================
@app.command()
def dashboard(
    server: ServerOption = None,
    queries: Annotated[
        list[str] | None,
        typer.Option(
            "--query", "-q",
            help="Query to execute (can be repeated for batch mode). Example: -q 'query 1' -q 'query 2'",
        ),
    ] = None,
    script: Annotated[
        str | None,
        typer.Option(
            "--script", "-f",
            help="File containing queries (one per line) for batch mode",
        ),
    ] = None,
    yolo: YoloOption = False,
    expert: ExpertModeOption = False,
    verbose: VerboseOption = False,
    debug: DebugOption = False,
    json_output: JsonOption = False,
) -> None:
    """Launch OLAV - interactive or batch mode.

    INTERACTIVE MODE (default):
        olav dashboard

    SINGLE QUERY:
        olav dashboard -q "check BGP status"

    BATCH MODE:
        olav dashboard -q "query1" -q "query2"
        olav dashboard --script queries.txt

    OPTIONS:
        -v  Verbose: Show ThinkingTree visualization
        -D  Debug: Show timing and tool call details
        -j  JSON: Output as JSON (for scripting)
        -y  YOLO: Auto-approve HITL prompts
        -E  Expert: Use expert mode (deep dive analysis)
    """
    import asyncio
    from pathlib import Path

    from olav.cli.display import Dashboard
    from olav.cli.thin_client import OlavThinClient

    # Determine mode
    mode = "expert" if expert else "standard"

    # Collect queries from options
    batch_queries: list[str] = []

    if queries:
        batch_queries.extend(queries)

    if script:
        script_path = Path(script)
        if not script_path.exists():
            console.print(f"[red]Error: Script file not found: {script}[/red]")
            raise typer.Exit(1)
        with open(script_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    batch_queries.append(line)
        console.print(f"[cyan]Loaded {len(batch_queries)} queries from {script}[/cyan]")

    async def run_dashboard():
        config, auth_token = _get_config_from_env(server)
        async with OlavThinClient(config, auth_token=auth_token) as client:
            dash = Dashboard(client, console, mode=mode)
            try:
                if batch_queries:
                    # Non-interactive batch mode
                    if not json_output:
                        console.print(f"[cyan]Running {len(batch_queries)} queries in batch mode[/cyan]")
                        if yolo:
                            console.print("[yellow]⚠️ YOLO mode: HITL approvals will be auto-accepted[/yellow]")
                        if verbose:
                            console.print("[magenta]📊 Verbose mode: ThinkingTree enabled[/magenta]")
                        if debug:
                            console.print("[magenta]🔍 Debug mode: timing/tool details enabled[/magenta]")
                    return await dash.run_batch(
                        batch_queries,
                        yolo=yolo,
                        verbose=verbose,
                        debug=debug,
                        json_output=json_output,
                    )
                # Interactive mode
                await dash.run()
            except KeyboardInterrupt:
                dash.stop()
                console.print("\n[yellow]Dashboard closed.[/yellow]")

    try:
        asyncio.run(run_dashboard())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard closed.[/yellow]")


# ============================================
# REPL Command (Interactive Read-Eval-Print Loop)
# ============================================
@app.command()
def repl(
    server: ServerOption = None,
    expert: ExpertModeOption = False,
) -> None:
    """Launch interactive REPL (Read-Eval-Print Loop) mode.

    A lightweight interactive session for quick queries without
    the full dashboard UI. Uses prompt_toolkit for line editing.

    Examples:
        olav repl                   # Standard mode
        olav repl --expert          # Expert mode (deep dive)
        olav repl --server http://localhost:8000

    In REPL:
        > check BGP status          # Send query
        > /mode expert              # Switch to expert mode
        > /exit or Ctrl+D           # Exit
    """
    import asyncio

    from olav.cli.display import Dashboard
    from olav.cli.thin_client import OlavThinClient

    mode = "expert" if expert else "standard"

    async def run_repl():
        config, auth_token = _get_config_from_env(server)
        async with OlavThinClient(config, auth_token=auth_token) as client:
            dash = Dashboard(client, console, mode=mode)
            try:
                await dash.run_repl()
            except KeyboardInterrupt:
                console.print("\n[yellow]REPL closed.[/yellow]")

    console.print("[bold cyan]OLAV REPL[/bold cyan] - Interactive Mode")
    console.print("[dim]Type your query and press Enter. Use /exit or Ctrl+D to quit.[/dim]")
    console.print()

    try:
        asyncio.run(run_repl())
    except KeyboardInterrupt:
        console.print("\n[yellow]REPL closed.[/yellow]")


# ============================================
# Entry Point
# ============================================
def cli_main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    cli_main()
