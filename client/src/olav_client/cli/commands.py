"""OLAV Client CLI (installable).

This is a lightweight CLI that talks to an OLAV server over HTTP/SSE.

It intentionally avoids importing any server-side modules (LangGraph, NetBox, OpenSearch, etc.).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console

from olav_client.cli.thin_client import ClientConfig, OlavThinClient, StreamEventType

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = typer.Typer(
    name="olav",
    help="OLAV (NetAIChatOps) - Lightweight client CLI",
    add_completion=True,
    no_args_is_help=False,
)

console = Console()


def _load_env_file() -> dict[str, str]:
    """Load .env from current working directory."""
    env_path = Path.cwd() / ".env"
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip()

    return env_vars


def _load_credentials_file() -> dict[str, str]:
    """Load credentials from ~/.olav/credentials (KEY=VALUE)."""
    credentials_path = Path.home() / ".olav" / "credentials"
    credentials: dict[str, str] = {}
    if not credentials_path.exists():
        return credentials

    with open(credentials_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            credentials[key.strip()] = value.strip()

    return credentials


def _get_config_from_env(server_url: str | None = None) -> tuple[ClientConfig, str | None]:
    """Resolve client config and auth token.

    Token lookup priority:
      1) OLAV_API_TOKEN env var
      2) OLAV_API_TOKEN from .env
      3) OLAV_SESSION_TOKEN from ~/.olav/credentials
    """
    env_vars = _load_env_file()
    credentials = _load_credentials_file()

    resolved_server_url = server_url or os.getenv("OLAV_SERVER_URL") or env_vars.get("OLAV_SERVER_URL")

    config = ClientConfig.from_file()
    if resolved_server_url:
        config.server_url = resolved_server_url

    auth_token = os.getenv("OLAV_API_TOKEN") or env_vars.get("OLAV_API_TOKEN") or credentials.get("OLAV_SESSION_TOKEN")

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
            timeout_value = None

    with open(config_path, "w", encoding="utf-8") as f:
        f.write("[server]\n")
        f.write(f'url = "{server_url}"\n')
        if timeout_value is not None:
            f.write(f"timeout = {timeout_value}\n")


ServerOption = Annotated[
    str | None,
    typer.Option(
        "--server",
        help="API server URL (defaults to OLAV_SERVER_URL or ~/.olav/config.toml)",
        envvar="OLAV_SERVER_URL",
    ),
]

QueryOption = Annotated[
    str | None,
    typer.Option(
        "--query",
        "-q",
        help="Single-shot query text (run and exit)",
    ),
]

StandardModeOption = Annotated[
    bool,
    typer.Option("--standard", "-S", help="Standard mode (default)"),
]

ExpertModeOption = Annotated[
    bool,
    typer.Option("--expert", "-E", help="Expert mode"),
]

VerboseOption = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Show tool/thinking events"),
]

YoloOption = Annotated[
    bool,
    typer.Option("--yolo", "-y", help="Auto-approve HITL (server must support yolo)"),
]


def _resolve_mode(standard: bool, expert: bool) -> str:
    if standard and expert:
        raise typer.BadParameter("Cannot use both --standard and --expert")
    return "expert" if expert else "standard"


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    query: QueryOption = None,
    server: ServerOption = None,
    standard: StandardModeOption = False,
    expert: ExpertModeOption = False,
    verbose: VerboseOption = False,
    yolo: YoloOption = False,
) -> None:
    """Run OLAV client.

    - No args: interactive chat loop
    - With -q/--query: single-shot
    """
    if ctx.invoked_subcommand is not None:
        return

    mode = _resolve_mode(standard, expert)

    if query:
        asyncio.run(_run_single_query(query, server, mode=mode, verbose=verbose, yolo=yolo))
        return

    asyncio.run(_run_repl(server, mode=mode, verbose=verbose, yolo=yolo))


async def _stream_query(
    client: OlavThinClient,
    message: str,
    thread_id: str,
    mode: str,
    verbose: bool,
    yolo: bool,
) -> None:
    content_started = False

    async for event in client.chat_stream(message, thread_id, mode=mode, yolo=yolo):
        if event.type == StreamEventType.THINKING and verbose:
            thinking = event.data.get("content") or event.data.get("thinking", {}).get("content")
            if thinking:
                console.print(f"[dim]thinking: {thinking}[/dim]")

        elif event.type == StreamEventType.TOOL_START and verbose:
            tool = event.data.get("tool") or event.data
            name = tool.get("display_name") or tool.get("name")
            args = tool.get("args")
            console.print(f"[cyan]tool_start[/cyan] {name} {args}")

        elif event.type == StreamEventType.TOOL_END and verbose:
            tool = event.data.get("tool") or event.data
            name = tool.get("name")
            success = tool.get("success", True)
            duration_ms = tool.get("duration_ms")
            console.print(f"[cyan]tool_end[/cyan] {name} success={success} duration_ms={duration_ms}")

        elif event.type == StreamEventType.TOKEN:
            chunk = event.data.get("content", "")
            if chunk:
                if not content_started:
                    content_started = True
                sys.stdout.write(chunk)
                sys.stdout.flush()

        elif event.type == StreamEventType.MESSAGE:
            # Fallback; if tokens weren’t provided.
            msg = event.data.get("content")
            if msg and not content_started:
                console.print(msg)
                content_started = True

        elif event.type == StreamEventType.INTERRUPT:
            # HITL approval required.
            workflow_type = event.data.get("workflow_type") or ""
            risk = event.data.get("risk_level")
            operation = event.data.get("operation")
            target = event.data.get("target_device")
            commands = event.data.get("commands") or []

            console.print("\n[yellow]⏸ Approval required (HITL)[/yellow]")
            if risk:
                console.print(f"Risk: {risk}")
            if operation:
                console.print(f"Operation: {operation}")
            if target:
                console.print(f"Target: {target}")
            if commands:
                console.print("Commands:")
                for c in commands:
                    console.print(f"  - {c}")

            decision: str
            if yolo:
                decision = "Y"
                console.print("[dim]--yolo enabled: auto-approving[/dim]")
            else:
                decision = console.input("Approve? (Y/N/or modification text): ").strip() or "N"

            result = await client.resume(thread_id=thread_id, decision=decision, workflow_type=workflow_type)
            if result.interrupted:
                console.print("[yellow]Still interrupted; run again to continue.[/yellow]")
            if result.content:
                console.print("\n" + result.content)

            break

        elif event.type == StreamEventType.ERROR:
            err = event.data.get("message") or event.data.get("error") or event.data
            console.print(f"\n[red]Error: {err}[/red]")
            break

    if content_started:
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _run_single_query(
    query: str,
    server_url: str | None,
    mode: str,
    verbose: bool,
    yolo: bool,
) -> None:
    config, auth_token = _get_config_from_env(server_url)
    thread_id = str(uuid4())

    async with OlavThinClient(config=config, auth_token=auth_token) as client:
        await _stream_query(client, query, thread_id=thread_id, mode=mode, verbose=verbose, yolo=yolo)


async def _run_repl(
    server_url: str | None,
    mode: str,
    verbose: bool,
    yolo: bool,
) -> None:
    config, auth_token = _get_config_from_env(server_url)
    thread_id = str(uuid4())

    console.print()
    console.print("[bold cyan]OLAV[/bold cyan] client")
    console.print(f"[dim]Server: {config.server_url}[/dim]")
    console.print(f"[dim]Mode: {mode}[/dim]")
    console.print("[dim]Type /exit to quit; /standard or /expert to switch mode[/dim]")
    console.print()

    async with OlavThinClient(config=config, auth_token=auth_token) as client:
        try:
            health = await client.health()
            console.print(f"[green]✅ Connected[/green] (v{health.version})")
        except Exception as e:
            console.print(f"[red]❌ Cannot connect: {e}[/red]")
            return

        current_mode = mode
        while True:
            user_input = console.input("You> ").strip()
            if not user_input:
                continue

            if user_input in ("/exit", "/quit", "exit", "quit"):
                break
            if user_input in ("/standard", "standard"):
                current_mode = "standard"
                console.print("[dim]Mode set to standard[/dim]")
                continue
            if user_input in ("/expert", "expert"):
                current_mode = "expert"
                console.print("[dim]Mode set to expert[/dim]")
                continue

            await _stream_query(client, user_input, thread_id=thread_id, mode=current_mode, verbose=verbose, yolo=yolo)


@app.command()
def status(
    server: ServerOption = None,
) -> None:
    """Basic connectivity status: /health + autocomplete endpoints."""
    asyncio.run(_status(server))


async def _status(server_url: str | None) -> None:
    config, auth_token = _get_config_from_env(server_url)

    async with OlavThinClient(config=config, auth_token=auth_token) as client:
        console.print("[bold]Server[/bold]")
        health = await client.health()
        console.print(f"  status={health.status} version={health.version} env={health.environment}")
        console.print(f"  orchestrator_ready={health.orchestrator_ready}")

        console.print("\n[bold]Devices[/bold]")
        devices = await client.get_device_names()
        console.print(f"  total={len(devices)}")

        console.print("\n[bold]SuzieQ tables[/bold]")
        tables = await client.get_suzieq_tables()
        console.print(f"  total={len(tables)}")


@app.command()
def register(
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Client name (e.g. alice-laptop)"),
    ],
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            "-t",
            help="Master token (or set OLAV_API_TOKEN)",
        ),
    ] = None,
    server: ServerOption = None,
    save: Annotated[
        bool,
        typer.Option("--save/--no-save", help="Save to ~/.olav/credentials"),
    ] = True,
) -> None:
    """Register this client with the OLAV server and store a session token."""
    asyncio.run(_register_client(name, token, server, save))


async def _register_client(
    client_name: str,
    master_token: str | None,
    server_url: str | None,
    save_credentials: bool,
) -> None:
    config, env_token = _get_config_from_env(server_url)

    token = master_token or env_token
    if not token:
        console.print("[red]Error: No master token provided.[/red]")
        console.print("Provide --token or set OLAV_API_TOKEN environment variable.")
        raise typer.Exit(1)

    console.print(f"[bold]Registering client '{client_name}'...[/bold]")
    console.print(f"Server: {config.server_url}")

    try:
        async with OlavThinClient(config, auth_token=None) as client:
            health = await client.health()
            if health.status != "healthy":
                console.print(f"[yellow]Warning: Server status is '{health.status}'[/yellow]")

            result = await client.register(client_name, token)

        session_token = result["session_token"]
        client_id = result["client_id"]
        expires_at = result["expires_at"]

        console.print("\n[green]✅ Registration successful![/green]")
        console.print(f"  Client ID:   {client_id}")
        console.print(f"  Client Name: {client_name}")
        console.print(f"  Expires:     {expires_at}")

        # Persist server URL so subsequent commands can omit --server.
        if server_url:
            _persist_server_url_to_config(config.server_url)
            console.print(f"[dim]Server URL saved to {Path.home() / '.olav' / 'config.toml'}[/dim]")

        if save_credentials:
            credentials_dir = Path.home() / ".olav"
            credentials_dir.mkdir(exist_ok=True)
            credentials_file = credentials_dir / "credentials"

            credentials: dict[str, str] = {}
            if credentials_file.exists():
                with open(credentials_file, encoding="utf-8") as f:
                    for raw in f:
                        line = raw.strip()
                        if line and "=" in line and not line.startswith("#"):
                            k, _, v = line.partition("=")
                            credentials[k.strip()] = v.strip()

            credentials["OLAV_SESSION_TOKEN"] = session_token
            credentials["OLAV_CLIENT_ID"] = client_id
            credentials["OLAV_CLIENT_NAME"] = client_name

            with open(credentials_file, "w", encoding="utf-8") as f:
                f.write("# OLAV Client Credentials\n")
                f.write("# Auto-generated by 'olav register'\n\n")
                for k, v in credentials.items():
                    f.write(f"{k}={v}\n")

            console.print(f"\n[dim]Credentials saved to {credentials_file}[/dim]")
            console.print("[dim]You can also export OLAV_API_TOKEN=<session_token>[/dim]")

    except Exception as e:
        console.print(f"[red]Error: Registration failed: {e}[/red]")
        raise typer.Exit(1)
