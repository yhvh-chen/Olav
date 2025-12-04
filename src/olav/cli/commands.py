"""OLAV CLI v2 - Main Entry Point.

A professional-grade CLI for OLAV Network Operations Platform.

Usage:
    olav                          # Interactive REPL
    olav query "check BGP state"  # Single query
    olav inspect run daily-check  # Run inspection
    olav doc search "BGP config"  # Search documents
    olav --init                   # Initialize infrastructure
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Annotated

import typer
from rich.console import Console

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ============================================
# App Definition
# ============================================
app = typer.Typer(
    name="olav",
    help="OLAV - Enterprise Network Operations ChatOps Platform",
    add_completion=True,
    no_args_is_help=False,
)

console = Console()


# ============================================
# Shared Options
# ============================================
ServerOption = Annotated[
    str | None,
    typer.Option(
        "--server",
        help="API server URL (default: http://localhost:8000)",
        envvar="OLAV_SERVER_URL",
    ),
]

# Mode options: -S (standard) and -E (expert) are mutually exclusive
StandardModeOption = Annotated[
    bool,
    typer.Option(
        "--standard", "-S",
        help="Standard mode: fast path with single tool calls (default)",
    ),
]

ExpertModeOption = Annotated[
    bool,
    typer.Option(
        "--expert", "-E",
        help="Expert mode: Supervisor-Driven deep dive with L1-L4 layer analysis",
    ),
]

VerboseOption = Annotated[
    bool,
    typer.Option(
        "--verbose", "-v",
        help="Show detailed output",
    ),
]

JsonOption = Annotated[
    bool,
    typer.Option(
        "--json", "-j",
        help="Output as JSON",
    ),
]

# Init Options
InitOption = Annotated[
    bool,
    typer.Option(
        "--init",
        help="Initialize infrastructure (PostgreSQL, OpenSearch indexes)",
    ),
]

InitFullOption = Annotated[
    bool,
    typer.Option(
        "--full",
        help="Full initialization including NetBox inventory import (use with --init)",
    ),
]

InitStatusOption = Annotated[
    bool,
    typer.Option(
        "--init-status",
        help="Show index status only",
    ),
]


def _resolve_mode(standard: bool, expert: bool) -> str:
    """Resolve mode from mutually exclusive flags.
    
    Args:
        standard: -S/--standard flag
        expert: -E/--expert flag
        
    Returns:
        Mode string: "standard" or "expert"
        
    Raises:
        typer.BadParameter: If both flags are set
    """
    if standard and expert:
        raise typer.BadParameter("Cannot use both --standard and --expert. Choose one.")
    
    if expert:
        return "expert"
    
    # Default to standard
    return "standard"


# ============================================
# Interactive REPL (Default Command)
# ============================================
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    server: ServerOption = None,
    standard: StandardModeOption = False,
    expert: ExpertModeOption = False,
    verbose: VerboseOption = False,
    init: InitOption = False,
    init_full: InitFullOption = False,
    init_status: InitStatusOption = False,
) -> None:
    """Start interactive REPL session (default if no command given)."""
    # Configure LangSmith tracing if enabled
    from olav.core.llm import configure_langsmith, is_langsmith_enabled
    if configure_langsmith():
        console.print("[dim]🔍 LangSmith tracing enabled[/dim]")
    
    # Handle --init flags
    if init or init_full or init_status:
        _run_init(status_only=init_status, full=init_full)
        raise typer.Exit()
    
    if ctx.invoked_subcommand is None:
        # Resolve mode from flags
        mode = _resolve_mode(standard, expert)
        # No subcommand = interactive mode
        asyncio.run(_interactive_session(server, mode, verbose))


def _run_init(status_only: bool = False, full: bool = False) -> None:
    """Run infrastructure initialization.
    
    Args:
        status_only: Only show index status, don't initialize
        full: Full initialization including NetBox inventory import
    """
    import subprocess
    from rich.panel import Panel
    
    console.print()
    console.print(Panel.fit(
        "[bold cyan]OLAV Infrastructure Initialization[/bold cyan]",
        border_style="blue",
    ))
    console.print()
    
    if status_only:
        console.print("[dim]Checking index status...[/dim]")
        console.print()
    else:
        if full:
            console.print("[cyan]📦 Full mode: including NetBox inventory import[/cyan]")
        console.print()
    
    # Step 1: Run init_all for PostgreSQL + Schema indexes
    import sys as _sys
    original_argv = _sys.argv.copy()
    _sys.argv = ["olav.etl.init_all", "--force"]  # Always force refresh
    
    if status_only:
        _sys.argv = ["olav.etl.init_all", "--status"]
    
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
    
    # If status only, we're done
    if status_only:
        return
    
    # Step 2: Full mode - NetBox inventory import + docs + configs
    if full:
        console.print()
        console.print("[bold]📋 Running full initialization steps...[/bold]")
        console.print()
        
        # 2a. Check NetBox connectivity
        console.print("[dim]Checking NetBox connectivity...[/dim]")
        try:
            result = subprocess.run(
                ["uv", "run", "python", "scripts/check_netbox.py", "--autocreate"],
                capture_output=True,
                text=True,
                cwd=str(_get_project_root()),
            )
            if result.returncode != 0:
                console.print(f"[red]❌ NetBox connectivity check failed[/red]")
                console.print(f"[dim]{result.stderr or result.stdout}[/dim]")
                raise typer.Exit(code=1)
            console.print("[green]  ✓ NetBox connectivity OK[/green]")
        except FileNotFoundError:
            console.print("[yellow]  ⚠ NetBox check script not found, skipping[/yellow]")
        
        # 2b. Import inventory to NetBox
        console.print("[dim]Importing inventory to NetBox...[/dim]")
        try:
            result = subprocess.run(
                ["uv", "run", "python", "scripts/netbox_ingest.py"],
                capture_output=True,
                text=True,
                cwd=str(_get_project_root()),
            )
            if result.returncode == 0:
                console.print("[green]  ✓ NetBox inventory imported[/green]")
            elif result.returncode == 99:
                console.print("[dim]  ✓ NetBox already has devices, skipped[/dim]")
            else:
                console.print(f"[red]❌ NetBox inventory import failed[/red]")
                console.print(f"[dim]{result.stderr or result.stdout}[/dim]")
                raise typer.Exit(code=1)
        except FileNotFoundError:
            console.print("[yellow]  ⚠ NetBox ingest script not found, skipping[/yellow]")
        
        # 2c. Initialize document RAG index
        console.print("[dim]Initializing document RAG index...[/dim]")
        try:
            from olav.etl.init_docs import main as init_docs_main
            init_docs_main()
            console.print("[green]  ✓ Document RAG index ready[/green]")
        except Exception as e:
            console.print(f"[yellow]  ⚠ Document index init failed: {e}[/yellow]")
        
        # 2d. Generate device configs
        console.print("[dim]Generating device configs...[/dim]")
        try:
            from olav.etl.generate_configs import main as generate_configs_main
            generate_configs_main()
            console.print("[green]  ✓ Device configs generated[/green]")
        except Exception as e:
            console.print(f"[yellow]  ⚠ Config generation failed: {e}[/yellow]")
    
    console.print()
    console.print("[green]✅ Initialization complete[/green]")


def _get_project_root():
    """Get project root directory."""
    from pathlib import Path
    # Look for pyproject.toml to find project root
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


async def _interactive_session(
    server_url: str | None,
    mode: str,
    verbose: bool,
) -> None:
    """Run interactive REPL session with prompt_toolkit."""
    from olav.cli.display import HITLPanel, ResultRenderer, ThinkingTree
    from olav.cli.repl import REPLSession, handle_slash_command
    from olav.cli.thin_client import (
        ClientConfig,
        OlavThinClient,
        StreamEventType,
    )
    
    # Setup
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
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
    console.print(f"[dim]Type /help for commands, Ctrl+R for history search[/dim]")
    console.print()
    
    async with OlavThinClient(config) as client:
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
                            console.print("[yellow]⏸️ 计划已修改，需要重新审批[/yellow]")
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
                        
                        async for event in client.chat_stream(user_input, repl.thread_id, repl.mode):
                            event_type = event.type
                            data = event.data
                            
                            if event_type == StreamEventType.THINKING:
                                thinking = data.get("thinking", {})
                                tree.add_thinking(thinking.get("content", ""))
                            
                            elif event_type == StreamEventType.TOOL_START:
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
                                console.print("[yellow]⚠️ 需要您的批准 (Y/N/修改内容):[/yellow]")
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
# Query Command
# ============================================
@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Query text")],
    server: ServerOption = None,
    standard: StandardModeOption = False,
    expert: ExpertModeOption = False,
    verbose: VerboseOption = False,
    json_output: JsonOption = False,
) -> None:
    """Execute a single query and exit."""
    mode = _resolve_mode(standard, expert)
    asyncio.run(_single_query(text, server, mode, verbose, json_output))


async def _single_query(
    text: str,
    server_url: str | None,
    mode: str,
    verbose: bool,
    json_output: bool,
) -> None:
    """Execute single query."""
    from olav.cli.display import ResultRenderer, ThinkingTree
    from olav.cli.thin_client import ClientConfig, OlavThinClient, StreamEventType
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    renderer = ResultRenderer(console)
    thread_id = f"cli-single-{int(time.time())}"
    
    async with OlavThinClient(config) as client:
        if not json_output:
            console.print(f"[bold green]You[/bold green]: {text}")
            console.print()
        
        content_buffer = ""
        tool_calls = []
        
        with ThinkingTree(console) as tree:
            async for event in client.chat_stream(text, thread_id, mode):
                # Server sends event with type in data.type
                event_type = event.type
                data = event.data
                
                if event_type == StreamEventType.THINKING:
                    # Thinking event: {"type": "thinking", "thinking": {"step": "...", "content": "..."}}
                    thinking = data.get("thinking", {})
                    tree.add_thinking(thinking.get("content", ""))
                
                elif event_type == StreamEventType.TOOL_START:
                    # Tool start: {"type": "tool_start", "tool": {"id": "...", "name": "...", "display_name": "...", "args": {...}}}
                    tool_info = data.get("tool", {})
                    tree.add_tool_call(
                        tool_info.get("display_name") or tool_info.get("name", "unknown"),
                        tool_info.get("args", {}),
                    )
                    tool_calls.append(tool_info)
                
                elif event_type == StreamEventType.TOOL_END:
                    # Tool end: {"type": "tool_end", "tool": {"id": "...", "name": "...", "duration_ms": 123, "success": true}}
                    tool_info = data.get("tool", {})
                    tree.mark_tool_complete(
                        tool_info.get("name", "unknown"),
                        success=tool_info.get("success", True),
                    )
                
                elif event_type == StreamEventType.TOKEN:
                    # Token: {"type": "token", "content": "..."}
                    content_buffer += data.get("content", "")
                
                elif event_type == StreamEventType.MESSAGE:
                    content_buffer = data.get("content", content_buffer)
                
                elif event_type == StreamEventType.INTERRUPT:
                    # HITL interrupt: {"type": "interrupt", "execution_plan": {...}}
                    # TODO: Handle HITL in a separate function
                    console.print("[yellow]⚠️ 需要人工审批...[/yellow]")
                    break
                
                elif event_type == StreamEventType.ERROR:
                    error_info = data.get("error", {})
                    error_msg = error_info.get("message") if isinstance(error_info, dict) else str(error_info)
                    if json_output:
                        import json
                        print(json.dumps({"error": error_msg}))
                    else:
                        renderer.render_error(error_msg or "Unknown error")
                    raise typer.Exit(1)
        
        if json_output:
            import json
            print(json.dumps({
                "content": content_buffer,
                "tools": tool_calls,
            }, ensure_ascii=False, indent=2))
        else:
            renderer.render_message(content_buffer)


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
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    async with OlavThinClient(config) as client:
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
    verbose: VerboseOption = False,
) -> None:
    """Run an inspection profile."""
    asyncio.run(_inspect_run(profile, scope, server, verbose))


async def _inspect_run(
    profile: str,
    scope: str,
    server_url: str | None,
    verbose: bool,
) -> None:
    """Run inspection."""
    from olav.cli.display import InspectionProgress
    from olav.cli.thin_client import ClientConfig, OlavThinClient, StreamEventType
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    console.print(f"[bold]Running Inspection: {profile}[/bold]")
    console.print(f"[dim]Scope: {scope}[/dim]")
    console.print()
    
    async with OlavThinClient(config) as client:
        results = {"passed": 0, "failed": 0, "warnings": 0}
        
        with InspectionProgress(console) as progress:
            async for event in client.run_inspection(profile, scope):
                if event.type == StreamEventType.THINKING:
                    # Progress update
                    data = event.data
                    if "total" in data:
                        progress.add_overall(data["total"], "总进度")
                    if "device" in data:
                        progress.add_device(data["device"], data.get("checks", 1))
                
                elif event.type == StreamEventType.TOOL_RESULT:
                    # Check result
                    status = event.data.get("status", "unknown")
                    if status == "pass":
                        results["passed"] += 1
                    elif status == "fail":
                        results["failed"] += 1
                    else:
                        results["warnings"] += 1
                    progress.update_overall()
                
                elif event.type == StreamEventType.MESSAGE:
                    # Device complete
                    progress.complete_device()
        
        # Summary
        console.print()
        console.print("[bold]Inspection Complete[/bold]")
        console.print(f"  ✅ Passed: {results['passed']}")
        console.print(f"  ❌ Failed: {results['failed']}")
        console.print(f"  ⚠️  Warnings: {results['warnings']}")


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
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    async with OlavThinClient(config) as client:
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
    from olav.cli.display import ResultRenderer
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    renderer = ResultRenderer(console)
    
    async with OlavThinClient(config) as client:
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
    
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    
    file_size = path.stat().st_size
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    async with OlavThinClient(config) as client:
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
# Session Commands
# ============================================
session_app = typer.Typer(help="Session management")
app.add_typer(session_app, name="session")


@session_app.command("list")
def session_list(
    limit: Annotated[int, typer.Option(help="Max sessions")] = 20,
    server: ServerOption = None,
    json_output: JsonOption = False,
) -> None:
    """List conversation sessions."""
    asyncio.run(_session_list(limit, server, json_output))


async def _session_list(limit: int, server_url: str | None, json_output: bool) -> None:
    """List sessions."""
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    config = ClientConfig.from_file()
    if server_url:
        config.server_url = server_url
    
    async with OlavThinClient(config) as client:
        try:
            sessions = await client.list_sessions(limit)
            
            if json_output:
                import json
                print(json.dumps(sessions, indent=2))
            else:
                console.print("[bold]Sessions:[/bold]")
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
            console.print(f"[red]Failed to list sessions: {e}[/red]")
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
# Version Command  
# ============================================
@app.command()
def version() -> None:
    """Show version information."""
    from olav import __version__
    
    console.print(f"[bold]OLAV v{__version__}[/bold]")
    console.print("Enterprise Network Operations ChatOps Platform")


# ============================================
# Dashboard Command (TUI Mode)
# ============================================
@app.command()
def dashboard() -> None:
    """Launch full-screen TUI dashboard.
    
    Interactive dashboard with:
    - Real-time system status
    - Device overview
    - Activity log
    - Colorful OLAV branding
    
    Press 'q' to exit, '/' to enter query mode.
    """
    import asyncio
    
    from olav.cli.display import Dashboard, show_welcome_banner
    from olav.cli.thin_client import ClientConfig, OlavThinClient
    
    async def run_dashboard():
        config = ClientConfig.from_file()
        async with OlavThinClient(config) as client:
            dash = Dashboard(client, console)
            try:
                await dash.run()
            except KeyboardInterrupt:
                dash.stop()
                console.print("\n[yellow]Dashboard closed.[/yellow]")
    
    try:
        asyncio.run(run_dashboard())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard closed.[/yellow]")


# ============================================
# Banner Command
# ============================================
@app.command()
def banner() -> None:
    """Show OLAV welcome banner with ASCII art."""
    from olav.cli.display import show_welcome_banner
    
    show_welcome_banner(console)


# ============================================
# Entry Point
# ============================================
def cli_main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    cli_main()
