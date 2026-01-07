"""OLAV v0.8 CLI - DeepAgents Network Operations Assistant

Main CLI entry point using Typer for command-line interface.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Now import the rest
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from olav.agent import create_olav_agent
from olav.tools.network import list_devices as nornir_list_devices

app = typer.Typer(
    name="olav",
    help="OLAV v0.8 - Network Operations AI Assistant (DeepAgents)",
    no_args_is_help=True,
)
console = Console()


@app.command()
def query(
    query_text: str = typer.Argument(..., help="Network operation query"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
) -> None:
    """Execute a network operations query.
    
    Examples:
        olav query "查看 R1 的接口状态"
        olav query "列出所有设备"
        olav query "R1 的 BGP 邻居" --debug
    """
    console.print(
        Panel(
            f"[bold cyan]Query[/bold cyan]: {query_text}",
            border_style="cyan",
        )
    )

    try:
        # Create agent
        agent = create_olav_agent(debug=debug)
        
        # Run agent query
        config = {"configurable": {"thread_id": "cli_query"}}
        
        # Use asyncio to run the async invoke
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        response = loop.run_until_complete(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": query_text}]},
                config=config,
            )
        )
        
        # Extract and display response
        if "messages" in response:
            for msg in response["messages"]:
                if hasattr(msg, "content") and msg.content:
                    console.print(
                        Panel(
                            msg.content,
                            title="[bold green]Response[/bold green]",
                            border_style="green",
                        )
                    )
        else:
            console.print("[yellow]No response received[/yellow]")

    except Exception as e:
        console.print(f"[bold red]❌ Error: {str(e)}[/bold red]")
        if debug:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)


@app.command()
def devices() -> None:
    """List all managed network devices."""
    console.print("[bold cyan]Loading network devices...[/bold cyan]")

    try:
        result = nornir_list_devices.invoke({})
        
        console.print(
            Panel(
                result,
                title="[bold cyan]Network Devices[/bold cyan]",
                border_style="cyan",
            )
        )

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(1)


@app.command()
def config() -> None:
    """Display current OLAV configuration."""
    table = Table(title="OLAV v0.8 Configuration", border_style="cyan")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    config_items = [
        ("LLM Provider", settings.llm_provider),
        ("LLM Model", settings.llm_model_name),
        ("LLM Base URL", settings.llm_base_url or "Default"),
        ("Environment", settings.environment),
        ("Log Level", settings.log_level),
        ("Guard Enabled", str(settings.guard_enabled)),
        ("DuckDB Path", settings.duckdb_path),
        ("Device Username", settings.device_username),
    ]

    for key, value in config_items:
        if "api_key" in key.lower() or "password" in key.lower():
            value = "***" if value else "Not set"
        table.add_row(key, str(value))

    console.print(table)


@app.command()
def version() -> None:
    """Show OLAV version and information."""
    console.print(
        Panel(
            "[bold cyan]OLAV v0.8[/bold cyan]\n"
            "Network Operations AI Assistant\n"
            "Powered by DeepAgents + LangChain",
            border_style="cyan",
        )
    )


@app.command()
def interactive() -> None:
    """Start interactive OLAV session.
    
    Type your queries and OLAV will respond.
    Commands: 'help', 'config', 'devices', 'quit'
    """
    console.print(
        Panel(
            "[bold cyan]OLAV Interactive Mode[/bold cyan]\n"
            "Type queries to start. 'help' for commands, 'quit' to exit.",
            border_style="cyan",
        )
    )

    agent = create_olav_agent(debug=False)
    config = {"configurable": {"thread_id": "interactive"}}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                console.print("[yellow]Goodbye![/yellow]")
                break

            if user_input.lower() == "help":
                console.print(
                    Panel(
                        "Commands:\n"
                        "  config    - Show current configuration\n"
                        "  devices   - List network devices\n"
                        "  help      - Show this help\n"
                        "  quit      - Exit\n\n"
                        "Or just type your network query!",
                        title="Help",
                        border_style="yellow",
                    )
                )
                continue

            if user_input.lower() == "config":
                config()
                continue

            if user_input.lower() == "devices":
                devices()
                continue

            # Process as query
            try:
                response = loop.run_until_complete(
                    agent.ainvoke(
                        {"messages": [{"role": "user", "content": user_input}]},
                        config=config,
                    )
                )

                if "messages" in response:
                    for msg in response["messages"]:
                        if hasattr(msg, "content") and msg.content:
                            console.print(f"\n[bold green]OLAV:[/bold green] {msg.content}\n")
                            
            except Exception as e:
                console.print(f"[bold red]Error: {str(e)}[/bold red]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'quit' to exit.[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/bold red]")


def main() -> None:
    """Main entry point."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Fatal error: {str(e)}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
