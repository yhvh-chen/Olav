"""OLAV v0.8 CLI - DeepAgents Network Operations Assistant

Main CLI entry point using Typer for command-line interface.
Enhanced with Phase 6 CLI features (prompt-toolkit, slash commands, memory).
"""

import asyncio
import sys
from pathlib import Path

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

# Phase 6 CLI enhancements
from olav.cli.session import OlavPromptSession
from olav.cli.memory import AgentMemory
from olav.cli.commands import execute_command, is_slash_command
from olav.cli.input_parser import parse_input, execute_shell_command
from olav.cli.display import display_banner, load_banner_from_config

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
        raise typer.Exit(1) from None


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
        raise typer.Exit(1) from None


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
    """Start interactive OLAV session with Phase 6 enhancements.

    Features:
    - Slash commands (/help, /devices, /skills, /quit, etc.)
    - File references (@file.txt)
    - Shell commands (!command)
    - Session memory with persistence
    - Command history with auto-completion

    Type your queries and OLAV will respond.
    """
    # Display welcome banner
    banner_type = load_banner_from_config()
    display_banner(banner_type, console)

    console.print(
        Panel(
            "[bold cyan]OLAV v0.8 Interactive Mode[/bold cyan]\n"
            "Enhanced with prompt-toolkit, slash commands, and session memory.\n\n"
            "[bold yellow]Features:[/bold yellow]\n"
            "  /help       - Show all commands\n"
            "  @file.txt   - Include file content\n"
            "  !command    - Execute shell command\n"
            "  Type queries to start, 'quit' to exit.",
            border_style="cyan",
        )
    )

    # Initialize Phase 6 components
    session = OlavPromptSession()
    memory = AgentMemory()
    agent = create_olav_agent(debug=False)
    config = {"configurable": {"thread_id": "interactive"}}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            # Use enhanced prompt session
            user_input = session.prompt_sync()

            if not user_input.strip():
                continue

            # Handle legacy commands for backward compatibility
            if user_input.lower() == "quit":
                console.print("[yellow]Goodbye![/yellow]")
                break

            if user_input.lower() == "help":
                user_input = "/help"  # Redirect to slash command
            elif user_input.lower() == "config":
                config()
                continue
            elif user_input.lower() == "devices":
                devices()
                continue

            # Parse input for Phase 6 features
            text, is_shell, shell_cmd = parse_input(user_input)

            # Handle shell commands (!command)
            if is_shell:
                console.print(f"[bold cyan]Executing:[/bold cyan] {shell_cmd}")
                success, stdout, stderr, code = execute_shell_command(shell_cmd)

                if stdout:
                    console.print(stdout)
                if stderr:
                    console.print(f"[bold red]{stderr}[/bold red]")

                # Add to memory
                memory.add("user", user_input)
                memory.add("assistant", f"Shell command exit code: {code}")
                continue

            # Handle slash commands (/help, /devices, etc.)
            if is_slash_command(text):
                result = execute_command(text)
                if result:
                    console.print(result)
                    # Add to memory
                    memory.add("user", user_input)
                    memory.add("assistant", result)
                continue

            # Process as normal query with file references expanded
            try:
                # Add user message to memory
                memory.add("user", text)

                # Get conversation context from memory
                context = memory.get_context()

                # Prepare messages for agent
                messages = [{"role": msg["role"], "content": msg["content"]}
                           for msg in context]

                # Invoke agent
                response = loop.run_until_complete(
                    agent.ainvoke(
                        {"messages": messages},
                        config=config,
                    )
                )

                # Extract and display response
                if "messages" in response:
                    for msg in response["messages"]:
                        if hasattr(msg, "content") and msg.content:
                            content = msg.content
                            console.print(f"\n[bold green]OLAV:[/bold green] {content}\n")

                            # Add assistant response to memory
                            memory.add("assistant", content)

            except Exception as e:
                console.print(f"[bold red]Error: {str(e)}[/bold red]")
                if "--debug" in user_input or "-d" in user_input:
                    import traceback
                    traceback.print_exc()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'quit' to exit.[/yellow]")
        except EOFError:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
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
