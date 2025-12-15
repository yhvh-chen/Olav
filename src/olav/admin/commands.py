"""OLAV Admin CLI - Server-side management commands.

Usage:
    uv run olav-admin token create --name "alice-laptop" --role operator
    uv run olav-admin token list
    uv run olav-admin token revoke <client_id>
    uv run olav-admin init [--force]

This is a server-side tool for administrators to:
- Create and manage session tokens for clients
- Initialize database and indices
- Perform maintenance operations
"""

import os
import sys
from datetime import UTC, datetime

import typer
from rich.console import Console
from rich.table import Table

from olav.server.auth import (
    SessionToken,
    UserRole,
    create_session,
    generate_access_token,
    get_active_sessions,
    revoke_session,
)

# Console for rich output
console = Console()

# Create Typer app
app = typer.Typer(
    name="olav-admin",
    help="OLAV (NetAIChatOps) Server Administration Tool",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

# Token subcommand group
token_app = typer.Typer(help="Session token management")
app.add_typer(token_app, name="token")


# ============================================
# Token Management Commands
# ============================================
@token_app.command("create")
def token_create(
    name: str = typer.Option(..., "--name", "-n", help="Client name (e.g., 'alice-laptop', 'ci-runner-1')"),
    role: str = typer.Option("operator", "--role", "-r", help="User role: admin, operator, viewer"),
    hours: int = typer.Option(168, "--hours", "-H", help="Token validity in hours (default: 168 = 7 days)"),
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table, token-only, json"),
) -> None:
    """Create a new session token for a client.

    Examples:
        olav-admin token create --name alice-laptop --role operator
        olav-admin token create -n ci-runner -r viewer -H 24
        olav-admin token create -n deploy-bot -r admin --format token-only
    """
    # Validate role
    try:
        user_role = UserRole(role.lower())
    except ValueError:
        console.print(f"[red]✗[/red] Invalid role: {role}")
        console.print("  Valid roles: admin, operator, viewer")
        raise typer.Exit(code=1)

    # Create session
    session = create_session(client_name=name, role=user_role, hours_valid=hours)

    if output_format == "token-only":
        # Just print the token (useful for piping)
        print(session.token)
    elif output_format == "json":
        import json
        print(json.dumps({
            "token": session.token,
            "client_id": session.client_id,
            "client_name": session.client_name,
            "role": session.role.value,
            "expires_at": session.expires_at.isoformat(),
        }, indent=2))
    else:
        # Table format (default)
        console.print()
        console.print("[green]✓[/green] Session token created successfully!")
        console.print()

        table = Table(title="Token Details", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Token", session.token)
        table.add_row("Client ID", session.client_id)
        table.add_row("Client Name", session.client_name)
        table.add_row("Role", _role_badge(session.role.value))
        table.add_row("Expires", session.expires_at.strftime("%Y-%m-%d %H:%M UTC"))
        table.add_row("Valid For", f"{hours} hours")

        console.print(table)
        console.print()
        console.print("[dim]Save this token securely - it won't be shown again![/dim]")


@token_app.command("list")
def token_list(
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
) -> None:
    """List all active session tokens.

    Examples:
        olav-admin token list
        olav-admin token list --format json
    """
    sessions = get_active_sessions()

    if not sessions:
        console.print("[yellow]No active sessions found.[/yellow]")
        return

    if output_format == "json":
        import json
        data = [
            {
                "client_id": s.client_id,
                "client_name": s.client_name,
                "role": s.role.value,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ]
        print(json.dumps(data, indent=2))
    else:
        # Table format
        table = Table(title=f"Active Sessions ({len(sessions)})", show_header=True)
        table.add_column("Client ID", style="dim")
        table.add_column("Client Name", style="cyan")
        table.add_column("Role")
        table.add_column("Created", style="dim")
        table.add_column("Expires")
        table.add_column("Status")

        now = datetime.now(UTC)
        for s in sorted(sessions, key=lambda x: x.created_at, reverse=True):
            remaining = s.expires_at - now
            hours_left = int(remaining.total_seconds() / 3600)

            if hours_left < 24:
                status = f"[yellow]⚠ {hours_left}h left[/yellow]"
            else:
                days_left = hours_left // 24
                status = f"[green]✓ {days_left}d left[/green]"

            table.add_row(
                s.client_id[:8] + "...",
                s.client_name,
                _role_badge(s.role.value),
                s.created_at.strftime("%m-%d %H:%M"),
                s.expires_at.strftime("%m-%d %H:%M"),
                status,
            )

        console.print()
        console.print(table)


@token_app.command("revoke")
def token_revoke(
    client_id: str = typer.Argument(..., help="Client ID to revoke (use 'token list' to find IDs)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Revoke a session token by client ID.

    Examples:
        olav-admin token revoke abc123...
        olav-admin token revoke abc123... --force
    """
    # Find session by client_id
    sessions = get_active_sessions()
    target_session: SessionToken | None = None

    for s in sessions:
        if s.client_id.startswith(client_id) or s.client_id == client_id:
            target_session = s
            break

    if target_session is None:
        console.print(f"[red]✗[/red] No session found with client ID starting with: {client_id}")
        raise typer.Exit(code=1)

    # Confirm
    if not force:
        console.print()
        console.print(f"About to revoke session for: [cyan]{target_session.client_name}[/cyan]")
        console.print(f"  Client ID: {target_session.client_id}")
        console.print(f"  Role: {_role_badge(target_session.role.value)}")
        console.print()
        confirmed = typer.confirm("Are you sure?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(code=0)

    # Revoke
    success = revoke_session(target_session.token)

    if success:
        console.print(f"[green]✓[/green] Session revoked for: {target_session.client_name}")
    else:
        console.print(f"[red]✗[/red] Failed to revoke session")
        raise typer.Exit(code=1)


# ============================================
# Master Token Command
# ============================================
@app.command("master-token")
def show_master_token(
    generate: bool = typer.Option(False, "--generate", "-g", help="Generate a new master token"),
) -> None:
    """Show or generate the master API token.

    The master token is used for initial authentication and creating session tokens.

    Examples:
        olav-admin master-token
        olav-admin master-token --generate
    """
    configured = settings.olav_api_token.strip() if getattr(settings, "olav_api_token", "") else ""

    if generate:
        token = secrets.token_urlsafe(32)
        console.print()
        console.print("[green]New Master Token (not yet saved):[/green]")
        console.print(f"  {token}")
        console.print()
        console.print("[dim]Persist by setting OLAV_API_TOKEN (in environment or .env) and restarting the server.[/dim]")
        return

    if configured:
        console.print()
        console.print("[green]Master Token (from settings):[/green]")
        console.print(f"  {configured}")
        return

    token = generate_access_token()
    console.print()
    console.print("[green]Master Token (auto-generated):[/green]")
    console.print(f"  {token}")
    console.print()
    console.print("[dim]Persist by setting OLAV_API_TOKEN (in environment or .env) and restarting the server.[/dim]")


# ============================================
# Init Command (Database/Index initialization)
# ============================================
@app.command("init")
def init_databases(
    postgres: bool = typer.Option(True, "--postgres/--no-postgres", help="Initialize PostgreSQL checkpointer tables"),
    opensearch: bool = typer.Option(True, "--opensearch/--no-opensearch", help="Initialize OpenSearch indices"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-initialization (destructive)"),
) -> None:
    """Initialize databases and indices.

    This runs the ETL init scripts to set up:
    - PostgreSQL: Checkpointer tables for LangGraph
    - OpenSearch: Schema indices (openconfig-schema, suzieq-schema)

    Examples:
        olav-admin init
        olav-admin init --postgres --no-opensearch
        olav-admin init --force
    """
    console.print()
    console.print("[bold]Initializing OLAV databases...[/bold]")
    console.print()

    if force:
        console.print("[yellow]⚠ Force mode: existing data may be overwritten[/yellow]")
        if not typer.confirm("Continue?"):
            raise typer.Exit(code=0)

    success = True

    if postgres:
        console.print("  Initializing PostgreSQL...", end=" ")
        try:
            from olav.etl.init_postgres import init_postgres
            init_postgres()
            console.print("[green]✓[/green]")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
            success = False

    if opensearch:
        console.print("  Initializing OpenSearch indices...", end=" ")
        try:
            from olav.etl.init_schema import init_schema
            init_schema()
            console.print("[green]✓[/green]")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
            success = False

    console.print()
    if success:
        console.print("[green]✓ Initialization complete![/green]")
    else:
        console.print("[red]✗ Some initializations failed. Check logs for details.[/red]")
        raise typer.Exit(code=1)


# ============================================
# Helper Functions
# ============================================
def _role_badge(role: str) -> str:
    """Return a colored role badge for display."""
    if role == "admin":
        return "[red]admin[/red]"
    elif role == "operator":
        return "[yellow]operator[/yellow]"
    elif role == "viewer":
        return "[green]viewer[/green]"
    return role


# ============================================
# Entry Point
# ============================================
def main() -> None:
    """Main entry point for olav-admin CLI."""
    app()


if __name__ == "__main__":
    main()
