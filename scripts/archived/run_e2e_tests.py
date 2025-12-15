"""E2E Test Runner with Infrastructure Validation.

Validates infrastructure before running tests and provides detailed reporting.

Usage:
    uv run python scripts/run_e2e_tests.py
    uv run python scripts/run_e2e_tests.py --check-only  # Only validate infrastructure
"""

import argparse
import asyncio
import os
import subprocess
import sys

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


async def check_infrastructure() -> dict[str, bool]:
    """Check if all required infrastructure is running."""
    console.print("\n[bold cyan]Checking Infrastructure...[/bold cyan]\n")
    
    checks = {}
    
    # Get server URL from environment
    server_url = os.getenv("OLAV_SERVER_URL", "http://localhost:8000")
    
    # Check API Server
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server_url}/health", timeout=5.0)
            checks["api_server"] = response.status_code == 200
            if checks["api_server"]:
                data = response.json()
                checks["postgres"] = data.get("postgres_connected", False)
                checks["orchestrator"] = data.get("orchestrator_ready", False)
            else:
                checks["postgres"] = False
                checks["orchestrator"] = False
    except httpx.ConnectError:
        checks["api_server"] = False
        checks["postgres"] = False
        checks["orchestrator"] = False
    except Exception as e:
        console.print(f"[red]Error checking API server: {e}[/red]")
        checks["api_server"] = False
        checks["postgres"] = False
        checks["orchestrator"] = False
    
    # Check OpenSearch (optional, via environment)
    opensearch_url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{opensearch_url}/_cluster/health", timeout=5.0)
            checks["opensearch"] = response.status_code == 200
    except:
        checks["opensearch"] = False
    
    # Check Redis (optional)
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        import redis.asyncio as aioredis
        redis_client = await aioredis.from_url(redis_url)
        await redis_client.ping()
        checks["redis"] = True
        await redis_client.close()
    except:
        checks["redis"] = False
    
    return checks


def display_infrastructure_status(checks: dict[str, bool]):
    """Display infrastructure status table."""
    table = Table(title="Infrastructure Status", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Status", style="white", width=15)
    table.add_column("Required", style="white", width=10)
    
    components = {
        "api_server": ("API Server", True),
        "postgres": ("PostgreSQL", True),
        "orchestrator": ("Orchestrator", True),
        "opensearch": ("OpenSearch", False),
        "redis": ("Redis", False),
    }
    
    for key, (name, required) in components.items():
        status = checks.get(key, False)
        status_text = "[green]✓ Running[/green]" if status else "[red]✗ Down[/red]"
        required_text = "Yes" if required else "No"
        table.add_row(name, status_text, required_text)
    
    console.print(table)


async def start_api_server_if_needed(checks: dict[str, bool]) -> bool:
    """Attempt to start API server if not running."""
    if checks.get("api_server", False):
        return True
    
    console.print("\n[yellow]API server not running. Attempting to start...[/yellow]")
    console.print("[dim]Running: uv run python -m olav.server.app &[/dim]\n")
    
    # Start server in background (Windows-compatible)
    try:
        if os.name == "nt":
            # Windows: use start command
            subprocess.Popen(
                ["cmd", "/c", "start", "uv", "run", "python", "-m", "olav.server.app"],
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            # Unix: use nohup
            subprocess.Popen(
                ["nohup", "uv", "run", "python", "-m", "olav.server.app", "&"],
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        
        # Wait for server to start
        console.print("[yellow]Waiting for server to start (10 seconds)...[/yellow]")
        await asyncio.sleep(10)
        
        # Re-check
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:8000/health", timeout=5.0)
                if response.status_code == 200:
                    console.print("[green]✓ Server started successfully[/green]\n")
                    return True
            except:
                pass
        
        console.print("[red]✗ Failed to start server[/red]")
        return False
    
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")
        return False


def run_pytest() -> int:
    """Run pytest for E2E tests."""
    console.print("\n[bold cyan]Running E2E Tests...[/bold cyan]\n")
    
    # Run pytest with verbose output
    cmd = [
        "uv", "run", "pytest",
        "tests/e2e/test_langserve_api.py",
        "-v",
        "--tb=short",
        "--color=yes",
    ]
    
    result = subprocess.run(cmd, cwd=os.getcwd())
    return result.returncode


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="E2E Test Runner")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check infrastructure, don't run tests",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Automatically start API server if not running",
    )
    args = parser.parse_args()
    
    console.print(Panel.fit(
        "OLAV E2E Integration Test Suite",
        border_style="bold blue"
    ))
    
    # Check infrastructure
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking infrastructure...", total=None)
        checks = await check_infrastructure()
        progress.update(task, completed=True)
    
    display_infrastructure_status(checks)
    
    # Validate required components
    required_components = ["api_server", "postgres", "orchestrator"]
    missing = [comp for comp in required_components if not checks.get(comp, False)]
    
    if missing and not args.auto_start:
        console.print(f"\n[bold red]✗ Missing required components: {', '.join(missing)}[/bold red]")
        console.print("\n[yellow]Start infrastructure:[/yellow]")
        console.print("  1. Start PostgreSQL: docker-compose up -d postgres")
        console.print("  2. Start API server: uv run python -m olav.server.app")
        console.print("\nOr run with --auto-start to attempt automatic startup")
        sys.exit(1)
    
    if missing and args.auto_start:
        if "api_server" in missing:
            server_started = await start_api_server_if_needed(checks)
            if not server_started:
                console.print("\n[red]Failed to start API server. Please start manually.[/red]")
                sys.exit(1)
        
        if "postgres" in missing or "orchestrator" in missing:
            console.print("\n[red]PostgreSQL or Orchestrator not available.[/red]")
            console.print("These require manual startup: docker-compose up -d postgres")
            sys.exit(1)
    
    if args.check_only:
        console.print("\n[green]✓ Infrastructure check complete[/green]")
        sys.exit(0)
    
    # Run tests
    console.print("\n[bold green]✓ All required components ready[/bold green]")
    
    exit_code = run_pytest()
    
    # Summary
    if exit_code == 0:
        console.print("\n" + "="*60)
        console.print("[bold green]✓ All E2E tests passed![/bold green]")
        console.print("="*60)
        console.print("\n[yellow]Next steps:[/yellow]")
        console.print("  • Review test coverage with: uv run pytest --cov=src/olav tests/")
        console.print("  • Test CLI client: uv run python cli.py --server http://localhost:8000")
        console.print("  • Monitor logs: docker-compose logs -f olav-app")
    else:
        console.print("\n" + "="*60)
        console.print("[bold red]✗ Some tests failed[/bold red]")
        console.print("="*60)
        console.print("\n[yellow]Debug steps:[/yellow]")
        console.print("  • Check server logs: docker-compose logs olav-app")
        console.print("  • Verify credentials: curl http://localhost:8000/health")
        console.print("  • Re-run with verbose: pytest tests/e2e/ -vv")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    # Windows event loop policy
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
